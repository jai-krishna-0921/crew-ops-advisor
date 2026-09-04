/**
 * SSE client for `POST /api/chat`.
 *
 * `EventSource` cannot issue a POST, and the chat request carries a body, so
 * this reads the response stream by hand: `fetch` plus a `ReadableStream`
 * reader, a decoder in streaming mode, and a buffer that survives chunk
 * boundaries landing in the middle of a frame.
 *
 * Reconnection policy, stated because the naive choice is wrong here:
 *
 *   A connection that fails *before the first event arrives* is retried, with
 *   backoff. Nothing has been observed yet, so a retry is free.
 *
 *   A connection that fails *mid stream* is NOT retried automatically. Re-running
 *   the turn would run the agent a second time, and a controller would have no
 *   way to tell a resumed answer from a fresh one. The caller is handed a
 *   recoverable error and offers a retry the controller chooses. Honesty about
 *   what happened beats a seamless-looking recovery.
 */

import type { ChatRequest, StreamEvent } from "@/lib/contracts";

export interface StreamCallbacks {
  onEvent: (event: StreamEvent) => void;
  /** Transport level failure. `recoverable` mirrors the ErrorEvent field. */
  onError?: (error: StreamError) => void;
  /** Fires exactly once, whether the stream ended, failed or was aborted. */
  onClose?: () => void;
}

export interface StreamError {
  message: string;
  recoverable: boolean;
  /** True when the stream had already delivered events before it broke. */
  midStream: boolean;
}

export interface StreamOptions {
  signal?: AbortSignal;
  /** Retries for a connection that never produced an event. */
  maxConnectRetries?: number;
}

const RETRY_BACKOFF_MS = [300, 900, 2400];

/** Splits an SSE buffer into complete frames, leaving the remainder behind. */
export function splitFrames(buffer: string): { frames: string[]; rest: string } {
  const frames: string[] = [];
  let rest = buffer;
  // A frame ends at a blank line. Accept LF and CRLF wire endings.
  const boundary = /\r?\n\r?\n/;
  for (;;) {
    const match = boundary.exec(rest);
    if (!match) break;
    frames.push(rest.slice(0, match.index));
    rest = rest.slice(match.index + match[0].length);
  }
  return { frames, rest };
}

/**
 * Parses one SSE frame into an event payload.
 *
 * Only `data:` lines carry meaning: the contract puts the discriminator inside
 * the JSON, so `event:` lines are ignored rather than trusted. Comment lines
 * (`:` keepalives) yield null.
 */
export function parseFrame(frame: string): StreamEvent | null {
  const data: string[] = [];
  for (const rawLine of frame.split(/\r?\n/)) {
    if (!rawLine || rawLine.startsWith(":")) continue;
    const colon = rawLine.indexOf(":");
    const field = colon === -1 ? rawLine : rawLine.slice(0, colon);
    if (field !== "data") continue;
    let value = colon === -1 ? "" : rawLine.slice(colon + 1);
    if (value.startsWith(" ")) value = value.slice(1);
    data.push(value);
  }
  if (data.length === 0) return null;
  const payload = data.join("\n");
  if (!payload || payload === "[DONE]") return null;
  try {
    return JSON.parse(payload) as StreamEvent;
  } catch {
    return null;
  }
}

export async function streamChat(
  url: string,
  request: ChatRequest,
  callbacks: StreamCallbacks,
  options: StreamOptions = {},
): Promise<void> {
  const maxRetries = options.maxConnectRetries ?? RETRY_BACKOFF_MS.length;
  let attempt = 0;
  let delivered = 0;

  for (;;) {
    try {
      await readOnce(url, request, callbacks, options.signal, () => {
        delivered += 1;
      });
      callbacks.onClose?.();
      return;
    } catch (error) {
      if (options.signal?.aborted) {
        callbacks.onClose?.();
        return;
      }
      const message = error instanceof Error ? error.message : String(error);
      const midStream = delivered > 0;

      if (!midStream && attempt < maxRetries) {
        await sleep(RETRY_BACKOFF_MS[Math.min(attempt, RETRY_BACKOFF_MS.length - 1)]);
        attempt += 1;
        continue;
      }

      callbacks.onError?.({
        message: midStream
          ? `The stream broke after ${delivered} events. The turn was not resumed: ask again to re-run it.`
          : message,
        recoverable: true,
        midStream,
      });
      callbacks.onClose?.();
      return;
    }
  }
}

async function readOnce(
  url: string,
  request: ChatRequest,
  callbacks: StreamCallbacks,
  signal: AbortSignal | undefined,
  markDelivered: () => void,
): Promise<void> {
  const response = await fetch(url, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      Accept: "text/event-stream",
    },
    body: JSON.stringify(request),
    signal,
    cache: "no-store",
  });

  if (!response.ok) {
    throw new Error(
      `The advisor API answered ${response.status} ${response.statusText}.`,
    );
  }
  if (!response.body) {
    throw new Error("The advisor API returned no stream body.");
  }

  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";

  try {
    for (;;) {
      const { value, done } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });
      const { frames, rest } = splitFrames(buffer);
      buffer = rest;
      for (const frame of frames) {
        const event = parseFrame(frame);
        if (!event) continue;
        markDelivered();
        callbacks.onEvent(event);
      }
    }
    // Flush anything the server sent without a trailing blank line.
    buffer += decoder.decode();
    const tail = parseFrame(buffer);
    if (tail) {
      markDelivered();
      callbacks.onEvent(tail);
    }
  } finally {
    reader.releaseLock();
  }
}

function sleep(ms: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

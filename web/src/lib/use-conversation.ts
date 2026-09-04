"use client";

/**
 * One hook that owns the conversation. Nothing else mutates turn state.
 *
 * The whole reason this is a hook rather than a pile of `useState` calls in
 * the view is the generation guard. Switching conversation while a stream is
 * running used to leave the stream running, and its events landed in whatever
 * turn list happened to be on screen. Here, every asynchronous path (the SSE
 * stream, the history fetch) captures the generation it started under and
 * checks it before writing. A stale writer is dropped.
 */

import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import type { AnswerMode, StreamEvent } from "@/lib/contracts";
import { api, chat } from "@/lib/api";
import {
  EMPTY_CONVERSATION,
  newLocalId,
  threadIdForAsk,
  turnsFromThread,
  type ConversationState,
} from "@/lib/conversation";
import {
  loadMemory,
  loadSession,
  rememberTurn,
  saveMemory,
  saveSession,
  type ThreadMemory,
} from "@/lib/session";
import { emptyTurn, reduceTurn } from "@/lib/turn";

export interface Conversation extends ConversationState {
  memory: ThreadMemory | null;
  ask: (question: string) => void;
  stop: () => void;
  newThread: () => void;
  openThread: (threadId: string) => void;
  dismissLoadError: () => void;
}

export function useConversation(mode: AnswerMode | "auto"): Conversation {
  const [state, setState] = useState<ConversationState>(EMPTY_CONVERSATION);
  const [memory, setMemory] = useState<ThreadMemory | null>(null);
  const [hydrated, setHydrated] = useState(false);

  const abortRef = useRef<AbortController | null>(null);
  /** Incremented by anything that changes which conversation is on screen. */
  const genRef = useRef(0);
  const stateRef = useRef(state);
  // Kept in step through an effect rather than assigned during render, so the
  // ref is only ever written outside the render phase.
  useEffect(() => {
    stateRef.current = state;
  }, [state]);

  /**
   * Restore the tab's working state.
   *
   * This has to run after mount. The server has no sessionStorage, so reading
   * it in a lazy initialiser would make the first client render disagree with
   * the server render and blow up hydration. Restoring persisted state in an
   * effect is the documented way round that, which is why the cascading-render
   * rule is waived here specifically.
   */
  useEffect(() => {
    const restored = loadSession();
    // eslint-disable-next-line react-hooks/set-state-in-effect -- post-mount rehydration, see above
    setState((current) =>
      restored.turns.length > 0 || restored.threadId ? restored : current,
    );
    if (restored.threadId) setMemory(loadMemory(restored.threadId));
    setHydrated(true);
  }, []);

  useEffect(() => {
    if (!hydrated) return;
    saveSession(state);
  }, [state, hydrated]);

  /** Abandon whatever is in flight and claim a fresh generation. */
  const beginGeneration = useCallback(() => {
    abortRef.current?.abort();
    abortRef.current = null;
    genRef.current += 1;
    return genRef.current;
  }, []);

  const newThread = useCallback(() => {
    beginGeneration();
    setState(EMPTY_CONVERSATION);
    setMemory(null);
  }, [beginGeneration]);

  const openThread = useCallback(
    (threadId: string) => {
      const gen = beginGeneration();
      // The id and the loading state are applied immediately so the rail
      // highlights the right row while the history is still in flight.
      setState({ threadId, turns: [], status: "loading", loadError: null });
      setMemory(loadMemory(threadId));

      api
        .thread(threadId)
        .then((detail) => {
          if (genRef.current !== gen) return;
          setState({
            threadId,
            turns: turnsFromThread(detail),
            status: "idle",
            loadError: null,
          });
        })
        .catch((error: unknown) => {
          if (genRef.current !== gen) return;
          setState({
            threadId,
            turns: [],
            status: "idle",
            loadError:
              error instanceof Error
                ? `That conversation could not be loaded: ${error.message}`
                : "That conversation could not be loaded.",
          });
        });
    },
    [beginGeneration],
  );

  const ask = useCallback(
    (question: string) => {
      const trimmed = question.trim();
      if (!trimmed) return;

      // Asking continues the current conversation, so the generation only
      // advances far enough to cancel a previous in-flight answer.
      abortRef.current?.abort();
      genRef.current += 1;
      const gen = genRef.current;

      const controller = new AbortController();
      abortRef.current = controller;

      const localId = newLocalId();
      const askedThreadId = threadIdForAsk(stateRef.current);

      setState((current) => ({
        ...current,
        turns: [...current.turns, emptyTurn(trimmed, localId)],
        status: "streaming",
        loadError: null,
      }));

      const apply = (event: StreamEvent) => {
        if (genRef.current !== gen) return;
        setState((current) => ({
          ...current,
          threadId:
            event.type === "run_started" ? event.thread_id : current.threadId,
          turns: current.turns.map((turn) =>
            turn.localId === localId ? reduceTurn(turn, event) : turn,
          ),
        }));

        if (event.type === "reply") {
          const threadId = event.reply.thread_id;
          setMemory((current) =>
            rememberTurn(current ?? loadMemory(threadId), trimmed, event.reply.text),
          );
        }
      };

      chat(
        {
          question: trimmed,
          thread_id: askedThreadId,
          force_mode: mode === "auto" ? null : mode,
        },
        {
          onEvent: apply,
          onError: (error) => {
            if (genRef.current !== gen) return;
            setState((current) => ({
              ...current,
              status: "idle",
              turns: current.turns.map((turn) =>
                turn.localId === localId
                  ? {
                      ...turn,
                      error: {
                        message: error.message,
                        recoverable: error.recoverable,
                      },
                    }
                  : turn,
              ),
            }));
          },
          onClose: () => {
            if (genRef.current !== gen) return;
            setState((current) => ({ ...current, status: "idle" }));
          },
        },
        controller.signal,
      ).catch((error: unknown) => {
        if (genRef.current !== gen) return;
        // A rejected promise here means the request never became a stream:
        // the API is down, CORS blocked it, or the body was rejected. An
        // aborted request is a deliberate switch, not a failure to report.
        const aborted = error instanceof DOMException && error.name === "AbortError";
        setState((current) => ({
          ...current,
          status: "idle",
          turns: aborted
            ? current.turns
            : current.turns.map((turn) =>
                turn.localId === localId
                  ? {
                      ...turn,
                      error: {
                        message:
                          error instanceof Error
                            ? error.message
                            : "The advisor could not be reached.",
                        recoverable: true,
                      },
                    }
                  : turn,
              ),
        }));
      });
    },
    [mode],
  );

  const stop = useCallback(() => {
    abortRef.current?.abort();
    abortRef.current = null;
    setState((current) => ({ ...current, status: "idle" }));
  }, []);

  const dismissLoadError = useCallback(() => {
    setState((current) => ({ ...current, loadError: null }));
  }, []);

  useEffect(() => {
    if (memory) saveMemory(memory);
  }, [memory]);

  // Abort on unmount so a stream cannot outlive the view that started it.
  useEffect(() => () => abortRef.current?.abort(), []);

  return useMemo(
    () => ({
      ...state,
      memory,
      ask,
      stop,
      newThread,
      openThread,
      dismissLoadError,
    }),
    [state, memory, ask, stop, newThread, openThread, dismissLoadError],
  );
}

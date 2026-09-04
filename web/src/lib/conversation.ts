/**
 * The conversation state machine.
 *
 * This exists because the obvious implementation has a real bug in it. Start a
 * new chat, type a question, then click an existing thread while the answer is
 * still streaming: the stream is still running, its events still arrive, and
 * they land in whichever turn list is on screen. You end up reading an answer
 * to a question that belongs to a different conversation.
 *
 * The fix is a generation counter. Every switch of conversation increments it,
 * and every stream callback carries the generation it was started under. An
 * event from a stale generation is dropped rather than applied. The stream is
 * also aborted on the way out, so the common case costs nothing.
 *
 * The same counter covers the slower version of the bug: opening a thread
 * kicks off an async history fetch, and if you open two threads quickly the
 * responses can land out of order. The later request wins because the earlier
 * one is stale by the time it resolves.
 */

import type { Reply, ThreadDetail } from "@/lib/contracts";
import { emptyTurn, type TurnState } from "@/lib/turn";

export type ConversationStatus = "idle" | "loading" | "streaming";

export interface ConversationState {
  /** The server's id. Null until the first `run_started` names one. */
  threadId: string | null;
  turns: TurnState[];
  status: ConversationStatus;
  /** Set when a thread's history could not be fetched. The chat still works. */
  loadError: string | null;
}

export const EMPTY_CONVERSATION: ConversationState = {
  threadId: null,
  turns: [],
  status: "idle",
  loadError: null,
};

export function newLocalId(): string {
  return `L-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 6)}`;
}

/**
 * A finished turn rebuilt from a stored `Reply`.
 *
 * History comes back as replies, not as event streams, so a restored turn has
 * no live trace. It is settled from the moment it appears, which is correct:
 * re-playing a trace for an answer that finished yesterday would be theatre.
 */
export function turnFromReply(reply: Reply): TurnState {
  return {
    ...emptyTurn(reply.question, `H-${reply.turn_id}`),
    turnId: reply.turn_id,
    threadId: reply.thread_id,
    mode: reply.mode,
    tools: (reply.tool_calls ?? []).map((envelope, index) => {
      // A restored run is synthesised from its stored envelope. The event
      // fields the live stream would have supplied (seq, timestamps) are
      // filled with what the reply knows, since nothing downstream reads
      // them for a settled turn.
      const at = reply.asked_at;
      return {
        call: {
          type: "tool_call" as const,
          turn_id: reply.turn_id,
          seq: index,
          at,
          tool: envelope.tool,
          args: envelope.args,
          label: envelope.tool,
        },
        result: {
          type: "tool_result" as const,
          turn_id: reply.turn_id,
          seq: index,
          at,
          tool: envelope.tool,
          ok: envelope.ok,
          latency_ms: envelope.latency_ms,
          summary: "",
          envelope,
        },
      };
    }),
    traces: reply.traces ?? [],
    verification: reply.verification ?? null,
    abstention: reply.abstention ?? null,
    reply,
    done: true,
    totalMs: reply.timings?.total_ms ?? null,
  };
}

export function turnsFromThread(detail: ThreadDetail): TurnState[] {
  return (detail.turns ?? []).map(turnFromReply);
}

/**
 * Whether a question should continue the current thread or start a new one.
 *
 * The server treats a null `thread_id` as "begin". Reading it off the state
 * rather than off `turns.length` matters: a restored thread has turns but its
 * id came from the server, and a fresh conversation has neither.
 */
export function threadIdForAsk(state: ConversationState): string | null {
  return state.turns.length === 0 ? null : state.threadId;
}

/** A short, stable label for a conversation in the thread list. */
export function conversationTitle(state: ConversationState): string | null {
  const first = state.turns[0];
  return first ? first.question : null;
}

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
  /**
   * Whether the stored session has been read back yet.
   *
   * Exposed because anything that asks a question on mount has to wait for
   * it. See the restore effect for what goes wrong otherwise.
   */
  hydrated: boolean;
  /** Increments when a superseded run settles into the log anyway. */
  stranded: number;
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
  /** Bumped when a run the view has moved on from settles anyway. */
  const [stranded, setStranded] = useState(0);

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
   *
   * IT NEVER OVERWRITES LIVE STATE, and that guard is load bearing. Opening
   * `/?q=...` fires a question from another effect on the same mount, and
   * effects run in an order this hook does not control. When restore won that
   * race it replaced the whole state, the just-appended turn went with it, and
   * the stream that was already running wrote every event into a turn list
   * that no longer had its localId in it. The answer arrived and landed
   * nowhere: no error, no spinner, an empty page. Restoring into a
   * conversation that has already started is always wrong, so it does not.
   */
  useEffect(() => {
    const restored = loadSession();
    if (restored.turns.length > 0 || restored.threadId) {
      // eslint-disable-next-line react-hooks/set-state-in-effect -- post-mount rehydration, see above
      setState((current) =>
        current.turns.length > 0 || current.threadId ? current : restored,
      );
      if (restored.threadId) setMemory(loadMemory(restored.threadId));
    }
    setHydrated(true);
  }, []);

  useEffect(() => {
    if (!hydrated) return;
    saveSession(state);
  }, [state, hydrated]);

  /**
   * Claim a fresh generation and LET THE RUNNING ANSWER FINISH.
   *
   * Switching conversations used to abort the request. That is the right thing
   * for the view, which must stop showing it, and the wrong thing for the
   * answer, which is not saved until it settles: the server records a turn
   * when the reply is produced, and a closed connection stops the generator
   * before it gets there. So starting a conversation, asking something, and
   * clicking an older thread while it was still working destroyed the new
   * conversation outright. It was never in the rail, and it was not in the
   * database either.
   *
   * The generation counter is what makes leaving it running safe: every event
   * from a superseded run is already dropped on arrival, so the stream writes
   * nothing to the screen. It finishes into the log instead, and the rail
   * picks it up on the next refresh.
   *
   * `stop()` still aborts, because that is a person saying they do not want
   * the answer, which is different from wanting to look at something else.
   */
  const detachGeneration = useCallback(() => {
    abortRef.current = null;
    genRef.current += 1;
    return genRef.current;
  }, []);

  const newThread = useCallback(() => {
    detachGeneration();
    setState(EMPTY_CONVERSATION);
    setMemory(null);
  }, [detachGeneration]);

  const openThread = useCallback(
    (threadId: string) => {
      const gen = detachGeneration();
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
    [detachGeneration],
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
        if (genRef.current !== gen) {
          // A superseded run still lands in the log, and the rail is how
          // anybody finds it again. Counting the settlements is enough: the
          // console watches this and refetches, so a conversation somebody
          // started and then navigated away from appears where they left it.
          if (event.type === "reply") setStranded((n) => n + 1);
          return;
        }
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
      hydrated,
      stranded,
      ask,
      stop,
      newThread,
      openThread,
      dismissLoadError,
    }),
    [state, memory, hydrated, stranded, ask, stop, newThread, openThread, dismissLoadError],
  );
}

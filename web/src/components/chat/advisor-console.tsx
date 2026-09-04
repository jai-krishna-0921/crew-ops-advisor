"use client";

/**
 * The Advisor: a three region console, not a chat page.
 *
 * Left, what you can ask and what you have asked. Centre, the conversation as
 * structured answers. Right, the evidence behind whichever turn you are
 * looking at.
 *
 * All fact linking state sits here, above all three regions, which is what
 * lets a figure in the centre light a row on the right.
 *
 * This component contains no answering logic. It folds events into turn state
 * and hands the result to presentation components.
 */

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { SidebarSimpleIcon, TableIcon } from "@phosphor-icons/react/dist/ssr";

import type {
  AnswerMode,
  Citation,
  SampleQuestion,
  StreamEvent,
  ThreadSummary,
} from "@/lib/contracts";
import { api, chat, newThreadId } from "@/lib/api";
import { collectFacts } from "@/lib/fact-link";
import {
  emptyTurn,
  reduceTurn,
  threadTitle,
  type TurnState,
} from "@/lib/turn";
import { TurnView } from "@/components/chat/turn";
import { Composer } from "@/components/chat/composer";
import { EvidenceDrawer } from "@/components/evidence/evidence-drawer";
import { FactProvider } from "@/components/evidence/fact-context";
import { SideRail } from "@/components/shell/side-rail";
import { EmptyState, IconButton } from "@/components/ui/primitives";
import { cx } from "@/components/ui/tone";

export function AdvisorConsole() {
  const router = useRouter();
  const params = useSearchParams();

  const [turns, setTurns] = useState<TurnState[]>([]);
  const [busy, setBusy] = useState(false);
  const [threadId, setThreadId] = useState<string | null>(null);
  const [mode, setMode] = useState<AnswerMode | "auto">("auto");
  const [drawerOpen, setDrawerOpen] = useState(true);
  const [railOpen, setRailOpen] = useState(true);
  const [activeId, setActiveId] = useState<string | null>(null);

  const [questions, setQuestions] = useState<SampleQuestion[]>([]);
  const [threads, setThreads] = useState<ThreadSummary[]>([]);

  const abortRef = useRef<AbortController | null>(null);
  const scrollRef = useRef<HTMLDivElement>(null);
  const seededRef = useRef<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    Promise.all([api.questions(), api.threads()])
      .then(([q, t]) => {
        if (cancelled) return;
        setQuestions(q);
        setThreads(t);
      })
      .catch(() => {
        // The rail degrades to an empty list. Typing still works.
      });
    return () => {
      cancelled = true;
    };
  }, []);

  const ask = useCallback(
    (question: string) => {
      const trimmed = question.trim();
      if (!trimmed) return;

      abortRef.current?.abort();
      const controller = new AbortController();
      abortRef.current = controller;

      const localId = `L-${Date.now().toString(36)}-${Math.random()
        .toString(36)
        .slice(2, 6)}`;
      const turn = emptyTurn(trimmed, localId);
      setTurns((current) => [...current, turn]);
      setActiveId(localId);
      setBusy(true);

      const apply = (event: StreamEvent) => {
        setTurns((current) =>
          current.map((item) =>
            item.localId === localId ? reduceTurn(item, event) : item,
          ),
        );
        if (event.type === "run_started") setThreadId(event.thread_id);
      };

      const activeThread = threadId ?? newThreadId();
      setThreadId(activeThread);

      chat(
        {
          question: trimmed,
          thread_id: turns.length === 0 ? null : activeThread,
          force_mode: mode === "auto" ? null : mode,
        },
        {
          onEvent: apply,
          onError: (error) => {
            setTurns((current) =>
              current.map((item) =>
                item.localId === localId
                  ? {
                      ...item,
                      error: {
                        message: error.message,
                        recoverable: error.recoverable,
                      },
                    }
                  : item,
              ),
            );
          },
          onClose: () => setBusy(false),
        },
        controller.signal,
      ).catch(() => setBusy(false));
    },
    [mode, threadId, turns.length],
  );

  // A question in the URL fires once. This makes every demo question a link.
  useEffect(() => {
    const q = params.get("q");
    if (!q || seededRef.current === q) return;
    seededRef.current = q;
    ask(q);
    router.replace("/", { scroll: false });
  }, [params, ask, router]);

  useEffect(() => {
    const node = scrollRef.current;
    if (!node) return;
    node.scrollTo({ top: node.scrollHeight, behavior: "smooth" });
  }, [turns.length]);

  const stop = () => {
    abortRef.current?.abort();
    setBusy(false);
  };

  const newThread = () => {
    abortRef.current?.abort();
    setTurns([]);
    setThreadId(null);
    setActiveId(null);
    setBusy(false);
    seededRef.current = null;
  };

  const activeTurn =
    turns.find((turn) => turn.localId === activeId) ?? turns[turns.length - 1] ?? null;

  /**
   * Every fact from every turn, so a figure in an older answer still resolves
   * when the reader points at it. The drawer lists only the active turn's, so
   * the audit trail stays scoped to one question.
   */
  const allFacts = useMemo(
    () =>
      collectFacts(
        ...turns.flatMap((turn) => [
          turn.reply?.facts ?? [],
          ...(turn.reply?.tool_calls ?? []).map((envelope) => envelope.facts),
          ...turn.tools.map((run) => run.result?.envelope?.facts ?? []),
        ]),
      ),
    [turns],
  );

  const drawerFacts = useMemo(() => {
    if (!activeTurn) return [];
    return collectFacts(
      activeTurn.reply?.facts ?? [],
      ...(activeTurn.reply?.tool_calls ?? []).map((envelope) => envelope.facts),
      ...activeTurn.tools.map((run) => run.result?.envelope?.facts ?? []),
    );
  }, [activeTurn]);

  const drawerCitations: Citation[] = useMemo(() => {
    if (!activeTurn) return [];
    const seen = new Set<string>();
    const out: Citation[] = [];
    const push = (citation: Citation) => {
      const key = `${citation.file}::${citation.pointer}`;
      if (seen.has(key)) return;
      seen.add(key);
      out.push(citation);
    };
    for (const citation of activeTurn.reply?.citations ?? []) push(citation);
    for (const run of activeTurn.tools) {
      for (const citation of run.result?.envelope?.citations ?? []) push(citation);
    }
    return out;
  }, [activeTurn]);

  return (
    <FactProvider
      facts={allFacts}
      drawerOpen={drawerOpen}
      setDrawerOpen={setDrawerOpen}
    >
      <div className="flex h-full min-h-0">
        <aside
          aria-label="Threads and sample questions"
          className={cx(
            "hidden min-h-0 shrink-0 border-r border-line lg:block",
            railOpen ? "w-[17rem]" : "w-0 overflow-hidden border-r-0",
          )}
        >
          {railOpen ? (
            <SideRail
              threads={threads}
              activeThreadId={threadId}
              questions={questions}
              onNewThread={newThread}
              onOpenThread={(id) => setThreadId(id)}
              onAsk={ask}
            />
          ) : null}
        </aside>

        <section className="flex min-h-0 min-w-0 flex-1 flex-col">
          <div className="flex h-9 shrink-0 items-center gap-2 border-b border-line px-3">
            <IconButton
              label={railOpen ? "Hide the thread rail" : "Show the thread rail"}
              onClick={() => setRailOpen((v) => !v)}
              active={railOpen}
              className="hidden lg:inline-flex"
            >
              <SidebarSimpleIcon size={13} weight="bold" aria-hidden />
            </IconButton>
            <h1 className="text-base font-semibold text-ink">Advisor</h1>
            <span className="num text-xs text-ink-3">
              {threadId ? threadId : "new thread"}
              {turns.length > 0 ? ` · ${threadTitle(turns[0].question)}` : ""}
            </span>
            <div className="ml-auto">
              <IconButton
                label={drawerOpen ? "Hide evidence" : "Show evidence"}
                onClick={() => setDrawerOpen(!drawerOpen)}
                active={drawerOpen}
              >
                <TableIcon size={13} weight="bold" aria-hidden />
              </IconButton>
            </div>
          </div>

          <div ref={scrollRef} className="min-h-0 flex-1 overflow-y-auto">
            {turns.length === 0 ? (
              <Welcome questions={questions} onAsk={ask} />
            ) : (
              turns.map((turn) => (
                <TurnView
                  key={turn.localId}
                  turn={turn}
                  onAsk={ask}
                  onRetry={ask}
                  onFocus={() => setActiveId(turn.localId)}
                  isActive={turn.localId === activeTurn?.localId}
                />
              ))
            )}
          </div>

          <Composer
            onSubmit={ask}
            onStop={stop}
            busy={busy}
            mode={mode}
            onModeChange={setMode}
          />
        </section>

        <aside
          aria-label="Evidence panel"
          className={cx(
            "hidden min-h-0 shrink-0 border-l border-line xl:block",
            drawerOpen ? "w-[24rem]" : "w-0 overflow-hidden border-l-0",
          )}
        >
          {drawerOpen ? (
            <EvidenceDrawer
              facts={drawerFacts}
              tools={activeTurn?.tools ?? []}
              citations={drawerCitations}
              onClose={() => setDrawerOpen(false)}
            />
          ) : null}
        </aside>
      </div>
    </FactProvider>
  );
}

function Welcome({
  questions,
  onAsk,
}: {
  questions: SampleQuestion[];
  onAsk: (question: string) => void;
}) {
  const byTier = [1, 2, 3].map((tier) => ({
    tier,
    items: questions.filter((question) => question.tier === tier).slice(0, 3),
  }));

  return (
    <div className="mx-auto max-w-4xl px-4 py-8 sm:px-6">
      <h2 className="text-xl font-semibold text-ink">
        Ask about crew, flights, legality or cover.
      </h2>
      <p className="mt-1.5 max-w-[68ch] text-md text-ink-2">
        The model plans and explains. Deterministic tools do every calculation,
        and a guard checks each figure in the answer against what the tools
        returned. Where it cannot answer reliably, it says so.
      </p>

      <div className="mt-6 grid gap-3 sm:grid-cols-3">
        {byTier.map(({ tier, items }) => (
          <div key={tier} className="rounded-md bg-surface p-3 hairline">
            <p className="label-micro">
              Tier {tier}
              {tier === 1
                ? ", lookup"
                : tier === 2
                  ? ", consequence"
                  : ", recommendation"}
            </p>
            <ul className="mt-2 space-y-1.5">
              {items.map((question) => (
                <li key={question.id}>
                  <button
                    type="button"
                    onClick={() => onAsk(question.question)}
                    className="text-left text-base leading-snug text-ink-2 underline decoration-line-strong decoration-dotted underline-offset-4 transition-colors duration-100 hover:text-ink hover:decoration-accent"
                  >
                    {question.question}
                  </button>
                </li>
              ))}
            </ul>
          </div>
        ))}
      </div>

      {questions.length === 0 ? (
        <div className="mt-6">
          <EmptyState
            title="Sample questions are not loaded"
            detail="The question bank comes from the API. Typing a question directly still works."
          />
        </div>
      ) : null}
    </div>
  );
}

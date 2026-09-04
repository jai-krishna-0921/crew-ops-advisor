"use client";

/**
 * The Advisor: a conversation.
 *
 * The problem statement asks for a conversational interface, so the
 * conversation is the page. One column, centred, at a comfortable reading
 * measure. Nothing sits permanently beside it competing for the eye.
 *
 * Everything that used to be a fixed panel is now summoned: threads from the
 * top bar, evidence from the answer it belongs to. That is the difference
 * between a controller talking to something and a controller operating a
 * dashboard, and only one of those is what was asked for.
 *
 * Fact linking state still lives here, above the whole exchange, so pointing
 * at a figure in any answer resolves against every fact the session has seen.
 *
 * No answering logic here. This folds events into turn state and hands the
 * result to presentation components.
 */

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import {
  ListIcon,
  PlusIcon,
  WarningCircleIcon,
} from "@phosphor-icons/react/dist/ssr";

import type {
  AnswerMode,
  Citation,
  SampleQuestion,
  ThreadSummary,
} from "@/lib/contracts";
import { api } from "@/lib/api";
import { collectFacts } from "@/lib/fact-link";
import { threadTitle } from "@/lib/turn";
import { useConversation } from "@/lib/use-conversation";
import { TurnView } from "@/components/chat/turn";
import { Composer } from "@/components/chat/composer";
import { EvidenceDrawer } from "@/components/evidence/evidence-drawer";
import { FactProvider } from "@/components/evidence/fact-context";
import { SideRail } from "@/components/shell/side-rail";
import { EmptyState } from "@/components/ui/primitives";
import { cx } from "@/components/ui/tone";

export function AdvisorConsole() {
  const router = useRouter();
  const params = useSearchParams();

  const [mode, setMode] = useState<AnswerMode | "auto">("auto");
  const [drawerOpen, setDrawerOpen] = useState(false);
  const [railOpen, setRailOpen] = useState(false);
  const [activeId, setActiveId] = useState<string | null>(null);

  const [questions, setQuestions] = useState<SampleQuestion[]>([]);
  const [threads, setThreads] = useState<ThreadSummary[]>([]);
  const [catalogueError, setCatalogueError] = useState<string | null>(null);

  const conversation = useConversation(mode);
  const { turns, threadId, status, loadError, ask, stop, newThread, openThread } =
    conversation;
  const busy = status === "streaming";

  const scrollRef = useRef<HTMLDivElement>(null);
  const seededRef = useRef<string | null>(null);

  const refreshThreads = useCallback(() => {
    api
      .threads()
      .then(setThreads)
      .catch(() => {
        // The thread list is a convenience. Losing it does not stop anyone
        // asking a question, so it fails quietly.
      });
  }, []);

  useEffect(() => {
    let cancelled = false;
    api
      .questions()
      .then((rows) => {
        if (!cancelled) setQuestions(rows);
      })
      .catch(() => {
        if (!cancelled) {
          setCatalogueError(
            "The sample questions could not be loaded. Typing a question still works.",
          );
        }
      });
    refreshThreads();
    return () => {
      cancelled = true;
    };
  }, [refreshThreads]);

  // A finished answer may have created a thread, so the list is refetched
  // once the run settles rather than on every event.
  useEffect(() => {
    if (status === "idle" && turns.length > 0) refreshThreads();
  }, [status, turns.length, refreshThreads]);

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
      <div className="relative flex h-full min-h-0 flex-col">
        <div className="flex h-10 shrink-0 items-center gap-2 border-b border-line px-3">
          <button
            type="button"
            onClick={() => setRailOpen(true)}
            className="inline-flex items-center gap-1.5 rounded-sm px-2 py-1 text-base text-ink-2 transition-colors duration-100 hover:bg-hover hover:text-ink"
          >
            <ListIcon size={13} weight="bold" aria-hidden />
            Threads
          </button>
          <span className="num truncate text-xs text-ink-3">
            {turns.length > 0 ? threadTitle(turns[0].question) : "New conversation"}
          </span>
          <button
            type="button"
            onClick={newThread}
            className="ml-auto inline-flex items-center gap-1.5 rounded-sm px-2 py-1 text-base text-ink-2 transition-colors duration-100 hover:bg-hover hover:text-ink"
          >
            <PlusIcon size={13} weight="bold" aria-hidden />
            New
          </button>
        </div>

        <div ref={scrollRef} className="min-h-0 flex-1 overflow-y-auto">
          {loadError ? (
            <div className="mx-auto w-full max-w-3xl px-4 pt-6 sm:px-6">
              <div className="flex items-start gap-2 rounded-lg bg-breach-wash px-3 py-2.5 ring-1 ring-breach-line">
                <WarningCircleIcon
                  size={14}
                  weight="fill"
                  aria-hidden
                  className="mt-0.5 shrink-0 text-breach"
                />
                <p className="min-w-0 flex-1 text-base text-ink">{loadError}</p>
                <button
                  type="button"
                  onClick={conversation.dismissLoadError}
                  className="shrink-0 rounded-sm px-1.5 py-0.5 text-xs text-ink-2 transition-colors duration-100 hover:bg-hover hover:text-ink"
                >
                  Dismiss
                </button>
              </div>
            </div>
          ) : null}

          {status === "loading" ? (
            <div className="mx-auto w-full max-w-3xl space-y-4 px-4 py-6 sm:px-6">
              {[0, 1].map((row) => (
                <div key={row} className="space-y-2">
                  <div className="ml-auto h-9 w-2/5 animate-pulse rounded-lg bg-surface" />
                  <div className="h-24 w-full animate-pulse rounded-lg bg-surface" />
                </div>
              ))}
            </div>
          ) : turns.length === 0 ? (
            <Welcome
              questions={questions}
              onAsk={ask}
              catalogueError={catalogueError}
            />
          ) : (
            <div className="mx-auto w-full max-w-3xl px-4 py-6 sm:px-6">
              {turns.map((turn) => (
                <TurnView
                  key={turn.localId}
                  turn={turn}
                  onAsk={ask}
                  onRetry={ask}
                  onFocus={() => setActiveId(turn.localId)}
                  isActive={turn.localId === activeTurn?.localId}
                  onOpenEvidence={() => {
                    setActiveId(turn.localId);
                    setDrawerOpen(true);
                  }}
                />
              ))}
            </div>
          )}
        </div>

        <div className="shrink-0 border-t border-line">
          <div className="mx-auto w-full max-w-3xl">
            <Composer
              onSubmit={ask}
              onStop={stop}
              busy={busy}
              mode={mode}
              onModeChange={setMode}
            />
          </div>
        </div>

        {/* Threads and the question bank are summoned, not resident. A chat
            that keeps a menu open beside it is a dashboard. */}
        <Sheet
          open={railOpen}
          onClose={() => setRailOpen(false)}
          side="left"
          label="Threads and sample questions"
        >
          <SideRail
            threads={threads}
            activeThreadId={threadId}
            questions={questions}
            onNewThread={() => {
              newThread();
              setRailOpen(false);
            }}
            onOpenThread={(id) => {
              // openThread aborts any running stream and loads that thread's
              // history. Setting the id alone used to leave the current turns
              // on screen under a different conversation's name.
              openThread(id);
              setActiveId(null);
              setRailOpen(false);
            }}
            onAsk={(question) => {
              ask(question);
              setRailOpen(false);
            }}
          />
        </Sheet>

        <Sheet
          open={drawerOpen}
          onClose={() => setDrawerOpen(false)}
          side="right"
          label="Evidence panel"
        >
          <EvidenceDrawer
            facts={drawerFacts}
            tools={activeTurn?.tools ?? []}
            citations={drawerCitations}
            onClose={() => setDrawerOpen(false)}
          />
        </Sheet>
      </div>
    </FactProvider>
  );
}

/**
 * An overlay panel. Escape closes it, the backdrop closes it, and it traps
 * nothing: a controller mid-disruption should never have to hunt for the way
 * out of a panel they opened by accident.
 */
function Sheet({
  open,
  onClose,
  side,
  label,
  children,
}: {
  open: boolean;
  onClose: () => void;
  side: "left" | "right";
  label: string;
  children: React.ReactNode;
}) {
  useEffect(() => {
    if (!open) return;
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") onClose();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open, onClose]);

  if (!open) return null;

  return (
    <div className="absolute inset-0 z-30">
      <button
        type="button"
        aria-label={`Close ${label}`}
        onClick={onClose}
        className="absolute inset-0 bg-ink/20"
      />
      <aside
        aria-label={label}
        className={cx(
          "absolute inset-y-0 flex w-[min(23rem,88vw)] flex-col bg-canvas shadow-xl",
          side === "left" ? "left-0 border-r border-line" : "right-0 border-l border-line",
        )}
      >
        {children}
      </aside>
    </div>
  );
}

function Welcome({
  questions,
  onAsk,
  catalogueError,
}: {
  questions: SampleQuestion[];
  onAsk: (question: string) => void;
  catalogueError: string | null;
}) {
  const byTier = [1, 2, 3].map((tier) => ({
    tier,
    items: questions.filter((question) => question.tier === tier).slice(0, 3),
  }));

  return (
    <div className="mx-auto w-full max-w-3xl px-4 py-8 sm:px-6">
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

      {catalogueError ? (
        <div className="mt-6">
          <EmptyState title="Sample questions are not loaded" detail={catalogueError} />
        </div>
      ) : null}
    </div>
  );
}

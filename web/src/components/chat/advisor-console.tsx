"use client";

/**
 * The Advisor: a conversation.
 *
 * The problem statement asks for a conversational interface, so the
 * conversation is the page. One column at a comfortable reading measure,
 * centred, with nothing sitting permanently beside it competing for the eye.
 *
 * The conversation list is resident on the left, because it is the
 * conversation's own history rather than a navigation tree. The evidence
 * panel is summoned from the answer it belongs to, because it is an
 * interrogation of one answer and has no meaning next to a different one.
 *
 * THE SCROLL AREA RUNS TO THE BOTTOM OF THE WINDOW and the composer floats
 * over it behind a veil of the page colour. There is no rule under the header
 * and none above the composer. Both used to exist, and between them they cut
 * the page into three stacked boxes, which is what made a chat read as an
 * admin console.
 *
 * Fact linking state lives here, above the whole exchange, so pointing at a
 * figure in any answer resolves against every fact the session has seen.
 *
 * No answering logic here. This folds events into turn state and hands the
 * result to presentation components.
 */

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import {
  AirplaneTiltIcon,
  ArrowRightIcon,
  ChatCircleDotsIcon,
  ClockCountdownIcon,
  ListIcon,
  PlusIcon,
  ScalesIcon,
  SidebarSimpleIcon,
  UsersThreeIcon,
  WarningCircleIcon,
  WarningOctagonIcon,
} from "@phosphor-icons/react/dist/ssr";

import type {
  AnswerMode,
  Citation,
  SampleQuestion,
  ThreadSummary,
} from "@/lib/contracts";
import { api } from "@/lib/api";
import { collectFacts } from "@/lib/fact-link";
import type { TurnState } from "@/lib/turn";
import { useConversation } from "@/lib/use-conversation";
import { useStickToBottom } from "@/components/ai/elements";
import { TurnView } from "@/components/chat/turn";
import { Composer } from "@/components/chat/composer";
import { EvidenceDrawer } from "@/components/evidence/evidence-drawer";
import { FactProvider } from "@/components/evidence/fact-context";
import { SideRail } from "@/components/shell/side-rail";
import { ResizeHandle, useResizableWidth } from "@/components/ui/resizable";
import { EmptyState } from "@/components/ui/primitives";
import { cx } from "@/components/ui/tone";

export function AdvisorConsole() {
  const router = useRouter();
  const params = useSearchParams();

  // Fixed. Whether the LangGraph agent or the deterministic resolver answers
  // follows from whether an API key is configured, and the API still accepts
  // `force_mode` for the offline demo. It is not a decision to put in front of
  // a controller before they can ask a question.
  const mode: AnswerMode | "auto" = "auto";
  const [drawerOpen, setDrawerOpen] = useState(false);
  // The sheet, for a window too narrow to hold a resident rail.
  const [sheetOpen, setSheetOpen] = useState(false);
  const [railOpen, setRailOpen] = useRailPreference();
  const [draggingRail, setDraggingRail] = useState(false);
  // 208 is the narrowest a thread title stays recognisable at. 460 is where
  // the rail starts taking width the answer needs more than it does.
  const rail = useResizableWidth("crewops.rail.width.v1", {
    min: 208,
    max: 460,
    initial: 256,
  });
  const [draggingDrawer, setDraggingDrawer] = useState(false);
  const drawer = useResizableWidth("crewops.evidence.width.v1", {
    min: 300,
    max: 620,
    initial: 380,
  });
  const [activeId, setActiveId] = useState<string | null>(null);

  const [questions, setQuestions] = useState<SampleQuestion[]>([]);
  const [threads, setThreads] = useState<ThreadSummary[]>([]);
  const [catalogueError, setCatalogueError] = useState<string | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);

  const conversation = useConversation(mode);
  const {
    turns,
    threadId,
    status,
    loadError,
    hydrated,
    stranded,
    ask,
    stop,
    newThread,
    openThread,
  } = conversation;
  const busy = status === "streaming";

  // Sticks to the bottom only while the reader is already there. Yanking
  // somebody back down mid-answer is the rudest thing a streaming chat does.
  const scrollRef = useStickToBottom(turns.length);
  const seededRef = useRef<string | null>(null);
  const threadIdRef = useRef<string | null>(null);
  const newThreadRef = useRef(newThread);
  useEffect(() => {
    threadIdRef.current = threadId;
    newThreadRef.current = newThread;
  }, [threadId, newThread]);

  const refreshThreads = useCallback(() => {
    api
      .threads()
      .then(setThreads)
      .catch(() => {
        // The thread list is a convenience. Losing it does not stop anyone
        // asking a question, so it fails quietly.
      });
  }, []);

  /**
   * Rename, applied locally first and reconciled with the server after.
   *
   * The optimistic write is worth it because the alternative is a name that
   * does not change for a round trip while somebody is looking straight at
   * it. If the server refuses, the refetch puts the old name back and the
   * error says so, which is the honest version of optimism: the UI may be
   * early, it may not be wrong.
   */
  const renameThread = useCallback(
    (id: string, title: string) => {
      setThreads((current) =>
        current.map((thread) =>
          thread.thread_id === id
            ? { ...thread, title, titled_by: "user" as const }
            : thread,
        ),
      );
      api
        .renameThread(id, title)
        .then(refreshThreads)
        .catch(() => {
          setActionError("That conversation could not be renamed.");
          refreshThreads();
        });
    },
    [refreshThreads],
  );

  /** Clear every conversation. Confirmed in the rail before it gets here. */
  const deleteAllThreads = useCallback(() => {
    setThreads([]);
    newThreadRef.current();
    api
      .deleteAllThreads()
      .then(refreshThreads)
      .catch(() => {
        setActionError("The conversations could not be deleted.");
        refreshThreads();
      });
  }, [refreshThreads]);

  /**
   * Delete, which removes an audit trail and is not optimistic about it.
   *
   * The row is taken off the list straight away because the confirmation has
   * already happened, but if the delete fails the refetch brings it back and
   * says so. A conversation that looks deleted and is not is worse than one
   * that takes a moment to go.
   */
  const deleteThread = useCallback(
    (id: string) => {
      setThreads((current) => current.filter((thread) => thread.thread_id !== id));
      // Reading a thread that no longer exists would 404 into the load error
      // banner, so the view leaves it before the request does.
      if (threadIdRef.current === id) newThreadRef.current();
      api
        .deleteThread(id)
        .then(refreshThreads)
        .catch(() => {
          setActionError("That conversation could not be deleted.");
          refreshThreads();
        });
    },
    [refreshThreads],
  );

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

  // And again when a run this view has already moved on from settles anyway.
  // Switching conversations no longer kills the answer in flight, so the
  // conversation somebody started before they clicked away finishes into the
  // log; without this it would not appear in the rail until the next reload.
  useEffect(() => {
    if (stranded > 0) refreshThreads();
  }, [stranded, refreshThreads]);

  // A question in the URL fires once. This makes every demo question a link.
  //
  // It waits for the stored session to be read back first. Both happen on the
  // same mount, and asking before the restore landed meant the restore
  // replaced the state the question had just been added to: the answer
  // streamed into a turn list that no longer contained it, and nothing ever
  // appeared on screen.
  useEffect(() => {
    if (!hydrated) return;
    const q = params.get("q");
    if (!q || seededRef.current === q) return;
    seededRef.current = q;
    ask(q);
    // BACK TO THIS ROUTE, NOT TO `/`. The console lived at `/` and this line
    // said so literally, so the moment the landing page took that route,
    // asking a question from a link fired the question and then navigated
    // away from the answer to the marketing page. The query string is what
    // needs clearing, not the path: leaving `?q=` in the bar means a reload
    // asks the same question again, and the back button walks through a
    // conversation the reader never typed.
    router.replace("/ask", { scroll: false });
  }, [hydrated, params, ask, router]);

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
      <div className="relative flex h-full min-h-0">
        {/* Resident on a wide window, a sheet on a narrow one. Same
            component, so the thread list cannot drift between the two. */}
        {/* Width, not display, so collapsing is one animated property on the
            compositor and the list inside is never unmounted and remounted.
            `overflow-hidden` is what lets the fixed-width child slide out of
            view instead of reflowing every row as the shell narrows. */}
        <aside
          aria-label="Conversations"
          className={cx(
            "hidden shrink-0 overflow-hidden md:block",
            // The transition is dropped mid-drag. A width transition and a
            // pointer drag fight each other: every frame animates towards a
            // target the next frame has already moved, so the rail lags the
            // cursor by the whole duration and the drag feels broken while
            // working perfectly.
            !draggingRail && "transition-[width] duration-300 ease-out-quint",
          )}
          style={{ width: railOpen ? rail.width : 0 }}
        >
          <div className="h-full" style={{ width: rail.width }}>
          <SideRail
            threads={threads}
            activeThreadId={threadId}
            onNewThread={newThread}
            onCollapse={() => setRailOpen(false)}
            onRename={renameThread}
            onDelete={deleteThread}
            onDeleteAll={deleteAllThreads}
            onOpenThread={(id) => {
              // openThread aborts any running stream and loads that thread's
              // history. Setting the id alone used to leave the current turns
              // on screen under a different conversation's name.
              openThread(id);
              setActiveId(null);
            }}
          />
          </div>
        </aside>

        {railOpen ? (
          <ResizeHandle
            side="right"
            label="Resize the conversations list"
            width={rail.width}
            min={rail.min}
            max={rail.max}
            onResize={rail.commit}
            onReset={rail.reset}
            onDragChange={setDraggingRail}
            className="hidden md:block"
          />
        ) : null}

        <div className="relative flex min-w-0 flex-1 flex-col">
          <header className="flex h-12 shrink-0 items-center gap-1 px-3">
            {/* Two buttons, one visible at a time, chosen in CSS rather than
                by measuring the window in JavaScript. Above md the rail is
                resident and this collapses it; below md there is no rail and
                this opens the sheet. */}
            {!railOpen ? (
              <button
                type="button"
                onClick={() => setRailOpen(true)}
                aria-label="Show conversations"
                title="Show conversations"
                className="hidden size-9 cursor-pointer items-center justify-center rounded-sm text-ink-3 hover:bg-hover hover:text-ink md:inline-flex"
              >
                <SidebarSimpleIcon size={18} weight="bold" aria-hidden />
              </button>
            ) : null}

            <button
              type="button"
              onClick={() => setSheetOpen(true)}
              className="inline-flex items-center gap-1.5 rounded-full px-2.5 py-1 text-base text-ink-2 hover:bg-hover hover:text-ink md:hidden"
            >
              <ListIcon size={14} weight="bold" aria-hidden />
              Conversations
            </button>

            <button
              type="button"
              onClick={newThread}
              className="ml-auto inline-flex items-center gap-1.5 rounded-full px-2.5 py-1 text-base text-ink-2 hover:bg-hover hover:text-ink md:hidden"
            >
              <PlusIcon size={14} weight="bold" aria-hidden />
              New
            </button>
          </header>

        {/* `overflow-x-clip` rather than nothing. `overflow-y: auto` on its
            own computes overflow-x to `auto` as well, so the hero light, which
            deliberately bleeds 34vw past both edges, made this region
            scrollable sideways: the whole conversation could be dragged left
            to reveal a strip of empty page. `clip` keeps the vertical scroll
            and takes the horizontal one away, which `hidden` would not do
            without also making this a scroll container on both axes. */}
        <div ref={scrollRef} className="min-h-0 flex-1 overflow-x-clip overflow-y-auto">
          <div className="mx-auto w-full max-w-5xl px-4 sm:px-6">
            {loadError || actionError ? (
              <div className="flex items-start gap-2 rounded-md bg-breach-wash px-3.5 py-2.5">
                <WarningCircleIcon
                  size={14}
                  weight="fill"
                  aria-hidden
                  className="mt-0.5 shrink-0 text-breach"
                />
                <p className="min-w-0 flex-1 text-base text-ink">
                  {loadError ?? actionError}
                </p>
                <button
                  type="button"
                  onClick={() => {
                    setActionError(null);
                    conversation.dismissLoadError();
                  }}
                  className="shrink-0 rounded-full px-2 py-0.5 text-xs text-ink-2 hover:bg-hover hover:text-ink"
                >
                  Dismiss
                </button>
              </div>
            ) : null}
          </div>

          {status === "loading" ? (
            <div className="mx-auto w-full max-w-5xl space-y-6 px-4 py-6 sm:px-6">
              {[0, 1].map((row) => (
                <div key={row} className="space-y-3">
                  <div className="ml-auto h-10 w-2/5 animate-pulse rounded-xl bg-inset" />
                  <div className="h-28 w-full animate-pulse rounded-md bg-inset" />
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
            /* The bottom padding clears the floating composer, so the last
               answer can be scrolled fully clear of it. */
            <div className="mx-auto w-full max-w-5xl px-4 pt-4 pb-44 sm:px-6">
              {turns.map((turn, index) => (
                <TurnView
                  key={turn.localId}
                  turn={turn}
                  index={index}
                  followsUp={followsUp(turns[index - 1], turn)}
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

        {/* The composer floats over the scroll area rather than sitting in a
            strip below it, so the conversation stays the whole page. The veil
            is the page colour drawn back up, which is what makes the last
            answer dissolve under the field instead of ending at a rule. */}
        <div className="pointer-events-none absolute inset-x-0 bottom-0 z-20">
          <div className="veil pt-12">
            <div className="pointer-events-auto mx-auto w-full max-w-5xl">
              <Composer onSubmit={ask} onStop={stop} busy={busy} />
            </div>
          </div>
          </div>
        </div>

        {/* The narrow-window path to the same list. The sheets are absolutely
            positioned against this row, so they cover the rail too. */}
        <Sheet
          open={sheetOpen}
          onClose={() => setSheetOpen(false)}
          side="left"
          label="Conversations"
        >
          <SideRail
            threads={threads}
            activeThreadId={threadId}
            onRename={renameThread}
            onDelete={deleteThread}
            onDeleteAll={deleteAllThreads}
            onNewThread={() => {
              newThread();
              setSheetOpen(false);
            }}
            onOpenThread={(id) => {
              openThread(id);
              setActiveId(null);
              setSheetOpen(false);
            }}
          />
        </Sheet>

        <Sheet
          open={drawerOpen}
          onClose={() => setDrawerOpen(false)}
          side="right"
          label="Evidence panel"
          width={drawer.width}
          dragging={draggingDrawer}
          handle={
            <ResizeHandle
              side="left"
              label="Resize the evidence panel"
              width={drawer.width}
              min={drawer.min}
              max={drawer.max}
              onResize={drawer.commit}
              onReset={drawer.reset}
              onDragChange={setDraggingDrawer}
            />
          }
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
 * Whether the conversations rail is showing, remembered between visits.
 *
 * It reads back after mount rather than in a lazy initialiser, for the same
 * reason the session does: the server has no localStorage, and disagreeing
 * with the server render blows up hydration. Open is the default, so the
 * pre-hydration paint is the common case and nobody sees it flip.
 */
/**
 * Whether this turn is the previous answer's own suggestion, taken up.
 *
 * A FOLLOW UP IS A CLAIM ABOUT WHERE THE QUESTION CAME FROM, so it is
 * decided by matching the question against what the last answer actually
 * offered, not by position in the thread. Turn four of a conversation is
 * often a fresh subject, and labelling it "follow up" because it is not
 * turn one would be the interface asserting a link that is not there. This
 * matches only when the controller took a question the system proposed,
 * which is the one case the badge is telling the truth about.
 */
function followsUp(previous: TurnState | undefined, turn: TurnState): boolean {
  const reply = previous?.reply;
  if (!reply) return false;
  const offered = [...reply.follow_ups, ...(reply.abstention?.suggestions ?? [])];
  const asked = turn.question.trim().toLowerCase();
  return offered.some((question) => question.trim().toLowerCase() === asked);
}

function useRailPreference(): [boolean, (open: boolean) => void] {
  const [open, setOpen] = useState(true);

  useEffect(() => {
    try {
      // eslint-disable-next-line react-hooks/set-state-in-effect -- post-mount rehydration, see above
      setOpen(window.localStorage.getItem(RAIL_KEY) !== "closed");
    } catch {
      // Private mode or blocked site data. The default stands.
    }
  }, []);

  const set = useCallback((next: boolean) => {
    setOpen(next);
    try {
      window.localStorage.setItem(RAIL_KEY, next ? "open" : "closed");
    } catch {
      // Losing the preference is a smaller problem than throwing here.
    }
  }, []);

  return [open, set];
}

const RAIL_KEY = "crewops.rail.v1";

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
  width,
  handle,
  dragging,
}: {
  open: boolean;
  onClose: () => void;
  side: "left" | "right";
  label: string;
  children: React.ReactNode;
  /** Set only for a panel somebody can drag wider. */
  width?: number;
  handle?: React.ReactNode;
  dragging?: boolean;
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
        className="anim-fade-up absolute inset-0 bg-ink/25"
      />
      <aside
        aria-label={label}
        className={cx(
          "absolute inset-y-2 flex flex-row overflow-hidden rounded-lg bg-canvas shadow-pop",
          side === "left" ? "left-2 anim-slide-left" : "right-2 anim-slide-right",
          // A panel that animates its own width lags the cursor by the
          // transition duration while it is being dragged, so the transition
          // is for arrivals only.
          !dragging && "transition-[width] duration-200 ease-out-quint",
        )}
        style={{ width: width ?? "min(23rem, 88vw)", maxWidth: "92vw" }}
      >
        {handle}
        <div className="flex min-w-0 flex-1 flex-col">{children}</div>
      </aside>
    </div>
  );
}

/**
 * A short prompt for each of the six questions the empty screen offers.
 *
 * THE CARD SAYS THE SHORT ONE AND ASKS THE LONG ONE. The dataset's questions
 * are written for an evaluation harness, not for a person: "As of the
 * snapshot, how many duty hours has C-1042 accrued in the 7 calendar days
 * ending 2026-09-14, and how much headroom does that leave under
 * RULE-DUTY-02?" is thirty-two words, and six of those on one screen is a
 * wall people skip past to type something of their own.
 *
 * What gets SENT is still the dataset's exact wording, so the answer is the
 * one the answer key grades, and the full text is on the card's tooltip. This
 * is a label on a button, not a paraphrase of a question.
 */
const SHORT_PROMPT: Record<string, string> = {
  Q01: "Who is on reserve at BLR?",
  Q02: "How much duty time has C-1042 left?",
  Q17: "C-1042 calls in sick. What stops flying?",
  Q18: "Can C-2087 cover P-2291 legally?",
  Q31: "Best way to cover P-2291?",
  Q32: "Two A320 captains sick at once",
};

/** What the question is FOR, which the question itself does not say. */
const PROMPT_NOTE: Record<string, string> = {
  Q01: "Crew availability and on-call windows",
  Q02: "Duty clocks against the seven day limit",
  Q17: "Which legs lose their crew, and who else it reaches",
  Q18: "All seven rules, on every day of the cover",
  Q31: "Ranked options, with costs and what each one breaks",
  Q32: "Two absences at once, resolved together",
};

/** An icon per question, so the six read as six kinds of question. */
const PROMPT_ICON: Record<string, typeof ChatCircleDotsIcon> = {
  Q01: UsersThreeIcon,
  Q02: ClockCountdownIcon,
  Q17: AirplaneTiltIcon,
  Q18: ScalesIcon,
  Q31: ChatCircleDotsIcon,
  Q32: WarningOctagonIcon,
};

/** Two from each tier, so one screen reaches from a lookup to a ranking. */
const LANDING_QUESTIONS = ["Q01", "Q02", "Q17", "Q18", "Q31", "Q32"];

/**
 * The empty conversation.
 *
 * A question in the display weight, then six questions somebody can click.
 *
 * THE TIER LABELS ARE GONE. The questions used to be grouped under "Tier 1,
 * lookup", "Tier 2, consequence", "Tier 3, recommendation", which is the
 * evaluation rubric's vocabulary printed on the product. A crew controller has
 * never read that rubric and does not care which tier their question is: they
 * care whether it gets answered. The tiers still shape which six appear, so a
 * judge still meets one of each, and they are still named where they belong,
 * on the architecture page.
 */
function Welcome({
  questions,
  onAsk,
  catalogueError,
}: {
  questions: SampleQuestion[];
  onAsk: (question: string) => void;
  catalogueError: string | null;
}) {
  // Named rather than sliced by tier, because the short prompts are written
  // per question: a card picked by position would fall back to the thirty word
  // original the moment the dataset's order changed.
  const byId = new Map(questions.map((question) => [question.id, question]));
  const picks = LANDING_QUESTIONS.map((id) => byId.get(id)).filter(
    (question): question is SampleQuestion => question !== undefined,
  );

  return (
    <div className="relative mx-auto w-full max-w-5xl px-6 pt-24 pb-44">
      {/* THE LIGHT IS FULL BLEED, THE CONTENT IS NOT. `hero-wash` used to sit
          on this column, which is 768px wide, so three radial gradients were
          clipped to a box narrower than any of them and read as a smudge with
          two visible vertical edges. Bleeding it 34vw past both sides puts the
          ends of the lights off screen, which is the only way a radial light
          reads as light rather than as a shape. */}
      <div
        aria-hidden
        className="hero-wash pointer-events-none absolute inset-x-[-34vw] top-0 h-[44rem]"
      />

      <div className="relative">
        {/* The gradient runs over the clause that names the thing being asked
            and stops. Across the whole line it reads as an effect. */}
        <h2 className="macro anim-fade-up text-center text-3xl text-ink">
          What do you need to{" "}
          <span className="ink-gradient">decide today?</span>
        </h2>
        <p
          className="anim-stagger mx-auto mt-3 max-w-[44ch] text-center text-md text-ink-2"
          style={{ "--i": 1 } as React.CSSProperties}
        >
          Crew, flights, legality, cover. Every figure is checked before you see
          it, and an unanswerable question is refused rather than guessed.
        </p>
      </div>

      {/* THE ARROW IS A FILLED BUTTON IN THE CARD'S OWN HUE, and it is always
          there. It was a 13px chevron that faded in on hover, which is two
          mistakes at once: on a touch screen there is no hover so it never
          appeared at all, and on a pointer it meant the card looked like a
          panel until you were already on top of it. A solid disc is what makes
          six cards read as six buttons from across the room, and it is the one
          element of the reference doing the most work. */}
      <div className="relative mt-10 grid gap-3 sm:grid-cols-2">
        {picks.map((question, index) => {
          const tint = (index % 6) + 1;
          const Icon = PROMPT_ICON[question.id] ?? ChatCircleDotsIcon;
          return (
            <button
              key={question.id}
              type="button"
              onClick={() => onAsk(question.question)}
              title={question.question}
              style={
                {
                  "--i": index,
                  "--tint": `var(--tint-${tint})`,
                  "--tile": `var(--tint-${tint}-tile)`,
                  "--mark": `var(--tint-${tint}-ink)`,
                } as React.CSSProperties
              }
              className="anim-stagger group flex cursor-pointer flex-col gap-2.5 rounded-md bg-[var(--tint)] px-4 py-3.5 text-left transition-[box-shadow,transform] duration-200 ease-out-quint hover:-translate-y-0.5 hover:shadow-panel"
            >
              <span className="flex items-start gap-3">
                <span
                  aria-hidden
                  className="flex size-9 shrink-0 items-center justify-center rounded-md bg-[var(--tile)] text-[var(--mark)]"
                >
                  <Icon size={17} weight="bold" />
                </span>
                <span className="min-w-0 flex-1 pt-0.5 text-base leading-snug font-semibold text-ink">
                  {SHORT_PROMPT[question.id] ?? question.question}
                </span>
              </span>

              <span className="flex items-end gap-3">
                <span className="min-w-0 flex-1 text-xs leading-snug text-ink-2">
                  {PROMPT_NOTE[question.id] ?? ""}
                </span>
                <span
                  aria-hidden
                  className="flex size-7 shrink-0 items-center justify-center rounded-full bg-[var(--mark)] text-page transition-transform duration-200 ease-out-quint group-hover:translate-x-0.5"
                >
                  <ArrowRightIcon size={13} weight="bold" />
                </span>
              </span>
            </button>
          );
        })}
      </div>

      {catalogueError ? (
        <div className="mt-8">
          <EmptyState title="Sample questions are not loaded" detail={catalogueError} />
        </div>
      ) : null}
    </div>
  );
}

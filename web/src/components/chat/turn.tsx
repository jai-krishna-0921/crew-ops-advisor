"use client";

/**
 * One exchange: what the controller asked, and what the Advisor answered.
 *
 * NEITHER SIDE IS IN A BUBBLE, AND THE PAGE IS NOT A CHAT.
 *
 * The answer never was: it is set as the page's own body text at full
 * measure, so a table or an option card can use the whole column instead of
 * bursting a rounded container. The question used to be, right aligned and
 * filled, on the argument that a bubble is how a page shows a thing somebody
 * said. That argument is fine and the result was still wrong, because two
 * facing shapes is the one visual signature every chat product shares, and
 * wearing it told a controller they were looking at a chat.
 *
 * They are not. A controller asks one question and the system produces a
 * record: a verdict, its arithmetic, the rules it checked, the options it
 * ranked and the ones it threw out. What a desk keeps of that is a numbered
 * log, so the turn is drawn as one. Each entry hangs off a spine with its
 * index on it, and the question is the entry's heading rather than something
 * a participant said. The transcript reads down the page as a docket of
 * decisions, which is what it is, and looks nothing like two people talking,
 * which is what it never was.
 *
 * The trace and the evidence are offered under the answer, not beside it. A
 * controller reads the answer first and interrogates it second, and the
 * layout follows that order rather than presenting both at once.
 */

import {
  ArrowClockwiseIcon,
  ArrowElbowDownRightIcon,
  MagnifyingGlassIcon,
  WarningCircleIcon,
  SpeakerHighIcon,
  StopIcon,
} from "@phosphor-icons/react/dist/ssr";

import { phaseOf, type TurnState } from "@/lib/turn";
import { AnswerBody } from "@/components/answer/answer-body";
import { LiveTrace, TraceChips, TraceSummary } from "@/components/chat/live-trace";
import { Thinking } from "@/components/ai/elements";

export function TurnView({
  turn,
  index,
  followsUp = false,
  onAsk,
  onRetry,
  onFocus,
  isActive,
  onOpenEvidence,
  onReadAloud,
  speaking = false,
}: {
  turn: TurnState;
  /** Position in the thread, zero based. Drawn as the entry's number. */
  index: number;
  /** This question is one the previous answer proposed, taken up. */
  followsUp?: boolean;
  onAsk: (question: string) => void;
  onRetry: (question: string) => void;
  onFocus: () => void;
  isActive: boolean;
  onOpenEvidence: () => void;
  onReadAloud?: () => void;
  speaking?: boolean;
}) {
  const phase = phaseOf(turn);
  const reply = phase === "settled" ? turn.reply : null;
  const factCount = reply?.facts.length ?? 0;

  return (
    <article
      onFocusCapture={onFocus}
      data-active={isActive ? "true" : undefined}
      className="anim-fade-up grid grid-cols-[1.5rem_minmax(0,1fr)] gap-x-3 pb-12 sm:grid-cols-[2.25rem_minmax(0,1fr)] sm:gap-x-5"
    >
      {/* THE SPINE. The index sits on it and the rule falls from there to the
          bottom of the entry, so a thread of ten answers reads as ten
          numbered records on one continuous line rather than as ten
          free floating blocks. It is decoration and is hidden from the
          reader of a screen reader, who gets the heading instead. */}
      <div aria-hidden className="relative">
        <span className="num block text-right text-xs leading-6 font-semibold text-ink-3 tabular-nums sm:text-center">
          {String(index + 1).padStart(2, "0")}
        </span>
        <span className="absolute inset-x-0 top-8 bottom-0 mx-auto w-px bg-line-soft" />
      </div>

      <div className="min-w-0">
        {/* The question is the entry's heading, not something a participant
            said, so it is set in the display face at the size of a section
            title and given a rule under it.

            A question the last answer proposed says so above itself. Without
            it every entry opens identically and a thread reads as a stack of
            unrelated enquiries, when half of them are the controller pulling
            on a thread the system handed them. */}
        <div className="border-b border-line-soft pb-2.5">
          {followsUp ? (
            <p className="mb-1 flex items-center gap-1.5 text-2xs font-semibold tracking-[0.08em] text-ink-3 uppercase">
              <ArrowElbowDownRightIcon size={11} weight="bold" aria-hidden />
              Follow-up
            </p>
          ) : null}
          <h2 className="macro text-[1.2rem] leading-snug text-ink">
            {turn.question}
          </h2>
        </div>

      {reply ? (
        <div className="mt-5 space-y-4">
          {/* THE WORKING COMES FIRST, FOLDED. It sat under the answer, on the
              argument that a controller reads the answer and interrogates it
              second. That is true of the DETAIL and not of the fact that
              detail exists: an answer that arrives with no visible account of
              where it came from has to be trusted before it can be checked,
              and this product's entire claim is the other way round. One line
              saying what ran, above, costs nothing to skip and changes what
              the answer is. */}
          {turn.plan || turn.tools.length > 0 ? (
            <Thinking
              summary="How this was worked out"
              meta={<TraceSummary turn={turn} />}
            >
              {/* The draft is blanked: replaying a stream for an answer that
                  has already settled would be theatre, and worse, would put
                  unverified prose back on screen under a verified one. */}
              <LiveTrace turn={{ ...turn, draft: "" }} />
            </Thinking>
          ) : null}

          <div className="anim-settle">
            <AnswerBody reply={reply} onAsk={onAsk} />
          </div>

          <div className="flex flex-wrap items-center gap-1.5 pt-1">
            <button
              type="button"
              onClick={onOpenEvidence}
              className="inline-flex cursor-pointer items-center gap-1.5 rounded-full bg-inset px-2.5 py-1 text-xs text-ink-2 hover:bg-hover hover:text-ink"
            >
              <MagnifyingGlassIcon size={11} weight="bold" aria-hidden />
              Evidence
              {factCount > 0 ? <span className="num">{factCount}</span> : null}
            </button>
            <TraceChips turn={turn} />
            {onReadAloud && (reply.abstention || ["verified", "repaired"].includes(reply.verification.status)) ? (
              <button type="button" onClick={onReadAloud} aria-label={speaking ? "Stop reading answer" : "Read answer aloud"}
                className="inline-flex cursor-pointer items-center gap-1.5 rounded-full bg-inset px-2.5 py-1 text-xs text-ink-2 hover:bg-hover hover:text-ink">
                {speaking ? <StopIcon size={12} weight="fill" aria-hidden /> : <SpeakerHighIcon size={12} aria-hidden />}
                {speaking ? "Stop reading" : "Read aloud"}
              </button>
            ) : null}
          </div>
        </div>
      ) : (
        <div className="mt-5">
          <LiveTrace turn={turn} />
        </div>
      )}

      {turn.error ? (
        <div className="mt-4 flex flex-wrap items-center gap-2 rounded-md bg-breach-wash px-3.5 py-2.5">
          <WarningCircleIcon size={14} weight="fill" aria-hidden className="text-breach" />
          <p className="min-w-0 flex-1 text-base text-ink">{turn.error.message}</p>
          {turn.error.recoverable ? (
            <button
              type="button"
              onClick={() => onRetry(turn.question)}
              className="inline-flex items-center gap-1.5 rounded-full bg-surface px-2.5 py-1 text-base text-ink hairline hover:bg-hover"
            >
              <ArrowClockwiseIcon size={12} weight="bold" aria-hidden />
              Ask again
            </button>
          ) : null}
        </div>
      ) : null}
      </div>
    </article>
  );
}

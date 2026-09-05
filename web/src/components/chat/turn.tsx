"use client";

/**
 * One exchange: what the controller asked, and what the Advisor answered.
 *
 * THE PAGE IS A NUMBERED LOG, NOT A TRANSCRIPT OF TWO PARTICIPANTS.
 *
 * A controller asks one question and the system produces a record: a
 * verdict, its arithmetic, the rules it checked, the options it ranked and
 * the ones it threw out. What a desk keeps of that is a numbered log, so
 * the turn is drawn as one. Each entry hangs off a spine with its index on
 * it, and the transcript reads down the page as a docket of decisions.
 *
 * THE ANSWER IS NOT IN A SHAPE. It is set as the page's own body text at
 * full measure, so a table, a bar or an option card can use the whole column
 * instead of bursting a rounded container.
 *
 * THE QUESTION IS, and the distinction is worth stating precisely, because
 * this file has been wrong in both directions. Filling a shape is how a page
 * shows that somebody said something, and taking the fill away entirely left
 * the question reading as a title for the answer rather than as a separate
 * act. What actually made the old version look like every chat product was
 * not the fill: it was floating the shape to the right and capping its
 * width, which is the signature of two participants facing each other. So
 * the fill is back, in the reader's own colour, and it is left aligned and
 * full width inside the entry. It is a filled panel in a log, not a bubble
 * in a conversation.
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
        {/* The question is the entry's heading, filled in the reader's own
            colour so it is unmistakably the thing they asked rather than the
            first line of what the system said back. Set as a plain rule and
            heading it was too quiet: an answer that opens with prose
            immediately under a line of type made the question read as a
            title for the answer instead of as a separate act.

            Left aligned and full width inside the entry, which is the
            difference between this and the bubble it replaced. Filling a
            shape says "somebody said this"; floating it to the right and
            capping its width is what turns a page into a transcript of two
            participants, and that was the part worth losing.

            A question the last answer proposed says so above itself. Without
            it every entry opens identically and a thread reads as a stack of
            unrelated enquiries, when half of them are the controller pulling
            on a thread the system handed them. */}
        <div
          className="rounded-md px-4 py-3"
          style={{
            backgroundImage: "var(--grad-voice)",
            color: "var(--voice-ink)",
          }}
        >
          {followsUp ? (
            /* No opacity on this. Knocking it back to 70 percent put a small
               bold uppercase label at about 3.5:1 against the panel it sits
               on, under the 4.5:1 that size needs. It is already secondary
               by being half the size of the question, uppercase and tracked
               out, so the colour does not have to do it as well. */
            <p className="mb-1 flex items-center gap-1.5 text-2xs font-semibold tracking-[0.08em] uppercase">
              <ArrowElbowDownRightIcon size={11} weight="bold" aria-hidden />
              Follow-up
            </p>
          ) : null}
          <h2 className="macro text-[1.2rem] leading-snug">{turn.question}</h2>
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

"use client";

/**
 * One exchange: what the controller asked, and what the Advisor answered.
 *
 * THE ANSWER IS NOT IN A BUBBLE. The question is, because a question is a
 * thing somebody said and a filled shape aligned right is how a page shows
 * that. The answer is set as the page's own body text at full measure, with
 * nothing drawn around it.
 *
 * That asymmetry is the whole layout, and it is what both of the chat
 * interfaces worth copying do. Two facing bubbles make a transcript of a
 * conversation between two participants of equal standing. What is actually
 * happening here is that a controller asks and the system produces a
 * document: a verdict, its arithmetic, a ranked table, the rules it checked.
 * A document does not go in a speech bubble. Once the frame is gone the
 * answer can also use the full width for a table or an option card, which the
 * bubble version could not without bursting its own container.
 *
 * The trace and the evidence are offered under the answer, not beside it. A
 * controller reads the answer first and interrogates it second, and the
 * layout follows that order rather than presenting both at once.
 */

import {
  ArrowClockwiseIcon,
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
  onAsk,
  onRetry,
  onFocus,
  isActive,
  onOpenEvidence,
  onReadAloud,
  speaking = false,
}: {
  turn: TurnState;
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
      className="anim-fade-up pb-12"
    >
      <div className="flex justify-end">
        {/* The question is the one thing on the page that is not the system
            talking, so it gets a colour rather than another grey fill. */}
        <p
          className="max-w-[42ch] rounded-xl rounded-br-sm px-4 py-2.5 text-md leading-snug"
          style={{
            backgroundImage: "var(--grad-voice)",
            color: "var(--voice-ink)",
          }}
        >
          {turn.question}
        </p>
      </div>

      {reply ? (
        <div className="mt-6 space-y-4">
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
        <div className="mt-6">
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
    </article>
  );
}

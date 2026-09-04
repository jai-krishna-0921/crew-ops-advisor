"use client";

/**
 * One exchange in the conversation: what the controller asked, and what the
 * Advisor answered.
 *
 * The question is set as the controller's own line, aligned right and filled,
 * so the page reads as a dialogue rather than as a report with a form field at
 * the top. The answer sits left and open, in the Advisor's voice.
 *
 * The transition from provisional to settled is the moment the whole design
 * turns on, so it is explicit: the draft is replaced rather than upgraded in
 * place, and the settled block animates as text coming into focus.
 *
 * The trace and the evidence are offered under the answer, not beside it. A
 * controller reads the answer first and interrogates it second, and the layout
 * should follow that order rather than presenting both at once.
 */

import {
  ArrowClockwiseIcon,
  MagnifyingGlassIcon,
  WarningCircleIcon,
} from "@phosphor-icons/react/dist/ssr";

import { phaseOf, type TurnState } from "@/lib/turn";
import { AnswerBody } from "@/components/answer/answer-body";
import { LiveTrace, TraceSummary } from "@/components/chat/live-trace";
import { Disclosure } from "@/components/ui/primitives";

export function TurnView({
  turn,
  onAsk,
  onRetry,
  onFocus,
  isActive,
  onOpenEvidence,
}: {
  turn: TurnState;
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
      className="pb-8"
    >
      <div className="flex justify-end">
        <p className="max-w-[46ch] rounded-lg rounded-br-sm bg-accent-tint px-3.5 py-2.5 text-md leading-snug text-ink ring-1 ring-accent-line">
          {turn.question}
        </p>
      </div>

      {reply ? (
        <div className="mt-5 space-y-3">
          <div className="anim-settle">
            <AnswerBody reply={reply} onAsk={onAsk} />
          </div>

          <div className="flex flex-wrap items-center gap-1.5 pt-1">
            <button
              type="button"
              onClick={onOpenEvidence}
              className="inline-flex items-center gap-1.5 rounded-sm bg-surface px-2 py-1 text-xs text-ink-2 hairline transition-colors duration-100 hover:bg-hover hover:text-ink"
            >
              <MagnifyingGlassIcon size={11} weight="bold" aria-hidden />
              Evidence
              {factCount > 0 ? <span className="num">{factCount}</span> : null}
            </button>
            {turn.plan || turn.tools.length > 0 ? (
              <Disclosure
                summary={
                  <span className="inline-flex items-center gap-2">
                    How this was worked out <TraceSummary turn={turn} />
                  </span>
                }
              >
                <div className="px-1 pb-2">
                  <LiveTrace turn={{ ...turn, draft: "" }} />
                </div>
              </Disclosure>
            ) : null}
          </div>
        </div>
      ) : (
        <div className="mt-5">
          <LiveTrace turn={turn} />
        </div>
      )}

      {turn.error ? (
        <div className="mt-3 flex flex-wrap items-center gap-2 rounded-md bg-breach-wash px-3 py-2 ring-1 ring-breach-line">
          <WarningCircleIcon
            size={14}
            weight="fill"
            aria-hidden
            className="text-breach"
          />
          <p className="min-w-0 flex-1 text-base text-ink">{turn.error.message}</p>
          {turn.error.recoverable ? (
            <button
              type="button"
              onClick={() => onRetry(turn.question)}
              className="inline-flex items-center gap-1.5 rounded-sm bg-surface px-2 py-1 text-base text-ink hairline transition-colors duration-100 hover:bg-hover"
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

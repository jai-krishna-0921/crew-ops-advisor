"use client";

/**
 * One exchange: the question, the live trace while it runs, and the settled
 * answer when it lands.
 *
 * The transition from provisional to settled is the moment the whole design
 * turns on, so it is explicit. The draft is replaced rather than upgraded in
 * place, and the settled block carries a short animation that reads as text
 * coming into focus rather than as text appearing from nowhere.
 *
 * Fact linking state lives one level up, on the page, so that pointing at a
 * figure here lights the matching row in the drawer over there.
 */

import { ArrowClockwiseIcon, WarningCircleIcon } from "@phosphor-icons/react/dist/ssr";

import { phaseOf, type TurnState } from "@/lib/turn";
import { AnswerBody } from "@/components/answer/answer-body";
import { LiveTrace, TraceSummary } from "@/components/chat/live-trace";
import { Disclosure } from "@/components/ui/primitives";
import { cx } from "@/components/ui/tone";

export function TurnView({
  turn,
  onAsk,
  onRetry,
  onFocus,
  isActive,
}: {
  turn: TurnState;
  onAsk: (question: string) => void;
  onRetry: (question: string) => void;
  onFocus: () => void;
  isActive: boolean;
}) {
  const phase = phaseOf(turn);
  const reply = phase === "settled" ? turn.reply : null;

  return (
    <article
      onFocusCapture={onFocus}
      onMouseDown={onFocus}
      data-active={isActive ? "true" : undefined}
      className={cx(
        "border-b border-line px-4 py-5 last:border-b-0 sm:px-6",
        isActive && "bg-canvas/40",
      )}
    >
      <h2 className="mb-3 flex items-start gap-2">
        <span className="label-micro mt-1 shrink-0">Asked</span>
        <span className="max-w-[62ch] text-md font-medium text-ink">
          {turn.question}
        </span>
      </h2>

      {reply ? (
        <div className="space-y-3">
          {turn.plan || turn.tools.length > 0 ? (
            <Disclosure
              summary={
                <span className="inline-flex items-center gap-2">
                  Agent trace <TraceSummary turn={turn} />
                </span>
              }
            >
              <div className="px-1 pb-2">
                <LiveTrace turn={{ ...turn, draft: "" }} />
              </div>
            </Disclosure>
          ) : null}
          <div className="anim-settle">
            <AnswerBody reply={reply} onAsk={onAsk} />
          </div>
        </div>
      ) : (
        <LiveTrace turn={turn} />
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

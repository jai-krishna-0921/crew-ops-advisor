"use client";

/**
 * The prompt bar.
 *
 * One field, one control. Enter sends, shift-enter breaks a line, and the
 * field grows to about five lines before it scrolls.
 *
 * IT FLOATS, so the scroll area runs to the bottom of the window and the last
 * answer dissolves under the field instead of stopping at an edge. That much
 * is worth keeping from every chat product: it makes the conversation the
 * whole page rather than a panel above a toolbar.
 *
 * WHAT MADE IT GENERIC was never the rounding. It was the furniture: a
 * sparkle on the left, standing in for "this is AI", and a circular gradient
 * arrow on the right, which together are the single most recognisable object
 * in consumer AI. Those are gone. A prompt caret marks where typing begins,
 * the way a terminal does, and the control carries a word.
 *
 * The pill shape stays, because a soft capsule is a genuinely good shape for
 * a single line of input and it is not what made the old bar look borrowed.
 *
 * The button says what it does. An icon-only circle is fine when the whole
 * world already knows the icon, and worse than a word when the product is
 * asking somebody to commit a decision to a log.
 *
 * While a turn is running the send control becomes a stop control. A
 * controller who has read enough should not have to wait for the agent to
 * finish before asking the next thing, and the same button doing both means
 * the target never moves.
 *
 * IT IS A FIELD AND A BUTTON, and everything else that was here is gone.
 *
 * Auto / Agent / Offline sat under the field as three uppercase pills, which
 * put a developer's plumbing in front of a crew controller as though it were a
 * decision they had to make before they could ask anything. It is not: whether
 * the LangGraph agent or the deterministic resolver answers follows from
 * whether an API key is configured, the answer is the same shape either way,
 * and both go through the same tools and the same grounding guard. Which one
 * is running is worth stating once, so the section rail states it.
 * `force_mode` stays on the API for the offline demo.
 *
 * Then "Enter to send" and a line about grounding replaced them, and they were
 * the same mistake in a quieter voice. "Enter to send" is a fact everybody
 * already knows, printed permanently under the one control on the page. The
 * grounding line was a claim about the product placed where the reader has
 * nothing to check it against; it belongs next to an answer, attached to the
 * verification that earned it, and that is where it now is.
 */

import { useEffect, useRef, useState, type ReactNode } from "react";
import { ArrowUpIcon, SparkleIcon, StopIcon } from "@phosphor-icons/react/dist/ssr";

import { cx } from "@/components/ui/tone";

export function Composer({
  onSubmit,
  onStop,
  busy,
  placeholder = "Ask about crew, flights, legality or cover",
  autoFocus = false,
  voicePanel,
}: {
  onSubmit: (question: string) => void;
  onStop: () => void;
  busy: boolean;
  placeholder?: string;
  autoFocus?: boolean;
  voicePanel?: ReactNode;
}) {
  const [value, setValue] = useState("");
  const ref = useRef<HTMLTextAreaElement>(null);

  useEffect(() => {
    const node = ref.current;
    if (!node) return;
    node.style.height = "auto";
    node.style.height = `${Math.min(node.scrollHeight, 168)}px`;
  }, [value]);

  useEffect(() => {
    if (autoFocus) ref.current?.focus();
  }, [autoFocus]);

  const send = () => {
    const question = value.trim();
    if (!question || busy) return;
    setValue("");
    onSubmit(question);
  };

  const canSend = value.trim().length > 0;

  return (
    <div className="px-4 pb-5 sm:px-6">
      <div className="relative overflow-hidden rounded-xl bg-surface shadow-float transition-shadow duration-200 ease-out-quint focus-within:shadow-pop">
        <div className="composer-input-surface">
          {voicePanel}

          {/* A mark, in the product's own gradient. The rule this composer was
              built on was that plumbing and unverifiable claims do not go in
              front of a controller: a mode switch is a decision they should not
              have to make, and "every figure is checked" printed under an empty
              field is a claim with nothing to check it against. Neither argument
              reaches a decorative glyph. It says nothing, asks nothing, and is
              aria-hidden. */}
          <SparkleIcon
            size={17}
            weight="fill"
            aria-hidden
            className="pointer-events-none absolute top-4 left-4 text-accent"
          />

          <textarea
            ref={ref}
            rows={1}
            value={value}
            onChange={(event) => setValue(event.target.value)}
            onKeyDown={(event) => {
              if (event.key === "Enter" && !event.shiftKey) {
                event.preventDefault();
                send();
              }
            }}
            placeholder={placeholder}
            aria-label="Ask the advisor"
            className="block max-h-42 w-full resize-none bg-transparent py-3.5 pr-14 pl-11 text-md leading-relaxed text-ink placeholder:text-ink-3 focus:outline-none"
          />

          <button
            type="button"
            onClick={busy ? onStop : send}
            disabled={!busy && !canSend}
            aria-label={busy ? "Stop generating" : "Send"}
            className={cx(
              "absolute right-2.5 bottom-2.5 inline-flex size-9 items-center justify-center rounded-full",
              "transition-[background-color,color,transform] duration-200 ease-out-quint",
              "disabled:cursor-not-allowed",
              busy
                ? "bg-ink text-page"
                : canSend
                  ? "bg-[image:var(--grad-accent)] text-page shadow-panel hover:scale-105"
                  : "bg-inset text-ink-3",
            )}
          >
            {busy ? (
              <StopIcon size={13} weight="fill" aria-hidden />
            ) : (
              <ArrowUpIcon size={16} weight="bold" aria-hidden />
            )}
          </button>
        </div>
      </div>
    </div>
  );
}

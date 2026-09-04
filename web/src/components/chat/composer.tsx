"use client";

/**
 * The prompt bar.
 *
 * One field, one control. Enter sends, shift-enter breaks a line, and the
 * field grows to about five lines before it scrolls.
 *
 * IT FLOATS, and that is the difference between this and the version it
 * replaces. The old one sat in a fixed strip with a rule along the top, so
 * the conversation ended at a line and the composer was a separate region of
 * the page. Here the scroll area runs to the bottom of the window and the
 * composer sits over it on a shadow, with the page colour drawn back up
 * behind it: the last answer dissolves under the field instead of stopping at
 * an edge. Every chat worth copying does it this way, and the reason is that
 * it keeps the conversation the whole page.
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

import { useEffect, useRef, useState } from "react";
import { ArrowUpIcon, StopIcon } from "@phosphor-icons/react/dist/ssr";

import { cx } from "@/components/ui/tone";

export function Composer({
  onSubmit,
  onStop,
  busy,
  placeholder = "Ask about crew, flights, legality or cover",
  autoFocus = false,
}: {
  onSubmit: (question: string) => void;
  onStop: () => void;
  busy: boolean;
  placeholder?: string;
  autoFocus?: boolean;
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
      <div className="relative rounded-xl bg-surface shadow-float transition-shadow duration-200 ease-out-quint focus-within:shadow-pop">
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
          className="block max-h-42 w-full resize-none bg-transparent py-3.5 pr-14 pl-4 text-md leading-relaxed text-ink placeholder:text-ink-3 focus:outline-none"
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
                ? "bg-accent text-page hover:scale-105"
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
  );
}

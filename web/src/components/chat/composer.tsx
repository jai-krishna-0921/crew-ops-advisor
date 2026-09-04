"use client";

/**
 * The prompt bar.
 *
 * One field, one control. Enter sends, shift-enter breaks a line, and the
 * field grows to about four lines before it scrolls.
 *
 * While a turn is running the send control becomes a stop control. A
 * controller who has read enough should not have to wait for the agent to
 * finish before asking the next thing, and the same button doing both means
 * the target never moves.
 *
 * The answer mode sits behind a quiet toggle rather than a form select. It
 * matters for a demo (it proves the deterministic path answers on its own)
 * and almost never otherwise, so it should not look like a required field.
 */

import { useEffect, useRef, useState } from "react";
import { ArrowUpIcon, StopIcon } from "@phosphor-icons/react/dist/ssr";

import type { AnswerMode } from "@/lib/contracts";
import { cx } from "@/components/ui/tone";

const MODES: ReadonlyArray<{ value: AnswerMode | "auto"; label: string; hint: string }> = [
  { value: "auto", label: "Auto", hint: "Use the agent when a key is configured" },
  { value: "agent", label: "Agent", hint: "Force the planning agent" },
  { value: "deterministic", label: "Offline", hint: "Force the deterministic resolver" },
];

export function Composer({
  onSubmit,
  onStop,
  busy,
  mode,
  onModeChange,
  placeholder = "Ask about crew, flights, legality or cover",
}: {
  onSubmit: (question: string) => void;
  onStop: () => void;
  busy: boolean;
  mode: AnswerMode | "auto";
  onModeChange: (mode: AnswerMode | "auto") => void;
  placeholder?: string;
}) {
  const [value, setValue] = useState("");
  const ref = useRef<HTMLTextAreaElement>(null);

  useEffect(() => {
    const node = ref.current;
    if (!node) return;
    node.style.height = "auto";
    node.style.height = `${Math.min(node.scrollHeight, 132)}px`;
  }, [value]);

  const send = () => {
    const question = value.trim();
    if (!question || busy) return;
    setValue("");
    onSubmit(question);
  };

  const canSend = value.trim().length > 0;

  return (
    <div className="px-4 pt-3 pb-5 sm:px-6">
      <div
        className={cx(
          "rounded-xl bg-surface transition-shadow duration-150",
          "ring-1 ring-line focus-within:ring-accent-line",
        )}
      >
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
          className="block w-full resize-none bg-transparent px-4 pt-3.5 pb-2 text-md leading-relaxed text-ink placeholder:text-ink-3 focus:outline-none"
        />

        <div className="flex items-center gap-1 px-2.5 pb-2.5">
          <div
            role="radiogroup"
            aria-label="Answer mode"
            className="flex items-center gap-0.5"
          >
            {MODES.map((option) => (
              <button
                key={option.value}
                type="button"
                role="radio"
                aria-checked={mode === option.value}
                title={option.hint}
                onClick={() => onModeChange(option.value)}
                className={cx(
                  "rounded-md px-2 py-1 text-xs transition-colors duration-100",
                  mode === option.value
                    ? "bg-hover text-ink"
                    : "text-ink-3 hover:text-ink-2",
                )}
              >
                {option.label}
              </button>
            ))}
          </div>

          <span className="ml-auto hidden text-xs text-ink-3 sm:inline">
            Enter to send
          </span>

          <button
            type="button"
            onClick={busy ? onStop : send}
            disabled={!busy && !canSend}
            aria-label={busy ? "Stop generating" : "Send"}
            className={cx(
              "ml-2 inline-flex size-8 items-center justify-center rounded-lg transition-all duration-100",
              "active:scale-95 disabled:cursor-not-allowed",
              busy
                ? "bg-ink text-page"
                : canSend
                  ? "bg-ink text-page hover:opacity-90"
                  : "bg-hover text-ink-3",
            )}
          >
            {busy ? (
              <StopIcon size={13} weight="fill" aria-hidden />
            ) : (
              <ArrowUpIcon size={15} weight="bold" aria-hidden />
            )}
          </button>
        </div>
      </div>
    </div>
  );
}

"use client";

/**
 * The question input.
 *
 * Enter sends, shift-enter breaks a line, and the field grows to four lines
 * before it scrolls. While a turn is running the send control becomes a stop
 * control: a controller who has seen enough should not have to wait for the
 * agent to finish before asking the next thing.
 */

import { useEffect, useRef, useState } from "react";
import { ArrowUpIcon, StopIcon } from "@phosphor-icons/react/dist/ssr";

import type { AnswerMode } from "@/lib/contracts";
import { Kbd } from "@/components/ui/primitives";
import { cx } from "@/components/ui/tone";

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
    node.style.height = `${Math.min(node.scrollHeight, 112)}px`;
  }, [value]);

  const send = () => {
    const question = value.trim();
    if (!question || busy) return;
    setValue("");
    onSubmit(question);
  };

  return (
    <form
      onSubmit={(event) => {
        event.preventDefault();
        send();
      }}
      className="border-t border-line bg-canvas px-4 py-3 sm:px-6"
    >
      <div
        className={cx(
          "rounded-lg bg-field transition-shadow duration-150",
          "hairline focus-within:ring-1 focus-within:ring-accent-line",
        )}
      >
        <label htmlFor="composer" className="sr-only">
          Ask the Crew Ops Advisor
        </label>
        <textarea
          id="composer"
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
          className="block w-full resize-none bg-transparent px-3 pt-2.5 pb-1 text-md text-ink outline-none placeholder:text-ink-3"
        />

        <div className="flex items-center gap-2 px-2 pb-2">
          <ModeSelect mode={mode} onChange={onModeChange} />

          <span className="ml-auto hidden items-center gap-1 text-2xs text-ink-3 sm:flex">
            <Kbd>Enter</Kbd> to send
            <Kbd>Shift</Kbd>
            <Kbd>Enter</Kbd> for a new line
          </span>

          {busy ? (
            <button
              type="button"
              onClick={onStop}
              className="inline-flex h-7 items-center gap-1.5 rounded-sm bg-inset px-2 text-base font-medium text-ink ring-1 ring-line transition-colors duration-100 hover:bg-hover"
            >
              <StopIcon size={12} weight="fill" aria-hidden />
              Stop
            </button>
          ) : (
            <button
              type="submit"
              disabled={value.trim().length === 0}
              aria-label="Send question"
              className="inline-flex h-7 w-7 items-center justify-center rounded-sm bg-accent text-page transition-opacity duration-100 disabled:opacity-30"
            >
              <ArrowUpIcon size={13} weight="bold" aria-hidden />
            </button>
          )}
        </div>
      </div>
    </form>
  );
}

function ModeSelect({
  mode,
  onChange,
}: {
  mode: AnswerMode | "auto";
  onChange: (mode: AnswerMode | "auto") => void;
}) {
  return (
    <div className="flex items-center gap-1.5">
      <label htmlFor="mode" className="label-micro">
        Mode
      </label>
      <select
        id="mode"
        value={mode}
        onChange={(event) => onChange(event.target.value as AnswerMode | "auto")}
        className="rounded-sm bg-inset px-1.5 py-1 text-xs text-ink-2 ring-1 ring-line outline-none hover:text-ink"
      >
        <option value="auto">Auto</option>
        <option value="agent">Agent</option>
        <option value="deterministic">Deterministic</option>
      </select>
    </div>
  );
}

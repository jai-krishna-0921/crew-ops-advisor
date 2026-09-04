"use client";

/**
 * The questions the system offers next.
 *
 * These were 11px grey chips, which is the visual weight of a footnote, and
 * they are not a footnote: when the advisor abstains they are the entire
 * usable content of the reply, the only thing on the card a controller can
 * act on. A refusal that offers three ways forward and renders them smaller
 * than the refusal is telling the reader to ignore them.
 *
 * So they are rows, at reading size, in the same tinted family as the landing
 * cards. One component for both the abstention's "try instead" and an answer's
 * follow ups, because they are the same object and were drifting apart.
 */

import { ArrowRightIcon } from "@phosphor-icons/react/dist/ssr";

import { Eyebrow } from "@/components/ui/primitives";

/**
 * The six card tints, cycled. Colour here is grouping rather than meaning:
 * these are peers, and nothing about the third suggestion is more urgent than
 * the first. It exists so three rows read as three choices at a glance rather
 * than as a paragraph that happens to have buttons in it.
 */
const TINTS = 6;

export function SuggestionList({
  label,
  questions,
  onAsk,
  offset = 0,
}: {
  label: string;
  questions: string[];
  onAsk?: (question: string) => void;
  /** Shifts the tint cycle, so two lists on one turn do not open on the
   *  same colour. */
  offset?: number;
}) {
  if (questions.length === 0) return null;

  return (
    <nav aria-label={label}>
      <Eyebrow>{label}</Eyebrow>
      <ul className="mt-2 flex flex-col gap-1.5">
        {questions.map((question, index) => {
          const tint = ((index + offset) % TINTS) + 1;
          return (
            <li key={question}>
              <button
                type="button"
                onClick={() => onAsk?.(question)}
                disabled={!onAsk}
                style={
                  {
                    "--row": `var(--tint-${tint})`,
                    "--tile": `var(--tint-${tint}-tile)`,
                    "--mark": `var(--tint-${tint}-ink)`,
                  } as React.CSSProperties
                }
                className="group flex w-full items-center gap-2.5 rounded-md bg-[var(--row)] px-2.5 py-2.5 text-left transition-[transform,box-shadow] duration-150 hover:-translate-y-px hover:shadow-[var(--shadow-pop)] disabled:cursor-default disabled:opacity-70 disabled:hover:translate-y-0 disabled:hover:shadow-none"
              >
                <span
                  aria-hidden
                  className="grid size-6 shrink-0 place-items-center rounded-sm bg-[var(--tile)] text-[var(--mark)]"
                >
                  <ArrowRightIcon size={12} weight="bold" />
                </span>
                <span className="min-w-0 flex-1 text-md font-medium text-ink">
                  {question}
                </span>
              </button>
            </li>
          );
        })}
      </ul>
    </nav>
  );
}

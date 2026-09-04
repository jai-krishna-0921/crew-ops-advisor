"use client";

/**
 * A refusal, rendered as a result.
 *
 * This is deliberately not an error state. No red, no warning triangle, no
 * apology. A system that says "I cannot answer that reliably" is doing the
 * right thing, and the card is designed to read that way: calm ground, the
 * reason named, what was missing, what was established anyway, and the
 * questions that would work instead.
 */

import { ArrowRightIcon, ShieldCheckIcon } from "@phosphor-icons/react/dist/ssr";

import type { Abstention, Fact } from "@/lib/contracts";
import { ABSTENTION_LABEL } from "@/lib/format";
import { GroundedText } from "@/components/answer/grounded-prose";
import { Eyebrow, Pill } from "@/components/ui/primitives";

export function AbstentionCard({
  abstention,
  facts,
  onAsk,
}: {
  abstention: Abstention;
  facts: Fact[];
  onAsk?: (question: string) => void;
}) {
  return (
    <section
      aria-label="The advisor declined to answer"
      className="rounded-md bg-surface hairline"
    >
      <header className="flex flex-wrap items-center gap-2 px-3 py-2">
        <ShieldCheckIcon size={15} weight="fill" aria-hidden className="text-unknown" />
        <h3 className="text-base font-semibold text-ink">No answer given</h3>
        <Pill tone="unknown">{ABSTENTION_LABEL[abstention.reason]}</Pill>
      </header>

      <div className="px-3 py-3">
        <p className="max-w-[68ch] text-md leading-relaxed text-ink">
          <GroundedText text={abstention.message} facts={facts} />
        </p>
      </div>

      <div className="grid gap-x-6 gap-y-3 px-3 py-3 sm:grid-cols-2">
        {abstention.missing.length > 0 ? (
          <div>
            <Eyebrow>What was missing</Eyebrow>
            <ul className="mt-1.5 space-y-1">
              {abstention.missing.map((item) => (
                <li key={item} className="flex gap-2 text-base text-ink-2">
                  <span
                    aria-hidden
                    className="mt-2 h-px w-2.5 shrink-0 bg-line-strong"
                  />
                  <span>
                    <GroundedText text={item} facts={facts} />
                  </span>
                </li>
              ))}
            </ul>
          </div>
        ) : null}

        {abstention.did_establish.length > 0 ? (
          <div>
            <Eyebrow>What was established anyway</Eyebrow>
            <ul className="mt-1.5 space-y-1">
              {abstention.did_establish.map((item) => (
                <li key={item} className="flex gap-2 text-base text-ink-2">
                  <span
                    aria-hidden
                    className="mt-1.5 h-1.5 w-1.5 shrink-0 rounded-full bg-pass"
                  />
                  <span>
                    <GroundedText text={item} facts={facts} />
                  </span>
                </li>
              ))}
            </ul>
          </div>
        ) : null}
      </div>

      {abstention.suggestions.length > 0 ? (
        <div className="px-3 py-3">
          <Eyebrow>Try instead</Eyebrow>
          <ul className="mt-1.5 flex flex-wrap gap-1.5">
            {abstention.suggestions.map((suggestion) => (
              <li key={suggestion}>
                <button
                  type="button"
                  onClick={() => onAsk?.(suggestion)}
                  disabled={!onAsk}
                  className="group inline-flex items-center gap-1.5 rounded-sm bg-inset px-2 py-1 text-base text-ink-2 transition-colors duration-100 hover:bg-hover hover:text-ink disabled:cursor-default disabled:opacity-70"
                >
                  {suggestion}
                  {onAsk ? (
                    <ArrowRightIcon
                      size={11}
                      weight="bold"
                      aria-hidden
                      className="text-ink-3 transition-transform duration-150 group-hover:translate-x-0.5"
                    />
                  ) : null}
                </button>
              </li>
            ))}
          </ul>
        </div>
      ) : null}
    </section>
  );
}

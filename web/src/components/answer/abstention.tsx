"use client";

/**
 * A refusal, rendered as a result.
 *
 * This is deliberately not an error state. No red, no warning triangle, no
 * apology. A system that says "I cannot answer that reliably" is doing the
 * right thing, and the card is designed to read that way: calm ground, the
 * reason named, what was missing, what was established anyway, and the
 * questions that would work instead.
 *
 * A GREETING IS NOT A REFUSAL and does not get the refusal's chrome. "Hey"
 * came back under a heading reading "No answer given" next to an empty status
 * pill, which is the product telling its first time user it has failed before
 * they have asked it anything. Nothing is missing from a greeting: the
 * controller has not asked for anything yet. It gets the product's name, a
 * capability statement and three ways in.
 */

import { ChatCircleDotsIcon, ShieldCheckIcon } from "@phosphor-icons/react/dist/ssr";

import type { Abstention, Fact } from "@/lib/contracts";
import { ABSTENTION_LABEL } from "@/lib/format";
import { GroundedText } from "@/components/answer/grounded-prose";
import { SuggestionList } from "@/components/answer/suggestions";
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
  const greeting = abstention.reason === "greeting";

  return (
    <section
      aria-label={greeting ? "Welcome" : "The advisor declined to answer"}
      className="rounded-md pl-3.5 brand-edge"
    >
      <header className="flex flex-wrap items-center gap-2 px-3 py-2">
        {greeting ? (
          <ChatCircleDotsIcon
            size={15}
            weight="fill"
            aria-hidden
            className="text-accent"
          />
        ) : (
          <ShieldCheckIcon
            size={15}
            weight="fill"
            aria-hidden
            className="text-unknown"
          />
        )}
        <h3 className="text-base font-semibold text-ink">
          {greeting ? "Extroc" : "No answer given"}
        </h3>
        {greeting ? null : (
          <Pill tone="unknown">{ABSTENTION_LABEL[abstention.reason]}</Pill>
        )}
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
        <div className="px-3 pt-1 pb-3">
          <SuggestionList
            label={greeting ? "Try asking" : "Try instead"}
            questions={abstention.suggestions}
            onAsk={onAsk}
          />
        </div>
      ) : null}
    </section>
  );
}

"use client";

/**
 * Prose with every attested figure linked to its Fact.
 *
 * The linking is done by `lib/fact-link.ts`, which matches surface forms of
 * values the API supplied. Anything it cannot attest is rendered as plain
 * text, which is the correct outcome: an unlinked number in a verified answer
 * means the guard let a word through, not that the UI failed.
 */

import { Fragment } from "react";

import type { Fact } from "@/lib/contracts";
import { linkFacts } from "@/lib/fact-link";
import { FactChip } from "@/components/evidence/fact-chip";
import { cx } from "@/components/ui/tone";

export function GroundedProse({
  text,
  facts,
  className,
}: {
  text: string;
  facts: Fact[];
  className?: string;
}) {
  const paragraphs = text.split(/\n{2,}/).filter((p) => p.trim().length > 0);

  return (
    <div className={cx("space-y-3 text-md leading-relaxed text-ink", className)}>
      {paragraphs.map((paragraph, index) => (
        <p key={index} className="max-w-[68ch]">
          <GroundedText text={paragraph} facts={facts} />
        </p>
      ))}
    </div>
  );
}

/** Inline variant, for list items and card copy. */
export function GroundedText({ text, facts }: { text: string; facts: Fact[] }) {
  const segments = linkFacts(text, facts);
  return (
    <>
      {segments.map((segment, index) =>
        segment.factKey ? (
          <FactChip key={index} factKey={segment.factKey}>
            {segment.text}
          </FactChip>
        ) : (
          <Fragment key={index}>{segment.text}</Fragment>
        ),
      )}
    </>
  );
}

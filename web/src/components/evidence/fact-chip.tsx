"use client";

/**
 * A figure inside prose, linked to the Fact that attests it.
 *
 * Hover or keyboard focus highlights the matching row in the evidence drawer
 * and opens a popover carrying the provenance and, for a computed fact, the
 * arithmetic. Clicking pins it and opens the drawer.
 *
 * THE POPOVER BELONGS TO THE CHIP UNDER THE CURSOR, NOT TO THE FACT. Shared
 * state was keyed by fact, and a crew id appears eight times in a ranked
 * answer, so hovering one `C-2210` lit all eight and opened eight tooltips at
 * once, most of them over text somebody was reading. Which fact is active is
 * still shared, because that is what highlights the row in the evidence
 * drawer and that genuinely is about the fact. Which chip is SHOWING is
 * local, because that is about the cursor.
 *
 * Rendered as a real button so it is reachable by keyboard and announced as
 * interactive. The underline is dotted rather than solid so a linked figure
 * reads as citable rather than as a hyperlink to somewhere else.
 */

import { useState } from "react";

import { useOptionalFacts } from "@/components/evidence/fact-context";
import { cx } from "@/components/ui/tone";
import { factValue, PROVENANCE_LABEL } from "@/lib/format";
import type { Provenance } from "@/lib/contracts";

const PROV_DOT: Record<Provenance, string> = {
  dataset: "bg-ink-3",
  computed: "bg-accent",
  assumed: "bg-caution",
};

export function FactChip({
  factKey,
  children,
}: {
  factKey: string;
  children: string;
}) {
  const context = useOptionalFacts();
  const [showing, setShowing] = useState(false);
  const fact = context?.facts.get(factKey);

  if (!context || !fact) {
    return <>{children}</>;
  }

  // Tinted whenever this fact is active anywhere, so the link between a
  // figure and its evidence row is still visible. Only the chip actually
  // under the cursor puts a panel on top of the page.
  const lit = context.active === factKey || context.pinned === factKey;
  const open = showing || context.pinned === factKey;

  return (
    <span className="relative inline-block">
      <button
        type="button"
        data-fact={factKey}
        data-fact-ui=""
        onMouseEnter={() => {
          setShowing(true);
          context.setActive(factKey);
        }}
        onMouseLeave={() => {
          setShowing(false);
          context.setActive(null);
        }}
        onFocus={() => {
          setShowing(true);
          context.setActive(factKey);
        }}
        onBlur={() => {
          setShowing(false);
          context.setActive(null);
        }}
        onClick={() => context.pin(factKey)}
        aria-label={`${fact.label}: ${factValue(fact.value, fact.unit)}. ${PROVENANCE_LABEL[fact.provenance]}. Show in evidence.`}
        className={cx(
          "num rounded-xs px-0.5 underline decoration-dotted decoration-1 underline-offset-[3px] transition-colors duration-100",
          lit
            ? "bg-accent-tint text-accent decoration-accent"
            : "text-ink decoration-ink-3 hover:bg-hover",
        )}
      >
        {children}
      </button>

      {open ? (
        <span
          role="tooltip"
          data-fact-ui=""
          className="anim-fade-up pointer-events-none absolute bottom-[calc(100%+6px)] left-0 z-40 block w-72 rounded-md bg-surface p-2.5 text-left shadow-[var(--shadow-pop)] hairline-strong"
        >
          <span className="flex items-center gap-1.5">
            <span
              aria-hidden
              className={cx("h-1.5 w-1.5 rounded-full", PROV_DOT[fact.provenance])}
            />
            <span className="label-micro">{PROVENANCE_LABEL[fact.provenance]}</span>
          </span>
          <span className="mt-1 block text-base font-medium text-ink">
            {fact.label}
          </span>
          <span className="num mt-0.5 block text-lg text-ink">
            {factValue(fact.value, fact.unit)}
          </span>
          {fact.derivation ? (
            <span className="mono mt-1.5 block rounded-sm bg-inset p-2 text-xs leading-relaxed break-words text-ink-2">
              {fact.derivation}
            </span>
          ) : null}
          <span className="num mt-1.5 block truncate text-2xs text-ink-3">
            {fact.source}
          </span>
        </span>
      ) : null}
    </span>
  );
}

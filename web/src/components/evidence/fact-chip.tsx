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
 * interactive.
 *
 * WEIGHT, NOT A RULE UNDER THE WORD. Every attested figure used to carry a
 * dotted underline, which was chosen to read as "citable" rather than as a
 * link. At the density this product actually hits, a sentence naming two
 * crew, a pairing, three figures and a rule id, that is six dotted rules in
 * one line and the paragraph turns into a page of struck-through text.
 * Setting the figure in semibold does the same job better: a controller
 * scanning for a quantity finds it faster, because weight is what the eye
 * picks out of prose, and nothing is drawn through the words.
 *
 * The underline is kept for hover and for the lit state, where it stops
 * being decoration and becomes feedback: it appears exactly when the figure
 * is the one being interrogated.
 *
 * THE PANEL IS IN A PORTAL, and it has to be. Absolutely positioned inside
 * the prose it was clipped in two different ways at once: the scroll area is
 * an `overflow` container, so a panel opening above a figure near the top of
 * the viewport was cut off at the scroll edge, and several of the cards a
 * figure can appear inside (`DataTable`, the option cards, anything with
 * `rounded-md overflow-hidden`) clip their own children by construction. No
 * z-index fixes either case: an ancestor that clips wins over any stacking
 * order a descendant asks for. Rendering into `document.body` with fixed
 * coordinates measured off the trigger takes the panel out of every one of
 * those boxes, and is the only version of this that cannot be broken by a
 * container somebody adds later.
 */

import { useCallback, useEffect, useLayoutEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";

import { useOptionalFacts } from "@/components/evidence/fact-context";
import { cx } from "@/components/ui/tone";
import { factValue, PROVENANCE_LABEL } from "@/lib/format";
import type { Provenance } from "@/lib/contracts";

/**
 * `useLayoutEffect` on the client, `useEffect` on the server.
 *
 * This component renders during SSR, and React warns about a layout effect
 * there because it can never run before a paint that is not happening. The
 * measurement genuinely does want to be pre paint on the client, so the hook
 * is swapped rather than downgraded for both.
 */
const useIsomorphicLayoutEffect =
  typeof window !== "undefined" ? useLayoutEffect : useEffect;

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
  const trigger = useRef<HTMLButtonElement>(null);
  const [at, setAt] = useState<Placement | null>(null);
  const fact = context?.facts.get(factKey);

  const open = showing || context?.pinned === factKey;

  const place = useCallback(() => {
    const node = trigger.current;
    if (!node) return;
    setAt(placeFor(node.getBoundingClientRect()));
  }, []);

  // Measured before paint, so the panel never shows for a frame at the wrong
  // coordinates and jumps.
  useIsomorphicLayoutEffect(() => {
    if (open) place();
    else setAt(null);
  }, [open, place]);

  // A PINNED PANEL OUTLIVES THE GESTURE THAT OPENED IT, so it has to keep up
  // with the page under it. Hover panels close long before any of this
  // matters; pinned ones would otherwise sit at coordinates the figure left
  // behind on the next scroll. `capture` catches the console's own scroll
  // container, which does not bubble a scroll event to the window.
  useEffect(() => {
    if (!open) return;
    const onMove = () => place();
    window.addEventListener("scroll", onMove, true);
    window.addEventListener("resize", onMove);
    return () => {
      window.removeEventListener("scroll", onMove, true);
      window.removeEventListener("resize", onMove);
    };
  }, [open, place]);

  if (!context || !fact) {
    return <>{children}</>;
  }

  // Tinted whenever this fact is active anywhere, so the link between a
  // figure and its evidence row is still visible. Only the chip actually
  // under the cursor puts a panel on top of the page.
  const lit = context.active === factKey || context.pinned === factKey;

  return (
    <span className="relative inline-block">
      <button
        ref={trigger}
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
          "num rounded-xs px-0.5 font-semibold transition-colors duration-100",
          "decoration-dotted decoration-1 underline-offset-[3px] hover:underline",
          lit
            ? "bg-accent-tint text-accent underline decoration-accent"
            : "text-ink decoration-ink-3 hover:bg-hover",
        )}
      >
        {children}
      </button>

      {open && at
        ? createPortal(
        <span
          role="tooltip"
          data-fact-ui=""
          style={{
            position: "fixed",
            left: at.left,
            top: at.top,
            bottom: at.bottom,
            width: PANEL_WIDTH,
          }}
          className="anim-fade-up pointer-events-none z-50 block rounded-md bg-surface p-2.5 text-left shadow-[var(--shadow-pop)] hairline-strong"
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
        </span>,
        document.body,
      )
        : null}
    </span>
  );
}

/* -------------------------------------------------------------- placing */

const PANEL_WIDTH = 288;
/** Enough room for the panel plus its shadow, before it would touch an edge. */
const EDGE = 10;
/** Roughly the tallest the panel gets, with a long derivation in it. */
const PANEL_MAX_HEIGHT = 190;

interface Placement {
  left: number;
  top?: number;
  bottom?: number;
}

/**
 * Where to put the panel, in viewport coordinates.
 *
 * Above the figure when there is room, below it when there is not, which is
 * what keeps a figure in the first line of an answer readable. Clamped
 * horizontally so a figure at the right edge of a wide table does not open a
 * panel half off the screen.
 *
 * The upward case is anchored by `bottom` rather than by a `top` derived
 * from an assumed height. The panel is as tall as the derivation inside it,
 * which is not known here, and pinning the wrong edge would leave a short
 * panel floating a gap above the figure it belongs to. `PANEL_MAX_HEIGHT` is
 * only ever used to ask whether there is room, never to place anything.
 */
function placeFor(rect: DOMRect): Placement {
  const left = Math.min(
    Math.max(EDGE, rect.left),
    window.innerWidth - PANEL_WIDTH - EDGE,
  );
  return rect.top >= PANEL_MAX_HEIGHT + EDGE
    ? { left, bottom: window.innerHeight - rect.top + 6 }
    : { left, top: rect.bottom + 6 };
}

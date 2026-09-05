"use client";

/**
 * Charts, under the same rule as everything else on the page.
 *
 * THE ONE THING TO UNDERSTAND BEFORE EDITING THIS FILE:
 *
 *   A bar's LENGTH is a drawing decision. A bar's LABEL is a claim.
 *
 * Geometry is a view over numbers the API supplied, in exactly the sense that
 * `DataTable`'s sorting is a view over rows the API supplied: it reorders and
 * rescales, it never produces a figure. So computing `observed / limit` to
 * decide how wide to paint a rectangle is allowed, because the ratio is
 * consumed by the compositor and never reaches the reader.
 *
 * Every number a reader can actually see is a different matter. It has to be
 * a value a tool put in the payload, printed through `lib/format`. That is
 * why there is not a single percentage on any of these charts: no tool emits
 * one, so nothing here may display one. A "68% of limit" caption would be a
 * figure this component invented, which is the one thing the whole submission
 * exists to prevent, and no amount of it being obviously correct arithmetic
 * would make it attested.
 *
 * The same rule kills the other tempting addition: a total under a set of
 * bars. `CostBars` prints `total_inr` because the costing engine computed it
 * and put it in the payload. It must never sum `line_items` itself, even
 * though the sum would agree, because then the total on screen would be the
 * browser's opinion rather than the engine's result.
 *
 * PAIRING IS THE PAYLOAD'S JOB, NOT THIS FILE'S. `LimitBar` takes an observed
 * and a limit that already arrived paired, which is why it is fed from
 * `RuleTrace` (`observed`, `limit`, `margin` on one record) and never from
 * two loose `Fact`s that happen to have related keys. Guessing that
 * `C-1042.duty_limit_7d` is the ceiling for `C-1042.2026-09-14.duty_7d`
 * because of how the strings are shaped would be the UI inferring a
 * relationship nobody computed. Bare facts get `FigureTiles`, which states
 * each value on its own and claims no relationship between them.
 */

import type { CostBreakdown, Fact, RuleUnit } from "@/lib/contracts";
import type { Tone } from "@/lib/format";
import { factValue, inr, withUnit } from "@/lib/format";
import { FactChip } from "@/components/evidence/fact-chip";
import { cx, TONE } from "@/components/ui/tone";

/* ------------------------------------------------------------- limit bar */

/**
 * Usage against a ceiling, with the ceiling drawn as a line rather than as
 * the end of the track.
 *
 * A breach is the case that has to read instantly, and a bar that simply
 * fills up cannot show one: at 61 hours against 60 it looks the same as at
 * 60. So the track is scaled past the limit whenever the observed value
 * exceeds it, the limit keeps its own marked position, and the overshoot is
 * painted in the breach tone beyond that mark. The bar is then literally the
 * shape of the sentence "over by 1.33h".
 */
export function LimitBar({
  observed,
  limit,
  unit,
  tone,
  marginHuman,
  label,
}: {
  observed: number;
  limit: number;
  unit?: RuleUnit | null;
  tone: Tone;
  /** The engine's own words for the margin, e.g. "over by 1.33h". */
  marginHuman?: string | null;
  label: string;
}) {
  // Scale so the limit sits at 72% of the track when nothing has overrun it,
  // which leaves visible headroom to the right and stops a compliant bar
  // from looking like it is about to tip over. An overrun rescales to fit.
  const span = observed > limit ? observed * 1.06 : limit / 0.72;
  const limitAt = span > 0 ? (limit / span) * 100 : 0;
  const fillTo = span > 0 ? Math.min(100, (observed / span) * 100) : 0;
  const over = observed > limit;

  return (
    <figure
      className="mt-2"
      role="img"
      aria-label={`${label}. ${withUnit(observed, unit)} against a limit of ${withUnit(limit, unit)}.`}
    >
      <div className="relative h-7 w-full overflow-hidden rounded-sm bg-inset">
        {/* Everything up to the limit, in the verdict's tone. When the value
            has overrun, this stops at the limit line and the overshoot is
            drawn separately, so the two read as different quantities rather
            than as one long bar. */}
        <span
          aria-hidden
          className={cx(
            "absolute inset-y-0 left-0 transition-[width] duration-500 ease-out-quint",
            over ? TONE.na.fill : TONE[tone].fill,
            "opacity-90",
          )}
          style={{ width: `${over ? limitAt : fillTo}%` }}
        />
        {over ? (
          <span
            aria-hidden
            className={cx(
              "absolute inset-y-0 transition-[width] duration-500 ease-out-quint",
              TONE.breach.fill,
            )}
            style={{ left: `${limitAt}%`, width: `${fillTo - limitAt}%` }}
          />
        ) : null}

        {/* The ceiling itself. A full height rule, not a tick, because it is
            the thing the bar is being judged against. */}
        <span
          aria-hidden
          className="absolute inset-y-0 w-px bg-ink"
          style={{ left: `${limitAt}%` }}
        />
      </div>

      <figcaption className="mt-1.5 flex flex-wrap items-baseline gap-x-3 gap-y-0.5">
        <span className="num text-base font-semibold text-ink">
          {withUnit(observed, unit)}
        </span>
        <span className="text-xs text-ink-3">
          of {withUnit(limit, unit)} allowed
        </span>
        {marginHuman ? (
          <span
            className={cx(
              "num ml-auto text-xs font-medium",
              over ? TONE.breach.text : TONE[tone].text,
            )}
          >
            {marginHuman}
          </span>
        ) : null}
      </figcaption>
    </figure>
  );
}

/* ------------------------------------------------------------ cost bars */

/**
 * A cost breakdown as proportional bars.
 *
 * The table this replaces was correct and unreadable: four rows of rupee
 * amounts in a column, where the only question anyone actually has ("what is
 * driving this number?") took arithmetic to answer. Bars answer it without
 * any, and the basis string stays on every row so the reader can still check
 * the multiplication that produced each figure.
 *
 * The total is printed from `total_inr`. It is not a sum of the rows above
 * it. See the file header.
 */
export function CostBars({ cost }: { cost: CostBreakdown }) {
  if (cost.line_items.length === 0) return null;

  // A BAR IS ONLY WORTH DRAWING WHEN THERE IS SOMETHING TO COMPARE IT WITH.
  // Most cover options cost exactly one thing, and a single bar is full width
  // whatever the number is, so it says nothing and still takes a row. Below
  // two lines this degrades to the plain statement it should have been.
  const comparable = cost.line_items.length > 1;

  // Scale against the largest line, so the biggest driver fills the track and
  // everything else is read against it. Against the total instead, a cost
  // split four ways would draw four stubs and show nothing.
  const widest = Math.max(...cost.line_items.map((line) => Math.abs(line.amount_inr)));

  // The engine's total, never a sum of the rows. Printing it under a single
  // line that already carries the same figure is the same number twice, so
  // the row is dropped when it would only repeat. Comparing two supplied
  // values to decide what to draw is a layout choice, not arithmetic: no
  // third number is produced either way.
  const totalRepeats =
    !comparable && cost.line_items[0].amount_inr === cost.total_inr;

  return (
    <div>
      <ul className={comparable ? "space-y-2.5" : "space-y-1.5"}>
        {cost.line_items.map((line) => {
          const width = widest > 0 ? (Math.abs(line.amount_inr) / widest) * 100 : 0;
          return (
            <li key={line.label}>
              <div className="flex items-baseline justify-between gap-3">
                <span className="text-base text-ink-2">{line.label}</span>
                <span className="num shrink-0 text-base font-semibold text-ink">
                  {inr(line.amount_inr)}
                </span>
              </div>
              {comparable ? (
                <div className="mt-1 h-1.5 w-full overflow-hidden rounded-full bg-inset">
                  <span
                    aria-hidden
                    className="block h-full rounded-full bg-[image:var(--grad-brand)] transition-[width] duration-500 ease-out-quint"
                    style={{ width: `${Math.max(2, width)}%` }}
                  />
                </div>
              ) : null}
              <p className="num mt-1 text-2xs text-ink-3">
                {line.basis}
                {line.rule_ref ? (
                  <span className="ml-1 opacity-70">({line.rule_ref})</span>
                ) : null}
              </p>
            </li>
          );
        })}
      </ul>

      {totalRepeats ? null : (
        <div className="mt-3 flex items-baseline justify-between gap-3 border-t border-line-soft pt-2">
          <span className="text-base font-medium text-ink">Total</span>
          <span className="num text-lg font-semibold text-ink">
            {inr(cost.total_inr)}
          </span>
        </div>
      )}
      {cost.note ? <p className="mt-1.5 text-xs text-ink-3">{cost.note}</p> : null}
    </div>
  );
}

/* --------------------------------------------------------- figure tiles */

/**
 * Loose facts, each stated on its own.
 *
 * This is the honest rendering for a payload that carries figures without
 * carrying any relationship between them. It deliberately draws no bar and no
 * ratio: `duty_7d` and `duty_limit_7d` may look like a value and its ceiling
 * to anybody reading the key names, but no tool said they were, and a chart
 * asserting it would be the UI answering a question instead of showing one.
 *
 * The value is a `FactChip`, so the derivation and provenance are one hover
 * away, exactly as they are for the same figure inside the prose.
 */
export function FigureTiles({ facts }: { facts: Fact[] }) {
  if (facts.length === 0) return null;

  return (
    <dl className="grid grid-cols-2 gap-px overflow-hidden rounded-md bg-line-soft sm:grid-cols-3">
      {facts.map((fact) => (
        <div key={fact.key} className="flex flex-col justify-between bg-surface px-3 py-2.5">
          {/* Two lines, then clip. These labels are written for an evidence
              row ("Headroom under RULE-DUTY-02") and are longer than a tile
              is wide, and an ellipsis after three words tells the reader
              nothing at all. */}
          <dt className="label-micro line-clamp-2 leading-tight" title={fact.label}>
            {fact.label}
          </dt>
          <dd className="mt-1.5 text-lg leading-none text-ink">
            <FactChip factKey={fact.key}>
              {factValue(fact.value, fact.unit)}
            </FactChip>
          </dd>
        </div>
      ))}
    </dl>
  );
}

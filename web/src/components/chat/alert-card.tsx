"use client";

/**
 * The proactive alert card, on the empty console.
 *
 * A controller does not arrive with a question. They arrive with a roster, and
 * the useful system is the one that has already looked. So this sits above the
 * sample questions, before anything has been typed, and answers "what is
 * already wrong" without being asked.
 *
 * Produced entirely by deterministic code (`crewops.ops.alerting`). No model
 * decides what appears here or how it is worded, which is why it renders with
 * the API key unset.
 *
 * TWO THINGS HERE ARE LOAD BEARING AND LOOK LIKE THEY COULD BE CUT.
 *
 * 1. **The limit line renders even when nothing crossed a threshold.** The
 *    shipped roster has no duty or flight hour breach in a 48 hour horizon, so
 *    the honest report is "checked, nothing crossing, here is the closest
 *    margin". A card that showed only the certification alerts would let a
 *    controller assume the duty clocks had not been looked at. "No alerts" and
 *    "the scan did not run" must never look the same.
 *
 * 2. **`projection.arithmetic` is rendered verbatim.** It is not recomposed
 *    from `banked_hours` and `committed_hours` in JSX. Recomposing it here
 *    would put the arithmetic back outside the kernel that owns it, which is
 *    the exact failure the whole hybrid design exists to prevent.
 *
 * The card fails quiet. If the scan cannot be reached it renders nothing at
 * all rather than an error, because this is an unsolicited panel on a screen
 * whose actual job is the composer below it: a controller who came here to
 * type a question should not be met with a broken widget.
 *
 * IT STARTS COLLAPSED. This screen's job is the composer, and an unsolicited
 * panel that opens itself to full height pushes the six sample questions down
 * the page to announce, most mornings, that there is nothing urgent. So the
 * resting state is one row: the alert sign, the count, and the severity. That
 * row still has to carry enough for a controller to decide whether to open it,
 * which is why the summary names the critical count rather than saying
 * "alerts".
 */

import { useEffect, useId, useState } from "react";
import Link from "next/link";
import {
  ArrowRightIcon,
  CaretRightIcon,
  ShieldCheckIcon,
  WarningOctagonIcon,
} from "@phosphor-icons/react/dist/ssr";

import type { AlertScan, ProactiveAlert } from "@/lib/contracts";
import { api } from "@/lib/api";
import { grouped, plural, SEVERITY_LABEL, SEVERITY_TONE } from "@/lib/format";
import { Pill, Token } from "@/components/ui/primitives";
import { cx, TONE } from "@/components/ui/tone";

/**
 * How many alerts get a row of their own.
 *
 * Three. This card sits above six question cards on a screen whose purpose is
 * the composer, so it has to summarise rather than exhaust. The rest are
 * counted in the footer and reachable in one click on the brief.
 */
const SHOWN = 3;

export function AlertCard({ onAsk }: { onAsk: (question: string) => void }) {
  const [scan, setScan] = useState<AlertScan | null>(null);
  const [open, setOpen] = useState(false);
  const panelId = useId();

  useEffect(() => {
    let cancelled = false;
    api
      .alerts()
      .then((value) => {
        if (!cancelled) setScan(value);
      })
      // Deliberately silent. See the note at the top of the file.
      .catch(() => undefined);
    return () => {
      cancelled = true;
    };
  }, []);

  if (scan === null) return null;

  const shown = scan.alerts.slice(0, SHOWN);
  const rest = scan.alerts.length - shown.length;
  const critical = scan.counts.critical ?? 0;

  // The tightest margin found on any limit rule. This is the evidence that the
  // duty and flight clocks were examined, and it is the whole reason
  // `closest_approaches` exists on the payload.
  const tightest = scan.closest_approaches
    .filter(
      (alert) => alert.projection !== null && alert.projection !== undefined,
    )
    .sort(
      (a, b) =>
        (a.projection?.margin_hours ?? 0) - (b.projection?.margin_hours ?? 0),
    )[0];

  const breaching = scan.alerts.length > 0;

  return (
    <section
      aria-label="Proactive alerts"
      className="anim-fade-up rounded-md bg-surface hairline"
    >
      {/* The resting state. One row, and the only thing on screen until the
          controller asks for the rest. */}
      <button
        type="button"
        aria-expanded={open}
        aria-controls={panelId}
        onClick={() => setOpen((value) => !value)}
        className="flex w-full cursor-pointer flex-wrap items-center gap-x-2.5 gap-y-1.5 rounded-md px-4 py-3 text-left transition-colors duration-150 hover:bg-hover"
      >
        <span
          aria-hidden
          className={cx(
            "flex size-7 shrink-0 items-center justify-center rounded-md",
            breaching ? "bg-breach-tint text-breach" : "bg-pass-tint text-pass",
          )}
        >
          {breaching ? (
            <WarningOctagonIcon size={15} weight="bold" />
          ) : (
            <ShieldCheckIcon size={15} weight="bold" />
          )}
        </span>

        <h3 className="min-w-0 flex-1 text-base font-semibold text-ink">
          Before you ask
          <span className="ml-2 font-normal text-ink-2">
            {breaching
              ? `${plural(scan.alerts.length, "item")} in the next ${scan.horizon_hours} hours`
              : `nothing to raise in the next ${scan.horizon_hours} hours`}
          </span>
        </h3>

        {critical > 0 ? <Pill tone="breach">{critical} critical</Pill> : null}

        <CaretRightIcon
          size={13}
          weight="bold"
          aria-hidden
          className={cx(
            "shrink-0 text-ink-3 transition-transform duration-200 ease-out-quint",
            open && "rotate-90",
          )}
        />
      </button>

      {/* `hidden` rather than an unmount, matching `Disclosure`: the scan is
          already fetched, so there is nothing to reload on the second open. */}
      <div id={panelId} hidden={!open} className="anim-fade-up pb-1">
        {shown.length > 0 ? (
          <ul className="space-y-1.5 px-4 pb-1">
            {shown.map((alert) => (
              <AlertRow key={alert.alert_id} alert={alert} onAsk={onAsk} />
            ))}
          </ul>
        ) : null}

        {/* The limit position. Present on every scan, breach or not. */}
        {tightest?.projection ? (
          <div className="mx-4 mt-2 rounded-sm bg-inset px-3 py-2">
            <p className="text-xs leading-relaxed text-ink-2">
              <span className="font-semibold text-ink">
                No duty or flight hour breach
              </span>{" "}
              in the next {scan.horizon_hours} hours. Closest is{" "}
              <Token>{tightest.crew_id}</Token> at{" "}
              <span className="num font-semibold text-ink">
                {tightest.projection.margin_hours.toFixed(2)}h
              </span>{" "}
              spare under <Token>{tightest.projection.rule_id}</Token>.
            </p>
            {/* Verbatim, never recomposed. */}
            <p className="mono mt-1 text-2xs leading-relaxed text-ink-3">
              {tightest.projection.arithmetic}
            </p>
          </div>
        ) : null}

        <footer className="flex flex-wrap items-center gap-x-3 gap-y-1 px-4 pt-2.5 pb-3">
          <p className="min-w-0 flex-1 text-2xs text-ink-3">
            Scanned {grouped(scan.scanned.crew ?? 0)} crew and{" "}
            {grouped(scan.scanned.duties_in_horizon ?? 0)} rostered duties.
            Deterministic: no model decides what appears here.
          </p>
          <Link
            href="/brief"
            className="group inline-flex shrink-0 items-center gap-1.5 text-xs font-medium text-accent"
          >
            {rest > 0 ? `${rest} more on the brief` : "Open the brief"}
            <ArrowRightIcon
              size={11}
              weight="bold"
              aria-hidden
              className="transition-transform duration-150 group-hover:translate-x-0.5"
            />
          </Link>
        </footer>
      </div>
    </section>
  );
}

/**
 * One alert.
 *
 * The whole row is the button, because the alert and the question that
 * investigates it are the same thought: a controller who reads "C-5417 is
 * rostered after their training lapses" wants to open that, not hunt for a
 * separate link.
 */
function AlertRow({
  alert,
  onAsk,
}: {
  alert: ProactiveAlert;
  onAsk: (question: string) => void;
}) {
  const tone = SEVERITY_TONE[alert.severity];
  return (
    <li>
      <button
        type="button"
        onClick={() => onAsk(alert.suggested_question)}
        title={alert.detail}
        className={cx(
          "group flex w-full cursor-pointer items-start gap-2.5 rounded-sm bg-inset px-3 py-2 text-left transition-[box-shadow,transform] duration-200 ease-out-quint hover:-translate-y-px hover:shadow-panel",
          TONE[tone].edge,
        )}
      >
        <Pill tone={tone} className="mt-0.5">
          {SEVERITY_LABEL[alert.severity]}
        </Pill>

        <span className="min-w-0 flex-1">
          <span className="block text-base leading-snug font-medium text-ink">
            {alert.title}
          </span>
          <span className="mt-0.5 flex flex-wrap items-center gap-x-2 gap-y-0.5 text-2xs text-ink-3">
            <Token>{alert.rule_id}</Token>
            <span>{alert.rank}</span>
            {alert.seats_at_risk > 0 ? (
              <span className="num">
                {grouped(alert.seats_at_risk)} seats exposed
              </span>
            ) : null}
          </span>
        </span>

        <ArrowRightIcon
          size={12}
          weight="bold"
          aria-hidden
          className="mt-1 shrink-0 text-ink-3 transition-transform duration-150 group-hover:translate-x-0.5"
        />
      </button>
    </li>
  );
}

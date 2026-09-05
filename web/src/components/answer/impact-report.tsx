"use client";

/**
 * Tier 2: what breaks, and what breaks next.
 *
 * The uncrewed legs are the obvious part and are shown as a flight strip. The
 * downstream risks are the reason the system exists, so they are given equal
 * weight and sorted by severity rather than by discovery order.
 */

import { ArrowRightIcon } from "@phosphor-icons/react/dist/ssr";

import type { DownstreamRisk, FlightRef, ImpactReport } from "@/lib/contracts";
import {
  clock,
  grouped,
  SEVERITY_LABEL,
  SEVERITY_ORDER,
  SEVERITY_TONE,
  shortDate,
} from "@/lib/format";
import { FlightTimeline } from "@/components/answer/charts";
import { GroundedText } from "@/components/answer/grounded-prose";
import { Pill, Token } from "@/components/ui/primitives";
import { cx, TONE } from "@/components/ui/tone";

export function ImpactReportView({ impact }: { impact: ImpactReport }) {
  const risks = [...impact.downstream_risks].sort(
    (a, b) => SEVERITY_ORDER[a.severity] - SEVERITY_ORDER[b.severity],
  );

  return (
    <section className="space-y-3" aria-label="Impact report">
      <div className="grid grid-cols-2 gap-2 sm:grid-cols-4">
        <Metric
          label="Uncrewed legs"
          value={grouped(impact.uncrewed_flights.length)}
          tone={impact.uncrewed_flights.length > 0 ? "breach" : undefined}
        />
        <Metric
          label="Pairings broken"
          value={grouped(impact.pairings_broken.length)}
          detail={impact.pairings_broken.join(", ")}
        />
        <Metric
          label="Passengers"
          value={grouped(impact.passengers_affected)}
          factKey="impact.passengers_affected"
        />
        <Metric
          label="Stations"
          value={grouped(impact.stations_affected.length)}
          detail={impact.stations_affected.join(", ")}
        />
      </div>

      {impact.uncrewed_flights.length > 0 ? (
        <div className="space-y-1.5">
          <SectionHead title="Uncrewed" meta={impact.trigger} />
          {/* The same flights twice, on purpose, and not as decoration. The
              timeline answers "when is the hole in the day", which the rows
              underneath can only answer by reading six pairs of times and
              comparing them; the rows answer "which aircraft, which
              stations, how many aboard", which the timeline cannot show. */}
          <FlightTimeline flights={impact.uncrewed_flights} />
          {/* A gap grid, not a bordered list. The divisions are the ground
              showing between the rows, so there is nothing to keep in sync
              and nothing to clear off the last child. */}
          <ul className="rules">
            {impact.uncrewed_flights.map((flight) => (
              <FlightRow key={flight.flight_no} flight={flight} />
            ))}
          </ul>
        </div>
      ) : null}

      {risks.length > 0 ? (
        <div className="space-y-1.5">
          <SectionHead
            title="Downstream risk"
            meta="The consequences a single day view misses"
          />
          <ul className="rules">
            {risks.map((risk, index) => (
              <RiskRow key={index} risk={risk} facts={impact.facts} />
            ))}
          </ul>
        </div>
      ) : null}
    </section>
  );
}

/** A heading that sits above a block rather than inside a frame on top of it. */
function SectionHead({ title, meta }: { title: string; meta?: string }) {
  return (
    <div className="flex flex-wrap items-baseline gap-x-2 px-0.5">
      <h4 className="text-base font-semibold text-ink">{title}</h4>
      {meta ? <span className="text-xs text-ink-3">{meta}</span> : null}
    </div>
  );
}

function Metric({
  label,
  value,
  detail,
  tone,
  factKey,
}: {
  label: string;
  value: string;
  detail?: string;
  tone?: "breach";
  factKey?: string;
}) {
  return (
    <div className="rounded-md bg-surface px-3.5 py-2.5 hairline">
      <p className="label-micro">{label}</p>
      <p
        className={cx(
          "num mt-0.5 text-2xl leading-none font-semibold",
          tone === "breach" ? "text-breach" : "text-ink",
        )}
        data-fact={factKey}
      >
        {value}
      </p>
      {detail ? (
        <p className="num mt-1 truncate text-xs text-ink-3" title={detail}>
          {detail}
        </p>
      ) : null}
    </div>
  );
}

function FlightRow({ flight }: { flight: FlightRef }) {
  return (
    <li className="flex flex-wrap items-center gap-x-3 gap-y-1 px-3 py-2">
      <Token>{flight.flight_no}</Token>
      <span className="num flex items-center gap-1.5 text-base text-ink">
        {flight.origin}
        <ArrowRightIcon size={11} weight="bold" aria-hidden className="text-ink-3" />
        {flight.destination}
      </span>
      <span className="num text-base text-ink-2">
        {clock(flight.departure)} to {clock(flight.arrival)}
      </span>
      <span className="num text-xs text-ink-3">{shortDate(flight.departure)}</span>
      {flight.aircraft_type ? (
        <span className="num text-xs text-ink-3">{flight.aircraft_type}</span>
      ) : null}
      {flight.passengers !== null && flight.passengers !== undefined ? (
        <span className="num ml-auto text-base text-ink-2">
          {grouped(flight.passengers)} pax
        </span>
      ) : null}
    </li>
  );
}

function RiskRow({
  risk,
  facts,
}: {
  risk: DownstreamRisk;
  facts: ImpactReport["facts"];
}) {
  const tone = SEVERITY_TONE[risk.severity];
  return (
    <li className={cx("flex gap-2.5 px-3 py-2.5", TONE[tone].edge)}>
      <div className="min-w-0 flex-1">
        <div className="flex flex-wrap items-center gap-1.5">
          <Pill tone={tone}>{SEVERITY_LABEL[risk.severity]}</Pill>
          {risk.crew_id ? <Token>{risk.crew_id}</Token> : null}
          {risk.flight_no ? <Token>{risk.flight_no}</Token> : null}
          {risk.pairing_id ? <Token>{risk.pairing_id}</Token> : null}
          {risk.rule_id ? <Token>{risk.rule_id}</Token> : null}
          {risk.duty_date ? (
            <span className="num text-xs text-ink-3">{shortDate(risk.duty_date)}</span>
          ) : null}
        </div>
        <p className="mt-1 max-w-[68ch] text-base leading-relaxed text-ink-2">
          <GroundedText text={risk.detail} facts={facts} />
        </p>
      </div>
    </li>
  );
}


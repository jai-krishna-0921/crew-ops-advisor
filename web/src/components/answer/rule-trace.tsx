"use client";

/**
 * One rule, evaluated, with its working shown.
 *
 * A controller who cannot challenge the reasoning will not trust the answer,
 * so `arithmetic` is not a tooltip or a disclosure: it is on the face of the
 * card, in monospace, with both operands and the limit.
 *
 * A breach is unmissable by construction: a solid left edge, a tinted ground,
 * the verdict word, and the signed margin rendered in the breach colour. Four
 * signals, only one of which is colour.
 */

import {
  CheckCircleIcon,
  MinusCircleIcon,
  QuestionIcon,
  WarningOctagonIcon,
} from "@phosphor-icons/react/dist/ssr";

import type { DayLegality, LegalityReport, RuleTrace, Verdict } from "@/lib/contracts";
import {
  decimal,
  shortDate,
  VERDICT_LABEL,
  VERDICT_TONE,
  withUnit,
} from "@/lib/format";
import { GroundedText } from "@/components/answer/grounded-prose";
import { MarginGauge, Pill, Token } from "@/components/ui/primitives";
import { cx, TONE } from "@/components/ui/tone";

const VERDICT_ICON: Record<Verdict, typeof CheckCircleIcon> = {
  pass: CheckCircleIcon,
  breach: WarningOctagonIcon,
  not_applicable: MinusCircleIcon,
  insufficient_data: QuestionIcon,
};

export function VerdictPill({ verdict }: { verdict: Verdict }) {
  const Icon = VERDICT_ICON[verdict];
  return (
    <Pill tone={VERDICT_TONE[verdict]}>
      <Icon size={11} weight="fill" aria-hidden />
      {VERDICT_LABEL[verdict]}
    </Pill>
  );
}

export function RuleTraceCard({
  trace,
  compact = false,
}: {
  trace: RuleTrace;
  compact?: boolean;
}) {
  const tone = VERDICT_TONE[trace.verdict];
  const breach = trace.verdict === "breach";
  const unknown = trace.verdict === "insufficient_data";

  return (
    <article
      className={cx(
        "rounded-md bg-surface hairline",
        (breach || unknown) && TONE[tone].edge,
        breach && "bg-breach-wash",
      )}
    >
      <div className="flex flex-wrap items-center gap-x-2 gap-y-1 px-2.5 py-2">
        <Token className={breach ? "text-breach" : undefined}>{trace.rule_id}</Token>
        <span className="text-base font-medium text-ink">{trace.title}</span>
        {trace.duty_date ? (
          <span className="num text-xs text-ink-3">{shortDate(trace.duty_date)}</span>
        ) : null}
        <span className="ml-auto">
          <VerdictPill verdict={trace.verdict} />
        </span>
      </div>

      {trace.limit !== null && trace.limit !== undefined ? (
        <div className="grid grid-cols-3 gap-2 border-t border-line-soft px-2.5 py-2">
          <Figure label="Limit" value={withUnit(trace.limit, trace.unit)} />
          <Figure
            label="Observed"
            value={
              trace.observed !== null && trace.observed !== undefined
                ? withUnit(trace.observed, trace.unit)
                : "not established"
            }
            tone={breach ? "breach" : undefined}
          />
          <Figure
            label="Margin"
            value={
              trace.margin_human ??
              (trace.margin !== null && trace.margin !== undefined
                ? `${trace.margin > 0 ? "+" : ""}${decimal(trace.margin)}`
                : "not established")
            }
            tone={breach ? "breach" : trace.verdict === "pass" ? "pass" : undefined}
          />
          {trace.margin !== null && trace.margin !== undefined ? (
            <div className="col-span-3">
              <MarginGauge
                margin={trace.margin}
                limit={trace.limit}
                tone={tone}
                label={`${trace.rule_id}: ${trace.margin_human ?? decimal(trace.margin)}`}
              />
            </div>
          ) : null}
        </div>
      ) : null}

      <div className="border-t border-line-soft px-2.5 py-2">
        <p className="num text-xs leading-relaxed text-ink-2">
          <GroundedText text={trace.arithmetic} facts={trace.inputs} />
        </p>
        {trace.note && !compact ? (
          <p className="mt-1.5 border-l-2 border-line-strong pl-2 text-xs text-ink-3">
            {trace.note}
          </p>
        ) : null}
      </div>
    </article>
  );
}

function Figure({
  label,
  value,
  tone,
}: {
  label: string;
  value: string;
  tone?: "breach" | "pass";
}) {
  return (
    <div>
      <p className="label-micro">{label}</p>
      <p
        className={cx(
          "num mt-0.5 text-base font-medium",
          tone === "breach"
            ? "text-breach"
            : tone === "pass"
              ? "text-pass"
              : "text-ink",
        )}
      >
        {value}
      </p>
    </div>
  );
}

/* --------------------------------------------------------- day grouping */

export function DayLegalityBlock({ day }: { day: DayLegality }) {
  const breaches = day.traces.filter((t) => t.verdict === "breach");
  return (
    <div className="space-y-1.5">
      <div className="flex items-center gap-2">
        <h4 className="num text-base font-semibold text-ink">
          {shortDate(day.duty_date)}
        </h4>
        <VerdictPill verdict={day.verdict} />
        <span className="text-xs text-ink-3">
          {day.traces.length} rules evaluated
          {breaches.length > 0
            ? `, ${breaches.length} breached`
            : ", none breached"}
        </span>
      </div>
      <div className="grid gap-1.5 md:grid-cols-2">
        {day.traces.map((trace, index) => (
          // The index is part of the key because one turn flattens the traces
          // of every candidate into one list, so a rule id and a date together
          // are not unique. Duplicate keys let React drop rows, and a silently
          // missing rule row in a legality view is the worst kind of bug here.
          <RuleTraceCard
            key={`${day.duty_date}-${trace.rule_id}-${index}`}
            trace={trace}
          />
        ))}
      </div>
    </div>
  );
}

export function LegalityReportView({ report }: { report: LegalityReport }) {
  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center gap-2">
        <Token>{report.crew_id}</Token>
        <span className="text-base text-ink-2">on</span>
        <Token>{report.assignment_ref}</Token>
        <VerdictPill verdict={report.overall} />
        {report.per_day.length > 1 ? (
          <span className="text-xs text-ink-3">
            Overall is the worst day, never an average.
          </span>
        ) : null}
      </div>
      {report.per_day.map((day) => (
        <DayLegalityBlock key={day.duty_date} day={day} />
      ))}
    </div>
  );
}

/** The one line a controller reads when scanning a rejected candidate. */
export function firstBreach(report: LegalityReport): RuleTrace | null {
  for (const day of report.per_day) {
    for (const trace of day.traces) {
      if (trace.verdict === "breach") return trace;
    }
  }
  return null;
}

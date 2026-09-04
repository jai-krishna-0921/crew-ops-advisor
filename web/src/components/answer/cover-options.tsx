"use client";

/**
 * Tier 3: ranked cover options, and the candidates that were ruled out.
 *
 * The rejects are not an appendix. A controller trusts a search they can see
 * the shape of, so every excluded candidate carries the RuleTrace that
 * excluded it, on the same footing as the options that survived.
 *
 * Every figure on these cards comes from the payload. The cost total is the
 * one the API computed, and the line items show their basis so the total can
 * be checked without re-deriving it here.
 */

import {
  AirplaneTakeoffIcon,
  ArrowsLeftRightIcon,
  ClockCountdownIcon,
  ProhibitIcon,
  SealCheckIcon,
  UserSwitchIcon,
  XCircleIcon,
} from "@phosphor-icons/react/dist/ssr";

import type { CoverKind, CoverOption, Recommendation } from "@/lib/contracts";
import { inr, joinParts, minutesToClock, plural } from "@/lib/format";
import { GroundedText } from "@/components/answer/grounded-prose";
import {
  firstBreach,
  LegalityReportView,
  RuleTraceCard,
  VerdictPill,
} from "@/components/answer/rule-trace";
import {
  Disclosure,
  Eyebrow,
  Panel,
  PanelHead,
  Pill,
  Token,
} from "@/components/ui/primitives";
import { cx } from "@/components/ui/tone";

const KIND_ICON: Record<CoverKind, typeof AirplaneTakeoffIcon> = {
  reserve: SealCheckIcon,
  reassign: UserSwitchIcon,
  deadhead: AirplaneTakeoffIcon,
  swap: ArrowsLeftRightIcon,
  cancel: ProhibitIcon,
};

const KIND_LABEL: Record<CoverKind, string> = {
  reserve: "Reserve callout",
  reassign: "Reassignment",
  deadhead: "Deadhead",
  swap: "Swap",
  cancel: "Cancellation",
};

export function RecommendationView({
  recommendation,
}: {
  recommendation: Recommendation;
}) {
  const { options, rejected } = recommendation;

  return (
    <section className="space-y-3" aria-label="Cover options">
      <div className="flex flex-wrap items-baseline gap-x-3 gap-y-1">
        <h3 className="text-lg font-semibold text-ink">
          {options.length === 1
            ? "One legal option"
            : `${options.length} legal options`}
        </h3>
        <p className="text-base text-ink-3">
          {plural(recommendation.candidates_evaluated, "candidate")} evaluated,{" "}
          {plural(rejected.length, "excluded", "excluded")}
        </p>
      </div>

      <p className="max-w-[68ch] rounded-md bg-inset px-3 py-2 text-base text-ink-2 hairline">
        <span className="label-micro mr-2 inline">Ranked by</span>
        {recommendation.ranking_basis}
      </p>

      <div className="space-y-2.5">
        {options.map((option) => (
          <CoverOptionCard key={option.crew_id} option={option} />
        ))}
      </div>

      {rejected.length > 0 ? (
        <Disclosure
          summary="Candidates ruled out"
          count={rejected.length}
          tone="breach"
        >
          <p className="mb-2 max-w-[68ch] px-2 text-base text-ink-3">
            Each of these was found, checked against all seven rules and
            excluded. The rule that excluded it is shown, not summarised.
          </p>
          <div className="space-y-2">
            {rejected.map((option) => (
              <RejectedCard key={option.crew_id} option={option} />
            ))}
          </div>
        </Disclosure>
      ) : null}

      {recommendation.notification_draft ? (
        <Panel>
          <PanelHead
            title="Draft callout"
            meta="Deterministic template, filled from computed facts"
          />
          <p className="num px-3 py-2.5 text-base leading-relaxed text-ink-2">
            <GroundedText
              text={recommendation.notification_draft}
              facts={recommendation.facts}
            />
          </p>
        </Panel>
      ) : null}
    </section>
  );
}

export function CoverOptionCard({ option }: { option: CoverOption }) {
  const Icon = KIND_ICON[option.kind];
  const best = option.rank === 1;

  return (
    <article
      className={cx(
        "rounded-md bg-surface",
        best ? "ring-1 ring-accent-line" : "hairline",
      )}
    >
      <header className="flex flex-wrap items-center gap-x-2 gap-y-1.5 border-b border-line-soft px-3 py-2.5">
        <span
          aria-label={`Rank ${option.rank}`}
          className={cx(
            "num flex h-6 w-6 shrink-0 items-center justify-center rounded-sm text-base font-semibold",
            best
              ? "bg-accent text-page"
              : "bg-inset text-ink-2 ring-1 ring-line",
          )}
        >
          {option.rank}
        </span>
        <h4 className="text-lg font-semibold text-ink">
          <GroundedText text={option.action} facts={option.facts} />
        </h4>
        <Pill tone="na">
          <Icon size={11} weight="bold" aria-hidden />
          {KIND_LABEL[option.kind]}
        </Pill>
        <VerdictPill verdict={option.legality.overall} />
        <span className="num ml-auto text-xl font-semibold text-ink">
          {inr(option.cost.total_inr)}
        </span>
      </header>

      <dl className="grid grid-cols-2 gap-x-3 gap-y-2 px-3 py-2.5 sm:grid-cols-4">
        <Stat label="Crew">
          <Token>{option.crew_id}</Token>
          <span className="ml-1.5 text-ink-2">{option.crew_name}</span>
        </Stat>
        <Stat label="Base and rank">
          {joinParts([option.crew_base, option.crew_rank])}
        </Stat>
        <Stat label="Coverage">{option.coverage_summary}</Stat>
        <Stat label="Reachable in">
          {option.reachable && option.reachability_minutes !== null
            ? minutesToClock(option.reachability_minutes ?? null)
            : "not reachable"}
        </Stat>
      </dl>

      {option.delay_minutes > 0 || option.uncovered_flights.length > 0 ? (
        <div className="flex flex-wrap items-center gap-2 border-t border-line-soft px-3 py-2">
          {option.delay_minutes > 0 ? (
            <Pill tone="caution">
              <ClockCountdownIcon size={11} weight="bold" aria-hidden />
              {minutesToClock(option.delay_minutes)} delay
            </Pill>
          ) : null}
          {option.uncovered_flights.length > 0 ? (
            <Pill tone="caution">
              Opens a gap: {option.uncovered_flights.join(", ")}
            </Pill>
          ) : null}
        </div>
      ) : null}

      <div className="border-t border-line-soft px-3 py-2.5">
        <Eyebrow>Reasoning</Eyebrow>
        <p className="mt-1 max-w-[68ch] text-base leading-relaxed text-ink-2">
          <GroundedText text={option.reasoning} facts={option.facts} />
        </p>
      </div>

      {option.cost.line_items.length > 0 ? (
        <div className="border-t border-line-soft px-3 py-2.5">
          <Eyebrow>Cost</Eyebrow>
          <table className="mt-1 w-full text-base">
            <tbody>
              {option.cost.line_items.map((line) => (
                <tr key={line.label} className="border-b border-line-soft last:border-0">
                  <td className="py-1 pr-2 align-top text-ink-2">{line.label}</td>
                  <td className="num py-1 pr-2 align-top text-xs text-ink-3">
                    {line.basis}
                    {line.rule_ref ? (
                      <span className="ml-1 text-ink-3 opacity-70">
                        ({line.rule_ref})
                      </span>
                    ) : null}
                  </td>
                  <td className="num py-1 text-right align-top whitespace-nowrap text-ink">
                    {inr(line.amount_inr)}
                  </td>
                </tr>
              ))}
              <tr>
                <td className="py-1 pr-2 font-medium text-ink">Total</td>
                <td />
                <td className="num py-1 text-right font-semibold text-ink">
                  {inr(option.cost.total_inr)}
                </td>
              </tr>
            </tbody>
          </table>
          {option.cost.note ? (
            <p className="mt-1 text-xs text-ink-3">{option.cost.note}</p>
          ) : null}
        </div>
      ) : null}

      {option.tradeoffs.length > 0 ? (
        <div className="border-t border-line-soft px-3 py-2.5">
          <Eyebrow>Trade-offs</Eyebrow>
          <ul className="mt-1 space-y-1">
            {option.tradeoffs.map((tradeoff) => (
              <li
                key={tradeoff}
                className="flex gap-2 text-base leading-relaxed text-ink-2"
              >
                <span aria-hidden className="mt-2 h-px w-2.5 shrink-0 bg-line-strong" />
                <span className="max-w-[64ch]">
                  <GroundedText text={tradeoff} facts={option.facts} />
                </span>
              </li>
            ))}
          </ul>
        </div>
      ) : null}

      <div className="border-t border-line-soft px-2 py-1.5">
        <Disclosure
          summary="All seven rules, per duty day"
          count={option.legality.per_day.length}
        >
          <div className="px-1 pb-2">
            <LegalityReportView report={option.legality} />
          </div>
        </Disclosure>
      </div>
    </article>
  );
}

function RejectedCard({ option }: { option: CoverOption }) {
  const breach = firstBreach(option.legality);
  return (
    <article className="rounded-md bg-surface hairline">
      <header className="flex flex-wrap items-center gap-2 border-b border-line-soft px-3 py-2">
        <XCircleIcon size={14} weight="fill" aria-hidden className="text-breach" />
        <Token>{option.crew_id}</Token>
        <span className="text-base text-ink-2">{option.crew_name}</span>
        <span className="text-xs text-ink-3">
          {joinParts([option.crew_base, option.crew_rank])}
        </span>
        <span className="ml-auto">
          <VerdictPill verdict={option.legality.overall} />
        </span>
      </header>
      <div className="px-3 py-2.5">
        <p className="max-w-[68ch] text-base leading-relaxed text-ink-2">
          <GroundedText text={option.reasoning} facts={option.facts} />
        </p>
      </div>
      {breach ? (
        <div className="px-2 pb-2">
          <RuleTraceCard trace={breach} compact />
        </div>
      ) : null}
      <div className="border-t border-line-soft px-2 py-1.5">
        <Disclosure summary="Every rule that was checked">
          <div className="px-1 pb-2">
            <LegalityReportView report={option.legality} />
          </div>
        </Disclosure>
      </div>
    </article>
  );
}

function Stat({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div>
      <dt className="label-micro">{label}</dt>
      <dd className="mt-0.5 text-base text-ink">{children}</dd>
    </div>
  );
}


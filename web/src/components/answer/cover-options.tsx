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

import { useId, useState } from "react";
import {
  AirplaneTakeoffIcon,
  ArrowsLeftRightIcon,
  CaretRightIcon,
  ClockCountdownIcon,
  ProhibitIcon,
  SealCheckIcon,
  UserSwitchIcon,
  XCircleIcon,
} from "@phosphor-icons/react/dist/ssr";

import type { CoverKind, CoverOption, Recommendation } from "@/lib/contracts";
import { inr, joinParts, minutesToClock, plural } from "@/lib/format";
import { GroundedText } from "@/components/answer/grounded-prose";
import { CostBars, OptionCostCompare } from "@/components/answer/charts";
import {
  firstBreach,
  LegalityReportView,
  RuleTraceCard,
  VerdictPill,
} from "@/components/answer/rule-trace";
import { ConfidenceMeter } from "@/components/ai/elements";
import { Pagination, usePaged } from "@/components/ui/pagination";
import { Disclosure, Eyebrow, Pill, Token } from "@/components/ui/primitives";
import { cx } from "@/components/ui/tone";

/**
 * Rejected candidates to a page.
 *
 * Covering P-2291 evaluates every qualified captain in the fleet, so the
 * excluded list runs to twenty cards each carrying the rule trace that
 * excluded it. Showing the shape of the search is the point; making somebody
 * scroll all of it to reach the notification draft underneath is not.
 */
const REJECTED_PER_PAGE = 6;

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
  const pagedRejects = usePaged(rejected, REJECTED_PER_PAGE);

  return (
    <section className="space-y-3" aria-label="Cover options">
      <div className="flex flex-wrap items-baseline gap-x-3 gap-y-1">
        <h3 className="macro text-xl text-ink">
          {options.length === 1
            ? "One legal option"
            : `${options.length} legal options`}
        </h3>
        <p className="text-base text-ink-3">
          {plural(recommendation.candidates_evaluated, "candidate")} evaluated,{" "}
          {plural(rejected.length, "excluded", "excluded")}
        </p>
      </div>

      <p className="max-w-[68ch] text-base text-ink-2">
        <span className="label-micro mr-2 inline">Ranked by</span>
        {recommendation.ranking_basis}
      </p>

      <OptionCostCompare options={options} />

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
            {pagedRejects.slice.map((option) => (
              <RejectedCard key={option.crew_id} option={option} />
            ))}
          </div>
          <div className="px-2">
            <Pagination
              paged={pagedRejects}
              label="Candidates ruled out"
              unit="candidate"
            />
          </div>
        </Disclosure>
      ) : null}

      {recommendation.notification_draft ? (
        <section className="rounded-md bg-inset px-4 py-3">
          <div className="flex flex-wrap items-baseline gap-x-2">
            <h4 className="text-base font-semibold text-ink">Draft callout</h4>
            <span className="text-xs text-ink-3">
              Deterministic template, filled from computed facts
            </span>
          </div>
          <p className="mt-1.5 text-base leading-relaxed text-ink-2">
            <GroundedText
              text={recommendation.notification_draft}
              facts={recommendation.facts}
            />
          </p>
        </section>
      ) : null}
    </section>
  );
}

/**
 * One option, open at rank 1 and folded below it.
 *
 * Every card used to render in full, and a search that clears six candidates
 * produced six of these end to end: confidence meter, four stats, reasoning,
 * cost bars, trade-offs and a rules disclosure, six times over. That is not
 * thoroughness, it is the same shape repeated until the reader stops
 * reading, and it buried the notification draft under a screen and a half of
 * alternatives nobody had asked for yet.
 *
 * The header carries what ranking is actually decided on: position, action,
 * kind, verdict and cost. Folded, the alternatives are a scannable list of
 * exactly those five things; opened, each is the whole case. Rank 1 starts
 * open because it is the recommendation, and the answer should not require a
 * click to say what to do.
 *
 * NOTHING IS HIDDEN THAT WAS NOT ALREADY A CLICK AWAY, and the cost
 * comparison above these cards still shows every option at once, so folding
 * costs the reader no information about the shape of the choice.
 */
export function CoverOptionCard({ option }: { option: CoverOption }) {
  const Icon = KIND_ICON[option.kind];
  const best = option.rank === 1;
  const [open, setOpen] = useState(best);
  const bodyId = useId();

  return (
    /* Rank 1 is marked by elevation and a solid edge, not by an outline. An
       outlined card among shadowed ones reads as a different KIND of object;
       the same object sitting higher reads as the same kind, ranked first,
       which is what it is. */
    <article
      className={cx(
        "overflow-hidden rounded-lg bg-surface",
        best ? "shadow-raised" : "hairline",
      )}
    >
      {best ? (
        <span
          aria-hidden
          className="block h-1 w-full bg-[image:var(--grad-rank)]"
        />
      ) : null}

      <header className="flex flex-wrap items-center gap-x-2.5 gap-y-1.5 px-4 pt-3.5">
        <span
          aria-label={`Rank ${option.rank}`}
          className={cx(
            "num flex size-6 shrink-0 items-center justify-center rounded-full text-sm font-semibold",
            best
              ? "bg-[image:var(--grad-accent)] text-page"
              : "bg-inset text-ink-2",
          )}
        >
          {option.rank}
        </span>
        <h4 className="macro text-lg text-ink">
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
        {/* The toggle is its own control rather than the whole header,
            because `option.action` is grounded prose and renders its own
            buttons for the figures in it. A header wrapped in a button would
            nest one button inside another, which is invalid and which breaks
            the fact popovers the action line depends on. */}
        <button
          type="button"
          aria-expanded={open}
          aria-controls={bodyId}
          onClick={() => setOpen((value) => !value)}
          className="-mr-1 inline-flex size-6 shrink-0 cursor-pointer items-center justify-center rounded-sm text-ink-3 hover:bg-hover hover:text-ink"
        >
          <span className="sr-only">
            {open ? "Hide" : "Show"} the detail for option {option.rank}
          </span>
          <CaretRightIcon
            size={12}
            weight="bold"
            aria-hidden
            className={cx(
              "transition-transform duration-200 ease-out-quint",
              open && "rotate-90",
            )}
          />
        </button>
      </header>

      {open ? (
        <div id={bodyId} className="anim-fade-up">
      <div className="px-4 pt-2">
        <ConfidenceMeter confidence={option.confidence} />
      </div>

      <dl className="grid grid-cols-2 gap-x-4 gap-y-3 px-4 py-3.5 sm:grid-cols-4">
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
        <div className="flex flex-wrap items-center gap-2 px-4 pb-3">
          {option.delay_minutes > 0 ? (
            <Pill tone="caution">
              <ClockCountdownIcon size={11} weight="bold" aria-hidden />
              {minutesToClock(option.delay_minutes)} delay
            </Pill>
          ) : null}
          {option.uncovered_flights.length > 0 ? (
            <div className="flex min-w-0 flex-wrap items-baseline gap-x-2 gap-y-1">
              <Pill tone="caution">
                Opens a gap on {plural(option.uncovered_flights.length, "leg")}
              </Pill>
              <span className="num min-w-0 text-xs text-ink-2">
                {option.uncovered_flights.join(", ")}
              </span>
            </div>
          ) : null}
        </div>
      ) : null}

      <div className="px-4 pb-3.5">
        <Eyebrow>Reasoning</Eyebrow>
        <p className="mt-1 max-w-[68ch] text-base leading-relaxed text-ink-2">
          <GroundedText text={option.reasoning} facts={option.facts} />
        </p>
      </div>

      {option.cost.line_items.length > 0 ? (
        <div className="mx-4 mb-3.5 rounded-md bg-inset px-3 py-2.5">
          <Eyebrow>Cost</Eyebrow>
          <div className="mt-2">
            <CostBars cost={option.cost} />
          </div>
        </div>
      ) : null}

      {option.tradeoffs.length > 0 ? (
        <div className="px-4 pb-3.5">
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

      <div className="px-2 pb-2">
        <Disclosure
          summary="All seven rules, per duty day"
          count={option.legality.per_day.length}
        >
          <div className="px-1 pb-2">
            <LegalityReportView report={option.legality} />
          </div>
        </Disclosure>
      </div>
        </div>
      ) : (
        <div className="pb-3" />
      )}
    </article>
  );
}

function RejectedCard({ option }: { option: CoverOption }) {
  const breach = firstBreach(option.legality);
  return (
    <article className="rounded-md bg-surface flat">
      <header className="flex flex-wrap items-center gap-2 px-4 pt-3">
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
      <div className="px-4 pt-1.5 pb-2">
        <p className="max-w-[68ch] text-base leading-relaxed text-ink-2">
          <GroundedText text={option.reasoning} facts={option.facts} />
        </p>
      </div>
      {breach ? (
        <div className="px-2 pb-2">
          <RuleTraceCard trace={breach} compact />
        </div>
      ) : null}
      <div className="px-2 pb-2">
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


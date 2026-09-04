"""Candidate enumeration, costing and ranking: the Tier 3 search.

The order of the filters is the reconstruction of the reference implementation
that produced every shipped cover answer key, and it is load-bearing, because
the order decides which reason a candidate is excluded for when several apply:

1. Skip the crew member who is out, anyone the caller forbids, anyone whose
   **rank does not exactly match** the required role, and anyone who is not
   `active`. Non-active crew are **silently dropped**: they never appear in the
   exclusion list, because they are not rule failures.
2. If the crew member is not based at the departure station, plan a deadhead.
   No positioning available is a RULE-BASE-07 exclusion, and it stops there.
3. If they are a reserve, test their on-call window against the **required
   report time**, which is the pairing's report plus any positioning delay.
   The scenario's narrative callout time never enters this test.
4. Run the full seven rule assessment. RULE-QUAL-05 short-circuits.
5. Price what survives, sort by `(cost, crew_id)`, then append the
   cancellation option **last regardless of its cost**, and number from 1.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from datetime import datetime as DateTime  # noqa: N812

from pydantic import BaseModel, ConfigDict

from crewops.contracts.evidence import Confidence, Fact, Provenance
from crewops.contracts.ops import (
    CostBreakdown,
    CoverKind,
    CoverOption,
    ImpactReport,
    Recommendation,
)
from crewops.contracts.rules import (
    ALL_RULE_IDS,
    DayLegality,
    LegalityReport,
    RuleId,
    Verdict,
)
from crewops.domain import (
    Crew,
    WorldOverlay,
    WorldState,
    add_hours,
    at_clock,
    format_duration,
)
from crewops.ops.costing import price_cancellation, price_cover
from crewops.ops.positioning import plan_positioning
from crewops.rules import (
    CoverAssessment,
    LegalityEngine,
    Positioning,
    ProposedDuty,
    messages,
)

#: Every crew option in a shipped answer key lists all seven rules, in this
#: order, whether or not each one had anything to say.
RULES_CHECKED: tuple[RuleId, ...] = ALL_RULE_IDS

RANKING_BASIS = (
    "Legal options sorted by cost ascending, ties broken by crew id. "
    "The cancellation option is appended last regardless of its cost, "
    "because cancelling is a last resort rather than a cheap one."
)


class ExcludedCandidate(BaseModel):
    """A candidate that was found and ruled out, with the reason stated."""

    model_config = ConfigDict(frozen=True)

    crew_id: str
    reason: str
    assessment: CoverAssessment | None = None


class RankedOption(BaseModel):
    """One way to cover the gap, priced and ranked."""

    model_config = ConfigDict(frozen=True)

    rank: int
    action: str
    crew_id: str | None
    legal: bool
    cost_inr: int
    delay_hours: float
    kind: CoverKind
    cost: CostBreakdown
    rules_checked: tuple[RuleId, ...] = ()
    assessment: CoverAssessment | None = None
    positioning: Positioning | None = None
    required_report_utc: DateTime | None = None
    covered_flights: tuple[str, ...] = ()
    is_reserve: bool = False

    def as_answer_key(self) -> dict[str, object]:
        """The shipped option shape, for parity assertions against the keys."""
        return {
            "action": self.action,
            "crew_id": self.crew_id,
            "legal": self.legal,
            "rules_checked": list(self.rules_checked),
            "cost_inr": self.cost_inr,
            "delay_hours": self.delay_hours,
            "rank": self.rank,
        }


@dataclass(frozen=True)
class CoverSearch:
    """The full result: what was tried, what survived, and what was ruled out.

    A dataclass rather than a pydantic model because it holds a reference to
    the `WorldState` so that `to_recommendation` can resolve crew names without
    the caller passing the world back in. What the HTTP layer serialises is the
    `Recommendation` this produces, not this internal search record.
    """

    world: WorldState
    assignment_ref: str
    role: str
    duties: tuple[ProposedDuty, ...]
    options: tuple[RankedOption, ...]
    excluded: tuple[ExcludedCandidate, ...]
    candidates_evaluated: int
    situation: str = ""
    impact: ImpactReport | None = None

    @property
    def total_legs(self) -> int:
        return sum(len(day.flight_ids) for day in self.duties)

    @property
    def all_flight_ids(self) -> tuple[str, ...]:
        return tuple(f for day in self.duties for f in day.flight_ids)

    @property
    def best(self) -> RankedOption | None:
        """The cheapest legal crew option, or None when only cancellation remains."""
        for option in self.options:
            if option.crew_id is not None:
                return option
        return None

    def to_recommendation(self) -> Recommendation:
        """The contract shaped view, including the rejects and why."""
        return Recommendation(
            situation=self.situation or f"Cover required for {self.assignment_ref}",
            impact=self.impact,
            options=[_to_cover_option(self.world, self, o) for o in self.options],
            rejected=[_rejected_option(self.world, self, e) for e in self.excluded],
            candidates_evaluated=self.candidates_evaluated,
            ranking_basis=RANKING_BASIS,
            facts=_search_facts(self),
        )


# --------------------------------------------------------------- the search


class CandidateSearcher:
    """Enumerates and ranks cover options. Deterministic, no model involved."""

    def __init__(self, world: WorldState, engine: LegalityEngine) -> None:
        self.world = world
        self.engine = engine

    def search(
        self,
        duties: Sequence[ProposedDuty],
        *,
        role: str,
        sick_crew_id: str | None = None,
        exclude_pairing: str | None = None,
        overlay: WorldOverlay | None = None,
        forbid_crew: Iterable[str] = (),
        situation: str = "",
        impact: ImpactReport | None = None,
    ) -> CoverSearch:
        if not duties:
            raise ValueError("A cover search needs at least one duty day")

        ordered = tuple(sorted(duties, key=lambda d: d.duty_date))
        view = overlay or self.world.overlay()
        forbidden = set(forbid_crew)
        first = ordered[0]
        required_station = first.origin

        priced: list[RankedOption] = []
        excluded: list[ExcludedCandidate] = []
        evaluated = 0

        for member in self.world.crew:
            if member.crew_id == sick_crew_id or member.crew_id in forbidden:
                continue
            # Rank equals role exactly. Senior Cabin Crew is not substitutable
            # for Cabin Crew, and vice versa.
            if member.rank != role:
                continue
            # Non-active crew are dropped before any rule runs and are never
            # reported as rule failures.
            if not member.is_active:
                continue

            evaluated += 1
            outcome = self._evaluate(
                member,
                ordered,
                view,
                required_station=required_station,
                exclude_pairing=exclude_pairing,
            )
            if isinstance(outcome, ExcludedCandidate):
                excluded.append(outcome)
            else:
                priced.append(outcome)

        priced.sort(key=lambda o: (o.cost_inr, o.crew_id or ""))
        options = [o.model_copy(update={"rank": i + 1}) for i, o in enumerate(priced)]
        options.append(self._cancellation(ordered, rank=len(options) + 1))

        return CoverSearch(
            world=self.world,
            assignment_ref=exclude_pairing or first.source_pairing_id or "the assignment",
            role=role,
            duties=ordered,
            options=tuple(options),
            excluded=tuple(excluded),
            candidates_evaluated=evaluated,
            situation=situation,
            impact=impact,
        )

    # ---------------------------------------------------------- one candidate

    def _evaluate(
        self,
        member: Crew,
        duties: Sequence[ProposedDuty],
        overlay: WorldOverlay,
        *,
        required_station: str,
        exclude_pairing: str | None,
    ) -> RankedOption | ExcludedCandidate:
        first = duties[0]
        is_reserve = self.world.is_reserve(member.crew_id)
        positioning: Positioning | None = None

        if member.base != required_station:
            positioning = plan_positioning(
                self.world,
                crew_id=member.crew_id,
                required_station=required_station,
                on_date=first.duty_date,
                first_departure_utc=self._first_departure(first),
            )
            if positioning is None:
                return ExcludedCandidate(
                    crew_id=member.crew_id, reason=messages.no_positioning(member.base)
                )

        delay_hours = positioning.delay_hours if positioning else 0.0
        required_report = add_hours(first.report_utc, delay_hours)

        if is_reserve:
            window_failure = self._window_failure(member.crew_id, required_report)
            if window_failure is not None:
                return ExcludedCandidate(crew_id=member.crew_id, reason=window_failure)

        assessment = self.engine.assess_cover(
            overlay,
            crew_id=member.crew_id,
            duties=duties,
            exclude_pairing=exclude_pairing,
            positioning=positioning,
        )
        if not assessment.ok:
            return ExcludedCandidate(
                crew_id=member.crew_id, reason=assessment.reason, assessment=assessment
            )

        cost = price_cover(
            self.world.costs,
            member,
            is_reserve=is_reserve,
            positioning=positioning,
            duty_days=len(duties),
        )
        label = "reserve callout" if is_reserve else "day-off callout"
        if positioning is not None:
            label += (
                f" + deadhead from {member.base} "
                f"(first departure delayed ~{delay_hours}h)"
            )
        return RankedOption(
            rank=0,
            action=f"Assign {member.rank} {member.crew_id} ({label})",
            crew_id=member.crew_id,
            legal=True,
            cost_inr=round(cost.total_inr),
            delay_hours=delay_hours,
            kind=CoverKind.DEADHEAD
            if positioning
            else (CoverKind.RESERVE if is_reserve else CoverKind.REASSIGN),
            cost=cost,
            rules_checked=RULES_CHECKED,
            assessment=assessment,
            positioning=positioning,
            required_report_utc=required_report,
            covered_flights=tuple(f for day in duties for f in day.flight_ids),
            is_reserve=is_reserve,
        )

    def _first_departure(self, duty: ProposedDuty) -> DateTime:
        if duty.flight_ids:
            return self.world.require_flight(duty.flight_ids[0]).dep_utc
        return add_hours(duty.report_utc, 1.0)

    def _window_failure(self, crew_id: str, required_report: DateTime) -> str | None:
        """A reserve is callable only if the required report falls in their window.

        Inclusive at both ends: C-3310's window opens at 06:00 and P-2291
        reports at 06:00Z, which is why C-3310 is the expected choice for S2
        rather than an exclusion. No window in this dataset wraps midnight, so
        the same date construction is safe.
        """
        reserve = self.world.reserve(crew_id)
        if reserve is None:
            return None
        window = reserve.oncall_window_utc
        day = required_report.date()
        opens = at_clock(day, window.start)
        closes = at_clock(day, window.end)
        if opens <= required_report <= closes:
            return None
        return messages.reserve_window_failure(
            window.start, window.end, required_report.strftime("%H:%M")
        )

    def _cancellation(self, duties: Sequence[ProposedDuty], *, rank: int) -> RankedOption:
        legs = sum(len(day.flight_ids) for day in duties)
        cost = price_cancellation(self.world.costs, legs=legs)
        return RankedOption(
            rank=rank,
            action=f"Cancel all {legs} flights of the pairing",
            crew_id=None,
            legal=True,
            cost_inr=round(cost.total_inr),
            delay_hours=0.0,
            kind=CoverKind.CANCEL,
            cost=cost,
            rules_checked=(),
            covered_flights=(),
        )


# ------------------------------------------------ contract shaped projection


def _synthetic_report(assignment_ref: str, duties: Sequence[ProposedDuty]) -> LegalityReport:
    """A legality report for the cancellation option, which has no crew member.

    Cancelling breaches nothing because nobody flies, so every rule is
    NOT_APPLICABLE with the reason stated. It is deliberately not PASS: a
    cancelled flight is not a compliant crewing decision, it is the absence of
    one.
    """
    days = [
        DayLegality(
            duty_date=day.duty_date,
            verdict=Verdict.NOT_APPLICABLE,
            traces=[],
        )
        for day in duties
    ]
    return LegalityReport(
        crew_id="",
        assignment_ref=assignment_ref,
        assignment_kind="pairing",
        overall=Verdict.NOT_APPLICABLE,
        per_day=days,
        rules_checked=[],
    )


def _to_cover_option(
    world: WorldState, search: CoverSearch, option: RankedOption
) -> CoverOption:
    member = world.crew_member(option.crew_id) if option.crew_id else None
    legality = (
        option.assessment.report
        if option.assessment
        else _synthetic_report(search.assignment_ref, search.duties)
    )
    return CoverOption(
        rank=option.rank,
        kind=option.kind,
        action=option.action,
        crew_id=option.crew_id or "",
        crew_name=member.name if member else "no crew assigned",
        crew_base=member.base if member else "",
        crew_rank=member.rank if member else search.role,
        legal=option.legal,
        legality=legality,
        rules_checked=list(option.rules_checked),
        cost=option.cost,
        coverage_summary=_coverage_summary(search, option),
        covered_flights=list(option.covered_flights),
        uncovered_flights=[] if option.crew_id else list(search.all_flight_ids),
        reachable=member is not None,
        reachability_minutes=member.reachability_minutes if member else None,
        delay_minutes=round(option.delay_hours * 60),
        reasoning=_reasoning(world, search, option),
        tradeoffs=_tradeoffs(world, search, option),
        confidence=Confidence.HIGH,
        facts=_option_facts(search, option),
    )


def _rejected_option(
    world: WorldState, search: CoverSearch, excluded: ExcludedCandidate
) -> CoverOption:
    member = world.crew_member(excluded.crew_id)
    legality = (
        excluded.assessment.report
        if excluded.assessment
        else _synthetic_report(search.assignment_ref, search.duties)
    )
    return CoverOption(
        rank=0,
        kind=CoverKind.REASSIGN,
        action=f"Rejected: {excluded.crew_id}",
        crew_id=excluded.crew_id,
        crew_name=member.name if member else excluded.crew_id,
        crew_base=member.base if member else "",
        crew_rank=member.rank if member else search.role,
        legal=False,
        legality=legality,
        rules_checked=list(RULES_CHECKED),
        cost=CostBreakdown(line_items=[], total_inr=0.0, note="Not priced: excluded."),
        coverage_summary="not available",
        covered_flights=[],
        uncovered_flights=list(search.all_flight_ids),
        reachable=member is not None,
        reachability_minutes=member.reachability_minutes if member else None,
        reasoning=excluded.reason,
        tradeoffs=[excluded.reason],
        confidence=Confidence.HIGH,
        facts=[],
    )


def _coverage_summary(search: CoverSearch, option: RankedOption) -> str:
    legs = search.total_legs
    if option.crew_id is None:
        return f"none: all {legs} flights cancelled"
    days = len(search.duties)
    if days == 1:
        return f"all {legs} flights"
    return f"all {legs} flights across {days} duty days"


def _reasoning(world: WorldState, search: CoverSearch, option: RankedOption) -> str:
    if option.crew_id is None:
        return (
            f"Cancelling all {search.total_legs} legs of {search.assignment_ref} costs "
            f"INR {option.cost_inr:,}. It is always available and always last, "
            "because it strands every passenger on those legs."
        )
    member = world.require_crew(option.crew_id)
    source = "on reserve" if option.is_reserve else "on a day off"
    detail = (
        f"{option.crew_id} ({member.rank}, {member.base}, {source}) clears all seven "
        f"rules on every day of {search.assignment_ref} at INR {option.cost_inr:,}"
    )
    if option.positioning is not None:
        detail += (
            f", after positioning from {option.positioning.from_station} on "
            f"{option.positioning.flight_no}, which delays the first departure by "
            f"{option.delay_hours}h"
        )
    return detail + "."


def _tradeoffs(world: WorldState, search: CoverSearch, option: RankedOption) -> list[str]:
    """What this option costs you. Never empty: an option with no stated
    downside is under-analysed, not perfect."""
    if option.crew_id is None:
        return [
            f"{search.total_legs} flights cancelled and every passenger on them "
            "re-accommodated",
            f"INR {option.cost_inr:,}, the most expensive outcome here",
            "No crew legality issue, because nobody flies",
        ]
    member = world.require_crew(option.crew_id)
    out: list[str] = []
    if option.is_reserve:
        out.append(
            f"Consumes a reserve: {option.crew_id} is no longer available for the "
            "next disruption on this date"
        )
    else:
        out.append(
            f"Calls {option.crew_id} in on a day off, at "
            f"INR {option.cost_inr:,} rather than a reserve rate"
        )
    if option.positioning is not None:
        out.append(
            f"Delays the first departure by {option.delay_hours}h and adds a "
            f"positioning sector from {option.positioning.from_station}"
        )
    out.append(f"Reachability is {member.reachability_minutes} minutes from callout")

    if option.assessment is not None:
        tightest = _tightest_margin(option.assessment)
        if tightest is not None:
            rule_id, margin = tightest
            out.append(
                f"Tightest remaining margin is {format_duration(margin)} under {rule_id}"
            )
    if len(search.duties) > 1:
        out.append(
            f"Commits {option.crew_id} to all {len(search.duties)} days of the pairing, "
            "including the overnight away from base"
        )
    return out


def _tightest_margin(assessment: CoverAssessment) -> tuple[str, float] | None:
    best: tuple[str, float] | None = None
    for day in assessment.report.per_day:
        for trace in day.traces:
            if trace.margin is None or trace.verdict is not Verdict.PASS:
                continue
            if trace.unit != "hours":
                continue
            if best is None or trace.margin < best[1]:
                best = (trace.rule_id, trace.margin)
    return best


def _option_facts(search: CoverSearch, option: RankedOption) -> list[Fact]:
    facts = [
        Fact(
            key=f"{search.assignment_ref}.option.{option.rank}.cost",
            label="Option cost",
            value=option.cost_inr,
            unit="inr",
            provenance=Provenance.COMPUTED,
            source="crewops.ops.candidates.CandidateSearcher",
            derivation=" + ".join(line.basis for line in option.cost.line_items)
            or "no cost lines",
        ),
        Fact(
            key=f"{search.assignment_ref}.option.{option.rank}.rank",
            label="Rank",
            value=option.rank,
            unit="count",
            provenance=Provenance.COMPUTED,
            source="crewops.ops.candidates.CandidateSearcher",
            derivation=RANKING_BASIS,
        ),
    ]
    if option.crew_id:
        facts.append(
            Fact(
                key=f"{search.assignment_ref}.option.{option.rank}.crew_id",
                label="Crew assigned",
                value=option.crew_id,
                unit="crew_id",
                provenance=Provenance.DATASET,
                source=f"crew.json#{option.crew_id}",
            )
        )
    if option.delay_hours:
        facts.append(
            Fact(
                key=f"{search.assignment_ref}.option.{option.rank}.delay_hours",
                label="Delay introduced",
                value=option.delay_hours,
                unit="hours",
                provenance=Provenance.COMPUTED,
                source="crewops.ops.positioning.plan_positioning",
                derivation=(
                    f"positioning arrives "
                    f"{option.positioning.arrival_utc:%H:%M}Z, plus 75 minutes to the "
                    f"new first departure = {option.delay_hours}h later"
                    if option.positioning
                    else f"{option.delay_hours}h"
                ),
            )
        )
    return facts


def _search_facts(search: CoverSearch) -> list[Fact]:
    source = "crewops.ops.candidates.CandidateSearcher"
    return [
        Fact(
            key=f"{search.assignment_ref}.candidates_evaluated",
            label="Candidates evaluated",
            value=search.candidates_evaluated,
            unit="count",
            provenance=Provenance.COMPUTED,
            source=source,
            derivation=(
                f"every active {search.role} in crew.json except the crew member "
                "being replaced"
            ),
        ),
        Fact(
            key=f"{search.assignment_ref}.options_found",
            label="Legal options found",
            value=len([o for o in search.options if o.crew_id]),
            unit="count",
            provenance=Provenance.COMPUTED,
            source=source,
            derivation="candidates clearing all seven rules on every day of the cover",
        ),
        Fact(
            key=f"{search.assignment_ref}.candidates_excluded",
            label="Candidates excluded",
            value=len(search.excluded),
            unit="count",
            provenance=Provenance.COMPUTED,
            source=source,
            derivation="candidates found and ruled out, each with its reason",
        ),
    ]


__all__ = [
    "RANKING_BASIS",
    "RULES_CHECKED",
    "CandidateSearcher",
    "CoverSearch",
    "ExcludedCandidate",
    "RankedOption",
]

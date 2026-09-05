"""Consequence and recommendation types.

Tier 2 produces an `ImpactReport`: what breaks, and what breaks next. Tier 3
produces ranked `CoverOption` values: what to do about it, priced, checked
against all seven rules, with the trade-off stated rather than buried.
"""

from __future__ import annotations

from datetime import date, datetime
from enum import Enum
from typing import Literal

from pydantic import BaseModel, Field

from crewops.contracts.evidence import Confidence, Fact
from crewops.contracts.rules import FeasibilityIssue, LegalityReport, RuleId, RuleTrace


class FlightRef(BaseModel):
    """A flight, with enough context to be actionable without a second lookup.

    `registration` is the aircraft tail. A question that names a tail has no
    other route back to a pairing, so it is carried here rather than looked up
    separately.
    """

    flight_no: str
    origin: str
    destination: str
    departure: datetime
    arrival: datetime
    aircraft_type: str | None = None
    registration: str | None = None
    seats: int | None = None
    passengers: int | None = None
    block_hours: float | None = None
    pairing_id: str | None = None


class FlightDelay(BaseModel):
    """One flight's delay, and what it did to the duty period around it.

    Scenario answer keys report a per-flight delay table, not a single headline
    number, so the impact model has to carry this at leg granularity.
    """

    flight_no: str
    delay_minutes: int
    original_departure: datetime
    new_departure: datetime
    original_arrival: datetime
    new_arrival: datetime
    cause: str
    fdp_before: float | None = None
    fdp_after: float | None = None
    fdp_limit: float | None = None
    sectors: int | None = None
    breaches_fdp: bool = False


class RiskSeverity(str, Enum):
    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class DownstreamRisk(BaseModel):
    """A second order consequence.

    The broken flight is obvious. These are the ones a controller misses, which
    is the entire reason this system exists.
    """

    crew_id: str | None = None
    flight_no: str | None = None
    pairing_id: str | None = None
    rule_id: RuleId | None = None
    severity: RiskSeverity
    detail: str = Field(description="For example 'Would exceed 60h/7d by 1h20m'")
    duty_date: date | None = None


class ImpactReport(BaseModel):
    """The answer to 'what happens if'.

    Produced entirely by deterministic code. The agent decides when to ask for
    one and how to narrate it, never what it contains.
    """

    trigger: str = Field(description="Plain restatement of the disruption modelled")
    trigger_kind: Literal[
        "crew_absence", "station_closure", "reassignment", "flight_delay", "custom"
    ]
    as_of: datetime

    uncrewed_flights: list[FlightRef] = Field(default_factory=list)
    delayed_flights: list[FlightDelay] = Field(default_factory=list)
    cancelled_flights: list[FlightRef] = Field(default_factory=list)
    pairings_broken: list[str] = Field(default_factory=list)
    crew_affected: list[str] = Field(default_factory=list)
    stations_affected: list[str] = Field(default_factory=list)
    passengers_affected: int = 0

    downstream_risks: list[DownstreamRisk] = Field(default_factory=list)

    explanation: str = Field(
        description="Deterministic template prose. The agent may rephrase it, "
        "but every figure in the rephrasing must also appear in `facts`."
    )
    facts: list[Fact] = Field(default_factory=list)


class CostLine(BaseModel):
    """One priced component. `basis` shows the multiplication, not just the total."""

    label: str
    amount_inr: float
    basis: str = Field(description="For example '4.5 block hours x INR 2,400/h'")
    rule_ref: str | None = Field(
        default=None, description="The key in costs.json this rate came from"
    )


class CostBreakdown(BaseModel):
    line_items: list[CostLine] = Field(default_factory=list)
    total_inr: float = 0.0
    note: str | None = None


class CoverKind(str, Enum):
    RESERVE = "reserve"
    REASSIGN = "reassign"
    DEADHEAD = "deadhead"
    SWAP = "swap"
    CANCEL = "cancel"


class CoverOption(BaseModel):
    """One ranked way to cover the gap.

    Every field here is computed. `reasoning` is built from a deterministic
    template so that it is true by construction. The agent may present it in
    its own words, subject to verification.
    """

    rank: int
    kind: CoverKind
    action: str = Field(description="Imperative, for example 'Assign reserve C-3310'")

    crew_id: str
    crew_name: str
    crew_base: str
    crew_rank: str

    legal: bool
    legality: LegalityReport
    rules_checked: list[RuleId] = Field(default_factory=list)

    cost: CostBreakdown
    coverage_summary: str = Field(description="For example 'all 3 flights'")
    covered_flights: list[str] = Field(default_factory=list)
    uncovered_flights: list[str] = Field(default_factory=list)

    reachable: bool = True
    reachability_minutes: int | None = None
    delay_minutes: int = Field(
        default=0, description="Knock-on delay this option introduces, in minutes"
    )

    reasoning: str
    tradeoffs: list[str] = Field(
        default_factory=list,
        description="What this option costs you. An option with no stated "
        "downside is under-analysed, not perfect.",
    )
    confidence: Confidence = Confidence.HIGH
    facts: list[Fact] = Field(default_factory=list)


class Recommendation(BaseModel):
    """The full Tier 3 answer: ranked options plus what was ruled out and why.

    `rejected` matters as much as `options`. A controller trusts a system that
    shows its rejects, because it proves the search was real.
    """

    situation: str
    impact: ImpactReport | None = None
    options: list[CoverOption] = Field(default_factory=list)
    rejected: list[CoverOption] = Field(
        default_factory=list,
        description="Candidates found and excluded, each with the breaching RuleTrace",
    )
    candidates_evaluated: int = 0
    ranking_basis: str = Field(
        default="",
        description="The ordering rule applied, stated plainly so it can be argued with",
    )
    covering_for: str | None = Field(
        default=None, description="The crew id whose seat this fills, when known"
    )
    role: str | None = Field(
        default=None, description="The role being covered. Rank must match it exactly."
    )
    joint_plan: JointPlan | None = Field(
        default=None, description="Set when this recommendation resolves several gaps together"
    )
    notification_draft: str | None = None
    facts: list[Fact] = Field(default_factory=list)


class RejectedCandidate(CoverOption):
    """A candidate the search found, checked and ruled out, with the rule named.

    A `CoverOption` already carries the full `LegalityReport`, so the breaching
    trace is reachable from it. That is not the same as it being *stated*: a
    consumer has to walk `per_day` and filter on the verdict to find it, and a
    ranking guard that wants "which rule excluded this person" cannot be
    written against a structure it has to search.

    So the trace is lifted to the surface here. `rule_id` is the exact id the
    rules engine returned (`RULE-DUTY-02`, not "a duty rule"), and `rule_trace`
    is the whole trace with the arithmetic behind it. Both are None only when
    the exclusion was a feasibility issue rather than a regulation, which is
    the case the seven-rule scope deliberately does not cover: being already
    rostered across the cover window is real and blocking, and giving it a
    `RULE-` id would misrepresent the rulebook.
    """

    rule_id: RuleId | None = Field(
        default=None,
        description="The rule that excluded this candidate, exactly as the "
        "engine returned it. None when the exclusion was a feasibility issue.",
    )
    rule_trace: RuleTrace | None = Field(
        default=None, description="The breaching trace, with its arithmetic"
    )
    feasibility: list[FeasibilityIssue] = Field(
        default_factory=list,
        description="Blocking non-regulatory exclusions, when that is what "
        "ruled the candidate out. Never given a RULE- id.",
    )
    exclusion_reason: str = Field(
        default="", description="The engine's own sentence for the exclusion"
    )


class RankedRecommendation(Recommendation):
    """The Tier 3 macro-tool's payload: enumerated, rule checked, priced, ranked.

    A `Recommendation` in every respect (it subclasses one, so every consumer
    that reads `options` and `rejected` keeps working unchanged), with the two
    lists a ranking guard actually wants to assert on stated under their own
    names.

    `legal_options` and `options` are the same objects, as are
    `rejected_options` and `rejected`. The duplication is deliberate and cheap:
    the inherited names keep the contract, the explicit names carry the promise
    that this payload enumerated **every** candidate, priced **every** survivor
    and attached a `RuleTrace` to **every** exclusion. A `Recommendation` that
    happens to have an empty `rejected` list makes no such promise.
    """

    legal_options: list[CoverOption] = Field(
        default_factory=list,
        description="Every candidate that cleared all seven rules on every day "
        "of the cover, priced and ranked. Ordered by the heuristic in "
        "`ranking_basis`.",
    )
    rejected_options: list[RejectedCandidate] = Field(
        default_factory=list,
        description="Every candidate found and excluded, each carrying the "
        "specific RuleTrace that excluded it.",
    )
    rules_per_candidate: list[RuleId] = Field(
        default_factory=list,
        description="The rule set run against every candidate, in order. Seven "
        "ids, always: a candidate checked against fewer was not checked.",
    )
    costs_source: str = Field(
        default="costs.json",
        description="Where the callout, deadhead and cancellation rates came from",
    )


class Gap(BaseModel):
    """One seat that needs filling."""

    pairing_id: str | None = None
    flight_numbers: list[str] = Field(default_factory=list)
    for_crew_id: str | None = None
    role: str | None = None
    label: str = ""


class JointPlan(BaseModel):
    """One allocation covering several simultaneous gaps at once.

    Solving gaps independently is unsafe: two searches can both return the same
    candidate at rank 1, and composing them puts one person on two aircraft.
    `assignments` is checked for that: no crew id may appear twice.

    When no feasible joint allocation exists, `feasible` is False and
    `why_infeasible` says so. Returning the best independent pair instead would
    be a confident, fluent, operationally wrong instruction, which is the worst
    thing this system can do.
    """

    objective: Literal["min_cost", "max_coverage", "min_delay"]
    feasible: bool
    assignments: list[CoverOption] = Field(default_factory=list)
    gaps_covered: list[str] = Field(default_factory=list)
    gaps_uncovered: list[str] = Field(default_factory=list)
    total_cost: CostBreakdown = Field(default_factory=CostBreakdown)
    contention: list[str] = Field(
        default_factory=list,
        description="Candidates that were rank 1 for more than one gap, and how "
        "the conflict was resolved. This is the reasoning a controller wants.",
    )
    why_infeasible: str | None = None
    tradeoffs: list[str] = Field(default_factory=list)
    facts: list[Fact] = Field(default_factory=list)

    @property
    def double_booked(self) -> list[str]:
        """Any crew id allocated more than once. Must always be empty."""
        seen: dict[str, int] = {}
        for option in self.assignments:
            seen[option.crew_id] = seen.get(option.crew_id, 0) + 1
        return sorted(crew_id for crew_id, n in seen.items() if n > 1)


# `Recommendation` is declared above `JointPlan` because it reads better in that
# order, so its forward reference is resolved here once both exist. The subclass
# inherits the same unresolved reference and needs the same treatment.
Recommendation.model_rebuild()
RankedRecommendation.model_rebuild()


class Alert(BaseModel):
    """One line on the proactive watchlist."""

    severity: RiskSeverity
    title: str
    detail: str
    crew_id: str | None = None
    flight_no: str | None = None
    pairing_id: str | None = None
    rule_id: RuleId | None = None
    due_date: date | None = None
    suggested_question: str | None = Field(
        default=None,
        description="A question the controller can click to open this thread",
    )
    facts: list[Fact] = Field(default_factory=list)


class Watchlist(BaseModel):
    """The 6 a.m. brief. Deterministic, no model involved."""

    as_of: datetime
    for_date: date
    alerts: list[Alert] = Field(default_factory=list)
    headline: str = ""
    scanned: dict[str, int] = Field(
        default_factory=dict, description="What was checked, for example {'crew': 150}"
    )


__all__ = [
    "Alert",
    "CostBreakdown",
    "CostLine",
    "CoverKind",
    "CoverOption",
    "DownstreamRisk",
    "FlightDelay",
    "FlightRef",
    "Gap",
    "ImpactReport",
    "JointPlan",
    "RankedRecommendation",
    "Recommendation",
    "RejectedCandidate",
    "RiskSeverity",
    "Watchlist",
]

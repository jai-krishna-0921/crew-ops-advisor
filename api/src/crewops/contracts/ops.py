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
from crewops.contracts.rules import LegalityReport, RuleId


class FlightRef(BaseModel):
    """A flight, with enough context to be actionable without a second lookup."""

    flight_no: str
    origin: str
    destination: str
    departure: datetime
    arrival: datetime
    aircraft_type: str | None = None
    passengers: int | None = None
    pairing_id: str | None = None


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
    notification_draft: str | None = None
    facts: list[Fact] = Field(default_factory=list)


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
    "FlightRef",
    "ImpactReport",
    "Recommendation",
    "RiskSeverity",
    "Watchlist",
]

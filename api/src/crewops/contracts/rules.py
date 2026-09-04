"""Legality types.

The seven rules in `rules.json` are the full regulatory scope. There is no
eighth rule. Every verdict carries the arithmetic that produced it, because a
controller who cannot challenge the reasoning will not trust the answer.
"""

from __future__ import annotations

from datetime import date
from enum import Enum
from typing import Literal

from pydantic import BaseModel, Field

from crewops.contracts.evidence import Fact

RuleId = Literal[
    "RULE-FDP-01",
    "RULE-DUTY-02",
    "RULE-FLT-03",
    "RULE-REST-04",
    "RULE-QUAL-05",
    "RULE-CERT-06",
    "RULE-BASE-07",
]

ALL_RULE_IDS: tuple[RuleId, ...] = (
    "RULE-FDP-01",
    "RULE-DUTY-02",
    "RULE-FLT-03",
    "RULE-REST-04",
    "RULE-QUAL-05",
    "RULE-CERT-06",
    "RULE-BASE-07",
)


class Verdict(str, Enum):
    PASS = "pass"
    BREACH = "breach"
    NOT_APPLICABLE = "not_applicable"
    INSUFFICIENT_DATA = "insufficient_data"


class RuleTrace(BaseModel):
    """One rule, evaluated against one crew member on one duty date.

    `arithmetic` is the line a controller reads to check our working. It must
    be a complete statement, not a summary: both operands, the operator, the
    result and the limit.
    """

    rule_id: RuleId
    title: str
    verdict: Verdict
    duty_date: date | None = None

    limit: float | None = None
    observed: float | None = None
    unit: Literal["hours", "minutes", "count", "boolean", "date"] | None = None

    margin: float | None = Field(
        default=None,
        description="Signed headroom. Positive is room to spare, negative is a breach.",
    )
    margin_human: str | None = Field(
        default=None, description="For example '1h20m over the limit' or '3h10m spare'"
    )

    arithmetic: str = Field(
        description=(
            "The full calculation. Example: '48.50h prior + 12.83h from P-2291 "
            "= 61.33h against a 60.00h limit, over by 1.33h'."
        )
    )
    inputs: list[Fact] = Field(default_factory=list)
    note: str | None = None


class FeasibilityIssue(BaseModel):
    """A reason a candidate cannot take an assignment that is not a regulation.

    Seven rules is the full regulatory scope. Inventing an eighth `RULE-` id
    would misrepresent the rulebook to a controller who has to defend the
    decision. But the shipped answer keys do exclude candidates for reasons the
    rulebook does not cover, most importantly being already rostered across the
    cover window.

    Those live here instead: real, blocking, and honestly labelled as
    operational feasibility rather than regulation. `code` is lowercase and
    never starts with `RULE-`.
    """

    code: Literal[
        "double_booked",
        "not_reachable",
        "not_on_duty_roster",
        "wrong_base_no_positioning",
        "reserve_window_missed",
        "crew_inactive",
        "no_positioning_flight",
    ]
    detail: str = Field(
        description=(
            "For example 'Already rostered on P-2203, which overlaps the "
            "cover on 2026-09-16'"
        )
    )
    duty_date: date | None = None
    blocking: bool = True
    inputs: list[Fact] = Field(default_factory=list)


class DayLegality(BaseModel):
    """All seven rules evaluated for a single duty date, plus feasibility."""

    duty_date: date
    verdict: Verdict
    traces: list[RuleTrace] = Field(default_factory=list)
    feasibility: list[FeasibilityIssue] = Field(default_factory=list)

    @property
    def breaches(self) -> list[RuleTrace]:
        return [t for t in self.traces if t.verdict is Verdict.BREACH]

    @property
    def blocked(self) -> bool:
        """True when a rule breaches or a blocking feasibility issue applies."""
        return bool(self.breaches) or any(f.blocking for f in self.feasibility)


class LegalityReport(BaseModel):
    """The legality of one crew member taking one assignment.

    A multi-day pairing produces one `DayLegality` per day. `overall` is BREACH
    if any day breaches. Legal on day one and breaching on day two is not a
    legal option, and the report must never round that away.
    """

    crew_id: str
    assignment_ref: str = Field(description="Pairing id, or a comma joined flight list")
    assignment_kind: Literal["pairing", "flight", "flight_set", "duty_day"]

    overall: Verdict
    per_day: list[DayLegality] = Field(default_factory=list)
    rules_checked: list[RuleId] = Field(default_factory=list)

    @property
    def breaches(self) -> list[RuleTrace]:
        return [t for day in self.per_day for t in day.breaches]

    @property
    def feasibility_issues(self) -> list[FeasibilityIssue]:
        return [f for day in self.per_day for f in day.feasibility]

    @property
    def is_legal(self) -> bool:
        """Regulatory legality only. A legal candidate can still be infeasible."""
        return self.overall is Verdict.PASS

    @property
    def is_assignable(self) -> bool:
        """Legal under the rulebook and operationally possible.

        This, not `is_legal`, is the question a controller is actually asking.
        """
        return self.is_legal and not any(f.blocking for f in self.feasibility_issues)

    @property
    def first_breach_date(self) -> date | None:
        for day in sorted(self.per_day, key=lambda d: d.duty_date):
            if day.verdict is Verdict.BREACH:
                return day.duty_date
        return None


__all__ = [
    "ALL_RULE_IDS",
    "DayLegality",
    "FeasibilityIssue",
    "LegalityReport",
    "RuleId",
    "RuleTrace",
    "Verdict",
]

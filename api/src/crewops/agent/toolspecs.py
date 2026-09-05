"""Argument schemas for the seventeen tools, and the dispatch onto `ToolSurface`.

`ToolSurface` is a `Protocol`, so there is no runtime schema to introspect and
nothing to generate from. The schemas below are written by hand against the
signatures in `contracts/tools.py`, and `test_toolspecs_match_contract` asserts
that the set of names here is exactly `TOOL_NAMES`. If the Core workstream
changes a signature, that test fails rather than a call silently breaking.

The descriptions matter as much as the types. They are the only thing telling
the model that retrieval will not answer a consequence question, or that a
multi day pairing needs a per day verdict.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import date, datetime
from typing import Any, Final, Literal

from pydantic import BaseModel, Field

from crewops.contracts import TOOL_NAMES, ToolEnvelope, ToolSurface

__all__ = ["TOOL_SPECS", "ToolSpec", "call_tool"]


# --------------------------------------------------------------- tier 1 args


class FindCrewArgs(BaseModel):
    base: str | None = Field(default=None, description="Three letter station, e.g. BLR")
    rank: str | None = Field(
        default=None,
        description="Exact rank: Captain, First Officer, Senior Cabin Crew or Cabin Crew. "
        "Rank equals role exactly; Senior Cabin Crew does not substitute for Cabin Crew.",
    )
    aircraft_type: str | None = Field(default=None, description="A320 or ATR72")
    on_reserve_date: date | None = Field(
        default=None, description="Only crew on the reserve roster for this date"
    )
    status: str | None = Field(
        default=None,
        description="Dataset crew status, for example active. Candidate searches "
        "drop non-active crew on their own, so this is for reporting, not "
        "eligibility.",
    )
    available_on: date | None = Field(
        default=None, description="Only crew with no rostered duty on this date"
    )
    name_contains: str | None = Field(
        default=None,
        description="Substring of the crew name. Names are not unique in this "
        "dataset, so never resolve a person by name alone.",
    )
    crew_ids: list[str] | None = Field(default=None, description="Explicit crew ids")
    limit: int = Field(default=50, description="Maximum rows to return")


class GetCrewDetailArgs(BaseModel):
    crew_id: str = Field(description="Crew id, e.g. C-1042")
    as_of: datetime | None = Field(
        default=None, description="Defaults to the dataset snapshot"
    )


class FindFlightsArgs(BaseModel):
    registration: str | None = Field(
        default=None,
        description="Aircraft tail. The only route from a tail to the pairing "
        "that flies it.",
    )
    origin: str | None = Field(default=None, description="Departure station")
    destination: str | None = Field(default=None, description="Arrival station")
    on_date: date | None = None
    from_time: datetime | None = None
    to_time: datetime | None = None
    time_of_day: Literal["morning", "afternoon", "evening", "night", "any"] = "any"
    flight_numbers: list[str] | None = Field(default=None, description="e.g. ['DX412']")
    pairing_id: str | None = None
    aircraft_type: str | None = None
    limit: int = 100


class FindPairingsArgs(BaseModel):
    registration: str | None = Field(
        default=None, description="Aircraft tail, e.g. VT-DXC. The route from a "
        "tail back to the pairing that flies it."
    )
    on_date: date | None = None
    base: str | None = None
    aircraft_type: str | None = None
    crew_id: str | None = None
    flight_number: str | None = Field(
        default=None, description="Find the pairing that contains this leg"
    )
    limit: int = 100


class GetDutyClocksArgs(BaseModel):
    crew_id: str
    as_of: datetime | None = Field(
        default=None, description="Defaults to the dataset snapshot"
    )


class ListReservesArgs(BaseModel):
    on_date: date = Field(description="The date the reserve cover is needed")
    base: str | None = None
    aircraft_type: str | None = None
    rank: str | None = None
    at_time: datetime | None = Field(
        default=None,
        description="The required REPORT time, not the callout time. The on-call "
        "window is tested against report, and the test is inclusive at both ends.",
    )
    crew_id: str | None = Field(
        default=None, description="One reserve, when the question names a crew id"
    )


class FindExpiringCertificationsArgs(BaseModel):
    within_days: int = 30
    as_of: date | None = None
    certification_type: str | None = Field(
        default=None, description="licence, medical or recurrent_training"
    )
    base: str | None = None


class FindCrewAtRiskArgs(BaseModel):
    min_score: float | None = Field(
        default=None, description="Only crew at or above this disruption risk score"
    )
    base: str | None = None
    on_date: date | None = None
    limit: int = 20


class AggregateArgs(BaseModel):
    collection: Literal[
        "flights", "crew", "pairings", "certifications", "reserves"
    ] = Field(description="What to aggregate over")
    metric: Literal["count", "sum", "max", "min", "mean", "distinct"] = Field(
        description="The aggregation to apply"
    )
    field: str | None = Field(
        default=None, description="Required for sum, max, min, mean and distinct"
    )
    group_by: str | None = Field(
        default=None,
        description="Field to group on. Pairings can be grouped by captain, "
        "first_officer or senior_cabin_crew as well as aircraft and "
        "aircraft_type. An unknown field is an error that lists the real ones.",
    )
    filters: dict[str, str | int | float | bool | None] | None = Field(
        default=None, description="Field to value equality filters"
    )
    limit: int = 50


class GetCostRatesArgs(BaseModel):
    rate_key: str | None = Field(
        default=None,
        description="One rate, e.g. reserve_callout_pilot. Omit for the whole table.",
    )


class GetPairingArgs(BaseModel):
    pairing_id: str = Field(description="Pairing id, e.g. P-2291")


class GetRosterArgs(BaseModel):
    crew_id: str
    from_date: date | None = None
    to_date: date | None = None


# --------------------------------------------------------------- tier 2 args


class CheckLegalityArgs(BaseModel):
    added_duty_hours: float | None = Field(
        default=None,
        description="Test a hypothetical without naming an assignment: how much "
        "more duty could this crew member take.",
    )
    added_flight_hours: float | None = Field(default=None)
    crew_id: str | None = Field(
        default=None, description="One crew member. Use crew_ids for several."
    )
    crew_ids: list[str] | None = Field(
        default=None,
        description="Several crew against the same assignment, in one call. "
        "Prefer this over repeating check_legality per person: it returns the "
        "same verdicts and costs one call instead of one per crew member.",
    )
    pairing_id: str | None = Field(
        default=None, description="Check the whole pairing, every duty day"
    )
    flight_numbers: list[str] | None = Field(
        default=None, description="Check a specific set of legs instead of a pairing"
    )
    on_date: date | None = None
    as_replacement_for: str | None = Field(
        default=None,
        description="Crew id being replaced. Their own duties on this assignment "
        "are subtracted from the base window before the cover is added.",
    )


class SimulateAbsenceArgs(BaseModel):
    crew_id: str
    from_date: date
    to_date: date | None = Field(
        default=None, description="Defaults to from_date. A sick call breaks every "
        "day of the pairing, not only today."
    )
    reason: str = "sick call"


class SimulateReassignmentArgs(BaseModel):
    crew_id: str = Field(description="The crew member being moved onto the assignment")
    pairing_id: str | None = None
    flight_numbers: list[str] | None = None
    displacing_crew_id: str | None = Field(
        default=None, description="Crew displaced by the move, if any"
    )


class SimulateStationClosureArgs(BaseModel):
    station: str
    from_time: datetime = Field(description="Closure start, inclusive")
    to_time: datetime = Field(description="Closure end, exclusive")


class SimulateDelayArgs(BaseModel):
    flight_number: str = Field(description="The leg running late, e.g. DX401")
    delay_minutes: int
    on_date: date | None = None
    mode: Literal["pre_departure", "mid_duty"] = Field(
        default="pre_departure",
        description="pre_departure slides report and release together, so duty "
        "length is unchanged. mid_duty extends release only, so the flight duty "
        "period grows against a fixed report and RULE-FDP-01 can breach. The two "
        "give different answers; pick the one the question describes.",
    )


class EarliestReportArgs(BaseModel):
    released_at: str | None = Field(
        default=None,
        description="When the crew was released from duty, ISO, e.g. "
        "2026-09-16T15:30:00Z",
    )
    crew_id: str | None = Field(
        default=None,
        description="Resolve the release from this crew member's last recorded "
        "release instead of naming a time",
    )


class ScanDutyHeadroomArgs(BaseModel):
    on_date: date = Field(description="The duty date to measure headroom against")
    threshold_hours: float | None = Field(
        default=None, description="Only crew with headroom at or below this"
    )
    base: str | None = None
    rank: str | None = None
    aircraft_type: str | None = None
    limit: int = 50


# --------------------------------------------------------------- tier 3 args


class FindCoverOptionsArgs(BaseModel):
    pairing_id: str | None = Field(default=None, description="The gap to cover")
    flight_numbers: list[str] | None = None
    for_crew_id: str | None = Field(
        default=None,
        description="The crew member who is out. Prefer this: it resolves the "
        "pairing on its own and it names the seat, which decides both the rank "
        "the search filters on and the callout rate it charges.",
    )
    role: str | None = Field(
        default=None,
        description="The seat to fill when the person is not known. Must match a "
        "rank exactly: Senior Cabin Crew is not substitutable for Cabin Crew.",
    )
    on_date: date | None = Field(
        default=None, description="Which day of the roster the gap falls on"
    )
    registration: str | None = Field(
        default=None,
        description="Aircraft tail, e.g. VT-DXF. Resolves to the pairing that "
        "tail flies on on_date, for questions that name the metal rather than "
        "the crew or the pairing.",
    )
    exclude_crew_ids: list[str] | None = Field(
        default=None, description="Usually the crew member who is out"
    )
    max_options: int = 5
    include_rejected: bool = Field(
        default=True,
        description="Keep this true. The rejected candidates and the rule that "
        "excluded each one are what prove the search was real.",
    )


class PlanJointCoverArgs(BaseModel):
    gaps: list[dict[str, str]] = Field(
        description="One entry per simultaneous gap, each naming a pairing or "
        "flight set and the crew or role being replaced"
    )
    objective: Literal["min_cost", "max_coverage", "min_delay"] = "min_cost"
    max_options: int = 3


class DraftNotificationArgs(BaseModel):
    crew_id: str = Field(description="The crew member being called out")
    pairing_id: str | None = None
    flight_numbers: list[str] | None = None
    channel: Literal["sms", "email", "app"] = "sms"
    option_rank: int | None = Field(
        default=None, description="Which ranked cover option this notification is for"
    )


# ---------------------------------------------------------- cross cutting args


class GetWatchlistArgs(BaseModel):
    for_date: date
    as_of: datetime | None = None


class GetWorldSummaryArgs(BaseModel):
    """No arguments. Returns dataset shape, snapshot time and station set."""


class ExplainRuleArgs(BaseModel):
    rule_id: str = Field(description="One of the seven, e.g. RULE-DUTY-02")


class ToolSpec:
    """One bindable tool: name, description, argument schema, dispatch."""

    __slots__ = ("args_model", "description", "invoke", "label", "name")

    def __init__(
        self,
        name: str,
        description: str,
        args_model: type[BaseModel],
        invoke: Callable[[ToolSurface, BaseModel], ToolEnvelope],
        label: Callable[[dict[str, Any]], str],
    ) -> None:
        self.name = name
        self.description = description
        self.args_model = args_model
        self.invoke = invoke
        self.label = label


def _fmt(args: dict[str, Any], *keys: str) -> str:
    parts = [f"{key}={args[key]}" for key in keys if args.get(key) not in (None, [], "")]
    return ", ".join(parts)


def _count(crew_ids: Any) -> str:
    """How a batched legality check narrates itself in the live trace."""
    if not isinstance(crew_ids, list) or not crew_ids:
        return "the rostered crew"
    if len(crew_ids) == 1:
        return str(crew_ids[0])
    return f"{len(crew_ids)} crew"


TOOL_SPECS: Final[tuple[ToolSpec, ...]] = (
    ToolSpec(
        "find_crew",
        "Crew matching a filter set: base, rank, aircraft rating, reserve status, "
        "availability. Returns a roster of people, not a consequence. An empty "
        "result is a finding; a failed lookup is not.",
        FindCrewArgs,
        lambda tools, a: tools.find_crew(**a.model_dump(exclude_none=True)),
        lambda a: f"Finding crew ({_fmt(a, 'base', 'rank', 'aircraft_type') or 'all'})",
    ),
    ToolSpec(
        "get_crew_detail",
        "One crew member in full: rank, base, ratings, roster, duty clocks, "
        "certifications, reserve status, risk score. Reach for this whenever a "
        "question names a person.",
        GetCrewDetailArgs,
        lambda tools, a: tools.get_crew_detail(**a.model_dump(exclude_none=True)),
        lambda a: f"Reading the file on {a.get('crew_id')}",
    ),
    ToolSpec(
        "find_flights",
        "Flights matching a filter set: origin, destination, date, time window, "
        "pairing, aircraft type.",
        FindFlightsArgs,
        lambda tools, a: tools.find_flights(**a.model_dump(exclude_none=True)),
        lambda a: (
            "Searching the schedule ("
            + (_fmt(a, "origin", "destination", "on_date") or "all")
            + ")"
        ),
    ),
    ToolSpec(
        "find_pairings",
        "Pairings matching a filter set. This is the route from an aircraft "
        "tail or a single leg back to the pairing that contains it, which is "
        "what a question naming VT-DXB needs before anything else can run.",
        FindPairingsArgs,
        lambda tools, a: tools.find_pairings(**a.model_dump(exclude_none=True)),
        lambda a: (
            "Finding pairings ("
            + (_fmt(a, "registration", "on_date", "flight_number") or "all")
            + ")"
        ),
    ),
    ToolSpec(
        "get_duty_clocks",
        "Duty and flight hour state for one crew member, with the remaining "
        "headroom under each limit. Use this for 'how many hours has X got left'.",
        GetDutyClocksArgs,
        lambda tools, a: tools.get_duty_clocks(**a.model_dump(exclude_none=True)),
        lambda a: f"Checking duty clocks for {a.get('crew_id')}",
    ),
    ToolSpec(
        "list_reserves",
        "Reserve crew for a date with their on-call windows. The window is tested "
        "against the required report time, inclusive at both ends.",
        ListReservesArgs,
        lambda tools, a: tools.list_reserves(**a.model_dump(exclude_none=True)),
        lambda a: f"Listing reserves ({_fmt(a, 'base', 'on_date', 'rank')})",
    ),
    ToolSpec(
        "find_expiring_certifications",
        "Licences, medicals and recurrent training lapsing inside a window. "
        "Validity is checked on valid_to only.",
        FindExpiringCertificationsArgs,
        lambda tools, a: tools.find_expiring_certifications(
            **a.model_dump(exclude_none=True)
        ),
        lambda a: f"Scanning certifications ({_fmt(a, 'within_days', 'base')})",
    ),
    ToolSpec(
        "get_pairing",
        "A pairing with every duty day, every leg, report and release times, and "
        "the crew assigned to each role.",
        GetPairingArgs,
        lambda tools, a: tools.get_pairing(**a.model_dump(exclude_none=True)),
        lambda a: f"Opening pairing {a.get('pairing_id')}",
    ),
    ToolSpec(
        "get_roster",
        "One crew member's assignments across a date range.",
        GetRosterArgs,
        lambda tools, a: tools.get_roster(**a.model_dump(exclude_none=True)),
        lambda a: f"Reading the roster for {a.get('crew_id')}",
    ),
    ToolSpec(
        "find_crew_at_risk",
        "Crew ranked by the precomputed disruption risk signal. The scores are "
        "provided, not modelled here: treat them like a weather forecast and "
        "reason about what to do, never about how they were produced.",
        FindCrewAtRiskArgs,
        lambda tools, a: tools.find_crew_at_risk(**a.model_dump(exclude_none=True)),
        lambda a: f"Ranking crew by risk ({_fmt(a, 'base', 'min_score') or 'all'})",
    ),
    ToolSpec(
        "aggregate",
        "Counts, extrema, distinct values and grouped totals. Reach for this "
        "whenever a question says 'how many', 'which is the longest' or 'which "
        "stations'. Counting a list yourself is arithmetic, and arithmetic is "
        "not yours to do. Pairing rows carry captain, first_officer and "
        "senior_cabin_crew, so 'which captain holds the most pairings or legs' "
        "is one call grouped by captain. Crew rows carry duty_hours_7d and "
        "flight_hours_28d as accrued at the snapshot, so 'who has the most "
        "duty hours in the last 7 days' and 'is anyone over 70 flight hours "
        "in 28 days' are one call each: those windows look BACKWARD from the "
        "snapshot and are not the roster week ahead, which is a different "
        "question with a different answer. An unknown field is an error "
        "naming the fields that collection does have: read that error and "
        "re-call, never fall back to fetching the records one at a time.",
        AggregateArgs,
        lambda tools, a: tools.aggregate(**a.model_dump(exclude_none=True)),
        lambda a: f"Aggregating {a.get('metric')} over {a.get('collection')}",
    ),
    ToolSpec(
        "get_cost_rates",
        "The cost model as shipped: rates, units and currency. Use it rather "
        "than recalling a rate.",
        GetCostRatesArgs,
        lambda tools, a: tools.get_cost_rates(**a.model_dump(exclude_none=True)),
        lambda a: f"Reading cost rates ({a.get('rate_key') or 'all'})",
    ),
    ToolSpec(
        "check_legality",
        "Evaluate all seven rules for crew taking one assignment. This is the "
        "only tool that produces a legality verdict. For a multi day pairing it "
        "returns one verdict per day and the overall is the worst day: legal on "
        "day one and breaching on day two is not a legal option. To check "
        "several crew against the same assignment, pass them all as crew_ids in "
        "one call rather than calling this once per person.",
        CheckLegalityArgs,
        lambda tools, a: tools.check_legality(**a.model_dump(exclude_none=True)),
        lambda a: (
            f"Checking {a.get('crew_id') or _count(a.get('crew_ids'))} against all "
            f"seven rules for "
            f"{a.get('pairing_id') or a.get('flight_numbers') or a.get('on_date')}"
        ),
    ),
    ToolSpec(
        "simulate_absence",
        "Model a crew member becoming unavailable. Returns which flights are now "
        "uncrewed, which pairings broke, how many passengers are exposed, and "
        "which other crew move closer to a limit as a result.",
        SimulateAbsenceArgs,
        lambda tools, a: tools.simulate_absence(**a.model_dump(exclude_none=True)),
        lambda a: f"Modelling {a.get('crew_id')} out from {a.get('from_date')}",
    ),
    ToolSpec(
        "simulate_reassignment",
        "Model moving a crew member onto an assignment. Checks the mover, anyone "
        "displaced, and the downstream legs.",
        SimulateReassignmentArgs,
        lambda tools, a: tools.simulate_reassignment(**a.model_dump(exclude_none=True)),
        lambda a: (
            f"Modelling {a.get('crew_id')} onto "
            f"{a.get('pairing_id') or a.get('flight_numbers')}"
        ),
    ),
    ToolSpec(
        "simulate_station_closure",
        "Model a station closing for a window and report the flight and crew "
        "impact. The window is half open: a departure exactly at the reopen time "
        "is not affected.",
        SimulateStationClosureArgs,
        lambda tools, a: tools.simulate_station_closure(
            **a.model_dump(exclude_none=True)
        ),
        lambda a: f"Closing {a.get('station')} from {a.get('from_time')}",
    ),
    ToolSpec(
        "simulate_delay",
        "Model one flight running late and cascade the consequence. Two models: "
        "pre_departure slides the whole duty later, mid_duty extends release "
        "against a fixed report so the flight duty period grows. They give "
        "different answers, so pick the one the question describes.",
        SimulateDelayArgs,
        lambda tools, a: tools.simulate_delay(**a.model_dump(exclude_none=True)),
        lambda a: (
            f"Delaying {a.get('flight_number')} by {a.get('delay_minutes')} minutes"
        ),
    ),
    ToolSpec(
        "scan_duty_headroom",
        "Every crew member's accrued duty and flight hours in one call, ranked "
        "with the least headroom, meaning the hardest worked, first. This is "
        "also the tool for 'who is my most used captain', 'who is worked "
        "hardest' and 'who is closest to a limit': filter with rank and base, "
        "and raise threshold_hours (60 covers the whole fleet) to rank everyone "
        "rather than only those near a limit. Never loop get_duty_clocks per "
        "crew member to build this yourself.",
        ScanDutyHeadroomArgs,
        lambda tools, a: tools.scan_duty_headroom(**a.model_dump(exclude_none=True)),
        lambda a: f"Sweeping duty headroom for {a.get('on_date')}",
    ),
    ToolSpec(
        "earliest_report",
        "RULE-REST-04 read forwards: the earliest a crew may next report after a "
        "release. Use this for any 'when can they fly again' or 'earliest they "
        "may report' question. Never add the rest hours to a timestamp yourself: "
        "this tool computes it and returns the arithmetic.",
        EarliestReportArgs,
        lambda tools, a: tools.earliest_report(**a.model_dump(exclude_none=True)),
        lambda a: (
            f"Applying RULE-REST-04 to {a.get('released_at') or a.get('crew_id')}"
        ),
    ),
    ToolSpec(
        "find_cover_options",
        "Enumerate, rule check, price and rank every way to cover a gap. This is "
        "the only tool that produces a ranked recommendation. It also returns the "
        "candidates it rejected and the rule that excluded each one.",
        FindCoverOptionsArgs,
        lambda tools, a: tools.find_cover_options(**a.model_dump(exclude_none=True)),
        lambda a: f"Searching for cover on {a.get('pairing_id') or a.get('flight_numbers')}",
    ),
    ToolSpec(
        "plan_joint_cover",
        "Cover two or more simultaneous gaps as one allocation. Use this, never "
        "two independent cover searches: two searches can return the same "
        "candidate as rank 1 for both gaps, and composing them puts one captain "
        "on two aircraft at once. If no feasible joint allocation exists, this "
        "says so rather than returning the best independent pair.",
        PlanJointCoverArgs,
        lambda tools, a: tools.plan_joint_cover(**a.model_dump(exclude_none=True)),
        lambda a: f"Planning joint cover for {len(a.get('gaps') or [])} gaps",
    ),
    ToolSpec(
        "draft_notification",
        "Draft the message to the crew member being called out. Deterministic "
        "template filled from computed facts. You may adjust tone; you may not "
        "introduce a time, a flight number or a report location it did not supply.",
        DraftNotificationArgs,
        lambda tools, a: tools.draft_notification(**a.model_dump(exclude_none=True)),
        lambda a: f"Drafting the callout to {a.get('crew_id')}",
    ),
    ToolSpec(
        "get_watchlist",
        "The proactive brief for a date: what is about to go wrong, ranked by "
        "severity.",
        GetWatchlistArgs,
        lambda tools, a: tools.get_watchlist(**a.model_dump(exclude_none=True)),
        lambda a: f"Building the watchlist for {a.get('for_date')}",
    ),
    ToolSpec(
        "get_world_summary",
        "Dataset shape, snapshot time, base and date range. Use it to ground a "
        "scope question and to say honestly what the system does and does not "
        "cover.",
        GetWorldSummaryArgs,
        lambda tools, _a: tools.get_world_summary(),
        lambda _a: "Reading the dataset summary",
    ),
    ToolSpec(
        "explain_rule",
        "The machine readable definition of one rule, as shipped. Use it rather "
        "than paraphrasing regulation from memory.",
        ExplainRuleArgs,
        lambda tools, a: tools.explain_rule(**a.model_dump(exclude_none=True)),
        lambda a: f"Reading {a.get('rule_id')}",
    ),
)

_BY_NAME: Final[dict[str, ToolSpec]] = {spec.name: spec for spec in TOOL_SPECS}

assert tuple(_BY_NAME) == TOOL_NAMES, (
    "toolspecs.TOOL_SPECS must match contracts.TOOL_NAMES exactly, in order"
)


def spec_for(name: str) -> ToolSpec | None:
    return _BY_NAME.get(name)


def call_tool(tools: ToolSurface, name: str, raw_args: dict[str, Any]) -> ToolEnvelope:
    """Coerce the model's arguments and dispatch onto the deterministic core.

    Coercion failures return an `ok=False` envelope rather than raising, so a
    malformed call becomes a fact the model can see and correct rather than a
    crashed turn.
    """
    spec = _BY_NAME.get(name)
    if spec is None:
        return ToolEnvelope(
            tool=name,
            args=raw_args,
            ok=False,
            error=f"No tool named {name!r}. Available: {', '.join(TOOL_NAMES)}.",
        )
    try:
        parsed = spec.args_model.model_validate(raw_args)
    except Exception as exc:
        return ToolEnvelope(
            tool=name,
            args=raw_args,
            ok=False,
            error=f"Arguments rejected by {name}: {exc}",
        )
    return spec.invoke(tools, parsed)

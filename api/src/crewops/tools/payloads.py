"""Typed payloads returned by the tool surface.

A tool returns a structured payload plus facts, never free prose the model is
expected to trust. Every numeric field here has a matching `Fact` in the
envelope that carries it, which is what lets the verifier reject a number
nobody computed.

Payloads are deliberately small: they are read into a prompt budget. When a
result is capped, the envelope sets `truncated=True` and the payload still
carries `total_matched` and the full id list, so nothing is silently lost.
"""

from __future__ import annotations

from datetime import date as DateType  # noqa: N812
from datetime import datetime as DateTime  # noqa: N812

from pydantic import BaseModel, ConfigDict, Field

from crewops.contracts.rules import RuleId


class Payload(BaseModel):
    model_config = ConfigDict(frozen=True)


# ------------------------------------------------------------------- crew


class CrewSummary(Payload):
    crew_id: str
    name: str
    rank: str
    base: str
    ratings: tuple[str, ...]
    status: str
    seniority: int
    reachability_minutes: int
    is_reserve: bool
    oncall_window: str | None = None


class CrewList(Payload):
    crew: tuple[CrewSummary, ...]
    total_matched: int
    all_crew_ids: tuple[str, ...] = Field(
        description="Every match, even when the detailed rows above are capped"
    )
    filters: dict[str, str] = Field(default_factory=dict)


class DutyDaySummary(Payload):
    duty_date: DateType
    pairing_id: str
    report_utc: DateTime
    release_utc: DateTime
    duty_hours: float
    block_hours: float
    sectors: int
    flight_numbers: tuple[str, ...]


class CertificationSummary(Payload):
    crew_id: str
    cert_type: str
    valid_to: DateType
    days_remaining: int
    valid_on_next_duty: bool | None = None


class ClockSummary(Payload):
    """Duty state recomputed as of a date, with headroom under each limit.

    "How many duty hours does C-1042 have left" is a headroom question, so both
    the consumed figure and the headroom are returned rather than leaving the
    subtraction to the reader.
    """

    crew_id: str
    as_of: DateType
    duty_hours_7d: float
    duty_limit_7d: float
    duty_headroom_7d: float
    flight_hours_28d: float
    flight_limit_28d: float
    flight_headroom_28d: float
    window_7d_start: DateType
    window_28d_start: DateType
    last_rest_ended: DateTime | None = None
    earliest_next_report: DateTime | None = None


class CrewDetail(Payload):
    crew: CrewSummary
    clocks: ClockSummary
    duties: tuple[DutyDaySummary, ...]
    certifications: tuple[CertificationSummary, ...]
    risk_score: float | None = None
    risk_drivers: tuple[str, ...] = ()
    flagged_exceptions: tuple[str, ...] = ()


# ---------------------------------------------------------------- flights


class FlightSummary(Payload):
    flight_id: str
    flight_no: str
    date: DateType
    dep_station: str
    arr_station: str
    dep_utc: DateTime
    arr_utc: DateTime
    block_hours: float
    aircraft: str
    aircraft_type: str
    seats: int
    pairing_id: str | None = None


class FlightList(Payload):
    flights: tuple[FlightSummary, ...]
    total_matched: int
    all_flight_ids: tuple[str, ...]
    total_seats: int
    filters: dict[str, str] = Field(default_factory=dict)


# --------------------------------------------------------------- reserves


class ReserveSummary(Payload):
    crew_id: str
    name: str
    rank: str
    base: str
    ratings: tuple[str, ...]
    window_start: str
    window_end: str
    reachability_minutes: int
    covers_time: bool | None = Field(
        default=None,
        description="Whether the window contains the queried report time, when one was given",
    )


class ReserveList(Payload):
    on_date: DateType
    reserves: tuple[ReserveSummary, ...]
    total_matched: int
    at_time: DateTime | None = None
    note: str = ""


class CertificationList(Payload):
    as_of: DateType
    until: DateType
    certifications: tuple[CertificationSummary, ...]
    total_matched: int
    note: str = ""


# ---------------------------------------------------------------- rosters


class PairingDayView(Payload):
    duty_date: DateType
    report_utc: DateTime
    release_utc: DateTime
    duty_hours: float
    block_hours: float
    sectors: int
    fdp_limit: float
    flights: tuple[FlightSummary, ...]


class PairingView(Payload):
    pairing_id: str
    aircraft: str
    aircraft_type: str
    days: tuple[PairingDayView, ...]
    crew: tuple[CrewSummary, ...]
    total_legs: int
    total_seats: int
    overnights_away_from_base: bool


class RosterView(Payload):
    crew_id: str
    from_date: DateType
    to_date: DateType
    duties: tuple[DutyDaySummary, ...]
    total_duty_hours: float
    total_block_hours: float
    days_off: tuple[DateType, ...]


# ------------------------------------------------------------ cross cutting


class WorldSummary(Payload):
    """Dataset shape and snapshot time.

    Grounds a scope question, and lets the system say honestly what it does and
    does not cover rather than guessing at the edges.
    """

    snapshot_utc: DateTime
    hub: str
    first_date: DateType
    last_date: DateType
    currency: str
    flights: int
    crew: int
    pairings: int
    pairing_days: int
    reserves: int
    certifications: int
    rules: int
    stations: tuple[str, ...]
    aircraft_types: tuple[str, ...]
    ranks: tuple[str, ...]
    coverage_note: str


class RuleExplanation(Payload):
    rule_id: RuleId
    text: str
    params: dict[str, float]
    title: str
    comparison: str = Field(description="How the breach test is written, in words")
    applies_to: str
    worked_example: str


class NotificationDraft(Payload):
    """A callout message built from computed facts.

    The agent may adjust tone. It may not introduce a time, a flight number or a
    report location the template did not supply.
    """

    crew_id: str
    channel: str
    subject: str
    body: str
    includes: tuple[str, ...] = Field(
        description="What the template covered, so completeness can be checked"
    )
    acknowledge_by_utc: DateTime | None = None


__all__ = [
    "CertificationList",
    "CertificationSummary",
    "ClockSummary",
    "CrewDetail",
    "CrewList",
    "CrewSummary",
    "DutyDaySummary",
    "FlightList",
    "FlightSummary",
    "NotificationDraft",
    "PairingDayView",
    "PairingView",
    "Payload",
    "ReserveList",
    "ReserveSummary",
    "RosterView",
    "RuleExplanation",
    "WorldSummary",
]

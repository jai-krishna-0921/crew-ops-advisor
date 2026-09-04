"""Typed records, one per shipped file.

Every model is frozen. The dataset is read only and the in memory projection of
it should be too: a mutation here would silently move the answer keys that the
golden tests assert against.

Timestamps are parsed to **naive** datetimes understood as UTC. Pydantic would
otherwise read the trailing `Z` as an offset and hand back an aware value,
which stops comparing against every other timestamp in the system.
"""

from __future__ import annotations

from datetime import date as DateType  # noqa: N812
from datetime import datetime as DateTime  # noqa: N812
from typing import Annotated, Any, Literal

from pydantic import BaseModel, BeforeValidator, ConfigDict

from crewops.domain.time_utils import parse_utc

Rank = Literal["Captain", "First Officer", "Senior Cabin Crew", "Cabin Crew"]
CrewStatus = Literal["active", "leave", "training"]
AircraftType = Literal["A320", "ATR72"]
CertType = Literal["licence", "medical_class1", "recurrent_training", "dangerous_goods"]

PILOT_RANKS: frozenset[str] = frozenset({"Captain", "First Officer"})
CABIN_RANKS: frozenset[str] = frozenset({"Senior Cabin Crew", "Cabin Crew"})


def _naive_utc(value: Any) -> Any:
    """Parse `2026-09-15T06:00:00Z` to a naive datetime, or pass a datetime through."""
    if isinstance(value, str):
        return parse_utc(value)
    if isinstance(value, DateTime) and value.tzinfo is not None:
        return value.replace(tzinfo=None)
    return value


NaiveUtc = Annotated[DateTime, BeforeValidator(_naive_utc)]


class Record(BaseModel):
    """Base for every dataset record: frozen, and strict about unexpected fields."""

    model_config = ConfigDict(frozen=True, extra="forbid")


# --------------------------------------------------------------------- flights


class Flight(Record):
    """One scheduled leg. No leg in this dataset crosses midnight UTC."""

    flight_id: str
    flight_no: str
    date: DateType
    dep_station: str
    arr_station: str
    dep_utc: NaiveUtc
    arr_utc: NaiveUtc
    block_hours: float
    aircraft: str
    aircraft_type: AircraftType
    seats: int

    @property
    def route(self) -> tuple[str, str]:
        return (self.dep_station, self.arr_station)


# ------------------------------------------------------------------------ crew


class Crew(Record):
    """A crew member.

    `rank` doubles as the role on a pairing: the two are equal for all 210
    roster seats, and `Senior Cabin Crew` is never substitutable for
    `Cabin Crew`. `name` is **not** unique (seven names are shared by two crew
    each), so never resolve a person by name alone.
    """

    crew_id: str
    name: str
    rank: Rank
    base: str
    ratings: tuple[AircraftType, ...]
    seniority: int
    reachability_minutes: int
    status: CrewStatus

    @property
    def is_pilot(self) -> bool:
        return self.rank in PILOT_RANKS

    @property
    def is_active(self) -> bool:
        return self.status == "active"

    def is_rated_for(self, aircraft_type: str) -> bool:
        return aircraft_type in self.ratings


# --------------------------------------------------------------------- rosters


class PairingDay(Record):
    """One duty day of a pairing.

    `report_utc` is the first departure minus 60 minutes and `release_utc` is
    the last arrival plus 30 minutes, for all 42 duty days in the dataset.
    """

    date: DateType
    flights: tuple[str, ...]
    report_utc: NaiveUtc
    release_utc: NaiveUtc

    @property
    def sectors(self) -> int:
        return len(self.flights)

    @property
    def duty_hours(self) -> float:
        return round((self.release_utc - self.report_utc).total_seconds() / 3600.0, 2)


class PairingCrew(Record):
    crew_id: str
    role: Rank


class Pairing(Record):
    """One pairing: one or two duty days flown by a fixed crew complement."""

    pairing_id: str
    aircraft: str
    days: tuple[PairingDay, ...]
    crew: tuple[PairingCrew, ...]

    @property
    def flight_ids(self) -> tuple[str, ...]:
        return tuple(fid for day in self.days for fid in day.flights)

    @property
    def total_sectors(self) -> int:
        return sum(day.sectors for day in self.days)

    def crew_in_role(self, role: str) -> tuple[str, ...]:
        return tuple(m.crew_id for m in self.crew if m.role == role)

    def role_of(self, crew_id: str) -> Rank | None:
        for member in self.crew:
            if member.crew_id == crew_id:
                return member.role
        return None


class FlaggedException(Record):
    """A roster assignment the dataset itself admits is illegal.

    There is exactly one: C-5417 on 2026-09-19 under RULE-CERT-06.
    """

    crew_id: str
    date: DateType
    rule: str
    note: str


class Rosters(Record):
    pairings: tuple[Pairing, ...]
    flagged_exceptions: tuple[FlaggedException, ...]
    note: str


# ---------------------------------------------------------------- duty clocks


class DayHistory(Record):
    """One day of pre snapshot accrual.

    Opaque: the duty to flight ratio is synthetic and 228 cells carry duty with
    zero flight hours. It is not reconstructible from the flight schedule.
    """

    date: DateType
    duty_hours: float
    flight_hours: float


EMPTY_DAY = DayHistory(date=DateType(1970, 1, 1), duty_hours=0.0, flight_hours=0.0)


class DutyClock(Record):
    """Shipped duty state for one crew member as of the snapshot.

    `duty_hours_7d` and `flight_hours_28d` are summaries that this system
    recomputes rather than trusts, because they are only correct as of
    2026-09-14 and go stale the moment a duty is simulated.
    """

    crew_id: str
    as_of_utc: NaiveUtc
    duty_hours_7d: float
    flight_hours_28d: float
    last_rest_ended: NaiveUtc | None = None
    daily_history: tuple[DayHistory, ...]


# -------------------------------------------------------------------- reserves


class OnCallWindow(Record):
    """An `HH:MM` to `HH:MM` UTC window. Inclusive at both ends."""

    start: str
    end: str

    def __str__(self) -> str:
        return f"{self.start}-{self.end}"


class Reserve(Record):
    """A reserve crew member. All 16 are on call on all 7 dates of the week, so
    `dates` never discriminates: the on call window is the only filter."""

    crew_id: str
    base: str
    dates: tuple[DateType, ...]
    oncall_window_utc: OnCallWindow
    note: str


# -------------------------------------------------------------- certifications


class Certification(Record):
    """One certificate.

    `valid_from` is present but unusable: it is generated as `valid_to - 730d`
    and never corrected after the engineered expiries, so one record has
    `valid_from > valid_to` and several show a future `valid_from` for a
    currently flying crew member. **Check `valid_to` only**, with `>=`.
    """

    crew_id: str
    cert_type: CertType
    valid_from: DateType
    valid_to: DateType

    def valid_on(self, day: DateType) -> bool:
        """A certificate expiring on the duty date is valid that day."""
        return self.valid_to >= day


# ----------------------------------------------------------------------- rules


class RuleDefinition(Record):
    """One of the seven rules, as shipped.

    RULE-QUAL-05, RULE-CERT-06 and RULE-BASE-07 carry no `params` key at all,
    so it must be optional.
    """

    rule_id: str
    text: str
    params: dict[str, float] | None = None

    def param(self, key: str, default: float) -> float:
        if not self.params:
            return default
        return float(self.params.get(key, default))


class RuleBook(Record):
    time_convention: str
    definitions: dict[str, str]
    rules: tuple[RuleDefinition, ...]

    def by_id(self, rule_id: str) -> RuleDefinition | None:
        for rule in self.rules:
            if rule.rule_id == rule_id:
                return rule
        return None


# ----------------------------------------------------------------------- costs


class Costs(Record):
    """The rate card.

    Two facts the shipped answer keys settle and that a reader will doubt:
    callout is charged **once per assignment**, not per duty day (a two day
    P-2291 cover by a reserve captain costs 18,500, not 37,000), and
    `hotel_overnight` is **never charged in any answer key**, including the DEL
    overnight of the two day pairings. It is carried here for completeness and
    deliberately not applied. There is no overtime rate, despite the
    problem-statement PDF describing one.
    """

    currency: str
    reserve_callout_pilot: int
    reserve_callout_cabin: int
    dayoff_callout_pilot: int
    dayoff_callout_cabin: int
    deadhead_positioning: int
    delay_cost_per_duty_hour: int
    cancellation_per_flight: int
    hotel_overnight: int
    notes: str

    def callout(self, *, is_reserve: bool, is_pilot: bool) -> int:
        if is_reserve:
            return self.reserve_callout_pilot if is_pilot else self.reserve_callout_cabin
        return self.dayoff_callout_pilot if is_pilot else self.dayoff_callout_cabin

    def callout_key(self, *, is_reserve: bool, is_pilot: bool) -> str:
        kind = "reserve" if is_reserve else "dayoff"
        who = "pilot" if is_pilot else "cabin"
        return f"{kind}_callout_{who}"


# --------------------------------------------------------------- risk signals


class RiskSignal(Record):
    """A **provided** disruption score. Never computed by this system."""

    crew_id: str
    as_of_utc: NaiveUtc
    disruption_risk_score: float
    drivers: tuple[str, ...]


# ----------------------------------------------------------- derived records


#: Stands in for `pairing_id` on a proposed duty that is not on the roster yet.
#: The shipped exclusion strings quote this token verbatim, for example
#: "RULE-REST-04: only 9.5h rest before COVER on 2026-09-15 (rest conflict)".
COVER_PAIRING_ID = "COVER"


class WeekDuty(Record):
    """One crew member's duty on one date of the schedule week.

    There is no crew to pairing index in the shipped data, so this is built by
    scanning all 39 pairings at load time. Every window sum, rest check and
    overlap check needs it.
    """

    crew_id: str
    duty_date: DateType
    report_utc: DateTime
    release_utc: DateTime
    duty_hours: float
    block_hours: float
    pairing_id: str
    sectors: int = 0
    aircraft_type: str = ""

    @property
    def is_cover(self) -> bool:
        return self.pairing_id == COVER_PAIRING_ID


__all__ = [
    "CABIN_RANKS",
    "COVER_PAIRING_ID",
    "EMPTY_DAY",
    "PILOT_RANKS",
    "AircraftType",
    "CertType",
    "Certification",
    "Costs",
    "Crew",
    "CrewStatus",
    "DayHistory",
    "DutyClock",
    "FlaggedException",
    "Flight",
    "NaiveUtc",
    "OnCallWindow",
    "Pairing",
    "PairingCrew",
    "PairingDay",
    "Rank",
    "Record",
    "Reserve",
    "RiskSignal",
    "Rosters",
    "RuleBook",
    "RuleDefinition",
    "WeekDuty",
]

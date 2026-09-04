"""The immutable world, loaded once and shared everywhere.

`WorldState` holds every shipped record plus the indices that the shipped data
does not carry. The most important of those is `week_duties`: there is **no**
reverse index from crew to pairing anywhere in the dataset, so it is built here
by scanning all 39 pairings, and every window sum, rest check and overlap check
downstream depends on it.

Nothing mutates a `WorldState` after construction. A simulation runs on a
`WorldOverlay`, which is a cheap copy-on-write layer over it.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import date as DateType  # noqa: N812
from datetime import datetime as DateTime  # noqa: N812
from datetime import timedelta
from pathlib import Path
from typing import Literal

from crewops.domain.loader import RawDataset, load_raw
from crewops.domain.models import (
    EMPTY_DAY,
    Certification,
    Costs,
    Crew,
    DayHistory,
    DutyClock,
    FlaggedException,
    Flight,
    Pairing,
    PairingDay,
    Reserve,
    RiskSignal,
    RuleBook,
    WeekDuty,
)
from crewops.domain.time_utils import window_dates

#: Which accrual a window sums.
ClockKind = Literal["duty", "flight"]


class WorldState:
    """The whole dataset, indexed, immutable after construction."""

    __slots__ = (
        "_cert_expiry",
        "_certs_by_crew",
        "_clock_by_crew",
        "_crew_by_id",
        "_crew_ids_by_base",
        "_crew_ids_by_rank",
        "_crew_ids_by_rating",
        "_flight_by_id",
        "_flight_ids_by_date",
        "_flight_ids_by_no",
        "_flight_ids_by_route",
        "_history",
        "_pairing_by_id",
        "_pairing_day_by_flight",
        "_pairing_id_by_flight",
        "_pairing_ids_by_aircraft",
        "_pairing_ids_by_crew",
        "_pairing_ids_by_date",
        "_reserve_by_id",
        "_risk_by_crew",
        "_week_duties",
        "certifications",
        "costs",
        "crew",
        "data_dir",
        "flagged_exceptions",
        "flights",
        "pairings",
        "reserves",
        "risk_signals",
        "rosters_note",
        "rules",
        "snapshot",
    )

    def __init__(self, raw: RawDataset) -> None:
        self.data_dir: Path = raw.data_dir
        self.flights: tuple[Flight, ...] = raw.flights
        self.crew: tuple[Crew, ...] = raw.crew
        self.pairings: tuple[Pairing, ...] = raw.rosters.pairings
        self.flagged_exceptions: tuple[FlaggedException, ...] = raw.rosters.flagged_exceptions
        self.rosters_note: str = raw.rosters.note
        self.reserves: tuple[Reserve, ...] = raw.reserves
        self.certifications: tuple[Certification, ...] = raw.certifications
        self.rules: RuleBook = raw.rules
        self.costs: Costs = raw.costs
        self.risk_signals: tuple[RiskSignal, ...] = raw.risk_signals

        # The snapshot is a constant across duty_clocks and risk_signals.
        self.snapshot: DateTime = raw.duty_clocks[0].as_of_utc

        self._build_flight_indices()
        self._build_crew_indices()
        self._build_roster_indices()
        self._build_clock_indices(raw.duty_clocks)

    # ------------------------------------------------------------- construction

    def _build_flight_indices(self) -> None:
        by_id: dict[str, Flight] = {}
        by_no: dict[str, list[str]] = defaultdict(list)
        by_date: dict[DateType, list[str]] = defaultdict(list)
        by_route: dict[tuple[str, str], list[str]] = defaultdict(list)
        for flight in self.flights:
            by_id[flight.flight_id] = flight
            by_no[flight.flight_no].append(flight.flight_id)
            by_date[flight.date].append(flight.flight_id)
            by_route[flight.route].append(flight.flight_id)
        self._flight_by_id = by_id
        self._flight_ids_by_no = {k: tuple(v) for k, v in by_no.items()}
        self._flight_ids_by_date = {k: tuple(v) for k, v in by_date.items()}
        self._flight_ids_by_route = {k: tuple(v) for k, v in by_route.items()}

    def _build_crew_indices(self) -> None:
        by_id: dict[str, Crew] = {}
        by_base: dict[str, list[str]] = defaultdict(list)
        by_rank: dict[str, list[str]] = defaultdict(list)
        by_rating: dict[str, list[str]] = defaultdict(list)
        for member in self.crew:
            by_id[member.crew_id] = member
            by_base[member.base].append(member.crew_id)
            by_rank[member.rank].append(member.crew_id)
            for rating in member.ratings:
                by_rating[rating].append(member.crew_id)
        self._crew_by_id = by_id
        self._crew_ids_by_base = {k: tuple(v) for k, v in by_base.items()}
        self._crew_ids_by_rank = {k: tuple(v) for k, v in by_rank.items()}
        self._crew_ids_by_rating = {k: tuple(v) for k, v in by_rating.items()}

        certs: dict[str, list[Certification]] = defaultdict(list)
        expiry: dict[str, dict[str, DateType]] = defaultdict(dict)
        for cert in self.certifications:
            certs[cert.crew_id].append(cert)
            expiry[cert.crew_id][cert.cert_type] = cert.valid_to
        self._certs_by_crew = {k: tuple(v) for k, v in certs.items()}
        self._cert_expiry = {k: dict(v) for k, v in expiry.items()}

        self._reserve_by_id = {r.crew_id: r for r in self.reserves}
        self._risk_by_crew = {r.crew_id: r for r in self.risk_signals}

    def _build_roster_indices(self) -> None:
        by_id: dict[str, Pairing] = {}
        by_date: dict[DateType, list[str]] = defaultdict(list)
        by_aircraft: dict[str, list[str]] = defaultdict(list)
        pairing_of_flight: dict[str, str] = {}
        day_of_flight: dict[str, PairingDay] = {}
        pairings_of_crew: dict[str, list[str]] = defaultdict(list)
        duties: dict[str, list[WeekDuty]] = defaultdict(list)

        for pairing in self.pairings:
            by_id[pairing.pairing_id] = pairing
            by_aircraft[pairing.aircraft].append(pairing.pairing_id)
            for member in pairing.crew:
                pairings_of_crew[member.crew_id].append(pairing.pairing_id)
            for day in pairing.days:
                by_date[day.date].append(pairing.pairing_id)
                block = 0.0
                aircraft_type = ""
                for fid in day.flights:
                    pairing_of_flight[fid] = pairing.pairing_id
                    day_of_flight[fid] = day
                    flight = self._flight_by_id[fid]
                    block += flight.block_hours
                    aircraft_type = flight.aircraft_type
                for member in pairing.crew:
                    duties[member.crew_id].append(
                        WeekDuty(
                            crew_id=member.crew_id,
                            duty_date=day.date,
                            report_utc=day.report_utc,
                            release_utc=day.release_utc,
                            duty_hours=day.duty_hours,
                            block_hours=round(block, 2),
                            pairing_id=pairing.pairing_id,
                            sectors=day.sectors,
                            aircraft_type=aircraft_type,
                        )
                    )

        self._pairing_by_id = by_id
        self._pairing_ids_by_date = {k: tuple(v) for k, v in by_date.items()}
        self._pairing_ids_by_aircraft = {k: tuple(v) for k, v in by_aircraft.items()}
        self._pairing_id_by_flight = pairing_of_flight
        self._pairing_day_by_flight = day_of_flight
        self._pairing_ids_by_crew = {k: tuple(v) for k, v in pairings_of_crew.items()}
        self._week_duties = {
            cid: tuple(sorted(v, key=lambda d: d.duty_date)) for cid, v in duties.items()
        }

    def _build_clock_indices(self, clocks: tuple[DutyClock, ...]) -> None:
        self._clock_by_crew = {c.crew_id: c for c in clocks}
        history: dict[str, dict[DateType, DayHistory]] = {}
        for clock in clocks:
            history[clock.crew_id] = {entry.date: entry for entry in clock.daily_history}
        self._history = history

    # ------------------------------------------------------------------- crew

    def crew_member(self, crew_id: str) -> Crew | None:
        return self._crew_by_id.get(crew_id)

    def require_crew(self, crew_id: str) -> Crew:
        member = self._crew_by_id.get(crew_id)
        if member is None:
            raise KeyError(f"No crew member {crew_id} in the dataset")
        return member

    def crew_ids_by_base(self, base: str) -> tuple[str, ...]:
        return self._crew_ids_by_base.get(base, ())

    def crew_ids_by_rank(self, rank: str) -> tuple[str, ...]:
        return self._crew_ids_by_rank.get(rank, ())

    def crew_ids_by_rating(self, aircraft_type: str) -> tuple[str, ...]:
        return self._crew_ids_by_rating.get(aircraft_type, ())

    # ---------------------------------------------------------------- flights

    def flight(self, flight_id: str) -> Flight | None:
        return self._flight_by_id.get(flight_id)

    def require_flight(self, flight_id: str) -> Flight:
        flight = self._flight_by_id.get(flight_id)
        if flight is None:
            raise KeyError(f"No flight {flight_id} in the dataset")
        return flight

    def flights_on(self, day: DateType) -> tuple[Flight, ...]:
        return tuple(self._flight_by_id[f] for f in self._flight_ids_by_date.get(day, ()))

    def flights_numbered(self, flight_no: str) -> tuple[Flight, ...]:
        return tuple(self._flight_by_id[f] for f in self._flight_ids_by_no.get(flight_no, ()))

    def flight_on(self, flight_no: str, day: DateType) -> Flight | None:
        return self._flight_by_id.get(f"{flight_no}-{day.isoformat()}")

    def flights_on_route(self, origin: str, destination: str) -> tuple[Flight, ...]:
        ids = self._flight_ids_by_route.get((origin, destination), ())
        return tuple(self._flight_by_id[f] for f in ids)

    @property
    def stations(self) -> tuple[str, ...]:
        found = {f.dep_station for f in self.flights} | {f.arr_station for f in self.flights}
        return tuple(sorted(found))

    @property
    def date_range(self) -> tuple[DateType, DateType]:
        days = sorted(self._flight_ids_by_date)
        return (days[0], days[-1])

    def window_dates_of_week(self) -> tuple[DateType, ...]:
        """Every date the schedule covers, 2026-09-14 to 2026-09-20 inclusive."""
        return tuple(sorted(self._flight_ids_by_date))

    # ---------------------------------------------------------------- rosters

    def pairing(self, pairing_id: str) -> Pairing | None:
        return self._pairing_by_id.get(pairing_id)

    def require_pairing(self, pairing_id: str) -> Pairing:
        pairing = self._pairing_by_id.get(pairing_id)
        if pairing is None:
            raise KeyError(f"No pairing {pairing_id} in the dataset")
        return pairing

    def pairings_on(self, day: DateType) -> tuple[Pairing, ...]:
        return tuple(self._pairing_by_id[p] for p in self._pairing_ids_by_date.get(day, ()))

    def pairings_for_aircraft(self, aircraft: str) -> tuple[Pairing, ...]:
        ids = self._pairing_ids_by_aircraft.get(aircraft, ())
        return tuple(self._pairing_by_id[p] for p in ids)

    def pairing_for_flight(self, flight_id: str) -> Pairing | None:
        pairing_id = self._pairing_id_by_flight.get(flight_id)
        return self._pairing_by_id.get(pairing_id) if pairing_id else None

    def pairing_day_for_flight(self, flight_id: str) -> PairingDay | None:
        return self._pairing_day_by_flight.get(flight_id)

    def pairing_ids_for_crew(self, crew_id: str) -> tuple[str, ...]:
        return self._pairing_ids_by_crew.get(crew_id, ())

    def week_duties(self, crew_id: str) -> tuple[WeekDuty, ...]:
        """Every rostered duty this crew member holds in the schedule week."""
        return self._week_duties.get(crew_id, ())

    def block_hours_of(self, flight_ids: tuple[str, ...]) -> float:
        return round(sum(self._flight_by_id[f].block_hours for f in flight_ids), 2)

    def seats_of(self, flight_ids: tuple[str, ...]) -> int:
        return sum(self._flight_by_id[f].seats for f in flight_ids)

    # ----------------------------------------------------------------- clocks

    def duty_clock(self, crew_id: str) -> DutyClock | None:
        return self._clock_by_crew.get(crew_id)

    def history_on(self, crew_id: str, day: DateType) -> DayHistory:
        """Pre snapshot accrual for one date. Absent dates read as zero."""
        return self._history.get(crew_id, {}).get(day, EMPTY_DAY)

    # ---------------------------------------------------------- certifications

    def certifications_for(self, crew_id: str) -> tuple[Certification, ...]:
        return self._certs_by_crew.get(crew_id, ())

    def certification_expiry(self, crew_id: str) -> dict[str, DateType]:
        """`cert_type -> valid_to`. `valid_from` is unusable and never returned."""
        return dict(self._cert_expiry.get(crew_id, {}))

    def expired_certifications(self, crew_id: str, on_date: DateType) -> tuple[Certification, ...]:
        """Certificates not valid on `on_date`. The test is `valid_to >= on_date`."""
        return tuple(c for c in self.certifications_for(crew_id) if not c.valid_on(on_date))

    # --------------------------------------------------------------- reserves

    def reserve(self, crew_id: str) -> Reserve | None:
        return self._reserve_by_id.get(crew_id)

    def is_reserve(self, crew_id: str) -> bool:
        return crew_id in self._reserve_by_id

    @property
    def reserve_ids(self) -> frozenset[str]:
        return frozenset(self._reserve_by_id)

    def reserves_on(self, day: DateType) -> tuple[Reserve, ...]:
        """Reserves on call for a date, in shipped file order.

        Every reserve carries the full week, so this never discriminates. The
        on call window is the only real filter.
        """
        return tuple(r for r in self.reserves if day in r.dates)

    # ------------------------------------------------------------------- risk

    def risk_signal(self, crew_id: str) -> RiskSignal | None:
        return self._risk_by_crew.get(crew_id)

    def flagged_exception_for(self, crew_id: str, day: DateType) -> FlaggedException | None:
        for flagged in self.flagged_exceptions:
            if flagged.crew_id == crew_id and flagged.date == day:
                return flagged
        return None

    # ---------------------------------------------------------------- overlay

    def overlay(self) -> WorldOverlay:
        """An identity overlay. Every simulation starts from one of these."""
        return WorldOverlay(self)


class WorldOverlay:
    """A copy-on-write layer over `WorldState`.

    A simulation says "C-1042 is absent" or "C-3310 takes P-2291" without
    touching the base state, so two simulations can never contaminate each
    other and the base is always the shipped truth. Every mutator returns a new
    overlay rather than modifying this one.

    Only the roster is overlaid. Flights, crew records, certificates and rates
    are static facts and are read straight off `self.base`.
    """

    __slots__ = ("_absent", "_added", "_removed_pairings", "base")

    def __init__(
        self,
        base: WorldState,
        *,
        absent: frozenset[str] = frozenset(),
        removed_pairings: frozenset[tuple[str, str]] = frozenset(),
        added: tuple[WeekDuty, ...] = (),
    ) -> None:
        self.base = base
        self._absent = absent
        #: (crew_id, pairing_id) pairs whose duties are lifted off the roster.
        self._removed_pairings = removed_pairings
        self._added = added

    # ------------------------------------------------------------- projection

    def week_duties(self, crew_id: str) -> tuple[WeekDuty, ...]:
        """The crew member's duties as this overlay sees them, sorted by date."""
        duties = [
            duty
            for duty in self.base.week_duties(crew_id)
            if (crew_id, duty.pairing_id) not in self._removed_pairings
        ]
        duties.extend(duty for duty in self._added if duty.crew_id == crew_id)
        duties.sort(key=lambda d: (d.duty_date, d.report_utc))
        return tuple(duties)

    def is_absent(self, crew_id: str) -> bool:
        return crew_id in self._absent

    def is_available(self, crew_id: str) -> bool:
        """Active in the base data and not marked absent by this overlay.

        `leave` and `training` crew are not available. They are dropped before
        any rule runs and never reported as rule failures.
        """
        member = self.base.crew_member(crew_id)
        return member is not None and member.is_active and crew_id not in self._absent

    @property
    def absent_crew(self) -> frozenset[str]:
        return self._absent

    @property
    def added_duties(self) -> tuple[WeekDuty, ...]:
        return self._added

    # --------------------------------------------------------------- mutators

    def with_absence(self, crew_id: str) -> WorldOverlay:
        """Mark a crew member unavailable and lift every duty they hold."""
        removed = self._removed_pairings | {
            (crew_id, duty.pairing_id) for duty in self.base.week_duties(crew_id)
        }
        return WorldOverlay(
            self.base,
            absent=self._absent | {crew_id},
            removed_pairings=removed,
            added=tuple(d for d in self._added if d.crew_id != crew_id),
        )

    def without_pairing(self, crew_id: str, pairing_id: str) -> WorldOverlay:
        """Lift one crew member off one pairing, leaving the rest of their week."""
        return WorldOverlay(
            self.base,
            absent=self._absent,
            removed_pairings=self._removed_pairings | {(crew_id, pairing_id)},
            added=self._added,
        )

    def with_duties(self, duties: tuple[WeekDuty, ...]) -> WorldOverlay:
        """Add proposed duties, for example a cover assignment being tested."""
        return WorldOverlay(
            self.base,
            absent=self._absent,
            removed_pairings=self._removed_pairings,
            added=self._added + duties,
        )

    # ----------------------------------------------------------------- clocks

    @staticmethod
    def window_dates(end: DateType, days: int) -> list[DateType]:
        """`[end - days + 1, end]`, inclusive. Calendar dates, not rolling hours."""
        return window_dates(end, days)

    def window_hours(self, crew_id: str, end: DateType, *, days: int, kind: ClockKind) -> float:
        """Accrued duty or block hours over a calendar day window.

        History plus roster, both clipped to the window, rounded to two places
        at the end. Verified 150/150 against the shipped `duty_hours_7d` and
        `flight_hours_28d`.

        2026-09-14 draws from **both** sources for 11 crew, because
        `daily_history` ends that day and the roster week begins it. The
        shipped summary fields carry that double count and the dataset's own
        validator asserts it. It is the convention. Do not remove it.
        """
        start = end - timedelta(days=days - 1)
        total = 0.0
        for day in window_dates(end, days):
            entry = self.base.history_on(crew_id, day)
            total += entry.duty_hours if kind == "duty" else entry.flight_hours
        for duty in self.week_duties(crew_id):
            if start <= duty.duty_date <= end:
                total += duty.duty_hours if kind == "duty" else duty.block_hours
        return round(total, 2)

    def duty_hours_7d(self, crew_id: str, end: DateType) -> float:
        return self.window_hours(crew_id, end, days=7, kind="duty")

    def flight_hours_28d(self, crew_id: str, end: DateType) -> float:
        return self.window_hours(crew_id, end, days=28, kind="flight")


def load_world(data_dir: Path | None = None) -> WorldState:
    """Load and index the shipped dataset. The one entry point."""
    return WorldState(load_raw(data_dir))


__all__ = ["ClockKind", "WorldOverlay", "WorldState", "load_world"]

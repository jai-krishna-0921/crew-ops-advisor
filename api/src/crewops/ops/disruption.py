"""Modelling a disruption: absence, reassignment, station closure and delay.

Every simulation runs on a `WorldOverlay`, never on the base state, so two
simulations cannot contaminate each other and the shipped data is always
recoverable.

Two delay models coexist in the shipped answer keys and both are implemented,
because they answer different questions:

* **Release slides, report does not** (scenario S3, a station closure part way
  through a duty). The crew have already reported; the delay pushes the end of
  the duty out, so `fdp_after = original duty length + delay`.
* **The whole duty slides** (scenario S4, a technical delay before the first
  departure). Report and release both move, so the duty length grows by the
  delay as well.

Using the wrong one produces a plausible number and the wrong verdict.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date as DateType  # noqa: N812
from datetime import datetime as DateTime  # noqa: N812
from datetime import timedelta

from crewops.contracts.evidence import Fact, Provenance
from crewops.contracts.ops import (
    DownstreamRisk,
    FlightRef,
    ImpactReport,
    RiskSeverity,
)
from crewops.domain import Flight, WorldOverlay, WorldState, hours_between
from crewops.rules import LegalityEngine, ProposedDuty, proposed_duty_from_flights

#: The shipped `action` string for an infeasible closure delay separates the
#: two clauses with U+2014. It is reproduced here from its escape so that the
#: output matches the answer key byte for byte without an em dash appearing in
#: source we author.
_SHIPPED_DASH = "\u2014"

CLOSURE_ACTION_LEGAL = "delay (crew legal)"
CLOSURE_ACTION_INFEASIBLE = (
    f"delay exceeds crew FDP {_SHIPPED_DASH} re-crew tail legs from reserves or cancel"
)

#: One turnaround after the station reopens, before the first movement.
REOPEN_TURNAROUND_MINUTES = 30

_SOURCE = "crewops.ops.disruption"


@dataclass(frozen=True)
class ClosureAssessment:
    """One affected flight, its minimum delay and what that does to crew FDP."""

    flight_id: str
    pairing_id: str
    min_delay_hours: float
    crew_fdp_after_delay: float
    fdp_limit: float
    action: str

    def as_answer_key(self) -> dict[str, object]:
        return {
            "flight_id": self.flight_id,
            "pairing_id": self.pairing_id,
            "min_delay_hours": self.min_delay_hours,
            "crew_fdp_after_delay": self.crew_fdp_after_delay,
            "fdp_limit": self.fdp_limit,
            "action": self.action,
        }

    @property
    def feasible(self) -> bool:
        return self.action == CLOSURE_ACTION_LEGAL


@dataclass(frozen=True)
class ClosureResult:
    affected: tuple[str, ...]
    assessments: tuple[ClosureAssessment, ...]
    station: str
    window_start: DateTime
    window_end: DateTime
    impact: ImpactReport


@dataclass(frozen=True)
class DelayResult:
    """A whole duty pushed back, and whether the rostered crew can still fly it."""

    pairing_id: str
    duty_date: DateType
    delay_hours: float
    fdp_before: float
    fdp_after_delay: float
    fdp_limit: float
    breach: bool
    breach_detail: str
    partial_duty_flights: tuple[str, ...]
    partial_fdp: float
    partial_fdp_limit: float
    dropped_flights: tuple[str, ...]
    impact: ImpactReport


class DisruptionSimulator:
    """Deterministic what-if modelling. No language model is reachable from here."""

    def __init__(self, world: WorldState, engine: LegalityEngine) -> None:
        self.world = world
        self.engine = engine

    # ------------------------------------------------------------- absence

    def absence(
        self,
        *,
        crew_id: str,
        from_date: DateType,
        to_date: DateType | None = None,
        reason: str = "sick call",
        as_of: DateTime | None = None,
    ) -> tuple[ImpactReport, WorldOverlay]:
        """Model a crew member becoming unavailable, and cascade it.

        Losing a crew member breaks **every day of every pairing they hold** in
        the window, not just today's. P-2291 loses its captain on day 1 and day
        2 is equally at risk, because the aircraft overnights at DEL and the
        cover has to take the whole remaining pairing.
        """
        end = to_date or from_date
        member = self.world.crew_member(crew_id)
        overlay = self.world.overlay().with_absence(crew_id)

        duties = [
            duty
            for duty in self.world.week_duties(crew_id)
            if from_date <= duty.duty_date <= end
        ]
        broken_pairings = sorted({duty.pairing_id for duty in duties})

        # Every day of a broken pairing is uncrewed, including days outside the
        # absence window, because the cover must take the pairing whole.
        uncrewed_ids: list[str] = []
        for pairing_id in broken_pairings:
            uncrewed_ids.extend(self.world.require_pairing(pairing_id).flight_ids)

        immediate_ids = [
            f
            for duty in duties
            for f in self._flights_of(duty.pairing_id, duty.duty_date)
        ]
        immediate_pax = self.world.seats_of(tuple(immediate_ids))
        total_pax = self.world.seats_of(tuple(uncrewed_ids))

        risks = self._absence_risks(
            crew_id, broken_pairings, duties_dates={d.duty_date for d in duties}
        )
        colleagues = sorted(
            {
                m.crew_id
                for pairing_id in broken_pairings
                for m in self.world.require_pairing(pairing_id).crew
                if m.crew_id != crew_id
            }
        )
        stations = sorted(
            {self.world.require_flight(f).dep_station for f in uncrewed_ids}
            | {self.world.require_flight(f).arr_station for f in uncrewed_ids}
        )

        role = member.rank if member else "crew member"
        name = f"{role} {crew_id}"
        explanation = (
            f"{name} is unavailable from {from_date} ({reason}). "
            f"That breaks {len(broken_pairings)} pairing"
            f"{'s' if len(broken_pairings) != 1 else ''} "
            f"({', '.join(broken_pairings) or 'none'}) and leaves "
            f"{len(uncrewed_ids)} leg{'s' if len(uncrewed_ids) != 1 else ''} without "
            f"a {role}. {immediate_pax} passengers are exposed on the day of the "
            f"absence and {total_pax} across the whole broken pairing."
            if broken_pairings
            else (
                f"{name} is unavailable from {from_date} ({reason}), but holds no "
                f"rostered duty between {from_date} and {end}, so no flight is "
                "left uncrewed."
            )
        )

        report = ImpactReport(
            trigger=f"{name} unavailable from {from_date} to {end} ({reason})",
            trigger_kind="crew_absence",
            as_of=as_of or self.world.snapshot,
            uncrewed_flights=[self._flight_ref(f) for f in uncrewed_ids],
            pairings_broken=broken_pairings,
            crew_affected=[crew_id, *colleagues],
            stations_affected=stations,
            passengers_affected=immediate_pax,
            downstream_risks=risks,
            explanation=explanation,
            facts=self._absence_facts(
                crew_id, broken_pairings, uncrewed_ids, immediate_ids, immediate_pax, total_pax
            ),
        )
        return report, overlay

    def _flights_of(self, pairing_id: str, on_date: DateType) -> tuple[str, ...]:
        pairing = self.world.require_pairing(pairing_id)
        for day in pairing.days:
            if day.date == on_date:
                return day.flights
        return ()

    def _absence_risks(
        self, crew_id: str, pairings: Sequence[str], *, duties_dates: set[DateType]
    ) -> list[DownstreamRisk]:
        """The consequences a controller misses: later days, and tight colleagues."""
        risks: list[DownstreamRisk] = []
        overlay = self.world.overlay()

        for pairing_id in pairings:
            pairing = self.world.require_pairing(pairing_id)
            for day in pairing.days:
                if day.date in duties_dates:
                    continue
                risks.append(
                    DownstreamRisk(
                        crew_id=crew_id,
                        pairing_id=pairing_id,
                        severity=RiskSeverity.HIGH,
                        detail=(
                            f"{pairing_id} continues on {day.date} with "
                            f"{len(day.flights)} more legs. The aircraft is away from "
                            "base overnight, so the cover has to take the whole "
                            "remaining pairing rather than one day of it"
                        ),
                        duty_date=day.date,
                    )
                )

        for pairing_id in pairings:
            pairing = self.world.require_pairing(pairing_id)
            for member in pairing.crew:
                if member.crew_id == crew_id:
                    continue
                for day in pairing.days:
                    projected = overlay.duty_hours_7d(member.crew_id, day.date)
                    headroom = round(self.engine.max_duty_7d - projected, 2)
                    if headroom <= 10.0:
                        risks.append(
                            DownstreamRisk(
                                crew_id=member.crew_id,
                                pairing_id=pairing_id,
                                rule_id="RULE-DUTY-02",
                                severity=(
                                    RiskSeverity.CRITICAL if headroom <= 5 else RiskSeverity.MEDIUM
                                ),
                                detail=(
                                    f"{member.crew_id} is already at {projected}h of "
                                    f"{self.engine.max_duty_7d:.0f}h over the 7 days "
                                    f"ending {day.date}, leaving {headroom}h. They are "
                                    "a poor candidate to absorb an extension"
                                ),
                                duty_date=day.date,
                            )
                        )
                    break
        return risks

    def _absence_facts(
        self,
        crew_id: str,
        pairings: Sequence[str],
        uncrewed: Sequence[str],
        immediate: Sequence[str],
        immediate_pax: int,
        total_pax: int,
    ) -> list[Fact]:
        return [
            Fact(
                key=f"{crew_id}.absence.pairings_broken",
                label="Pairings broken",
                value=len(pairings),
                unit="count",
                provenance=Provenance.COMPUTED,
                source=_SOURCE,
                derivation=f"pairings holding {crew_id} in the absence window: "
                + (", ".join(pairings) or "none"),
            ),
            Fact(
                key=f"{crew_id}.absence.uncrewed_flights",
                label="Legs left uncrewed",
                value=len(uncrewed),
                unit="count",
                provenance=Provenance.COMPUTED,
                source=_SOURCE,
                derivation="every leg of every day of each broken pairing",
            ),
            Fact(
                key=f"{crew_id}.absence.passengers_immediate",
                label="Passengers exposed on the day of the absence",
                value=immediate_pax,
                unit="count",
                provenance=Provenance.COMPUTED,
                source=_SOURCE,
                derivation=(
                    f"{len(immediate)} legs x seats from flights.json = {immediate_pax}"
                ),
            ),
            Fact(
                key=f"{crew_id}.absence.passengers_total",
                label="Passengers exposed across the whole broken pairing",
                value=total_pax,
                unit="count",
                provenance=Provenance.COMPUTED,
                source=_SOURCE,
                derivation=f"{len(uncrewed)} legs x seats from flights.json = {total_pax}",
            ),
        ]

    # ------------------------------------------------------ station closure

    def station_closure(
        self, *, station: str, from_time: DateTime, to_time: DateTime
    ) -> ClosureResult:
        """Which flights a closure touches, and what the delay does to crew FDP.

        The window is **half-open**, `[start, end)`: a movement exactly at the
        reopen time is not affected. The delay is measured from the event at the
        closed station, which is the departure when the flight departs there
        inside the window and the arrival otherwise, forward to reopen plus one
        turnaround.
        """
        affected: list[Flight] = []
        for flight in self.world.flights:
            departs_in = (
                flight.dep_station == station and from_time <= flight.dep_utc < to_time
            )
            arrives_in = flight.arr_station == station and from_time <= flight.arr_utc < to_time
            if departs_in or arrives_in:
                affected.append(flight)

        target = to_time + timedelta(minutes=REOPEN_TURNAROUND_MINUTES)
        assessments: list[ClosureAssessment] = []
        for flight in affected:
            pairing = self.world.pairing_for_flight(flight.flight_id)
            day = self.world.pairing_day_for_flight(flight.flight_id)
            if pairing is None or day is None:  # pragma: no cover - every leg is covered
                continue
            departs_in_window = (
                flight.dep_station == station and from_time <= flight.dep_utc < to_time
            )
            anchor = flight.dep_utc if departs_in_window else flight.arr_utc
            shift = hours_between(anchor, target)
            # The crew have already reported, so the delay pushes the release
            # out and the report stays where it is.
            fdp_after = hours_between(day.report_utc, day.release_utc + timedelta(hours=shift))
            limit = self.engine.fdp_limit_for(day.sectors)
            assessments.append(
                ClosureAssessment(
                    flight_id=flight.flight_id,
                    pairing_id=pairing.pairing_id,
                    min_delay_hours=round(shift, 2),
                    crew_fdp_after_delay=round(fdp_after, 2),
                    fdp_limit=limit,
                    action=(
                        CLOSURE_ACTION_LEGAL
                        if fdp_after <= limit
                        else CLOSURE_ACTION_INFEASIBLE
                    ),
                )
            )

        impact = self._closure_impact(station, from_time, to_time, assessments)
        return ClosureResult(
            affected=tuple(a.flight_id for a in assessments),
            assessments=tuple(assessments),
            station=station,
            window_start=from_time,
            window_end=to_time,
            impact=impact,
        )

    def _closure_impact(
        self,
        station: str,
        from_time: DateTime,
        to_time: DateTime,
        assessments: Sequence[ClosureAssessment],
    ) -> ImpactReport:
        infeasible = [a for a in assessments if not a.feasible]
        uncrewed = [a.flight_id for a in infeasible]
        pairings = sorted({a.pairing_id for a in assessments})
        crew_affected = sorted(
            {
                member.crew_id
                for pairing_id in pairings
                for member in self.world.require_pairing(pairing_id).crew
            }
        )
        risks = [
            DownstreamRisk(
                flight_no=self.world.require_flight(a.flight_id).flight_no,
                pairing_id=a.pairing_id,
                rule_id="RULE-FDP-01",
                severity=RiskSeverity.CRITICAL,
                detail=(
                    f"Delaying to reopen plus {REOPEN_TURNAROUND_MINUTES} minutes runs "
                    f"the duty to {a.crew_fdp_after_delay}h against a {a.fdp_limit}h "
                    f"limit. The rostered crew cannot legally complete it"
                ),
                duty_date=self.world.require_flight(a.flight_id).date,
            )
            for a in infeasible
        ]
        return ImpactReport(
            trigger=(
                f"{station} closed {from_time:%Y-%m-%d %H:%M}Z to {to_time:%H:%M}Z"
            ),
            trigger_kind="station_closure",
            as_of=self.world.snapshot,
            uncrewed_flights=[self._flight_ref(f) for f in uncrewed],
            pairings_broken=sorted({a.pairing_id for a in infeasible}),
            crew_affected=crew_affected,
            stations_affected=[station],
            passengers_affected=self.world.seats_of(tuple(uncrewed)),
            downstream_risks=risks,
            explanation=(
                f"{len(assessments)} flights touch {station} inside the window. "
                f"Delaying each to reopen plus a {REOPEN_TURNAROUND_MINUTES} minute "
                f"turnaround keeps {len(assessments) - len(infeasible)} of them within "
                f"crew FDP. The other {len(infeasible)} exceed RULE-FDP-01 and need "
                "reserve re-crew on the tail legs, or cancellation."
            ),
            facts=[
                Fact(
                    key=f"closure.{station}.affected",
                    label="Flights affected",
                    value=len(assessments),
                    unit="count",
                    provenance=Provenance.COMPUTED,
                    source=_SOURCE,
                    derivation=(
                        f"departures from or arrivals into {station} inside "
                        f"[{from_time:%H:%M}, {to_time:%H:%M}), end exclusive"
                    ),
                ),
                Fact(
                    key=f"closure.{station}.infeasible",
                    label="Flights whose crew cannot absorb the delay",
                    value=len(infeasible),
                    unit="count",
                    provenance=Provenance.COMPUTED,
                    source=_SOURCE,
                    derivation="duty length plus minimum delay exceeds the FDP limit",
                ),
            ],
        )

    # ---------------------------------------------------------------- delay

    def whole_duty_delay(
        self, *, pairing_id: str, on_date: DateType, delay_hours: float
    ) -> DelayResult:
        """A technical delay before the first departure. The whole duty slides.

        Report and release both move, so the duty **length** grows by the
        delay. Dropping the tail leg then changes the sector count and
        therefore raises the FDP limit, which is why a partial re-crew is often
        legal where the full duty is not.
        """
        pairing = self.world.require_pairing(pairing_id)
        day = next((d for d in pairing.days if d.date == on_date), None)
        if day is None:
            raise KeyError(f"{pairing_id} has no duty day on {on_date}")

        fdp_before = day.duty_hours
        fdp_after = round(fdp_before + delay_hours, 2)
        limit = self.engine.fdp_limit_for(day.sectors)
        breach = fdp_after > limit

        # The partial duty a controller would actually fly: drop the last leg.
        kept = day.flights[:-1]
        dropped = day.flights[len(kept) :]
        partial = (
            proposed_duty_from_flights(self.world, kept).shifted(delay_hours)
            if kept
            else None
        )
        partial_fdp = partial.duty_hours if partial else 0.0
        partial_limit = self.engine.fdp_limit_for(len(kept)) if kept else 0.0

        detail = (
            f"RULE-FDP-01: the delayed duty runs {fdp_after}h against a {limit}h limit "
            f"for {day.sectors} sectors, so the rostered crew cannot legally complete "
            f"{self.world.require_flight(day.flights[-1]).flight_no}."
            if breach
            else (
                f"RULE-FDP-01: the delayed duty runs {fdp_after}h against a {limit}h "
                f"limit for {day.sectors} sectors, which is legal."
            )
        )

        impact = ImpactReport(
            trigger=(
                f"{pairing.aircraft} delayed {delay_hours}h before "
                f"{self.world.require_flight(day.flights[0]).flight_no} on {on_date}"
            ),
            trigger_kind="flight_delay",
            as_of=self.world.snapshot,
            uncrewed_flights=[self._flight_ref(f) for f in dropped] if breach else [],
            pairings_broken=[pairing_id] if breach else [],
            crew_affected=[m.crew_id for m in pairing.crew],
            stations_affected=sorted(
                {self.world.require_flight(f).dep_station for f in day.flights}
            ),
            passengers_affected=self.world.seats_of(dropped) if breach else 0,
            downstream_risks=(
                [
                    DownstreamRisk(
                        flight_no=self.world.require_flight(dropped[0]).flight_no,
                        pairing_id=pairing_id,
                        rule_id="RULE-FDP-01",
                        severity=RiskSeverity.CRITICAL,
                        detail=detail,
                        duty_date=on_date,
                    )
                ]
                if breach and dropped
                else []
            ),
            explanation=(
                f"The duty was {fdp_before}h and becomes {fdp_after}h once the whole "
                f"duty slides {delay_hours}h. "
                + (
                    f"That is over the {limit}h limit for {day.sectors} sectors. "
                    f"Dropping the last leg leaves {len(kept)} sectors at {partial_fdp}h "
                    f"against a {partial_limit}h limit, which the rostered crew can fly."
                    if breach and kept
                    else f"That is within the {limit}h limit."
                )
            ),
            facts=[
                Fact(
                    key=f"{pairing_id}.{on_date}.fdp_after_delay",
                    label="FDP after the delay",
                    value=fdp_after,
                    unit="hours",
                    provenance=Provenance.COMPUTED,
                    source=_SOURCE,
                    derivation=f"{fdp_before}h duty + {delay_hours}h delay = {fdp_after}h",
                ),
                Fact(
                    key=f"{pairing_id}.{on_date}.fdp_limit",
                    label="FDP limit",
                    value=limit,
                    unit="hours",
                    provenance=Provenance.COMPUTED,
                    source=_SOURCE,
                    derivation=f"13.0 - 0.5 x max(0, {day.sectors} - 2) = {limit}h",
                ),
                Fact(
                    key=f"{pairing_id}.{on_date}.partial_fdp",
                    label="FDP of the shortened duty",
                    value=partial_fdp,
                    unit="hours",
                    provenance=Provenance.COMPUTED,
                    source=_SOURCE,
                    derivation=(
                        f"dropping the last leg leaves {len(kept)} sectors, "
                        f"{partial_fdp}h against a {partial_limit}h limit"
                    ),
                ),
            ],
        )
        return DelayResult(
            pairing_id=pairing_id,
            duty_date=on_date,
            delay_hours=delay_hours,
            fdp_before=fdp_before,
            fdp_after_delay=fdp_after,
            fdp_limit=limit,
            breach=breach,
            breach_detail=detail,
            partial_duty_flights=kept,
            partial_fdp=partial_fdp,
            partial_fdp_limit=partial_limit,
            dropped_flights=dropped,
            impact=impact,
        )

    def mid_duty_delay(self, *, flight_id: str, delay_hours: float) -> DelayResult:
        """A delay that lands part way through a duty already under way.

        The crew have already reported, so the delay pushes the release out
        and the report stays exactly where it is: `fdp_after = original duty
        length + delay`. This is the model verified against scenario S3,
        generalised here to one named flight rather than every flight a
        station closure window happens to touch. `whole_duty_delay` computes
        the same breach arithmetic for a delay before the first departure;
        the two differ in which duty gets offered as the partial re-crew,
        because here the legs before the delayed one already flew on time and
        need no shift at all.
        """
        pairing = self.world.pairing_for_flight(flight_id)
        day = self.world.pairing_day_for_flight(flight_id)
        if pairing is None or day is None:
            raise KeyError(f"{flight_id} is not covered by any pairing in the roster")
        pairing_id = pairing.pairing_id
        on_date = day.date
        flight = self.world.require_flight(flight_id)

        fdp_before = day.duty_hours
        fdp_after = round(fdp_before + delay_hours, 2)
        limit = self.engine.fdp_limit_for(day.sectors)
        breach = fdp_after > limit

        # The partial duty a controller would actually fly: drop the last leg.
        # Legs before the delayed one already operated on time, so nothing
        # here needs shifting, unlike the pre-departure model where the whole
        # remaining duty moves later.
        kept = day.flights[:-1]
        dropped = day.flights[len(kept) :]
        partial = proposed_duty_from_flights(self.world, kept) if kept else None
        partial_fdp = partial.duty_hours if partial else 0.0
        partial_limit = self.engine.fdp_limit_for(len(kept)) if kept else 0.0

        detail = (
            f"RULE-FDP-01: {flight.flight_no} is delayed {delay_hours}h mid duty, so "
            f"the duty runs {fdp_after}h against a {limit}h limit for {day.sectors} "
            f"sectors, and the rostered crew cannot legally complete "
            f"{self.world.require_flight(day.flights[-1]).flight_no}."
            if breach
            else (
                f"RULE-FDP-01: {flight.flight_no} is delayed {delay_hours}h mid duty, "
                f"so the duty runs {fdp_after}h against a {limit}h limit for "
                f"{day.sectors} sectors, which is legal."
            )
        )

        impact = ImpactReport(
            trigger=(
                f"{flight.flight_no} on {on_date} delayed {delay_hours}h mid duty "
                f"({pairing.aircraft})"
            ),
            trigger_kind="flight_delay",
            as_of=self.world.snapshot,
            uncrewed_flights=[self._flight_ref(f) for f in dropped] if breach else [],
            pairings_broken=[pairing_id] if breach else [],
            crew_affected=[m.crew_id for m in pairing.crew],
            stations_affected=sorted(
                {self.world.require_flight(f).dep_station for f in day.flights}
            ),
            passengers_affected=self.world.seats_of(dropped) if breach else 0,
            downstream_risks=(
                [
                    DownstreamRisk(
                        flight_no=self.world.require_flight(dropped[0]).flight_no,
                        pairing_id=pairing_id,
                        rule_id="RULE-FDP-01",
                        severity=RiskSeverity.CRITICAL,
                        detail=detail,
                        duty_date=on_date,
                    )
                ]
                if breach and dropped
                else []
            ),
            explanation=(
                f"The duty was {fdp_before}h and becomes {fdp_after}h once "
                f"{flight.flight_no} runs {delay_hours}h late mid duty, because the "
                "crew already reported and only the release moves. "
                + (
                    f"That is over the {limit}h limit for {day.sectors} sectors. "
                    f"Dropping the last leg leaves {len(kept)} sectors at "
                    f"{partial_fdp}h against a {partial_limit}h limit, which the "
                    "rostered crew can fly on the original schedule."
                    if breach and kept
                    else f"That is within the {limit}h limit."
                )
            ),
            facts=[
                Fact(
                    key=f"{pairing_id}.{on_date}.fdp_after_delay",
                    label="FDP after the delay",
                    value=fdp_after,
                    unit="hours",
                    provenance=Provenance.COMPUTED,
                    source=_SOURCE,
                    derivation=f"{fdp_before}h duty + {delay_hours}h delay = {fdp_after}h, "
                    "report unmoved",
                ),
                Fact(
                    key=f"{pairing_id}.{on_date}.fdp_limit",
                    label="FDP limit",
                    value=limit,
                    unit="hours",
                    provenance=Provenance.COMPUTED,
                    source=_SOURCE,
                    derivation=f"13.0 - 0.5 x max(0, {day.sectors} - 2) = {limit}h",
                ),
                Fact(
                    key=f"{pairing_id}.{on_date}.partial_fdp",
                    label="FDP of the shortened duty",
                    value=partial_fdp,
                    unit="hours",
                    provenance=Provenance.COMPUTED,
                    source=_SOURCE,
                    derivation=(
                        f"dropping the last leg leaves {len(kept)} sectors, "
                        f"unshifted, {partial_fdp}h against a {partial_limit}h limit"
                    ),
                ),
            ],
        )
        return DelayResult(
            pairing_id=pairing_id,
            duty_date=on_date,
            delay_hours=delay_hours,
            fdp_before=fdp_before,
            fdp_after_delay=fdp_after,
            fdp_limit=limit,
            breach=breach,
            breach_detail=detail,
            partial_duty_flights=kept,
            partial_fdp=partial_fdp,
            partial_fdp_limit=partial_limit,
            dropped_flights=dropped,
            impact=impact,
        )

    # -------------------------------------------------------- reassignment

    def reassignment(
        self,
        *,
        crew_id: str,
        duties: Sequence[ProposedDuty],
        assignment_ref: str,
        displacing_crew_id: str | None = None,
        exclude_pairing: str | None = None,
    ) -> ImpactReport:
        """Move a crew member onto an assignment and report who it puts at risk.

        Checks the mover, the crew member being displaced, and the legs that
        the displaced crew member no longer covers.
        """
        overlay = self.world.overlay()
        if displacing_crew_id:
            overlay = overlay.with_absence(displacing_crew_id)

        mover = self.engine.assess_cover(
            overlay,
            crew_id=crew_id,
            duties=duties,
            exclude_pairing=exclude_pairing,
        )

        risks: list[DownstreamRisk] = [
            DownstreamRisk(
                crew_id=crew_id,
                pairing_id=assignment_ref,
                rule_id=trace.rule_id,
                severity=RiskSeverity.CRITICAL,
                detail=trace.arithmetic,
                duty_date=trace.duty_date,
            )
            for trace in mover.report.breaches
        ]

        uncrewed: list[str] = []
        if displacing_crew_id:
            for pairing_id in self.world.pairing_ids_for_crew(displacing_crew_id):
                if pairing_id == exclude_pairing:
                    continue
                uncrewed.extend(self.world.require_pairing(pairing_id).flight_ids)
                risks.append(
                    DownstreamRisk(
                        crew_id=displacing_crew_id,
                        pairing_id=pairing_id,
                        severity=RiskSeverity.HIGH,
                        detail=(
                            f"{displacing_crew_id} still holds {pairing_id}, which now "
                            "needs its own cover"
                        ),
                    )
                )

        verdict = "clears all seven rules" if mover.ok else "breaches: " + mover.reason
        return ImpactReport(
            trigger=f"Move {crew_id} onto {assignment_ref}",
            trigger_kind="reassignment",
            as_of=self.world.snapshot,
            uncrewed_flights=[self._flight_ref(f) for f in uncrewed],
            pairings_broken=sorted({assignment_ref}) if not mover.ok else [],
            crew_affected=[c for c in (crew_id, displacing_crew_id) if c],
            stations_affected=sorted({d.origin for d in duties if d.origin}),
            passengers_affected=self.world.seats_of(tuple(uncrewed)),
            downstream_risks=risks,
            explanation=(
                f"Moving {crew_id} onto {assignment_ref} {verdict}."
                + (
                    f" {displacing_crew_id} is displaced and their remaining "
                    f"{len(uncrewed)} legs need cover."
                    if displacing_crew_id
                    else ""
                )
            ),
            facts=[
                Fact(
                    key=f"{crew_id}.reassignment.legal",
                    label="Reassignment is legal",
                    value=mover.ok,
                    unit="boolean",
                    provenance=Provenance.COMPUTED,
                    source=_SOURCE,
                    derivation=mover.reason or "all seven rules pass on every duty day",
                )
            ],
        )

    # -------------------------------------------------------------- helpers

    def _flight_ref(self, flight_id: str) -> FlightRef:
        flight = self.world.require_flight(flight_id)
        pairing = self.world.pairing_for_flight(flight_id)
        return FlightRef(
            flight_no=flight.flight_no,
            origin=flight.dep_station,
            destination=flight.arr_station,
            departure=flight.dep_utc,
            arrival=flight.arr_utc,
            aircraft_type=flight.aircraft_type,
            passengers=flight.seats,
            pairing_id=pairing.pairing_id if pairing else None,
        )


__all__ = [
    "CLOSURE_ACTION_INFEASIBLE",
    "CLOSURE_ACTION_LEGAL",
    "REOPEN_TURNAROUND_MINUTES",
    "ClosureAssessment",
    "ClosureResult",
    "DelayResult",
    "DisruptionSimulator",
]

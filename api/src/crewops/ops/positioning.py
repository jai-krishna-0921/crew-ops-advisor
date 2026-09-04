"""Deadhead positioning: getting a crew member to a station they are not based at.

RULE-BASE-07 allows a cross base cover only with positioning, and the cost
applies. In this dataset the only positioning that exists is **DEL to BLR**,
because DEL is the only non hub base and every pairing that a DEL based crew
member could be asked to cover departs BLR.

The rule for choosing the flight is "the earliest arrival into the required
station on the cover date, from the crew member's base". On even dates that is
DX589 (arrives BLR 07:45Z); on odd dates DX589 does not operate and it is DX402
(arrives 08:45Z). That reproduces the reference implementation's date parity
without hard coding a calendar.
"""

from __future__ import annotations

from datetime import date as DateType  # noqa: N812
from datetime import datetime as DateTime  # noqa: N812
from datetime import timedelta

from crewops.domain import WorldState, hours_between
from crewops.rules import Positioning

#: Minutes from the positioning arrival to the new first departure: 15 minutes
#: to transit the terminal plus the standard 60 minute report lead. Getting
#: this wrong shifts the delay hours and therefore the cost.
TRANSIT_MINUTES = 15
REPORT_LEAD_MINUTES = 60
POSITIONING_LEAD_MINUTES = TRANSIT_MINUTES + REPORT_LEAD_MINUTES


def positioning_options(
    world: WorldState, *, from_station: str, to_station: str, on_date: DateType
) -> tuple[str, ...]:
    """Flight numbers that could position a crew member, earliest arrival first."""
    candidates = [
        flight
        for flight in world.flights_on(on_date)
        if flight.dep_station == from_station and flight.arr_station == to_station
    ]
    candidates.sort(key=lambda f: f.arr_utc)
    return tuple(f.flight_no for f in candidates)


def plan_positioning(
    world: WorldState,
    *,
    crew_id: str,
    required_station: str,
    on_date: DateType,
    first_departure_utc: DateTime,
) -> Positioning | None:
    """The cheapest delay positioning for this crew member, or None if impossible.

    Returning None is a RULE-BASE-07 exclusion, not an error: it is the honest
    statement that no same day positioning flight exists from their base.
    """
    member = world.crew_member(crew_id)
    if member is None or member.base == required_station:
        return None

    legs = [
        flight
        for flight in world.flights_on(on_date)
        if flight.dep_station == member.base and flight.arr_station == required_station
    ]
    if not legs:
        return None
    earliest = min(legs, key=lambda f: f.arr_utc)

    new_departure = earliest.arr_utc + timedelta(minutes=POSITIONING_LEAD_MINUTES)
    delay_hours = round(max(0.0, hours_between(first_departure_utc, new_departure)), 2)
    return Positioning(
        from_station=member.base,
        to_station=required_station,
        flight_no=earliest.flight_no,
        arrival_utc=earliest.arr_utc,
        delay_hours=delay_hours,
    )


__all__ = [
    "POSITIONING_LEAD_MINUTES",
    "REPORT_LEAD_MINUTES",
    "TRANSIT_MINUTES",
    "plan_positioning",
    "positioning_options",
]

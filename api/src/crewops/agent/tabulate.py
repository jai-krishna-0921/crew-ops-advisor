"""Result sets, projected into tables.

WHY THIS EXISTS. The list tools return structured payloads, and every one of
them used to reach the screen as prose: twelve reserves joined into one string,
markdown collapsed the newlines, and a controller got a ninety word run-on
sentence with fourteen clock times buried in it. A result set read as a
paragraph is a result set nobody can scan, and scanning is the entire
interaction a Tier 1 question is.

WHY IT IS A PROJECTION AND NOT A PROMPT CHANGE. A table is fact-shaped. Every
cell below is copied out of a payload field that a deterministic tool already
produced and already attested, so a `Table` is exactly as grounded as the
payload it came from and the verifier has nothing new to check. Asking a model
to format a table would put a hundred figures through a language model on the
way to the screen, which is the one thing this system does not do.

THE RULES THIS FILE OBEYS, and they are the same rules the renderers obey:

  * A cell is a field, or a join of fields with a literal separator. Nothing
    here adds, subtracts, rounds or reformats a number.
  * The one exception is a timestamp, which is rendered as its clock time when
    the date it belongs to is carried in its own column beside it. That is a
    selection from an exact value, not a derivation: `01:00` and the row's date
    together are the whole timestamp. Every table that does it says so in its
    caption, because a bare clock time with no zone on it is how an operations
    tool gets somebody to the airport an hour late.
  * An empty result produces no table. A header with no rows under it is a
    frame with nothing to read in it, and the prose already says the count.
  * Column order is the order a controller reads in: identity first, then the
    thing they filtered on, then the thing they will compare down the column.
"""

from __future__ import annotations

from datetime import date, datetime

from crewops.contracts import Table
from crewops.contracts.ops import JointPlan, Recommendation
from crewops.tools import payloads as P  # noqa: N812  short alias, matches resolve/render.py

__all__ = ["tabulate"]


def _clock(value: datetime) -> str:
    """The clock time of a timestamp, UTC, with the date left to its column."""
    return value.strftime("%H:%M")


def _date(value: date) -> str:
    """A date as ISO 8601. Serialisation, not formatting: nothing is dropped."""
    return value.isoformat()


def tabulate(payload: object) -> Table | None:
    """The table for a payload, or None when it is not a result set."""
    if isinstance(payload, P.ReserveList):
        return _reserves(payload)
    if isinstance(payload, P.CrewList):
        return _crew(payload)
    if isinstance(payload, P.FlightList):
        return _flights(payload)
    if isinstance(payload, P.RosterView):
        return _roster(payload)
    if isinstance(payload, P.CertificationList):
        return _certifications(payload)
    if isinstance(payload, Recommendation):
        return _cover_options(payload)
    if isinstance(payload, JointPlan):
        return _allocation(payload)
    return None


def _cover_options(payload: Recommendation) -> Table | None:
    """The ranked options for one gap.

    A ranked list is a result set, and it was the last one still reaching the
    screen as prose. `_render_recommendation` states the best option and the
    runner up and stops, on purpose: linearising thirteen options with their
    cost lines produced five thousand characters that buried the decision.

    That argument is against a paragraph, not against showing the ranking. So
    the ranking goes where a ranking belongs. It also fixes the case the prose
    could never reach: when a turn resolves two gaps at once, there are two of
    these payloads, and prose that renders the first one silently drops a whole
    pairing. One table per payload cannot do that.
    """
    if not payload.options:
        return None
    return Table(
        title=payload.situation or "Ranked cover options",
        columns=["Rank", "Action", "Crew", "Base", "Cost INR", "Covers", "Delay min"],
        rows=[
            [
                option.rank,
                option.action,
                option.crew_id or None,
                option.crew_base or None,
                option.cost.total_inr,
                option.coverage_summary,
                option.delay_minutes,
            ]
            for option in payload.options
        ],
        row_ids=[f"{option.rank}:{option.crew_id or 'cancel'}" for option in payload.options],
        caption=_caption(
            payload.ranking_basis,
            f"{payload.candidates_evaluated} candidates evaluated, "
            f"{len(payload.rejected)} excluded by a rule."
            if payload.candidates_evaluated
            else "",
        ),
    )


def _allocation(payload: JointPlan) -> Table | None:
    """Who takes which gap, when several are open at once.

    The point of the allocation is the constraint prose keeps losing: the same
    reserve cannot take both pairings. A row per assignment shows the pairing
    each person is going to, side by side, which is the one view that makes a
    double booking visible at a glance.
    """
    if not payload.assignments:
        return None
    # `gaps_covered` is written in assignment order by the solver, so the pair
    # is positional. A row whose gap the solver did not label is left blank
    # rather than matched to a neighbour's.
    gaps = list(payload.gaps_covered)
    gaps += [""] * (len(payload.assignments) - len(gaps))
    return Table(
        title=f"Joint allocation, {payload.objective.replace('_', ' ')}",
        columns=["Gap", "Action", "Crew", "Base", "Cost INR", "Covers"],
        rows=[
            [
                gap,
                option.action,
                option.crew_id or None,
                option.crew_base or None,
                option.cost.total_inr,
                option.coverage_summary,
            ]
            for gap, option in zip(gaps, payload.assignments, strict=True)
        ],
        row_ids=[
            option.crew_id or f"gap-{index}"
            for index, option in enumerate(payload.assignments)
        ],
        caption=_caption(
            f"Total INR {payload.total_cost.total_inr:,.0f}.",
            "No crew id appears twice: one person, one pairing.",
            "; ".join(payload.contention),
        ),
    )


def _reserves(payload: P.ReserveList) -> Table | None:
    if not payload.reserves:
        return None
    return Table(
        title=f"Reserves on call, {payload.on_date}",
        columns=["Crew", "Name", "Rank", "Base", "On call", "Reachable"],
        rows=[
            [
                reserve.crew_id,
                reserve.name,
                reserve.rank,
                reserve.base,
                f"{reserve.window_start} to {reserve.window_end}",
                reserve.reachability_minutes,
            ]
            for reserve in payload.reserves
        ],
        row_ids=[reserve.crew_id for reserve in payload.reserves],
        caption=_caption(
            payload.note,
            # Stated rather than implied. A capped list that does not say it is
            # capped is a wrong answer to "who is on reserve".
            _cap_note(len(payload.reserves), payload.total_matched, "reserve"),
            "Reachable is minutes from callout to report, from the crew record.",
        ),
    )


def _crew(payload: P.CrewList) -> Table | None:
    if not payload.crew:
        return None
    return Table(
        title=f"{payload.total_matched} crew matched",
        columns=["Crew", "Name", "Rank", "Base", "Rated", "Status"],
        rows=[
            [
                member.crew_id,
                member.name,
                member.rank,
                member.base,
                ", ".join(member.ratings) or "none on file",
                member.status,
            ]
            for member in payload.crew
        ],
        row_ids=[member.crew_id for member in payload.crew],
        caption=_caption(_cap_note(len(payload.crew), payload.total_matched, "crew")),
    )


def _flights(payload: P.FlightList) -> Table | None:
    if not payload.flights:
        return None
    return Table(
        title=f"{payload.total_matched} flights matched",
        columns=[
            "Flight",
            "Date",
            "From",
            "To",
            "Departs",
            "Arrives",
            "Block",
            "Aircraft",
            "Seats",
        ],
        rows=[
            [
                flight.flight_no,
                _date(flight.date),
                flight.dep_station,
                flight.arr_station,
                _clock(flight.dep_utc),
                _clock(flight.arr_utc),
                flight.block_hours,
                flight.aircraft_type,
                flight.seats,
            ]
            for flight in payload.flights
        ],
        row_ids=[flight.flight_id for flight in payload.flights],
        caption=_caption(
            _cap_note(len(payload.flights), payload.total_matched, "flight"),
            "Departs and arrives are clock times on the flight date, UTC.",
        ),
    )


def _roster(payload: P.RosterView) -> Table | None:
    if not payload.duties:
        return None
    return Table(
        title=f"{payload.crew_id}, {payload.from_date} to {payload.to_date}",
        columns=[
            "Date",
            "Pairing",
            "Report",
            "Release",
            "Duty",
            "Block",
            "Sectors",
            "Flights",
        ],
        rows=[
            [
                _date(duty.duty_date),
                duty.pairing_id,
                _clock(duty.report_utc),
                _clock(duty.release_utc),
                duty.duty_hours,
                duty.block_hours,
                duty.sectors,
                ", ".join(duty.flight_numbers),
            ]
            for duty in payload.duties
        ],
        row_ids=[f"{_date(duty.duty_date)}:{duty.pairing_id}" for duty in payload.duties],
        caption=_caption(
            "Report and release are clock times on the date in the first column, "
            "UTC. Duty and block are hours."
        ),
    )


def _certifications(payload: P.CertificationList) -> Table | None:
    if not payload.certifications:
        return None
    return Table(
        title=f"Certifications expiring by {payload.until}",
        columns=["Crew", "Certification", "Valid to", "Days left"],
        rows=[
            [
                cert.crew_id,
                cert.cert_type,
                _date(cert.valid_to),
                cert.days_remaining,
            ]
            for cert in payload.certifications
        ],
        row_ids=[f"{cert.crew_id}:{cert.cert_type}" for cert in payload.certifications],
        caption=_caption(
            payload.note,
            f"Measured against the snapshot date, {payload.as_of}.",
        ),
    )


def _cap_note(shown: int, total: int, noun: str) -> str:
    if shown >= total:
        return ""
    return f"Showing {shown} of {total} matching {noun} records."


def _caption(*parts: str) -> str | None:
    joined = " ".join(part for part in parts if part)
    return joined or None

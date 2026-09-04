"""Intent matching for the Tier 1 shapes widened in this pass.

`match_intent` is pure pattern matching, so these are direct, fast checks
that a question shape lands on the right tool plan without going through the
whole resolver.
"""

from __future__ import annotations

from datetime import date, datetime

from crewops.resolve.intents import match_intent
from crewops.resolve.triage import extract_entities

SNAPSHOT = datetime(2026, 9, 14, 18, 0, 0)


def test_which_aircraft_operates_matches_the_flights_intent() -> None:
    """Q05 shape. This used to fall through to the underspecified abstention
    because no pattern in the flights intent covered "which aircraft"."""
    intent = match_intent(
        "Which aircraft operates DX412 on 2026-09-15, and how many seats does it have?"
    )
    assert intent is not None
    assert intent.name == "flights"


def test_how_many_seats_matches_the_flights_intent() -> None:
    intent = match_intent("How many seats does DX412 have on 2026-09-15?")
    assert intent is not None
    assert intent.name == "flights"


def test_unfiltered_flight_question_widens_instead_of_picking_a_date() -> None:
    """Q12 shape: no date, route or flight number named.

    The old default silently restricted this to the snapshot date, which
    hides a schedule-wide superlative that spans other days. The fix widens
    the row cap instead of guessing a date.
    """
    question = "What is the longest block time in the schedule, and which flights have it?"
    intent = match_intent(question)
    assert intent is not None
    plan = intent.build(extract_entities(question), SNAPSHOT)
    assert len(plan) == 1
    args = plan[0].args
    assert "on_date" not in args
    assert args.get("limit", 0) >= 147


def test_a_dated_flight_question_still_narrows_by_date() -> None:
    """A question that does name a date must still filter by it, not widen."""
    intent = match_intent("Which flights depart DEL on 2026-09-15?")
    assert intent is not None
    entities = extract_entities("Which flights depart DEL on 2026-09-15?")
    plan = intent.build(entities, SNAPSHOT)
    args = plan[0].args
    assert args.get("on_date") == date(2026, 9, 15)
    assert args.get("origin") == "DEL"

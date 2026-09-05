"""A superlative over the week must name each flight number once.

Q12 asks for the longest block time and which flights have it. Four distinct
numbers hold 2.75h, but each of them operates on several days of the week, and
`find_flights` returns one row per operating day. `_render_flights` listed the
`flight_no` of every matching row, so the answer read:

    on DX401, DX589, DX402, DX401, DX402, DX588, DX401, DX589, DX402, ...

Twenty-one entries for four flights. It graded correct only because containment
matching does not care about repeats, which is the grader hiding a defect rather
than the answer being right: a controller reading that cannot tell whether DX401
appears three times because it is one flight flown daily or because the search
found three different things.

The fix is a dedupe that preserves rank order, not a set: the reading order is
the schedule order, and sorting them would be this module reordering an answer
the tool returned.
"""

from __future__ import annotations

import datetime as dt
import re

import pytest

QUESTION = "What is the longest block time in the schedule, and which flights have it?"


@pytest.fixture(scope="module")
def answer(resolver) -> str:
    snapshot = dt.datetime(2026, 9, 14, 18, 0, 0)
    reply = resolver.answer(
        QUESTION, thread_id="t-dedupe", turn_id="u-1", asked_at=snapshot
    )
    return f"{reply.headline or ''}\n{reply.text}"


def test_the_longest_block_time_is_still_stated(answer: str) -> None:
    assert "2.75" in answer


def test_every_flight_number_is_named_once(answer: str) -> None:
    numbers = re.findall(r"\bDX\d{3}\b", answer)
    assert numbers, "the answer named no flights at all"
    assert len(numbers) == len(set(numbers)), (
        "a flight number is repeated: " + ", ".join(sorted(numbers))
    )


def test_all_four_flights_at_the_maximum_are_named(answer: str) -> None:
    # Verified against the dataset: four numbers hold 2.75h block time.
    for flight_no in ("DX401", "DX402", "DX588", "DX589"):
        assert flight_no in answer, f"{flight_no} holds the maximum and was dropped"

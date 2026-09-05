"""A delay that breaks a duty must name the legs and price the way out.

S4: VT-DXA takes a 90 minute technical delay before DX401 on 16 Sep and the
whole four sector duty slides. FDP goes 11.25h to 12.75h against a 12.0h limit,
so the rostered crew cannot legally finish. The engine gets all of that exactly
right and has done since the first commit.

What it then said was:

    Dropping the last leg leaves 3 sectors at 9.5h against a 12.5h limit,
    which the rostered crew can fly.

Three sectors. Which three? The answer key names them: the crew keep DX401 to
DX403 and a reserve set takes DX404. `partial_duty_flights` and
`dropped_flights` were sitting in the payload the whole time, as flight ids
nothing ever read. Same defect as the closure renderer and the joint cover
renderer: the collection is computed, counted, and its members thrown away.

The second half is the decision. A controller asking about a technical delay is
asking what it costs to fix, and the answer key ranks two ways out: re-crew the
last sector with a full reserve set at INR 75,000, or cancel it at INR 250,000.
`price_crew_set` in `ops/costing.py` computes the 75,000 and its docstring says
"as in the S4 partial re-crew". Nothing called it. The figure was implemented,
tested at the engine level, and never reached an answer.
"""

from __future__ import annotations

import datetime as dt

import pytest

from crewops.eval.grading import rendered_surface

SNAPSHOT = dt.datetime(2026, 9, 14, 18, 0, 0)

S4 = (
    "VT-DXA has a 90-minute technical delay before DX401 on 16 Sep. "
    "All four legs shift by 90 minutes."
)


@pytest.fixture(scope="module")
def reply(resolver):
    return resolver.answer(S4, thread_id="t-s4", turn_id="u-1", asked_at=SNAPSHOT)


@pytest.fixture(scope="module")
def surface(reply) -> str:
    return rendered_surface(reply)


def test_the_answer_is_not_an_abstention(reply) -> None:
    assert reply.kind.value == "answer", reply.text


def test_the_breach_is_still_stated(surface: str) -> None:
    assert "12.75" in surface
    assert "RULE-FDP-01" in surface


def test_the_legs_the_crew_keeps_are_named(surface: str) -> None:
    for flight_no in ("DX401", "DX402", "DX403"):
        assert flight_no in surface, f"{flight_no} is flyable and was not named"


def test_the_leg_that_needs_re_crewing_is_named(surface: str) -> None:
    assert "DX404" in surface


def test_re_crewing_the_last_sector_is_priced(surface: str) -> None:
    # Two pilots at 18,500 and four cabin crew at 9,500, from costs.json.
    assert "75,000" in surface or "75000" in surface


def test_cancellation_is_priced_as_the_comparison(surface: str) -> None:
    # One leg at 250,000. Stating it beside the 75,000 is what makes the
    # recommendation arguable rather than asserted.
    assert "250,000" in surface or "250000" in surface

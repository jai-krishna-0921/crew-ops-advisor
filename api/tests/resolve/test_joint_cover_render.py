"""Two gaps means two ranked lists, and a ranked list means every rank.

S6 is two simultaneous captain sick calls, C-3940 off P-2205 and C-1938 off
P-2212. The `joint_cover` intent routes it correctly and plans three calls:
`plan_joint_cover` for the allocation, then `find_cover_options` per gap. The
ops engine reproduces the answer key exactly, all thirteen options for each
gap, every cost, every rank. Verified directly against the engine.

Two pieces of plumbing threw most of that away.

  * `_payload(envelopes, Recommendation)` returns the FIRST match, so the
    second gap was computed, priced, ranked and then never rendered. The reply
    described P-2205 and said nothing at all about P-2212. This is the same
    class as the closure bug in `test_closure_render.py`: the renderer names
    one member of a collection and drops the rest.
  * `find_cover_options(max_options=5)` truncated thirteen ranked options to
    five plus cancellation. Ranks 6 to 12 (C-2143, C-3187, C-3983, C-5647,
    C-5820, C-5837 and the C-2210 deadhead) never left the tool. A cap is right
    for a lookup that happens to be long; it is wrong for a question whose
    entire subject IS the ranking.

The fix is a table per gap rather than more prose. `_render_recommendation`
argues, correctly, that linearising every option into the paragraph produces
five thousand characters nobody can read at 6 a.m. A table is the answer to
that: scannable, fact-shaped, one row per option, and the grader counts it
because a controller can read it.
"""

from __future__ import annotations

import datetime as dt

import pytest

from crewops.eval.grading import rendered_surface

SNAPSHOT = dt.datetime(2026, 9, 14, 18, 0, 0)

S6 = (
    "At 00:30Z on 18 Sep, the captains of both VT-DXA (C-3940) and VT-DXB "
    "(C-1938) call in sick. One qualified reserve captain's window covers the "
    "early reports; the desk must allocate scarce cover across both pairings."
)

#: Ranks 6 to 11 of both gaps, day-off callouts at INR 24,000. Truncated away
#: by the option cap, and each one is a captain a controller could actually
#: ring at 00:30Z.
MID_RANKED = ("C-2143", "C-3187", "C-3983", "C-5647", "C-5820", "C-5837")


@pytest.fixture(scope="module")
def reply(resolver):
    return resolver.answer(S6, thread_id="t-s6", turn_id="u-1", asked_at=SNAPSHOT)


@pytest.fixture(scope="module")
def surface(reply) -> str:
    return rendered_surface(reply)


def test_the_answer_is_not_an_abstention(reply) -> None:
    assert reply.kind.value == "answer", reply.text


def test_both_pairings_are_addressed(surface: str) -> None:
    assert "P-2205" in surface, "the VT-DXA gap is missing"
    assert "P-2212" in surface, "the VT-DXB gap was computed and never rendered"


def test_the_cheapest_option_for_each_gap_is_named(surface: str) -> None:
    assert "C-3305" in surface
    assert "C-1017" in surface


def test_the_middle_of_the_ranking_survives_the_cap(surface: str) -> None:
    missing = [crew_id for crew_id in MID_RANKED if crew_id not in surface]
    assert not missing, f"ranked options truncated away: {', '.join(missing)}"


def test_the_deadhead_option_is_priced_for_both_gaps(surface: str) -> None:
    # C-2210 is DEL based, so RULE-BASE-07 charges positioning. The two gaps
    # need different delay, so they price differently: 60,100 and 57,400.
    assert "C-2210" in surface
    assert "60,100" in surface or "60100" in surface
    assert "57,400" in surface or "57400" in surface


def test_nobody_is_allocated_to_both_pairings(reply) -> None:
    plans = [
        envelope.payload
        for envelope in reply.tool_calls
        if envelope.ok and type(envelope.payload).__name__ == "JointPlan"
    ]
    assert plans, "the joint allocation never ran"
    assert not plans[0].double_booked, plans[0].double_booked

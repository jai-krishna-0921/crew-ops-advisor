"""A joint plan was computed, and the screen showed prose.

"Both A320 captains (VT-DXA and VT-DXB) are sick at 00:30Z on 18 Sep. Give the
optimal joint crewing plan." is Q32, and the agent answers it correctly:

    Optimal joint plan: C-3305 (V. Menon) to P-2205 on VT-DXA,
    C-1017 to P-2212 on VT-DXB, total INR 42,500.

`plan_joint_cover` returned a typed `JointPlan` carrying both assignments as
full `CoverOption` records, each with its legality report, its cost breakdown
and its reasoning, plus the contention list showing which candidate was rank 1
for both gaps and how the conflict was resolved. `build_reply` lifts a
`Recommendation` off the envelopes and nothing else, so `reply.recommendation`
was None and every one of those structures was dropped on the floor. The
controller got a sentence.

Simultaneous disruption is the first entry in the failure analysis and one of
the optional enhancements the problem statement names. Computing it correctly
and then not showing it is the same defect as the callout draft: the answer
existed, was right, and never reached the screen.

`Recommendation` already has a `joint_plan` field and `JointPlan.assignments`
is already a `list[CoverOption]`, so this is a wrap, not a new shape. No figure
moves and no rule is re-evaluated.
"""

from __future__ import annotations

import datetime as dt

import pytest


@pytest.fixture(scope="module")
def envelope():
    from crewops.agent.factory import load_tools

    return load_tools().plan_joint_cover(
        gaps=[
            {"pairing_id": "P-2205", "role": "Captain", "on_date": "2026-09-18"},
            {"pairing_id": "P-2212", "role": "Captain", "on_date": "2026-09-18"},
        ]
    )


def _reply(envelope):
    from crewops.agent.reply import build_reply

    return build_reply(
        {
            "envelopes": [envelope],
            "draft": "Two captains covered.",
            "verification": None,
            "tier": 3,
            "abstention": None,
            "timings": {},
            "model_calls": 0,
        },
        question="Both A320 captains are sick on 18 Sep. Give the joint plan.",
        thread_id="t-joint",
        turn_id="u-1",
        asked_at=dt.datetime(2026, 9, 14, 18, 0, 0),
        total_ms=1,
    )


def test_the_tool_still_returns_a_feasible_plan(envelope) -> None:
    assert envelope.ok, envelope.error
    assert envelope.payload.feasible
    assert len(envelope.payload.assignments) == 2


def test_the_plan_reaches_the_reply(envelope) -> None:
    reply = _reply(envelope)
    assert reply.recommendation is not None, (
        "the joint plan was computed and dropped before it reached the screen"
    )


def test_both_assignments_arrive_as_ranked_options(envelope) -> None:
    """Two priced, legality-checked cards instead of one sentence."""
    reply = _reply(envelope)
    assert reply.recommendation is not None
    options = reply.recommendation.options
    assert len(options) == 2, options
    assert all(option.crew_id for option in options)
    assert all(option.legality.per_day for option in options)


def test_nobody_is_on_two_aircraft(envelope) -> None:
    """The invariant the joint search exists for, asserted where it is read."""
    reply = _reply(envelope)
    assert reply.recommendation is not None
    plan = reply.recommendation.joint_plan
    assert plan is not None
    assert plan.double_booked == []


def test_the_contention_reasoning_survives(envelope) -> None:
    """Which candidate was rank 1 for both gaps, and how it was settled, is
    the part a controller argues with."""
    reply = _reply(envelope)
    assert reply.recommendation is not None
    assert reply.recommendation.joint_plan is not None
    assert reply.recommendation.ranking_basis, "the plan arrived with no stated basis"


def test_an_infeasible_plan_offers_no_options() -> None:
    """Returning the best independent pair when no joint allocation exists
    would put one person on two aircraft. It must stay empty."""
    from crewops.agent.reply import build_reply
    from crewops.contracts import JointPlan, ToolEnvelope

    infeasible = ToolEnvelope(
        tool="plan_joint_cover",
        ok=True,
        args={},
        payload=JointPlan(
            objective="min_cost",
            feasible=False,
            why_infeasible="No allocation covers both gaps without double booking.",
        ),
    )
    reply = build_reply(
        {
            "envelopes": [infeasible],
            "draft": "No joint plan is available.",
            "verification": None,
            "tier": 3,
            "abstention": None,
            "timings": {},
            "model_calls": 0,
        },
        question="Both captains are sick.",
        thread_id="t-joint",
        turn_id="u-2",
        asked_at=dt.datetime(2026, 9, 14, 18, 0, 0),
        total_ms=1,
    )
    if reply.recommendation is not None:
        assert reply.recommendation.options == []

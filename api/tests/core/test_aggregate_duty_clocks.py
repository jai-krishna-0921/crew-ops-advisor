"""A superlative over duty clocks had no tool, so the model invented one.

Stress testing Tier 1 with questions outside the shipped 38:

    "Who has the most duty hours in the last 7 days?"
    -> "C-2143, Captain P. Sen, has the most duty hours in the last 7 days:
        42.51h over 2026-09-14 to 2026-09-20"

The real answer is C-3305 at 56.4h. The model did not hallucinate a number: it
summed the ROSTER WEEK AHEAD, because that was the only duty figure any tool
would give it. "The last 7 days" is a backward window and `duty_clocks.json`
carries it per crew, but `aggregate` flattened crew to seven fields and none of
them was a duty clock, so `aggregate(collection="crew", metric="max",
field="duty_hours_7d")` came back:

    crew has no field 'duty_hours_7d'. Available fields: base, crew_id, name,
    rank, reachability_minutes, seniority, status.

The offline path abstained, which is the safe outcome and the right one. The
agent answered a different question, which is the unsafe one, and it is the
failure mode the rubric punishes hardest.

The fix is the standing rule in CLAUDE.md: when an answer needs a figure, the
tool output has to carry it. No rule changes and no arithmetic moves; two
columns that were already loaded into `WorldState` become visible to the
aggregate that was already there.
"""

from __future__ import annotations

import pytest


@pytest.fixture(scope="module")
def tools():
    from crewops.agent.factory import load_tools

    return load_tools()


def test_the_duty_clock_is_aggregatable(tools) -> None:
    envelope = tools.aggregate(collection="crew", metric="max", field="duty_hours_7d")
    assert envelope.ok, envelope.error


def test_it_finds_the_crew_with_the_most_duty_hours(tools) -> None:
    """Verified against duty_clocks.json: C-3305 at 56.4h, then C-2087 at 51.83."""
    envelope = tools.aggregate(
        collection="crew", metric="max", field="duty_hours_7d", limit=3
    )
    assert envelope.ok, envelope.error
    rendered = str(envelope.payload)
    assert "56.4" in rendered, rendered


def test_the_flight_hour_window_is_aggregatable_too(tools) -> None:
    """C-2143 at 79.24h is the 28 day maximum, and a different crew member
    from the 7 day one. Getting these two confused is the whole point of
    exposing both rather than one."""
    envelope = tools.aggregate(
        collection="crew", metric="max", field="flight_hours_28d", limit=3
    )
    assert envelope.ok, envelope.error
    assert "79.24" in str(envelope.payload)


def test_the_clocks_can_be_filtered_like_any_other_field(tools) -> None:
    envelope = tools.aggregate(
        collection="crew", metric="max", field="duty_hours_7d", filters={"base": "BLR"}
    )
    assert envelope.ok, envelope.error


def test_the_existing_crew_fields_still_work(tools) -> None:
    """Adding columns must not disturb what the aggregate already answered."""
    envelope = tools.aggregate(collection="crew", metric="count", group_by="base")
    assert envelope.ok, envelope.error
    assert "BLR" in str(envelope.payload)


def test_an_unknown_field_is_still_an_error(tools) -> None:
    envelope = tools.aggregate(collection="crew", metric="max", field="lunch_hours")
    assert not envelope.ok
    assert "duty_hours_7d" in (envelope.error or ""), (
        "the error lists the available fields, so the new ones have to appear in it"
    )


# ------------------------------------- the model has to know the field exists


def test_the_tool_description_names_the_clock_fields() -> None:
    """Exposing a column the model is never told about changes nothing.

    The fields landed and the answer stayed wrong: asked again, the agent still
    summed the roster week ahead, because the only duty figure it knew how to
    reach was the one it was already reaching for. A capability the planner
    cannot see is not a capability.
    """
    from crewops.agent.toolspecs import TOOL_SPECS

    spec = next(s for s in TOOL_SPECS if s.name == "aggregate")
    assert "duty_hours_7d" in spec.description, spec.description
    assert "flight_hours_28d" in spec.description, spec.description

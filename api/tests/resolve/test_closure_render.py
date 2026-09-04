"""A closure answer must name the flights, not just count them.

Q29 asks which flights are affected when HYD closes 05:00 to 09:00 on 19 Sep.
The answer is `DX461-2026-09-19` and `DX462-2026-09-19`.
`simulate_station_closure` computes exactly that and puts it in
`payload["affected_flights"]`. The renderer said:

    2 flights touch HYD inside the window

The count is right and the answer is useless: a controller cannot act on "2",
and the grader, looking for the flight identifiers, found none and marked the
turn **wrong** rather than partial. Q19 is the same bug at 13 flights, scoring
partial.

`_render_impact` lists `report.uncrewed_flights`, and a closure's flights are
not uncrewed, they are delayed. All four flight lists on the `ImpactReport` are
empty for a closure, so nothing was ever printed.

This is the same class as commit 7fb1838, "Render collection members, not just
their count", which fixed one template and did not reach this one. It is also
the more dangerous half of the Q12 duplication bug: a renderer that summarises
where the key wants members turns a correct computation into a wrong answer.
"""

from __future__ import annotations

import datetime as dt

import pytest

EXPECTED = ["DX461-2026-09-19", "DX462-2026-09-19"]


@pytest.fixture(scope="module")
def closure_envelopes() -> list:
    from crewops.agent.factory import load_tools

    tools = load_tools()
    envelope = tools.simulate_station_closure(
        station="HYD",
        from_time=dt.datetime(2026, 9, 19, 5, 0),
        to_time=dt.datetime(2026, 9, 19, 9, 0),
    )
    assert envelope.ok, envelope.error
    return [envelope]


def test_the_tool_computes_the_right_flights(closure_envelopes: list) -> None:
    """The control. The computation was never the problem."""
    payload = closure_envelopes[0].payload
    assert payload["affected_flights"] == EXPECTED


def test_the_rendered_answer_names_every_affected_flight(closure_envelopes: list) -> None:
    from crewops.resolve.render import render

    text = render("impact", closure_envelopes, "Station HYD is closed 05:00-09:00Z on 19 Sep.")
    for flight in EXPECTED:
        bare = flight.split("-")[0]
        assert bare in text, (
            f"{bare} is missing from the answer, so a controller is told how many "
            f"flights are affected but not which ones:\n{text}"
        )


def test_the_count_is_still_there(closure_envelopes: list) -> None:
    """Naming them must not cost the summary a controller reads first."""
    from crewops.resolve.render import render

    text = render("impact", closure_envelopes, "Station HYD is closed.")
    assert "2" in text


def test_a_large_closure_does_not_run_off_the_screen() -> None:
    """Q19 affects 13 flights. Listing them must stay readable, not paginate
    away the answer: the key wants all thirteen."""
    from crewops.agent.factory import load_tools
    from crewops.resolve.render import render

    tools = load_tools()
    envelope = tools.simulate_station_closure(
        station="BLR",
        from_time=dt.datetime(2026, 9, 17, 8, 0),
        to_time=dt.datetime(2026, 9, 17, 14, 0),
    )
    assert envelope.ok, envelope.error
    expected = envelope.payload["affected_flights"]
    assert len(expected) == 13, f"dataset drift: got {len(expected)}"

    text = render("impact", [envelope], "BLR is closed 08:00-14:00Z on 17 Sep.")
    missing = [f for f in expected if f.split("-")[0] not in text]
    assert not missing, f"{len(missing)} of 13 flights were not named: {missing}"

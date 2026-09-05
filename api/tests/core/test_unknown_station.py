"""An unknown station is not a finding of zero.

    "Who is on reserve at IDR on 2026-09-17, and what are their on-call
     windows?"
    -> "There are no reserves at IDR on 2026-09-17. The lookup returned 0
        matches."

Every word of that is wrong in the way that matters. IDR is not a station in
this dataset, so there was never a list to be empty. The reply reads as a
finding about IDR's reserve cover, and a controller could take it as one.

The codebase already states the principle in the other direction, in the
message a failed lookup carries: **"A failed lookup is not a finding of
'none'."** This is the mirror. A filter on an identifier the dataset has never
heard of is not a query that returned nothing; it is a query that could not be
asked. `get_crew_detail` and `find_pairings` have said so about crew ids and
pairing ids from the start. Stations were the gap: they are filters rather than
subjects, so an unknown one silently matched no rows.

The distinction that has to survive: **BOM is a real station with no reserves,
and that IS zero.** Refusing every empty result would be worse than the bug.
"""

from __future__ import annotations

import datetime as dt

import pytest

DATE = dt.date(2026, 9, 17)


@pytest.fixture(scope="module")
def tools():
    from crewops.agent.factory import load_tools

    return load_tools()


UNKNOWN = ["IDR", "INR", "LHR", "ZZZ"]


@pytest.mark.parametrize("station", UNKNOWN)
def test_reserves_at_an_unknown_station_is_refused(tools, station: str) -> None:
    envelope = tools.list_reserves(on_date=DATE, base=station)
    assert not envelope.ok, (
        f"{station} is not a station and the lookup reported {envelope.payload}"
    )
    assert station in (envelope.error or "")


@pytest.mark.parametrize("station", UNKNOWN)
def test_the_refusal_names_the_stations_that_exist(tools, station: str) -> None:
    """A refusal a controller can act on names what they could have meant."""
    error = tools.list_reserves(on_date=DATE, base=station).error or ""
    assert "BLR" in error and "MAA" in error, error


def test_crew_at_an_unknown_base_is_refused(tools) -> None:
    envelope = tools.find_crew(base="IDR")
    assert not envelope.ok, envelope.payload


def test_flights_from_an_unknown_station_are_refused(tools) -> None:
    assert not tools.find_flights(origin="IDR").ok
    assert not tools.find_flights(destination="IDR").ok


def test_a_real_station_with_no_match_is_still_zero(tools) -> None:
    """The distinction the whole change rests on. BOM exists; whatever it has
    or does not have on a date is a finding, not an error."""
    envelope = tools.list_reserves(on_date=DATE, base="BOM")
    assert envelope.ok, envelope.error
    assert envelope.payload.total_matched == 0


def test_a_real_station_with_matches_is_untouched(tools) -> None:
    envelope = tools.list_reserves(on_date=DATE, base="BLR")
    assert envelope.ok, envelope.error
    assert envelope.payload.total_matched == 12


def test_case_is_not_the_point(tools) -> None:
    """"blr" is a spelling of a station that exists."""
    assert tools.list_reserves(on_date=DATE, base="blr").ok


def test_an_unfiltered_lookup_is_never_touched(tools) -> None:
    assert tools.list_reserves(on_date=DATE).ok
    assert tools.find_crew(rank="Captain").ok

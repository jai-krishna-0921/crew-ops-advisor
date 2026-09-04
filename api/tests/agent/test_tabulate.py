"""A result set is a table, not a paragraph.

The list tools return structured payloads, and every one of them used to reach
the screen as prose: `_render_reserves` joined twelve reserves into one string,
markdown collapsed the newlines, and a controller got a 90 word run-on
sentence with fourteen clock times in it. That is unreadable at any speed, and
unreadable at speed is the whole failure mode this product exists to avoid.

The fix is a projection, and it is a projection rather than a prompt change
because a table is a fact-shaped thing: every cell here is copied out of a
payload field, so a `Table` is exactly as attested as the payload it came from
and the verifier has nothing new to check.
"""

from __future__ import annotations

from crewops.agent.reply import collect_tables
from crewops.contracts import Table, ToolEnvelope
from crewops.tools import payloads as P  # noqa: N812  short alias, matches resolve/render.py


def _envelope(tool: str, payload: object) -> ToolEnvelope:
    return ToolEnvelope(tool=tool, args={}, ok=True, payload=payload, latency_ms=1)


def _reserve(crew_id: str, minutes: int) -> P.ReserveSummary:
    return P.ReserveSummary(
        crew_id=crew_id,
        name="A. Nair",
        rank="Captain",
        base="BLR",
        ratings=("A320",),
        window_start="00:00",
        window_end="05:30",
        reachability_minutes=minutes,
    )


def test_a_reserve_list_becomes_a_table() -> None:
    payload = P.ReserveList(
        on_date="2026-09-15",
        reserves=(_reserve("C-3305", 45), _reserve("C-3310", 60)),
        total_matched=2,
    )

    tables = collect_tables([_envelope("list_reserves", payload)])

    assert len(tables) == 1
    table = tables[0]
    assert isinstance(table, Table)
    assert table.columns == [
        "Crew",
        "Name",
        "Rank",
        "Base",
        "On call",
        "Reachable",
    ]
    assert table.row_ids == ["C-3305", "C-3310"]
    assert table.rows[0][0] == "C-3305"
    assert table.rows[0][4] == "00:00 to 05:30"
    assert table.rows[0][5] == 45
    assert table.rows[1][5] == 60


def test_every_cell_comes_from_the_payload() -> None:
    """No cell may be a value the projection computed rather than copied."""
    payload = P.ReserveList(
        on_date="2026-09-15", reserves=(_reserve("C-3305", 45),), total_matched=1
    )
    table = collect_tables([_envelope("list_reserves", payload)])[0]
    reserve = payload.reserves[0]

    flat = {str(cell) for cell in table.rows[0]}
    assert flat <= {
        reserve.crew_id,
        reserve.name,
        reserve.rank,
        reserve.base,
        f"{reserve.window_start} to {reserve.window_end}",
        str(reserve.reachability_minutes),
    }


def test_an_empty_list_produces_no_table() -> None:
    """An empty table is a frame with a header and nothing to read."""
    payload = P.ReserveList(on_date="2026-09-15", reserves=(), total_matched=0)
    assert collect_tables([_envelope("list_reserves", payload)]) == []


def test_a_crew_list_becomes_a_table() -> None:
    payload = P.CrewList(
        crew=(
            P.CrewSummary(
                crew_id="C-1042",
                name="A. Nair",
                rank="Captain",
                base="BLR",
                ratings=("A320",),
                status="active",
                seniority=12,
                reachability_minutes=45,
                is_reserve=False,
            ),
        ),
        total_matched=1,
        all_crew_ids=("C-1042",),
    )

    table = collect_tables([_envelope("find_crew", payload)])[0]
    assert table.columns == ["Crew", "Name", "Rank", "Base", "Rated", "Status"]
    assert table.rows[0][4] == "A320"


def test_a_flight_list_becomes_a_table() -> None:
    payload = P.FlightList(
        flights=(
            P.FlightSummary(
                flight_id="F-1",
                flight_no="DX101",
                date="2026-09-15",
                dep_station="BLR",
                arr_station="DEL",
                dep_utc="2026-09-15T01:00:00Z",
                arr_utc="2026-09-15T03:30:00Z",
                block_hours=2.5,
                aircraft="VT-DXA",
                aircraft_type="A320",
                seats=180,
            ),
        ),
        total_matched=1,
        all_flight_ids=("F-1",),
        total_seats=180,
    )

    table = collect_tables([_envelope("find_flights", payload)])[0]
    assert table.columns == [
        "Flight",
        "Date",
        "From",
        "To",
        "Departs",
        "Arrives",
        "Block",
        "Aircraft",
        "Seats",
    ]
    assert table.rows[0][0] == "DX101"
    assert table.rows[0][8] == 180


def test_a_roster_becomes_a_table_of_duty_days() -> None:
    payload = P.RosterView(
        crew_id="C-1042",
        from_date="2026-09-15",
        to_date="2026-09-16",
        duties=(
            P.DutyDaySummary(
                duty_date="2026-09-15",
                pairing_id="P-2291",
                report_utc="2026-09-15T02:00:00Z",
                release_utc="2026-09-15T11:00:00Z",
                duty_hours=9.0,
                block_hours=6.5,
                sectors=4,
                flight_numbers=("DX101", "DX102"),
            ),
        ),
        total_duty_hours=9.0,
        total_block_hours=6.5,
        days_off=(),
    )

    table = collect_tables([_envelope("get_roster", payload)])[0]
    assert table.columns == [
        "Date",
        "Pairing",
        "Report",
        "Release",
        "Duty",
        "Block",
        "Sectors",
        "Flights",
    ]
    assert table.rows[0][7] == "DX101, DX102"


def test_a_payload_that_is_already_a_table_still_passes_through() -> None:
    table = Table(title="Given", columns=["a"], rows=[["b"]])
    assert collect_tables([_envelope("whatever", table)]) == [table]


def test_a_failed_envelope_contributes_nothing() -> None:
    payload = P.ReserveList(
        on_date="2026-09-15", reserves=(_reserve("C-3305", 45),), total_matched=1
    )
    envelope = ToolEnvelope(tool="list_reserves", args={}, ok=False, payload=payload, latency_ms=1)
    assert collect_tables([envelope]) == []

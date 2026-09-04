"""Anchor 1: the clock formula, against all 150 crew.

This is the invariant everything else stands on. If it moves, every answer key
that depends on a 7 day or 28 day window moves with it.

    window_hours(crew, end, days, kind)
        = sum(daily_history[d][kind]  for end-days+1 <= d <= end)
        + sum(roster duty length      for end-days+1 <= d <= end)

`daily_history` runs to 2026-09-14 and the roster week starts 2026-09-14, so
that date contributes from both sources for 11 crew. The shipped summary fields
carry the double count, so it is the dataset's convention, not a bug.
"""

from __future__ import annotations

import json
from datetime import date, datetime
from pathlib import Path

import pytest

from crewops.domain import DATA_DIR, WorldState, load_world
from crewops.domain.time_utils import format_duration, hours_between, parse_utc

SNAPSHOT_DATE = date(2026, 9, 14)


@pytest.fixture(scope="module")
def world() -> WorldState:
    return load_world()


@pytest.fixture(scope="module")
def raw_clocks() -> list[dict[str, object]]:
    payload = json.loads((DATA_DIR / "duty_clocks.json").read_text(encoding="utf-8"))
    assert isinstance(payload, list)
    return payload


def test_dataset_directory_is_the_shipped_one() -> None:
    assert DATA_DIR.name == "data"
    assert DATA_DIR.parent.name == "crew-ops-advisor-dataset"
    assert (DATA_DIR / "flights.json").exists()


def test_world_counts_match_the_shipped_dataset(world: WorldState) -> None:
    assert len(world.flights) == 147
    assert len(world.crew) == 150
    assert len(world.pairings) == 39
    assert len(world.reserves) == 16
    assert len(world.certifications) == 600
    assert len(world.rules.rules) == 7
    assert world.snapshot == datetime(2026, 9, 14, 18, 0, 0)


def test_duty_hours_7d_reproduces_for_all_150_crew(
    world: WorldState, raw_clocks: list[dict[str, object]]
) -> None:
    """The headline proof. 150/150, including the 2026-09-14 double count."""
    ov = world.overlay()
    failures: list[str] = []
    for record in raw_clocks:
        crew_id = str(record["crew_id"])
        shipped = float(record["duty_hours_7d"])  # type: ignore[arg-type]
        computed = ov.window_hours(crew_id, SNAPSHOT_DATE, days=7, kind="duty")
        if abs(computed - shipped) > 0.005:
            failures.append(f"{crew_id}: shipped {shipped} computed {computed}")
    assert not failures, "duty_hours_7d mismatch:\n  " + "\n  ".join(failures)


def test_flight_hours_28d_reproduces_for_all_150_crew(
    world: WorldState, raw_clocks: list[dict[str, object]]
) -> None:
    ov = world.overlay()
    failures: list[str] = []
    for record in raw_clocks:
        crew_id = str(record["crew_id"])
        shipped = float(record["flight_hours_28d"])  # type: ignore[arg-type]
        computed = ov.window_hours(crew_id, SNAPSHOT_DATE, days=28, kind="flight")
        if abs(computed - shipped) > 0.005:
            failures.append(f"{crew_id}: shipped {shipped} computed {computed}")
    assert not failures, "flight_hours_28d mismatch:\n  " + "\n  ".join(failures)


def test_the_2026_09_14_overlap_is_present_and_deliberate(world: WorldState) -> None:
    """11 crew draw from both history and roster on 2026-09-14.

    Dropping the roster contribution reproduces duty_hours_7d for only 118 of
    150 crew, and 150 - 118 = 32 is exactly the number of crew rostered that
    day. The double count is the dataset's own arithmetic.
    """
    both = [
        c.crew_id
        for c in world.crew
        if world.history_on(c.crew_id, SNAPSHOT_DATE).duty_hours > 0
        and any(d.duty_date == SNAPSHOT_DATE for d in world.week_duties(c.crew_id))
    ]
    assert len(both) == 11

    rostered_on_snapshot = {
        c.crew_id
        for c in world.crew
        if any(d.duty_date == SNAPSHOT_DATE for d in world.week_duties(c.crew_id))
    }
    assert len(rostered_on_snapshot) == 32


def test_history_only_variant_is_wrong_for_exactly_32_crew(
    world: WorldState, raw_clocks: list[dict[str, object]]
) -> None:
    """Guards against a future 'fix' that drops the roster contribution."""
    matches = 0
    for record in raw_clocks:
        crew_id = str(record["crew_id"])
        shipped = float(record["duty_hours_7d"])  # type: ignore[arg-type]
        hist_only = sum(
            world.history_on(crew_id, SNAPSHOT_DATE.fromordinal(d)).duty_hours
            for d in range(SNAPSHOT_DATE.toordinal() - 6, SNAPSHOT_DATE.toordinal() + 1)
        )
        if abs(round(hist_only, 2) - shipped) <= 0.005:
            matches += 1
    assert matches == 118


def test_c1042_worked_example(world: WorldState) -> None:
    ov = world.overlay()
    assert ov.window_hours("C-1042", SNAPSHOT_DATE, days=7, kind="duty") == 20.93
    assert ov.window_hours("C-1042", SNAPSHOT_DATE, days=28, kind="flight") == 64.27


def test_windows_are_calendar_dates_inclusive(world: WorldState) -> None:
    """[end - 6, end] inclusive, not a rolling 168 hours."""
    ov = world.overlay()
    seven = ov.window_dates(date(2026, 9, 15), days=7)
    assert seven[0] == date(2026, 9, 9)
    assert seven[-1] == date(2026, 9, 15)
    assert len(seven) == 7
    assert len(ov.window_dates(date(2026, 9, 14), days=28)) == 28


def test_c2087_base_window_ending_15_sep_is_51_83(world: WorldState) -> None:
    """The number the 61.33h breach is built on."""
    ov = world.overlay()
    assert ov.window_hours("C-2087", date(2026, 9, 15), days=7, kind="duty") == 51.83


def test_parse_utc_is_naive(world: WorldState) -> None:
    parsed = parse_utc("2026-09-15T06:00:00Z")
    assert parsed == datetime(2026, 9, 15, 6, 0)
    assert parsed.tzinfo is None
    assert world.flights[0].dep_utc.tzinfo is None


def test_hours_between_rounds_to_two_places() -> None:
    assert hours_between(datetime(2026, 9, 15, 6, 0), datetime(2026, 9, 15, 15, 30)) == 9.5
    assert hours_between(datetime(2026, 9, 15, 0, 0), datetime(2026, 9, 15, 0, 20)) == 0.33


@pytest.mark.parametrize(
    ("hours", "rendered"),
    [(1.33, "1h20m"), (8.25, "8h15m"), (1.08, "1h05m"), (0.5, "0h30m"), (12.0, "12h00m")],
)
def test_format_duration_matches_the_shipped_keys(hours: float, rendered: str) -> None:
    assert format_duration(hours) == rendered


def test_dataset_files_are_not_writable_through_the_loader() -> None:
    """The loader opens for reading only. A regression here corrupts answer keys."""
    source = (Path(__file__).resolve().parents[2] / "src/crewops/domain/loader.py").read_text(
        encoding="utf-8"
    )
    assert "write_text" not in source
    assert 'mode="w"' not in source

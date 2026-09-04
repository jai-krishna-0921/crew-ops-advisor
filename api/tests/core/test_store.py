"""The SQLite projection.

Two things matter here: the projection agrees with `WorldState` row for row,
and it can never be built inside the shipped dataset.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest

from crewops.domain import WorldState
from crewops.store import DatasetStore, open_store


@pytest.fixture(scope="module")
def store(world: WorldState) -> DatasetStore:
    with open_store(world) as built:
        yield built


def test_projection_row_counts_match_the_world(store: DatasetStore) -> None:
    counts = store.counts()
    assert counts["crew"] == 150
    assert counts["flight"] == 147
    assert counts["pairing"] == 39
    assert counts["pairing_day"] == 42
    # 25 A320 pairings x 6 crew plus 14 ATR72 pairings x 4 crew = 206 seats,
    # covering 102 distinct crew. `docs/DATA-MODEL.md` states 210 in two places;
    # the shipped data says 206 and the data wins.
    assert counts["pairing_crew"] == 206
    assert counts["certification"] == 600
    assert counts["reserve"] == 16
    assert counts["duty_clock"] == 150
    assert counts["daily_history"] == 4200


def test_the_store_refuses_to_be_built_inside_the_dataset(world: WorldState) -> None:
    """The shipped data is read only. A projection written there would move
    the answer keys every golden test asserts against."""
    with pytest.raises(ValueError, match="read only"):
        DatasetStore(world, path=world.data_dir / "projection.sqlite3")
    with pytest.raises(ValueError, match="read only"):
        DatasetStore(world, path=world.data_dir / "nested" / "projection.sqlite3")


def test_the_default_store_lives_in_a_temporary_directory(world: WorldState) -> None:
    store = DatasetStore(world)
    try:
        assert world.data_dir.resolve() not in store.path.resolve().parents
        assert store.path.exists()
    finally:
        path = store.path
        store.close()
        assert not path.exists()


def test_find_crew_agrees_with_the_world(store: DatasetStore, world: WorldState) -> None:
    del_captains = store.find_crew_ids(rank="Captain", base="DEL")
    assert del_captains == ["C-2210"]

    atr_only = store.find_crew_ids(aircraft_type="ATR72", rank="Captain", status="active")
    expected = sorted(
        c.crew_id
        for c in world.crew
        if c.rank == "Captain" and c.is_active and "ATR72" in c.ratings
    )
    assert atr_only == expected


def test_an_empty_result_is_a_finding_not_an_error(store: DatasetStore) -> None:
    assert store.find_crew_ids(base="JFK") == []
    assert store.find_crew_ids(crew_ids=[]) == []
    assert store.find_flight_ids(origin="BLR", destination="JFK") == []


def test_find_flights_agrees_with_the_world(store: DatasetStore) -> None:
    """Q09: BLR to BOM on 17 Sep is DX431 then DX412, in departure order."""
    ids = store.find_flight_ids(
        origin="BLR", destination="BOM", on_date=date(2026, 9, 17)
    )
    assert [i.split("-")[0] for i in ids] == ["DX431", "DX412"]

    assert len(store.find_flight_ids(on_date=date(2026, 9, 16))) == 21


def test_reserve_date_filter(store: DatasetStore) -> None:
    """Q01: 12 reserves at BLR. Every reserve is on call all seven days."""
    ids = store.find_crew_ids(base="BLR", on_reserve_date=date(2026, 9, 15))
    assert len(ids) == 12
    for day in (date(2026, 9, d) for d in range(14, 21)):
        assert len(store.find_crew_ids(on_reserve_date=day)) == 16


def test_expiring_certifications_matches_q04(store: DatasetStore) -> None:
    rows = store.expiring_certifications(
        as_of=date(2026, 9, 15), until=date(2026, 10, 15)
    )
    found = {(r["crew_id"], r["cert_type"], r["valid_to"]) for r in rows}
    assert found == {
        ("C-5417", "recurrent_training", "2026-09-17"),
        ("C-2087", "licence", "2026-09-18"),
        ("C-2091", "medical_class1", "2026-09-23"),
        ("C-3116", "dangerous_goods", "2026-09-28"),
        ("C-5020", "recurrent_training", "2026-10-03"),
        ("C-2993", "medical_class1", "2026-10-08"),
    }
    assert [r["valid_to"] for r in rows] == sorted(r["valid_to"] for r in rows)


def test_valid_from_is_not_projected_at_all(store: DatasetStore) -> None:
    """A column nobody can read is a column nobody can misread."""
    columns = {r[1] for r in store.query("PRAGMA table_info(certification)")}
    assert "valid_to" in columns
    assert "valid_from" not in columns


def test_crew_on_date_returns_the_roster(store: DatasetStore) -> None:
    rows = store.crew_on_date(date(2026, 9, 15))
    assert len(rows) == 32
    assert {r["crew_id"] for r in rows} >= {"C-1042"}


def test_the_store_module_never_references_the_dataset_path() -> None:
    source = (
        Path(__file__).resolve().parents[2] / "src/crewops/store/projection.py"
    ).read_text(encoding="utf-8")
    assert "crew-ops-advisor-dataset" not in source

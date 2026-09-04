"""A SQLite projection of `WorldState`.

`WorldState` stays the source of truth in memory. This is a **projection**: it
is built from the world at startup and never written back to. It exists so that
retrieval is a real query layer with indices and predicates rather than a
linear scan over dictionaries, which is the honest answer to "does this
approach scale past 150 crew".

The database file is a temporary file or a caller supplied path. It is **never**
written inside `data/`: the shipped dataset is read only, and a stray write
there would silently move the answer keys every golden test asserts against.

Tools may use whichever is clearer for a given query. Set arithmetic and
filtering read better in SQL; graph walks over pairings and any rule
computation read better in Python and stay there.
"""

from __future__ import annotations

import sqlite3
import tempfile
from collections.abc import Iterator, Sequence
from contextlib import contextmanager
from datetime import date as DateType  # noqa: N812
from pathlib import Path
from typing import Any

from crewops.domain import WorldState

SCHEMA = """
CREATE TABLE crew (
    crew_id              TEXT PRIMARY KEY,
    name                 TEXT NOT NULL,
    rank                 TEXT NOT NULL,
    base                 TEXT NOT NULL,
    seniority            INTEGER NOT NULL,
    reachability_minutes INTEGER NOT NULL,
    status               TEXT NOT NULL,
    is_reserve           INTEGER NOT NULL,
    risk_score           REAL
);
CREATE INDEX ix_crew_rank_base ON crew(rank, base);
CREATE INDEX ix_crew_status ON crew(status);

CREATE TABLE crew_rating (
    crew_id       TEXT NOT NULL REFERENCES crew(crew_id),
    aircraft_type TEXT NOT NULL,
    PRIMARY KEY (crew_id, aircraft_type)
);

CREATE TABLE flight (
    flight_id     TEXT PRIMARY KEY,
    flight_no     TEXT NOT NULL,
    flight_date   TEXT NOT NULL,
    dep_station   TEXT NOT NULL,
    arr_station   TEXT NOT NULL,
    dep_utc       TEXT NOT NULL,
    arr_utc       TEXT NOT NULL,
    block_hours   REAL NOT NULL,
    aircraft      TEXT NOT NULL,
    aircraft_type TEXT NOT NULL,
    seats         INTEGER NOT NULL,
    pairing_id    TEXT
);
CREATE INDEX ix_flight_date ON flight(flight_date);
CREATE INDEX ix_flight_route ON flight(dep_station, arr_station);
CREATE INDEX ix_flight_no ON flight(flight_no);

CREATE TABLE pairing (
    pairing_id TEXT PRIMARY KEY,
    aircraft   TEXT NOT NULL,
    day_count  INTEGER NOT NULL,
    leg_count  INTEGER NOT NULL,
    start_date TEXT NOT NULL
);

CREATE TABLE pairing_day (
    pairing_id  TEXT NOT NULL REFERENCES pairing(pairing_id),
    duty_date   TEXT NOT NULL,
    report_utc  TEXT NOT NULL,
    release_utc TEXT NOT NULL,
    sectors     INTEGER NOT NULL,
    duty_hours  REAL NOT NULL,
    block_hours REAL NOT NULL,
    PRIMARY KEY (pairing_id, duty_date)
);
CREATE INDEX ix_pairing_day_date ON pairing_day(duty_date);

CREATE TABLE pairing_crew (
    pairing_id TEXT NOT NULL REFERENCES pairing(pairing_id),
    crew_id    TEXT NOT NULL REFERENCES crew(crew_id),
    role       TEXT NOT NULL,
    PRIMARY KEY (pairing_id, crew_id)
);
CREATE INDEX ix_pairing_crew_crew ON pairing_crew(crew_id);

CREATE TABLE week_duty (
    crew_id     TEXT NOT NULL REFERENCES crew(crew_id),
    duty_date   TEXT NOT NULL,
    pairing_id  TEXT NOT NULL,
    report_utc  TEXT NOT NULL,
    release_utc TEXT NOT NULL,
    duty_hours  REAL NOT NULL,
    block_hours REAL NOT NULL,
    PRIMARY KEY (crew_id, duty_date, pairing_id)
);
CREATE INDEX ix_week_duty_date ON week_duty(duty_date);

CREATE TABLE certification (
    crew_id   TEXT NOT NULL REFERENCES crew(crew_id),
    cert_type TEXT NOT NULL,
    valid_to  TEXT NOT NULL,
    PRIMARY KEY (crew_id, cert_type)
);
CREATE INDEX ix_certification_valid_to ON certification(valid_to);

CREATE TABLE reserve (
    crew_id      TEXT PRIMARY KEY REFERENCES crew(crew_id),
    base         TEXT NOT NULL,
    window_start TEXT NOT NULL,
    window_end   TEXT NOT NULL
);

CREATE TABLE reserve_date (
    crew_id     TEXT NOT NULL REFERENCES reserve(crew_id),
    on_call_date TEXT NOT NULL,
    PRIMARY KEY (crew_id, on_call_date)
);

CREATE TABLE duty_clock (
    crew_id          TEXT PRIMARY KEY REFERENCES crew(crew_id),
    as_of_utc        TEXT NOT NULL,
    duty_hours_7d    REAL NOT NULL,
    flight_hours_28d REAL NOT NULL,
    last_rest_ended  TEXT
);

CREATE TABLE daily_history (
    crew_id       TEXT NOT NULL REFERENCES crew(crew_id),
    history_date  TEXT NOT NULL,
    duty_hours    REAL NOT NULL,
    flight_hours  REAL NOT NULL,
    PRIMARY KEY (crew_id, history_date)
);
CREATE INDEX ix_daily_history_date ON daily_history(history_date);
"""


class DatasetStore:
    """A queryable projection of the world. Read only once built."""

    def __init__(self, world: WorldState, *, path: Path | None = None) -> None:
        self.world = world
        self._tempdir: tempfile.TemporaryDirectory[str] | None = None
        if path is None:
            self._tempdir = tempfile.TemporaryDirectory(prefix="crewops-store-")
            path = Path(self._tempdir.name) / "crewops.sqlite3"
        self._guard_path(path, world)
        self.path = path
        self.connection = sqlite3.connect(str(path), check_same_thread=False)
        self.connection.row_factory = sqlite3.Row
        self.connection.executescript(SCHEMA)
        self._populate()
        self.connection.commit()

    @staticmethod
    def _guard_path(path: Path, world: WorldState) -> None:
        """Refuse to build the projection inside the shipped dataset."""
        dataset_root = world.data_dir.resolve()
        target = path.resolve()
        if dataset_root == target or dataset_root in target.parents:
            raise ValueError(
                f"Refusing to write a SQLite projection inside the dataset at "
                f"{dataset_root}. The shipped data is read only."
            )

    # ------------------------------------------------------------- building

    def _populate(self) -> None:
        world = self.world
        risk = {r.crew_id: r.disruption_risk_score for r in world.risk_signals}
        reserve_ids = world.reserve_ids

        self.connection.executemany(
            "INSERT INTO crew VALUES (?,?,?,?,?,?,?,?,?)",
            [
                (
                    c.crew_id,
                    c.name,
                    c.rank,
                    c.base,
                    c.seniority,
                    c.reachability_minutes,
                    c.status,
                    int(c.crew_id in reserve_ids),
                    risk.get(c.crew_id),
                )
                for c in world.crew
            ],
        )
        self.connection.executemany(
            "INSERT INTO crew_rating VALUES (?,?)",
            [(c.crew_id, rating) for c in world.crew for rating in c.ratings],
        )
        self.connection.executemany(
            "INSERT INTO flight VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
            [
                (
                    f.flight_id,
                    f.flight_no,
                    f.date.isoformat(),
                    f.dep_station,
                    f.arr_station,
                    f.dep_utc.isoformat(sep=" "),
                    f.arr_utc.isoformat(sep=" "),
                    f.block_hours,
                    f.aircraft,
                    f.aircraft_type,
                    f.seats,
                    p.pairing_id if (p := world.pairing_for_flight(f.flight_id)) else None,
                )
                for f in world.flights
            ],
        )
        self.connection.executemany(
            "INSERT INTO pairing VALUES (?,?,?,?,?)",
            [
                (
                    p.pairing_id,
                    p.aircraft,
                    len(p.days),
                    p.total_sectors,
                    p.days[0].date.isoformat(),
                )
                for p in world.pairings
            ],
        )
        self.connection.executemany(
            "INSERT INTO pairing_day VALUES (?,?,?,?,?,?,?)",
            [
                (
                    p.pairing_id,
                    d.date.isoformat(),
                    d.report_utc.isoformat(sep=" "),
                    d.release_utc.isoformat(sep=" "),
                    d.sectors,
                    d.duty_hours,
                    world.block_hours_of(d.flights),
                )
                for p in world.pairings
                for d in p.days
            ],
        )
        self.connection.executemany(
            "INSERT INTO pairing_crew VALUES (?,?,?)",
            [(p.pairing_id, m.crew_id, m.role) for p in world.pairings for m in p.crew],
        )
        self.connection.executemany(
            "INSERT INTO week_duty VALUES (?,?,?,?,?,?,?)",
            [
                (
                    d.crew_id,
                    d.duty_date.isoformat(),
                    d.pairing_id,
                    d.report_utc.isoformat(sep=" "),
                    d.release_utc.isoformat(sep=" "),
                    d.duty_hours,
                    d.block_hours,
                )
                for c in world.crew
                for d in world.week_duties(c.crew_id)
            ],
        )
        self.connection.executemany(
            "INSERT INTO certification VALUES (?,?,?)",
            [(c.crew_id, c.cert_type, c.valid_to.isoformat()) for c in world.certifications],
        )
        self.connection.executemany(
            "INSERT INTO reserve VALUES (?,?,?,?)",
            [
                (r.crew_id, r.base, r.oncall_window_utc.start, r.oncall_window_utc.end)
                for r in world.reserves
            ],
        )
        self.connection.executemany(
            "INSERT INTO reserve_date VALUES (?,?)",
            [(r.crew_id, d.isoformat()) for r in world.reserves for d in r.dates],
        )
        clocks = [world.duty_clock(c.crew_id) for c in world.crew]
        self.connection.executemany(
            "INSERT INTO duty_clock VALUES (?,?,?,?,?)",
            [
                (
                    clock.crew_id,
                    clock.as_of_utc.isoformat(sep=" "),
                    clock.duty_hours_7d,
                    clock.flight_hours_28d,
                    clock.last_rest_ended.isoformat(sep=" ") if clock.last_rest_ended else None,
                )
                for clock in clocks
                if clock is not None
            ],
        )
        self.connection.executemany(
            "INSERT INTO daily_history VALUES (?,?,?,?)",
            [
                (clock.crew_id, e.date.isoformat(), e.duty_hours, e.flight_hours)
                for clock in clocks
                if clock is not None
                for e in clock.daily_history
            ],
        )

    # -------------------------------------------------------------- queries

    def query(self, sql: str, params: Sequence[Any] = ()) -> list[sqlite3.Row]:
        return list(self.connection.execute(sql, tuple(params)))

    def scalar(self, sql: str, params: Sequence[Any] = ()) -> Any:
        row = self.connection.execute(sql, tuple(params)).fetchone()
        return None if row is None else row[0]

    def counts(self) -> dict[str, int]:
        tables = (
            "crew",
            "flight",
            "pairing",
            "pairing_day",
            "pairing_crew",
            "week_duty",
            "certification",
            "reserve",
            "duty_clock",
            "daily_history",
        )
        return {t: int(self.scalar(f"SELECT count(*) FROM {t}") or 0) for t in tables}

    def find_crew_ids(
        self,
        *,
        base: str | None = None,
        rank: str | None = None,
        aircraft_type: str | None = None,
        status: str | None = None,
        on_reserve_date: DateType | None = None,
        free_on: DateType | None = None,
        name_contains: str | None = None,
        crew_ids: Sequence[str] | None = None,
        limit: int | None = None,
    ) -> list[str]:
        """Crew matching a filter set, ordered by crew id.

        An empty list here is a **finding**, not a failure. The caller decides
        how to say "no crew match that filter", which is a different answer from
        "the lookup broke".
        """
        sql = ["SELECT c.crew_id FROM crew c"]
        where: list[str] = []
        params: list[Any] = []

        if aircraft_type:
            sql.append("JOIN crew_rating r ON r.crew_id = c.crew_id AND r.aircraft_type = ?")
            params.append(aircraft_type)
        if base:
            where.append("c.base = ?")
            params.append(base)
        if rank:
            where.append("c.rank = ?")
            params.append(rank)
        if status:
            where.append("c.status = ?")
            params.append(status)
        if name_contains:
            where.append("lower(c.name) LIKE ?")
            params.append(f"%{name_contains.lower()}%")
        if crew_ids is not None:
            if not crew_ids:
                return []
            where.append(f"c.crew_id IN ({','.join('?' * len(crew_ids))})")
            params.extend(crew_ids)
        if on_reserve_date is not None:
            where.append(
                "EXISTS (SELECT 1 FROM reserve_date rd WHERE rd.crew_id = c.crew_id "
                "AND rd.on_call_date = ?)"
            )
            params.append(on_reserve_date.isoformat())
        if free_on is not None:
            where.append(
                "NOT EXISTS (SELECT 1 FROM week_duty w WHERE w.crew_id = c.crew_id "
                "AND w.duty_date = ?)"
            )
            params.append(free_on.isoformat())

        if where:
            sql.append("WHERE " + " AND ".join(where))
        sql.append("ORDER BY c.crew_id")
        if limit is not None:
            sql.append("LIMIT ?")
            params.append(limit)
        return [str(row["crew_id"]) for row in self.query(" ".join(sql), params)]

    def find_flight_ids(
        self,
        *,
        origin: str | None = None,
        destination: str | None = None,
        on_date: DateType | None = None,
        from_time: str | None = None,
        to_time: str | None = None,
        flight_numbers: Sequence[str] | None = None,
        pairing_id: str | None = None,
        aircraft_type: str | None = None,
        limit: int | None = None,
    ) -> list[str]:
        """Flights matching a filter set, in departure order."""
        where: list[str] = []
        params: list[Any] = []
        if origin:
            where.append("dep_station = ?")
            params.append(origin)
        if destination:
            where.append("arr_station = ?")
            params.append(destination)
        if on_date is not None:
            where.append("flight_date = ?")
            params.append(on_date.isoformat())
        if from_time:
            where.append("dep_utc >= ?")
            params.append(from_time)
        if to_time:
            where.append("dep_utc <= ?")
            params.append(to_time)
        if flight_numbers is not None:
            if not flight_numbers:
                return []
            where.append(f"flight_no IN ({','.join('?' * len(flight_numbers))})")
            params.extend(flight_numbers)
        if pairing_id:
            where.append("pairing_id = ?")
            params.append(pairing_id)
        if aircraft_type:
            where.append("aircraft_type = ?")
            params.append(aircraft_type)

        sql = "SELECT flight_id FROM flight"
        if where:
            sql += " WHERE " + " AND ".join(where)
        sql += " ORDER BY flight_date, dep_utc, flight_no"
        if limit is not None:
            sql += " LIMIT ?"
            params.append(limit)
        return [str(row["flight_id"]) for row in self.query(sql, params)]

    def expiring_certifications(
        self,
        *,
        as_of: DateType,
        until: DateType,
        certification_type: str | None = None,
        base: str | None = None,
    ) -> list[sqlite3.Row]:
        """Certificates whose `valid_to` falls in `[as_of, until]`, soonest first.

        `valid_from` is not projected into the store at all: it is unusable in
        this dataset and a column nobody can read is a column nobody can
        misread.
        """
        sql = [
            "SELECT ct.crew_id, ct.cert_type, ct.valid_to, c.name, c.rank, c.base, c.status",
            "FROM certification ct JOIN crew c ON c.crew_id = ct.crew_id",
            "WHERE ct.valid_to >= ? AND ct.valid_to <= ?",
        ]
        params: list[Any] = [as_of.isoformat(), until.isoformat()]
        if certification_type:
            sql.append("AND ct.cert_type = ?")
            params.append(certification_type)
        if base:
            sql.append("AND c.base = ?")
            params.append(base)
        sql.append("ORDER BY ct.valid_to, ct.crew_id")
        return self.query(" ".join(sql), params)

    def crew_on_date(self, on_date: DateType) -> list[sqlite3.Row]:
        """Everyone rostered on a date, with the pairing they are flying."""
        return self.query(
            "SELECT w.crew_id, w.pairing_id, w.report_utc, w.release_utc, w.duty_hours, "
            "c.rank, c.base FROM week_duty w JOIN crew c ON c.crew_id = w.crew_id "
            "WHERE w.duty_date = ? ORDER BY w.report_utc, w.crew_id",
            [on_date.isoformat()],
        )

    # ------------------------------------------------------------ lifecycle

    def close(self) -> None:
        self.connection.close()
        if self._tempdir is not None:
            self._tempdir.cleanup()
            self._tempdir = None

    def __enter__(self) -> DatasetStore:
        return self

    def __exit__(self, *_: object) -> None:
        self.close()


@contextmanager
def open_store(world: WorldState, *, path: Path | None = None) -> Iterator[DatasetStore]:
    store = DatasetStore(world, path=path)
    try:
        yield store
    finally:
        store.close()


__all__ = ["SCHEMA", "DatasetStore", "open_store"]

"""Read the shipped dataset into typed records.

**The dataset is read only.** Nothing in this module opens a file for writing,
and nothing anywhere in `crewops` may. Regenerating or mutating it would
silently move the answer keys every golden test asserts against.

The loader parses and validates; it does not interpret. Every derived index and
every piece of arithmetic lives in `world.py` and `crewops.rules`.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from pydantic import TypeAdapter

from crewops.domain.models import (
    Certification,
    Costs,
    Crew,
    DutyClock,
    Flight,
    Reserve,
    RiskSignal,
    Rosters,
    RuleBook,
)

#: Environment override, for a judge who has the dataset somewhere else.
DATA_DIR_ENV = "CREWOPS_DATA_DIR"


def _default_data_dir() -> Path:
    """Locate `data/crew-ops-advisor-dataset/data` by walking up from this file."""
    override = os.environ.get(DATA_DIR_ENV)
    if override:
        return Path(override).expanduser().resolve()

    here = Path(__file__).resolve()
    for parent in here.parents:
        candidate = parent / "data" / "crew-ops-advisor-dataset" / "data"
        if candidate.is_dir():
            return candidate
    raise FileNotFoundError(
        "Could not locate the shipped dataset. Expected "
        "data/crew-ops-advisor-dataset/data above this file, or set "
        f"{DATA_DIR_ENV}."
    )


DATA_DIR: Path = _default_data_dir()

def read_json(path: Path) -> Any:
    """Read one dataset file. Read only, always."""
    with path.open(encoding="utf-8") as handle:
        return json.load(handle)


def _parse[T](adapter: TypeAdapter[T], path: Path) -> T:
    return adapter.validate_python(read_json(path))


_FLIGHTS = TypeAdapter(tuple[Flight, ...])
_CREW = TypeAdapter(tuple[Crew, ...])
_ROSTERS = TypeAdapter(Rosters)
_CLOCKS = TypeAdapter(tuple[DutyClock, ...])
_RESERVES = TypeAdapter(tuple[Reserve, ...])
_CERTS = TypeAdapter(tuple[Certification, ...])
_RULES = TypeAdapter(RuleBook)
_COSTS = TypeAdapter(Costs)
_RISK = TypeAdapter(tuple[RiskSignal, ...])


class RawDataset:
    """Every shipped file, parsed and validated, with no interpretation applied."""

    def __init__(self, data_dir: Path | None = None) -> None:
        root = data_dir or DATA_DIR
        if not root.is_dir():
            raise FileNotFoundError(f"Dataset directory does not exist: {root}")
        self.data_dir: Path = root
        self.flights: tuple[Flight, ...] = _parse(_FLIGHTS, root / "flights.json")
        self.crew: tuple[Crew, ...] = _parse(_CREW, root / "crew.json")
        self.rosters: Rosters = _parse(_ROSTERS, root / "rosters.json")
        self.duty_clocks: tuple[DutyClock, ...] = _parse(_CLOCKS, root / "duty_clocks.json")
        self.reserves: tuple[Reserve, ...] = _parse(_RESERVES, root / "reserve_pool.json")
        self.certifications: tuple[Certification, ...] = _parse(
            _CERTS, root / "certifications.json"
        )
        self.rules: RuleBook = _parse(_RULES, root / "rules.json")
        self.costs: Costs = _parse(_COSTS, root / "costs.json")
        self.risk_signals: tuple[RiskSignal, ...] = _parse(_RISK, root / "risk_signals.json")

    #: The files a citation can point at.
    FILES: tuple[str, ...] = (
        "flights.json",
        "crew.json",
        "rosters.json",
        "duty_clocks.json",
        "reserve_pool.json",
        "certifications.json",
        "rules.json",
        "costs.json",
        "risk_signals.json",
    )


def load_raw(data_dir: Path | None = None) -> RawDataset:
    """Parse every shipped file. Prefer `crewops.domain.load_world`."""
    return RawDataset(data_dir)


__all__ = ["DATA_DIR", "DATA_DIR_ENV", "RawDataset", "load_raw", "read_json"]

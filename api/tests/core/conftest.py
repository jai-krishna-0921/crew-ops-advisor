"""Shared fixtures for the core engine tests.

The scenarios and questions files are answer keys, not inputs, so they are
loaded here for assertions and never touched by the engine itself.
"""

from __future__ import annotations

import json
from typing import Any

import pytest

from crewops.domain import DATA_DIR, WorldState, load_world
from crewops.ops import OpsEngine
from crewops.rules import LegalityEngine


@pytest.fixture(scope="session")
def world() -> WorldState:
    return load_world()


@pytest.fixture(scope="session")
def engine(world: WorldState) -> LegalityEngine:
    return LegalityEngine(world)


@pytest.fixture(scope="session")
def ops(world: WorldState) -> OpsEngine:
    return OpsEngine(world)


@pytest.fixture(scope="session")
def scenarios() -> dict[str, dict[str, Any]]:
    raw = json.loads((DATA_DIR / "scenarios.json").read_text(encoding="utf-8"))
    return {s["scenario_id"]: s for s in raw}


@pytest.fixture(scope="session")
def questions() -> dict[str, dict[str, Any]]:
    raw = json.loads((DATA_DIR / "questions.json").read_text(encoding="utf-8"))
    return {q["question_id"]: q for q in raw}

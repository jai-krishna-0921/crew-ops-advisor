"""Shared fixtures for `resolve/` tests.

Built on the real dataset and the real `Tools` registry, the same objects the
deterministic resolver uses at runtime. A hand rolled fixture would not catch
a mismatch between a render function and the actual payload shape a tool
returns, which is exactly the class of bug this package exists to avoid.
"""

from __future__ import annotations

from datetime import datetime

import pytest

from crewops.domain import WorldState, load_world
from crewops.resolve.resolver import DeterministicResolver
from crewops.tools.registry import Tools
from crewops.verify import Verifier

SNAPSHOT = datetime(2026, 9, 14, 18, 0, 0)


@pytest.fixture(scope="session")
def world() -> WorldState:
    return load_world()


@pytest.fixture(scope="session")
def tools(world: WorldState) -> Tools:
    return Tools(world)


@pytest.fixture(scope="session")
def verifier() -> Verifier:
    return Verifier()


@pytest.fixture(scope="session")
def resolver(tools: Tools) -> DeterministicResolver:
    return DeterministicResolver(tools, snapshot=SNAPSHOT)

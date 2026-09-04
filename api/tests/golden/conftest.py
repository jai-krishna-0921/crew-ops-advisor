"""Shared fixtures for answer-key parity.

Until the core lands there is nothing to call, so `advisor` skips with a message
naming the entry points it looked for. A skip is informative. An import error at
collection time is not, and it would make the whole suite red for a reason
unrelated to the code under test.

Case lists live in `crewops.eval.cases`, not here, so the test modules import
them from the package rather than from a conftest.
"""

from __future__ import annotations

from collections.abc import Callable, Iterator

import pytest

from crewops.contracts.reply import Reply
from crewops.eval import runner
from crewops.eval.cases import Case, dataset_available
from crewops.eval.grading import Grade, grade

AskFn = Callable[[Case], Grade]


@pytest.fixture(scope="session", autouse=True)
def _dataset_present() -> None:
    if not dataset_available():
        pytest.skip("provided dataset not found under data/crew-ops-advisor-dataset/")


@pytest.fixture(scope="session")
def advisor() -> Iterator[runner.AdvisorHandle]:
    runner.load_env()
    handle = runner.probe()
    if handle is None:
        pytest.skip(runner.missing_message())
    yield handle


@pytest.fixture(scope="session")
def ask(advisor: runner.AdvisorHandle) -> AskFn:
    """Run one case and grade it, caching so each case is asked once per session.

    Golden tests are parametrised per case so a failure names the question
    rather than the file. Without the cache, the aggregate tests that walk every
    case would ask all 38 a second time.

    Deterministic mode is used, so `make golden` is meaningful with no API key.
    """
    cache: dict[str, Grade] = {}

    def _ask(case: Case) -> Grade:
        if case.case_id in cache:
            return cache[case.case_id]
        try:
            reply, latency_ms = advisor.ask(case.prompt, mode=runner.MODE_DETERMINISTIC)
        except Exception as exc:
            result = grade(case, None, error=f"{type(exc).__name__}: {exc}")
        else:
            assert isinstance(reply, Reply)
            result = grade(case, reply, latency_ms=latency_ms)
        cache[case.case_id] = result
        return result

    return _ask

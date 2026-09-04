"""Answer-key parity across the 6 worked scenarios.

Scenarios are asked as their own `narrative` field, which is the text the
dataset wrote for a human. Asking the structured event instead would test JSON
parsing rather than the conversational interface the problem statement requires
as the primary one.

Each scenario is an alternate timeline applied to the base snapshot. They do
not chain: S2's sick call does not exist in S6's world. Nothing here may leave
state behind that a later scenario sees.
"""

from __future__ import annotations

from collections.abc import Callable

import pytest

from crewops.eval.cases import Case, load_scenarios, scenario_cases
from crewops.eval.grading import Grade, Outcome

AskFn = Callable[[Case], Grade]

pytestmark = pytest.mark.golden

_CASES = scenario_cases()

#: S2 is the flagship: it is the scenario the problem statement's own worked
#: examples come from, and every anchor fact in CLAUDE.md is derived from it.
FLAGSHIP = "S2"


@pytest.mark.parametrize("case", _CASES, ids=[c.case_id for c in _CASES])
def test_scenario_parity(case: Case, ask: AskFn) -> None:
    result = ask(case)

    if result.outcome is Outcome.ABSTAINED:
        pytest.xfail(
            f"{case.case_id} ({case.explanation}) abstained "
            f"({result.abstention_reason}): {result.note}"
        )

    assert result.outcome is not Outcome.ERROR, f"{case.case_id} raised: {result.note}"
    assert not result.unsafe, f"{case.case_id} inverted a verdict: {result.note}"
    assert result.outcome is Outcome.CORRECT, (
        f"{case.case_id} '{case.explanation}'\n"
        f"  outcome        {result.outcome.value}\n"
        f"  primary recall {result.primary_recall:.0%}\n"
        f"  full recall    {result.full_recall:.0%}\n"
        f"  missing facts  {', '.join(result.missed) or 'none'}"
    )


def test_flagship_scenario_holds(ask: AskFn) -> None:
    """S2 must be answered, exactly, always.

    It is the demo. If it abstains or drifts, the presentation has no spine.
    """
    matches = [case for case in _CASES if case.case_id == FLAGSHIP]
    if not matches:
        pytest.skip(f"{FLAGSHIP} not present in scenarios.json")
    result = ask(matches[0])
    assert result.outcome is Outcome.CORRECT, (
        f"{FLAGSHIP} is {result.outcome.value} at {result.primary_recall:.0%} recall. "
        f"Missing: {', '.join(result.missed) or 'none'}"
    )


def test_no_unsafe_scenario_answers(ask: AskFn) -> None:
    offences = [f"{g.case_id}: {g.note}" for g in (ask(case) for case in _CASES) if g.unsafe]
    assert not offences, "verdict inversions in the worked scenarios:\n  " + "\n  ".join(offences)


def test_every_shipped_scenario_is_covered() -> None:
    """The suite tests all six, not a convenient subset."""
    if not _CASES:
        pytest.skip("dataset unavailable")
    assert {c.case_id for c in _CASES} == {s.scenario_id for s in load_scenarios()}
    assert len(_CASES) == 6

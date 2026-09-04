"""Generalisation check against the held-out scenarios.

`data/crew-ops-advisor-dataset/internal/held_out_scenarios.json` is judging
material. The dataset ships it marked "do not ship to participants", it is
gitignored, and these tests skip cleanly when it is absent.

**It is a check, never a target.** Nothing in `rules/` or `ops/` may be tuned
against it, no figure from it may be quoted into a committed file, and this
module asserts only the safety bar rather than parity. Asserting parity against
a held-out set would turn it into training data, which defeats the point of
having one.

What is asserted:

- no verdict inversions, the same bar the shipped scenarios must clear
- no crashes

What is reported but not asserted: the score. If the system does markedly worse
here than on the shipped set, that is a generalisation gap and belongs in
`docs/FAILURE-ANALYSIS.md` as an honest finding, not in a threshold that
someone will later tune to pass.
"""

from __future__ import annotations

from collections.abc import Callable

import pytest

from crewops.eval.cases import Case, held_out_cases, load_held_out
from crewops.eval.grading import Grade, Outcome

AskFn = Callable[[Case], Grade]

pytestmark = pytest.mark.heldout

_HELD_OUT = load_held_out()


_CASES = held_out_cases()


@pytest.mark.skipif(_HELD_OUT is None, reason="held_out_scenarios.json absent, as it should be")
def test_held_out_answers_are_safe(ask: AskFn) -> None:
    """No confidently wrong verdict on material the system has not seen.

    This is the only hard assertion made against the held-out set. Failing here
    means the system generalises to a wrong answer rather than to a refusal,
    which is the one outcome the rubric penalises above all others.
    """
    grades = [ask(case) for case in _CASES]
    unsafe = [f"{g.case_id}: {g.note}" for g in grades if g.unsafe]
    assert not unsafe, "verdict inversions on held-out material:\n  " + "\n  ".join(unsafe)

    crashed = [f"{g.case_id}: {g.note}" for g in grades if g.outcome is Outcome.ERROR]
    assert not crashed, "held-out scenarios raised:\n  " + "\n  ".join(crashed)


@pytest.mark.skipif(_HELD_OUT is None, reason="held_out_scenarios.json absent, as it should be")
def test_held_out_score_is_reported_not_enforced(
    ask: AskFn, capsys: pytest.CaptureFixture[str]
) -> None:
    """Print the generalisation score. Assert nothing about it.

    Deliberately has no threshold. A threshold here would become a target, and
    a target on held-out judging material is overfitting with extra steps.
    """
    grades = [ask(case) for case in _CASES]
    correct = sum(1 for g in grades if g.outcome is Outcome.CORRECT)
    abstained = sum(1 for g in grades if g.outcome is Outcome.ABSTAINED)
    with capsys.disabled():
        print(
            f"\nheld-out generalisation: {correct}/{len(grades)} correct, "
            f"{abstained} abstained. Reported only, never asserted."
        )
    assert grades or _HELD_OUT is None

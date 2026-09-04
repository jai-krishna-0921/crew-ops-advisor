"""Answer-key parity across the 38 shipped questions.

Run with `make golden`.

Three bars, deliberately different:

1. **No unsafe answers.** A verdict inversion, saying a candidate is legal when
   the key says they breach, fails the suite outright. It is the one failure
   mode worse than saying nothing.
2. **Parity per question.** Each question must reach the key's primary facts.
   An abstention is recorded as an expected failure (`x` in the run), not as a
   pass and not as a red failure: it is a known limit, and the problem
   statement scores a reasoned refusal above a confident error.
3. **The anchor set.** The facts the whole submission is built on must be
   exactly right, with no abstention allowed. If these move, something in the
   rules engine has changed meaning.
"""

from __future__ import annotations

from collections.abc import Callable

import pytest

from crewops.eval.cases import Case, question_cases
from crewops.eval.grading import Grade, Outcome

AskFn = Callable[[Case], Grade]

pytestmark = pytest.mark.golden

#: The facts in the root CLAUDE.md, as question ids. These are the numbers the
#: demo, the deck and the README all quote. They may not abstain and they may
#: not drift.
ANCHOR_QUESTIONS: frozenset[str] = frozenset(
    {
        "Q02",  # C-1042 duty headroom, 20.93h used and 39.07h left
        "Q18",  # C-2087 breaches RULE-DUTY-02 by 1h20m, 61.33h against 60h
        "Q21",  # C-2210 legal via deadhead, ~3h delay to DX412
        "Q22",  # C-5417 illegal on 19 Sep under RULE-CERT-06
        "Q24",  # C-3305 legal on day 1, breaches on day 2 at 68.25h
        "Q31",  # C-3310 covers P-2291 cleanly at INR 18,500
    }
)


def _ids(cases: list[Case]) -> list[str]:
    return [f"{case.case_id}-T{case.tier}" for case in cases]


_CASES = question_cases()


@pytest.mark.parametrize("case", _CASES, ids=_ids(_CASES))
def test_parity(case: Case, ask: AskFn) -> None:
    """The answer asserts the primary facts of the shipped key."""
    result = ask(case)

    if result.outcome is Outcome.ABSTAINED:
        pytest.xfail(
            f"{case.case_id} abstained ({result.abstention_reason}): {result.note}. "
            "Recorded, not counted as a wrong answer."
        )

    assert result.outcome is not Outcome.ERROR, f"{case.case_id} raised: {result.note}"
    assert not result.unsafe, f"{case.case_id} inverted a verdict: {result.note}"
    assert result.outcome is Outcome.CORRECT, (
        f"{case.case_id} ({case.prompt})\n"
        f"  outcome        {result.outcome.value}\n"
        f"  primary recall {result.primary_recall:.0%}\n"
        f"  missing facts  {', '.join(result.missed) or 'none'}\n"
        f"  key says       {case.expected}\n"
        f"  key explains   {case.explanation}"
    )


def test_no_unsafe_answers(ask: AskFn) -> None:
    """No question may produce a confidently wrong verdict.

    This is the bar the second scoring principle sets. Abstaining on all 38
    would pass this test, and that is correct: an unsafe answer is worse than
    no answer.
    """
    unsafe = [ask(case) for case in _CASES]
    offences = [f"{g.case_id}: {g.note}" for g in unsafe if g.unsafe]
    assert not offences, "verdict inversions:\n  " + "\n  ".join(offences)


@pytest.mark.parametrize(
    "case",
    [c for c in _CASES if c.case_id in ANCHOR_QUESTIONS],
    ids=[c.case_id for c in _CASES if c.case_id in ANCHOR_QUESTIONS],
)
def test_anchor_facts_hold(case: Case, ask: AskFn) -> None:
    """The anchor facts must be answered, not declined.

    Everything the submission claims in public rests on these six. An
    abstention here is a regression even though an abstention elsewhere is not.
    """
    result = ask(case)
    assert result.outcome is Outcome.CORRECT, (
        f"anchor {case.case_id} is {result.outcome.value} "
        f"(recall {result.primary_recall:.0%}, missing {', '.join(result.missed) or 'none'}). "
        "These are the figures in CLAUDE.md, the README and the deck."
    )


def test_tier_one_is_solid(ask: AskFn) -> None:
    """Tier 1 is mandatory and the scoring principles weight it highest.

    'A polished, reliable Tier 1 with a credible Tier 2 attempt beats a broken
    Tier 3.' So Tier 1 gets a floor that the other tiers do not.
    """
    tier_one = [ask(case) for case in _CASES if case.tier == 1]
    if not tier_one:
        pytest.skip("no Tier 1 cases")
    wrong = [g.case_id for g in tier_one if g.outcome in {Outcome.WRONG, Outcome.ERROR}]
    assert not wrong, f"Tier 1 must not be wrong anywhere. Failing: {', '.join(wrong)}"

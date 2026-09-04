"""Tests for the grader itself.

The grader is the instrument every other number in this repository is measured
with. An untested instrument is worse than no instrument, because it produces
numbers people believe.

These run with no advisor and no API key: they build `Reply` objects by hand
and check that the grader reaches the right verdict about them. They are not
marked `golden`, because they assert nothing about the system under test.
"""

from __future__ import annotations

from datetime import datetime

import pytest

from crewops.contracts.evidence import (
    Abstention,
    AbstentionReason,
    VerificationReport,
    VerificationStatus,
)
from crewops.contracts.reply import AnswerMode, Reply, ReplyKind
from crewops.eval import atoms
from crewops.eval.cases import RUBRIC_QUESTIONS, load_questions, load_scenarios
from crewops.eval.grading import Outcome, grade, reduce_expected


def reply(
    text: str, *, kind: ReplyKind = ReplyKind.ANSWER, abstention: Abstention | None = None
) -> Reply:
    return Reply(
        thread_id="t",
        turn_id="u",
        question="q",
        asked_at=datetime(2026, 9, 14, 18, 0),
        kind=kind,
        mode=AnswerMode.DETERMINISTIC,
        text=text,
        abstention=abstention,
        verification=VerificationReport(status=VerificationStatus.VERIFIED),
    )


@pytest.fixture(scope="module")
def questions() -> dict[str, object]:
    return {case.case_id: case for case in load_questions()}


# ------------------------------------------------------------- normalisation


@pytest.mark.parametrize(
    ("left", "right"),
    [
        ("1h20m", "1.33 hours"),
        ("8h15m", "8.25 h"),
        ("1h05m", "1.08 hours"),
        ("INR 18,500", "18500"),
        ("18,500", "18500.0"),
        ("2026-09-17T03:30:00Z", "2026-09-17 03:30"),
    ],
)
def test_equivalent_renderings_of_the_same_fact_match(left: str, right: str) -> None:
    """`1h20m` and 1.33 hours are the same fact.

    The answer keys format durations as hours and minutes. A good prose answer
    formats them as decimal hours, or the other way round. If the grader could
    not see through that, it would mark correct answers wrong and the whole
    scorecard would be misleading in the direction that matters most.
    """
    left_atoms = atoms.extract(left)
    right_atoms = atoms.extract(right)
    assert left_atoms, f"nothing extracted from {left!r}"
    assert right_atoms, f"nothing extracted from {right!r}"
    _, missed = atoms.containment(left_atoms, right_atoms)
    assert not missed, f"{left!r} did not match {right!r}: missed {[str(m) for m in missed]}"


def test_a_flight_number_satisfies_a_flight_id() -> None:
    """Keys mix `DX402` and `DX402-2026-09-17` for the same leg."""
    required = atoms.extract("DX402-2026-09-17")
    produced = atoms.extract("DX402 on 2026-09-17 is affected")
    _, missed = atoms.containment(required, produced)
    assert not missed


def test_identifiers_do_not_leak_their_digits_as_numbers() -> None:
    """`C-1042` must not also register as the number 1042."""
    found = atoms.extract("C-1042 operates P-2291 on DX412-2026-09-15")
    assert {atom.kind for atom in found} == {"identifier"}, [str(a) for a in found]


def test_a_job_title_is_not_a_ranking_position() -> None:
    """Q01's reserves carry `"rank": "Captain"`, which is not an ordinal.

    Reading it as one collapsed twelve required reserves to whichever name
    sorted first, and every answer to Q01 would have scored correct while
    listing one of them.
    """
    from crewops.eval.grading import reduce_expected as reduce_

    rows = [{"crew_id": "C-1", "rank": "Captain"}, {"crew_id": "C-2", "rank": "Cabin Crew"}]
    assert len(reduce_(rows)) == 2
    ordinals = [{"crew_id": "C-1", "rank": 2}, {"crew_id": "C-2", "rank": 1}]
    assert reduce_(ordinals) == [{"crew_id": "C-2", "rank": 1}]


def test_zero_is_not_required_of_an_answer() -> None:
    """`delay_hours: 0.0` is an assertion of no delay, not a digit to recite."""
    required = [a for a in atoms.extract_from({"delay_hours": 0.0}) if not atoms.is_trivial(a)]
    assert required == []


def test_a_cost_survives_the_triviality_filter() -> None:
    kept = [a for a in atoms.extract_from({"cost_inr": 18500}) if not atoms.is_trivial(a)]
    assert [a.canon for a in kept] == ["18500"]


# -------------------------------------------------------------------- verdicts


def test_a_verdict_inversion_is_wrong_and_flagged_unsafe(questions: dict) -> None:
    """The single most important behaviour in this file.

    The key says C-2087 breaches. An answer that recites every correct figure
    but concludes 'legal' is an operational error, not a near miss, and the
    scorecard must say so on its own line rather than averaging it away.
    """
    result = grade(
        questions["Q18"],
        reply(
            "Captain C-2087 is legal for P-2291. On 2026-09-15 the window reaches "
            "61.33 hours and on 2026-09-16 it reaches 61.08 hours, 1h20m and 1h05m."
        ),
    )
    assert result.outcome is Outcome.WRONG
    assert result.unsafe is True
    assert "verdict inverted" in result.note


def test_a_correct_breach_answer_is_correct(questions: dict) -> None:
    result = grade(
        questions["Q18"],
        reply(
            "No. Assigning Captain C-2087 to P-2291 breaches RULE-DUTY-02. On "
            "2026-09-15 the seven day duty window reaches 61.33 hours against a 60 "
            "hour limit, over by 1h20m. On 2026-09-16 it reaches 61.08 hours, over "
            "by 1h05m."
        ),
    )
    assert result.outcome is Outcome.CORRECT
    assert result.unsafe is False


def test_the_multi_day_trap_is_gradeable(questions: dict) -> None:
    """C-3305 passes day one and breaches day two.

    This is the case a plausible implementation gets wrong, so the grader has to
    be able to tell the two answers apart.
    """
    good = grade(
        questions["Q24"],
        reply(
            "No. C-3305 breaches RULE-DUTY-02 on 2026-09-16: the seven day window "
            "reaches 68.25 hours against the 60 hour limit, over by 8h15m."
        ),
    )
    bad = grade(
        questions["Q24"],
        reply("Yes, C-3305 is legal to cover P-2291 across both days at 68.25 hours."),
    )
    assert good.outcome is Outcome.CORRECT
    assert bad.outcome is Outcome.WRONG
    assert bad.unsafe is True


# ----------------------------------------------------------------- abstention


def test_an_abstention_is_never_a_failure(questions: dict) -> None:
    """The rubric scores a reasoned refusal above a confident error.

    A scorecard that folded abstentions into the wrong column would push this
    project in exactly the wrong direction, so this is asserted rather than
    assumed.
    """
    result = grade(
        questions["Q18"],
        reply(
            "",
            kind=ReplyKind.ABSTAIN,
            abstention=Abstention(
                reason=AbstentionReason.REQUIRES_UNMODELLED_RULE,
                message="that needs a rule outside the seven provided",
            ),
        ),
    )
    assert result.outcome is Outcome.ABSTAINED
    assert result.outcome.is_failure is False
    assert result.abstention_reason == "requires_unmodelled_rule"


def test_an_exception_is_an_error_not_a_wrong_answer(questions: dict) -> None:
    result = grade(questions["Q01"], None, error="ValueError: boom")
    assert result.outcome is Outcome.ERROR
    assert result.outcome.is_failure is True


# ------------------------------------------------------------------ reduction


def test_tier_three_keys_reduce_to_the_chosen_option(questions: dict) -> None:
    """S2's key lists six options. No usable answer recites all six."""
    reduced = reduce_expected(questions["Q31"].expected)
    assert isinstance(reduced, list)
    assert len(reduced) == 1
    assert reduced[0]["crew_id"] == "C-3310"


def test_boilerplate_rule_lists_are_not_required(questions: dict) -> None:
    """`rules_checked` is identical on every option in every key.

    Requiring it would make recall a measure of how much boilerplate the answer
    repeated. It is dropped from the primary view and retained in `full_recall`.
    """
    reduced = reduce_expected(questions["Q31"].expected)
    assert "rules_checked" not in reduced[0]


def test_a_plain_list_key_is_not_reduced(questions: dict) -> None:
    """Q01's twelve reserves are all genuinely required."""
    reduced = reduce_expected(questions["Q01"].expected)
    assert len(reduced) == 12


def test_scenario_keys_reduce_to_the_expected_choice() -> None:
    scenarios = {s.scenario_id: s for s in load_scenarios()}
    reduced = reduce_expected(scenarios["S2"].answer_key)
    assert "options" not in reduced
    assert reduced["expected_choice"]["crew_id"] == "C-3310"


# --------------------------------------------------------------------- rubric


def test_rubric_questions_are_not_graded_on_exact_match(questions: dict) -> None:
    """Q30, Q36 and Q38 ship keys that say they are not exact-match targets.

    Grading them on containment scores three correct answers as wrong and
    understates the submission.
    """
    result = grade(
        questions["Q38"],
        reply(
            "Three per aircraft line: crew legality headroom on the seven day duty "
            "clock for the rostered crew, reserve availability by on-call window and "
            "rating, and the provided risk_signals for the rostered crew."
        ),
    )
    assert result.graded_as == "rubric"
    assert result.outcome is Outcome.CORRECT


def test_the_rubric_set_matches_the_keys_that_say_so() -> None:
    """Guard against the rubric list drifting from the dataset's own wording."""
    hedged = {
        case.case_id
        for case in load_questions()
        if "not exact match" in str(case.expected).lower()
        or "not template wording" in str(case.expected).lower()
        or "judged on" in str(case.expected).lower()
    }
    assert hedged <= RUBRIC_QUESTIONS, (
        f"{sorted(hedged - RUBRIC_QUESTIONS)} hedge their own answer key but are "
        "graded on exact containment"
    )


# ------------------------------------------------------------------- coverage


def test_the_shipped_counts_are_what_we_think_they_are() -> None:
    """16 Tier 1, 14 Tier 2, 8 Tier 3, 6 scenarios.

    If this fails, `data/` moved, and every answer key in the repository is
    suspect.
    """
    cases = load_questions()
    assert len(cases) == 38
    per_tier = {tier: sum(1 for c in cases if c.tier == tier) for tier in (1, 2, 3)}
    assert per_tier == {1: 16, 2: 14, 3: 8}
    assert len(load_scenarios()) == 6

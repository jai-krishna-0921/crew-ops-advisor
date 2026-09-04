"""A sick call needs the options, not only the damage.

S1, S2 and S6 are sick calls. All three matched `sick_impact`, which runs
`simulate_absence` and stops, and all three graded **wrong** at 15%, 14% and 7%
recall. Their answer keys want `options` and `excluded_candidates` alongside
the uncovered flights.

The prompts never say "what should I do", so `cover_options` never matched
them. But a scenario is a situation, not a question: a controller told that a
captain is sick at 01:30Z needs to know who can take the pairing, and the keys
are written for the controller rather than for the sentence.

Measured before writing this: routing S1 to `find_cover_options` alone takes it
from wrong at 15% to partial at 88%, with the option crew matching the key
exactly. Adding `simulate_absence` back for the uncovered legs takes it to
**correct at 100%**. So this is a planning gap, not a rules, tool or rendering
gap: both tools already return exactly the right answer and nothing was asking
the second one.
"""

from __future__ import annotations

import datetime as dt

import pytest

from crewops.resolve.intents import match_intent
from crewops.resolve.triage import canonical_question, triage_question

SICK_CALL = "Captain C-3231 calls in sick at 01:30Z on 16 Sep for pairing P-2224."


def plan_for(question: str) -> list:
    q = canonical_question(question)
    intent = match_intent(q)
    assert intent is not None, f"no intent matched {question!r}"
    entities = triage_question(q).entities
    return intent.build(entities, dt.datetime(2026, 9, 14, 18, 0))


def test_a_sick_call_still_models_the_absence() -> None:
    """The control. The impact half must not be lost."""
    tools = [call.tool for call in plan_for(SICK_CALL)]
    assert "simulate_absence" in tools


def test_a_sick_call_also_searches_for_cover() -> None:
    """The gap. Three of the six worked scenarios turned on this."""
    tools = [call.tool for call in plan_for(SICK_CALL)]
    assert "find_cover_options" in tools, (
        f"a sick call plans only {tools}. The controller is told what broke and "
        "not who can fix it, and the answer key wants both."
    )


def test_the_cover_search_asks_about_the_crew_who_went_sick() -> None:
    """`for_crew_id`, not `exclude_crew_ids`.

    Measured: `for_crew_id` returns exactly the option set the S1 key lists.
    """
    calls = {call.tool: call.args for call in plan_for(SICK_CALL)}
    args = calls["find_cover_options"]
    assert args.get("for_crew_id") == "C-3231"
    assert args.get("include_rejected") is True, (
        "the key lists excluded candidates, so the rejected ones have to come back"
    )


def test_the_cover_search_names_the_pairing_when_the_question_does() -> None:
    calls = {call.tool: call.args for call in plan_for(SICK_CALL)}
    assert calls["find_cover_options"].get("pairing_id") == "P-2224"


def test_a_sick_call_without_a_pairing_still_plans_something() -> None:
    """`find_cover_options` resolves the pairing from the crew and the date."""
    tools = [call.tool for call in plan_for("Captain C-1042 calls in sick on 15 Sep.")]
    assert "simulate_absence" in tools


@pytest.mark.golden
class TestAgainstTheAnswerKeys:
    """The measurement this change exists for."""

    @staticmethod
    def grade(case_id: str) -> object:
        import asyncio

        from crewops.agent import Advisor
        from crewops.agent.factory import load_tools
        from crewops.eval import cases, grading

        by_id = {c.case_id: c for c in cases.scenario_cases()}
        if case_id not in by_id:
            pytest.skip(f"{case_id} not in scenarios.json")
        case = by_id[case_id]
        advisor = Advisor(load_tools())
        reply = asyncio.run(advisor.ask(case.prompt, force_mode="deterministic"))
        return grading.grade(case, reply)

    def test_s1_is_no_longer_wrong(self) -> None:
        grade = self.grade("S1")
        from crewops.eval.grading import Outcome

        assert grade.outcome is not Outcome.WRONG, (  # type: ignore[attr-defined]
            f"S1 still {grade.outcome.value} at {grade.primary_recall:.0%}, "  # type: ignore[attr-defined]
            f"missing {grade.missed[:6]}"  # type: ignore[attr-defined]
        )

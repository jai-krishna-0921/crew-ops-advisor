"""Tier 1 through the agent path, against a live provider.

Tier 1 is the mandatory tier and the deterministic resolver already answers it
at 15 of 16 with nothing wrong. Routing the same questions through the LangGraph
agent is only worth doing if it does not make that worse, so this file measures
exactly that and nothing else.

The assertion is the rubric's own scoring principle, not an accuracy target:

    Answering ten questions correctly and saying "I cannot answer that
    reliably" on the eleventh scores higher than answering all eleven with
    three wrong.

So an abstention is a pass here. A wrong answer is the only failure, because a
wrong answer is the one outcome a controller cannot recover from: they act on
it. That is also why the deterministic mode is scored in the same run and used
as the floor. A provider that turns a question the offline path gets right into
a question the agent path gets wrong has made the system worse, and the whole
point of the boundary is that adding the model must not be able to do that.

Skips with no provider configured, so `make test` stays offline and free. Run
it deliberately:

    uv run pytest -m llm -v

Note that hosted models are not reproducible even at temperature 0. Treat a
single failure as a signal to look, not as a verdict: `make eval --mode both`
is the instrument, and this is the tripwire.
"""

from __future__ import annotations

import pytest

from crewops.eval import cases, grading, runner

pytestmark = [pytest.mark.llm, pytest.mark.golden]


@pytest.fixture(scope="module")
def handle() -> runner.AdvisorHandle:
    runner.load_env()
    if not runner.has_api_key():
        pytest.skip(
            "No model provider configured. "
            "Set ANTHROPIC_API_KEY, OPENAI_API_KEY or OLLAMA_API_KEY."
        )
    built = runner.probe()
    if built is None:
        pytest.skip(runner.missing_message())
    if not built.has_model:
        pytest.skip("A provider is configured but no model was built: no agent path to test.")
    return built


@pytest.fixture(scope="module")
def tier1() -> list[cases.Case]:
    selected = [case for case in cases.question_cases() if case.tier == 1]
    if not selected:
        pytest.skip("No Tier 1 cases found in questions.json")
    return selected


def test_the_agent_never_answers_a_tier_1_question_wrongly(
    handle: runner.AdvisorHandle, tier1: list[cases.Case]
) -> None:
    """The one outcome that is worse than no answer.

    Grounding verification is what is supposed to make this impossible: an
    answer whose figures trace back to no tool output is rejected before it
    reaches anyone. A failure here therefore means one of two things, and it is
    worth knowing which. Either the model stated something the tools never
    returned and the verifier's extractor did not recognise it as a checkable
    atom, or the model called the wrong tool and reported its answer faithfully.

    The second is the harder one, and no amount of token attestation catches
    it: every atom is genuinely attested, it just answers a different question.
    """
    wrong: list[str] = []
    for case in tier1:
        reply, _ = handle.ask(case.prompt, mode=runner.MODE_AGENT)
        grade = grading.grade(case, reply)
        if grade.outcome is grading.Outcome.WRONG:
            wrong.append(f"{case.case_id}: {case.prompt}\n      missed {', '.join(grade.missed)}")

    assert not wrong, (
        f"The agent answered {len(wrong)} of {len(tier1)} Tier 1 questions wrongly. "
        "An abstention here would have been a pass; a wrong answer is what a "
        "controller acts on.\n    " + "\n    ".join(wrong)
    )


def test_the_agent_does_not_regress_what_the_offline_path_gets_right(
    handle: runner.AdvisorHandle, tier1: list[cases.Case]
) -> None:
    """Adding the model must not subtract correctness.

    This is the claim the architecture rests on: deterministic code computes,
    the model only chooses and phrases. If that boundary holds then the agent
    can be slower or more talkative than the resolver, but it cannot be less
    right, because it is reading the same tool output.

    Abstentions are tolerated. They cost coverage, not trust.
    """
    regressed: list[str] = []
    for case in tier1:
        offline, _ = handle.ask(case.prompt, mode=runner.MODE_DETERMINISTIC)
        if grading.grade(case, offline).outcome is not grading.Outcome.CORRECT:
            continue
        agent, _ = handle.ask(case.prompt, mode=runner.MODE_AGENT)
        outcome = grading.grade(case, agent).outcome
        if outcome is grading.Outcome.WRONG:
            regressed.append(f"{case.case_id}: correct offline, {outcome.value} via the agent")

    assert not regressed, (
        "These questions are answered correctly by the deterministic resolver "
        "and wrongly by the agent reading the same tools:\n    "
        + "\n    ".join(regressed)
    )

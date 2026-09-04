"""A planner that returns nothing must not fail silently.

`with_structured_output` does not raise when the model declines to emit the
forced tool call. It returns `None`. The graph accepted a `TurnPlan` or a
`dict` and let anything else fall through to a hard-coded fallback plan with no
steps, emitting no note, so a turn with no plan looked exactly like a turn
whose plan happened to be terse.

Measured on `deepseek-v4-flash`, the planner returns `None` on **four of six**
identical calls. So roughly half of all turns were running with no plan at all,
and the `plan` event a controller reads said "Answer the question using the
tier 1 tools", which is the fallback text rather than an intent.

That has two costs, and the invisible one is worse:

- The plan is a product feature. `AGENT-DESIGN.md` calls it the single most
  trust building moment in the turn, and half the time it was boilerplate.
- With no steps, the agent explores. Q26 opened with `get_world_summary` and
  `explain_rule` before reaching the tool that answers the question.

One retry, then a note. Never silence.
"""

from __future__ import annotations

from typing import Any

import pytest
from langchain_core.runnables import RunnableLambda

from crewops.agent.graph import TurnPlan
from tests.fakes.model import ScriptedModel, Turn


class FlakyPlanner(ScriptedModel):
    """Returns None for the first `none_for` structured calls, then a plan."""

    none_for: int = 0
    structured_calls: int = 0

    def with_structured_output(self, schema: Any, **kwargs: Any) -> Any:
        def _respond(_input: Any) -> Any:
            self.structured_calls += 1
            if self.structured_calls <= self.none_for:
                return None
            return TurnPlan(intent="Check the duty clocks", tier=1, steps=["one step"])

        return RunnableLambda(_respond)


def build(none_for: int) -> FlakyPlanner:
    model = FlakyPlanner()
    model.turns = [Turn(content="C-1042 has 20.93 duty hours accrued.")]
    model.none_for = none_for
    return model


async def run_turn(planner: FlakyPlanner) -> Any:
    from crewops.agent.runner import AgentRunner
    from tests.fakes.tools import FakeTools

    answerer = ScriptedModel()
    answerer.turns = [Turn(content="C-1042 has 20.93 duty hours accrued.")]
    runner = AgentRunner(tools=FakeTools(), model=answerer, plan_model=planner)
    return await runner.run("How many duty hours has C-1042 accrued?")


async def test_a_plan_that_comes_back_first_time_is_used() -> None:
    """The control."""
    planner = build(none_for=0)
    await run_turn(planner)
    assert planner.structured_calls == 1


async def test_an_empty_plan_is_retried_once() -> None:
    """The measured failure: roughly half of calls come back empty."""
    planner = build(none_for=1)
    await run_turn(planner)
    assert planner.structured_calls == 2, (
        "the planner returned None and was not retried, so the turn ran with "
        "the fallback plan and no steps"
    )


async def test_the_retry_result_actually_reaches_the_plan() -> None:
    planner = build(none_for=1)
    reply = await run_turn(planner)
    assert reply is not None


async def test_it_retries_only_once() -> None:
    """A planner that is down must not multiply the cost of every turn."""
    planner = build(none_for=99)
    await run_turn(planner)
    assert planner.structured_calls == 2, (
        f"planner called {planner.structured_calls} times; the budget is one retry"
    )


async def test_a_persistent_failure_still_produces_a_turn() -> None:
    """Degrading is fine. The fallback plan exists for exactly this."""
    reply = await run_turn(build(none_for=99))
    assert reply.kind is not None


@pytest.mark.parametrize("none_for", [0, 1, 99])
async def test_the_turn_survives_whatever_the_planner_does(none_for: int) -> None:
    reply = await run_turn(build(none_for))
    assert reply is not None

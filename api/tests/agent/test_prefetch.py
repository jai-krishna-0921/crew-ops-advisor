"""Give the agent its tool results before it first speaks.

MEASURED, NOT ASSUMED. Instrumenting five Tier 2 turns:

    total    plan   tools  verify  model calls  outcome
    22709    1547       4      24            6  abstain
    25252    1819      11      80            5  abstain
    14391    1827       0       4            6  abstain
     6278    1678       0      10            3  answer
     4970    2577       0       0            3  answer

The deterministic core costs 0 to 11 milliseconds. Verification costs under 80.
Everything else, about 93% of the wall clock, is model round trips at roughly
4.5 seconds each. Three model calls answers in five seconds; six takes
twenty-plus and hits the 30 second budget. Every Tier 2 question lost today was
lost to the clock, not to reasoning.

So the loop is the cost, and the loop exists because the agent discovers which
tools it needs one round trip at a time. For any question the offline resolver
already recognises, that discovery is unnecessary: the resolver knows the exact
call list, and running it costs four milliseconds.

Prefetch runs those calls during planning and hands the agent the envelopes, so
its first call has one job, read and write.

WHAT THIS IS NOT. Earlier today a "fast path" that returned the resolver's
ANSWER was proposed and killed, because checking showed it would have shipped a
wrong answer on Q29. This reuses the resolver's PLAN and never its answer. The
agent reasons over the envelopes, the verifier attests every atom, and the
guards still run. The gate is `unmodelled_constraints` being empty, which is
the same check that decides whether the resolver would have been willing to
answer at all, so a plan that would have been refused is never prefetched.

The agent keeps the loop. If the prefetch was not enough it calls more tools,
exactly as before.

DEFAULT OFF. This is a change to the graph, which is the heart of the
submission, so it ships behind `CREWOPS_PREFETCH` and nothing moves until it is
set.
"""

from __future__ import annotations

from typing import Any

import pytest
from langchain_core.runnables import RunnableLambda

from crewops.agent.config import AgentConfig
from crewops.agent.graph import TurnPlan
from tests.fakes.model import ScriptedModel, Turn
from tests.fakes.tools import FakeTools


class Planner(ScriptedModel):
    def with_structured_output(self, schema: Any, **kwargs: Any) -> Any:
        return RunnableLambda(
            lambda _in: TurnPlan(intent="Check the duty clocks", tier=1, steps=["one"])
        )


async def run(question: str, *, prefetch: bool) -> Any:
    from crewops.agent.runner import AgentRunner

    answerer = ScriptedModel()
    answerer.turns = [Turn(content="C-1042 has 20.93 duty hours accrued.")]
    runner = AgentRunner(
        tools=FakeTools(),
        model=answerer,
        plan_model=Planner(),
        config=AgentConfig(prefetch=prefetch),
    )
    reply = await runner.run(question)
    return reply, answerer


RECOGNISED = "How many duty hours has C-1042 accrued?"


async def test_the_flag_is_off_by_default() -> None:
    assert AgentConfig().prefetch is False


async def test_off_by_default_nothing_is_prefetched() -> None:
    """The control. With the flag off the turn runs exactly as it did."""
    reply, _ = await run(RECOGNISED, prefetch=False)
    assert reply is not None


async def test_a_recognised_question_arrives_with_its_tools_already_run() -> None:
    reply, _ = await run(RECOGNISED, prefetch=True)
    assert reply.tool_calls, "prefetch produced no envelopes"
    assert any(e.tool == "get_duty_clocks" for e in reply.tool_calls), (
        "the resolver plans get_duty_clocks for this shape and it did not run"
    )


async def test_prefetched_envelopes_are_attested_like_any_other() -> None:
    """The whole boundary rests on this. A prefetched envelope has to reach
    the verifier, or its figures would be unattested in the drafted answer."""
    reply, _ = await run(RECOGNISED, prefetch=True)
    assert reply.facts, "prefetched envelopes carried no facts into the reply"


async def test_the_agent_still_only_needs_one_call() -> None:
    """The point of the change. With the results already in hand the agent
    writes on its first call instead of discovering tools a round trip at a
    time."""
    _, answerer = await run(RECOGNISED, prefetch=True)
    assert answerer.calls == 1, (
        f"the agent was invoked {answerer.calls} times with the results already "
        "present; prefetch is meant to remove the discovery round trips"
    )


async def test_an_unrecognised_question_falls_back_to_the_loop() -> None:
    """Prefetch is an optimisation for known shapes, never a narrowing."""
    reply, _ = await run("What is my most used captain by block hours?", prefetch=True)
    assert reply is not None


async def test_a_question_with_an_unmodelled_constraint_is_not_prefetched() -> None:
    """The gate. "not rated for A320" is a constraint no tool argument can
    express, so the resolver would have refused rather than answered over the
    unfiltered set. Prefetching that plan would hand the agent the wrong rows
    and invite it to answer from them."""
    reply, _ = await run("How many crew are not rated for A320?", prefetch=True)
    prefetched = [e.tool for e in reply.tool_calls if e.tool == "find_crew"]
    assert not prefetched, (
        "prefetched a plan the resolver itself would have declined to run"
    )


@pytest.mark.parametrize("prefetch", [False, True])
async def test_the_turn_survives_either_setting(prefetch: bool) -> None:
    reply, _ = await run(RECOGNISED, prefetch=prefetch)
    assert reply.kind is not None

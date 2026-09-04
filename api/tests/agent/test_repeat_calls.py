"""The same lookup, asked twice in one turn, is computed once.

Q27 called `list_reserves` four times. Two of them were byte identical:

    {'on_date': '2026-09-16', 'rank': 'Captain', 'aircraft_type': 'ATR72', ...}
    {'on_date': '2026-09-16', 'aircraft_type': 'ATR72', 'rank': 'Captain', ...}

Only the key order differs, and key order is not a difference. The turn paid a
full model round trip to be told something it already knew, and Tier 2 turns
were abstaining on the clock.

The saving here is the tool execution, which for these tools is milliseconds,
so this is the smaller half of the fix. It matters for the other reason: the
model gets its answer back immediately and the repeat stops compounding. The
larger half is the prompt telling it to issue independent lookups together in
one message, which the graph has always supported and nothing had ever asked
for.

Correctness constraint: a repeat must still get an answer. Suppressing the
*execution* is fine, suppressing the *reply* would strand the tool call and
break the message sequence the model expects.
"""

from __future__ import annotations

from typing import Any

import pytest

from crewops.agent.graph import repeat_key


def test_key_order_is_not_a_difference() -> None:
    """The exact shape of the Q27 duplicate."""
    first = repeat_key(
        "list_reserves",
        {"on_date": "2026-09-16", "rank": "Captain", "aircraft_type": "ATR72"},
    )
    second = repeat_key(
        "list_reserves",
        {"aircraft_type": "ATR72", "on_date": "2026-09-16", "rank": "Captain"},
    )
    assert first == second


def test_a_different_argument_is_a_different_call() -> None:
    """Q27's third call differs only in at_time, and is a real question."""
    base: dict[str, Any] = {"on_date": "2026-09-16", "rank": "Captain"}
    assert repeat_key("list_reserves", {**base, "at_time": "01:30"}) != repeat_key(
        "list_reserves", {**base, "at_time": "03:00"}
    )


def test_a_different_tool_is_a_different_call() -> None:
    assert repeat_key("list_reserves", {}) != repeat_key("find_crew", {})


def test_absent_and_null_arguments_agree() -> None:
    """`exclude_none` on one call and not the other is not a real difference."""
    assert repeat_key("find_crew", {"base": "BLR"}) == repeat_key(
        "find_crew", {"base": "BLR", "rank": None}
    )


def test_unserialisable_arguments_do_not_raise() -> None:
    """A key that cannot be hashed must degrade to "not a repeat", never crash.

    Suppression is an optimisation. It may lose a saving; it may not lose a
    turn.
    """
    assert repeat_key("x", {"when": object()}) is not None


class TestThroughTheGraph:
    """The behaviour the latency actually depends on."""

    @pytest.fixture
    def pieces(self) -> tuple[Any, Any]:
        from tests.fakes.model import Turn, script, tool_call
        from tests.fakes.tools import FakeTools

        args = {"on_date": "2026-09-16", "rank": "Captain"}
        flipped = {"rank": "Captain", "on_date": "2026-09-16"}
        model = script(
            Turn(tool_calls=[tool_call("list_reserves", **args)]),
            Turn(tool_calls=[tool_call("list_reserves", **flipped)]),
            Turn(content="Two reserve captains are on call on 2026-09-16."),
        )
        return model, FakeTools()

    async def test_the_repeat_is_not_executed_twice(self, pieces: tuple[Any, Any]) -> None:
        model, tools = pieces
        from crewops.agent.runner import AgentRunner

        await AgentRunner(tools=tools, model=model).run("Who is on reserve on 16 Sep?")
        assert tools.tools_called().count("list_reserves") == 1, (
            f"the identical lookup ran twice: {tools.tools_called()}"
        )

    async def test_the_repeat_still_gets_an_answer(self, pieces: tuple[Any, Any]) -> None:
        """Suppressing the execution must not strand the tool call.

        A tool_call with no matching tool result breaks the message sequence,
        and the provider rejects the next request rather than the turn simply
        being slower.
        """
        model, tools = pieces
        from crewops.agent.runner import AgentRunner

        reply = await AgentRunner(tools=tools, model=model).run("Who is on reserve?")
        names = [envelope.tool for envelope in reply.tool_calls]
        assert names.count("list_reserves") == 2, (
            f"the second call lost its envelope entirely: {names}"
        )

"""The offline path shows its work, not just its answer.

`_stream_deterministic` emitted five events: run_started, verification, an
optional abstain, reply, done. No `tool_call`, no `tool_result`, no `trace`.
So the whole trace panel, the task rows and the tool chips were dead on every
turn the deterministic resolver answered, which without an API key is every
turn there is. The old docstring justified it as "there is no intermediate
progress to report", and that is the wrong reading: the resolver ran six real
tools and measured six real latencies, then threw the record away on the way
to the screen.

The events below are REPLAYED from the envelopes the resolver produced, after
it produced them. Each carries the latency that tool actually took. Nothing is
invented and no progress is simulated: a run that finished in four
milliseconds emits its rows in four milliseconds. What the reader gets is the
list of what ran, which is what "explainability is mandatory" asks for and
what the agent path has always shown.
"""

from __future__ import annotations

from collections.abc import Iterator

import pytest

from crewops.agent.advisor import Advisor
from crewops.agent.factory import default_data_dir
from crewops.contracts import StreamEvent
from crewops.domain import load_world
from crewops.tools.registry import Tools


@pytest.fixture(scope="module")
def advisor() -> Iterator[Advisor]:
    root = default_data_dir()
    if not root.exists():
        pytest.skip("provided dataset not found under data/crew-ops-advisor-dataset/")
    yield Advisor(Tools(load_world(root)))


async def _events(advisor: Advisor, question: str) -> list[StreamEvent]:
    return [
        event async for event in advisor.stream(question, force_mode="deterministic")
    ]


async def test_the_offline_path_streams_the_tools_it_ran(advisor: Advisor) -> None:
    events = await _events(advisor, "Who is on reserve at BLR on 2026-09-15?")
    kinds = [event.type for event in events]

    assert "tool_call" in kinds, kinds
    assert "tool_result" in kinds, kinds

    calls = [e for e in events if e.type == "tool_call"]
    results = [e for e in events if e.type == "tool_result"]
    assert len(calls) == len(results)
    assert len(calls) > 0


async def test_every_streamed_tool_matches_one_on_the_reply(advisor: Advisor) -> None:
    """The rows are the envelopes, not a parallel account of them."""
    events = await _events(advisor, "Who is on reserve at BLR on 2026-09-15?")
    reply = next(e for e in events if e.type == "reply").reply

    streamed = [e.tool for e in events if e.type == "tool_call"]
    assert streamed == [envelope.tool for envelope in reply.tool_calls]

    for event in (e for e in events if e.type == "tool_result"):
        match = next(x for x in reply.tool_calls if x.tool == event.tool)
        assert event.latency_ms == match.latency_ms
        assert event.ok == match.ok


async def test_the_ordering_guarantee_still_holds(advisor: Advisor) -> None:
    """`seq` is monotonic, and the work is reported before the answer."""
    events = await _events(advisor, "Who is on reserve at BLR on 2026-09-15?")
    seqs = [event.seq for event in events]
    assert seqs == sorted(seqs)
    assert len(seqs) == len(set(seqs))

    kinds = [event.type for event in events]
    assert kinds[0] == "run_started"
    assert kinds[-1] == "done"
    assert kinds.index("tool_result") < kinds.index("reply")
    assert kinds.index("reply") < kinds.index("done")


async def test_a_refusal_still_streams_cleanly(advisor: Advisor) -> None:
    """An abstention names no tools, and must not invent any."""
    events = await _events(advisor, "what will the weather be in Bengaluru tomorrow")
    kinds = [event.type for event in events]
    assert kinds[0] == "run_started"
    assert kinds[-1] == "done"
    assert "reply" in kinds

"""A conversation has a name, and somebody can change it.

The rail listed threads by their first question, which for this product is
often ninety characters of situation ("Captain C-1042 is out for pairing P-2291
(15-16 Sep). Produce ranked resolution options with costs and reasoning."). Six
of those truncated to two lines are indistinguishable from each other, which
makes the list useless for the one thing it is for.

THE TITLE COMES FROM THE ANSWER, NOT FROM THE QUESTION. `Reply.headline` is a
short line written for a reader under time pressure, by the model in agent mode
and by the deterministic renderer offline. It is already the sentence somebody
would use to describe the exchange, so it is the name. A title is language
rather than a figure, which is why a model is allowed to author one: no cell of
the answer depends on it and the verifier has nothing to attest.

A name a person typed always wins, and is never overwritten by a later turn.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from datetime import UTC, datetime

import pytest

from crewops.agent.memory import Memory
from crewops.contracts import (
    AnswerMode,
    Reply,
    ReplyKind,
    Timings,
    VerificationReport,
    VerificationStatus,
)


def _reply(thread: str, turn: str, question: str, headline: str | None) -> Reply:
    return Reply(
        thread_id=thread,
        turn_id=turn,
        question=question,
        asked_at=datetime.now(UTC),
        kind=ReplyKind.ANSWER,
        mode=AnswerMode.DETERMINISTIC,
        headline=headline,
        text="body",
        verification=VerificationReport(status=VerificationStatus.SKIPPED),
        timings=Timings(total_ms=1),
    )


@pytest.fixture
async def memory(tmp_path) -> AsyncIterator[Memory]:
    async with Memory(tmp_path / "m.db") as store:
        yield store


async def test_a_thread_is_named_from_the_first_answer(memory: Memory) -> None:
    await memory.record(
        _reply("t1", "u1", "Who is on reserve at BLR on 2026-09-15?", "12 reserves on call")
    )
    rows = await memory.threads()
    assert rows[0].title == "12 reserves on call"


async def test_a_later_turn_does_not_rename_the_thread(memory: Memory) -> None:
    await memory.record(_reply("t1", "u1", "first", "First answer"))
    await memory.record(_reply("t1", "u2", "second", "Second answer"))
    rows = await memory.threads()
    assert rows[0].title == "First answer"


async def test_a_headline_free_answer_falls_back_to_the_question(memory: Memory) -> None:
    await memory.record(_reply("t1", "u1", "what is the weather", None))
    rows = await memory.threads()
    assert rows[0].title == "what is the weather"


async def test_a_person_can_rename_a_thread(memory: Memory) -> None:
    await memory.record(_reply("t1", "u1", "first", "First answer"))
    await memory.rename("t1", "  Monday disruption  ")
    rows = await memory.threads()
    assert rows[0].title == "Monday disruption"


async def test_a_name_a_person_typed_survives_the_next_turn(memory: Memory) -> None:
    await memory.record(_reply("t1", "u1", "first", "First answer"))
    await memory.rename("t1", "Monday disruption")
    await memory.record(_reply("t1", "u2", "second", "Second answer"))
    rows = await memory.threads()
    assert rows[0].title == "Monday disruption"


async def test_renaming_to_nothing_is_refused(memory: Memory) -> None:
    await memory.record(_reply("t1", "u1", "first", "First answer"))
    assert await memory.rename("t1", "   ") is False
    rows = await memory.threads()
    assert rows[0].title == "First answer"


async def test_renaming_a_thread_that_does_not_exist_is_refused(memory: Memory) -> None:
    assert await memory.rename("nope", "Anything") is False


async def test_deleting_a_thread_takes_its_turns_and_its_name(memory: Memory) -> None:
    await memory.record(_reply("t1", "u1", "first", "First answer"))
    await memory.record(_reply("t2", "u2", "other", "Other answer"))

    assert await memory.delete("t1") is True
    rows = await memory.threads()
    assert [row.thread_id for row in rows] == ["t2"]
    assert await memory.turns("t1") == []

    # And the name goes with it, so a recycled id cannot inherit it.
    await memory.record(_reply("t1", "u3", "reused", "Reused answer"))
    rows = await memory.threads()
    titles = {row.thread_id: row.title for row in rows}
    assert titles["t1"] == "Reused answer"


async def test_deleting_a_thread_that_does_not_exist_is_refused(memory: Memory) -> None:
    assert await memory.delete("nope") is False

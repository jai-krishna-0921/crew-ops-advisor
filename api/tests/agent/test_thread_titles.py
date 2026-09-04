"""A conversation has a name, and somebody can change it.

This file owns the *storage* rules: named once on the first turn, never
renamed by a later one, a name a person typed always wins, and deleting a
thread takes its name with it so a recycled id cannot inherit one.

Where the name itself comes from moved, and `tests/agent/test_titles.py` owns
that now. It used to be `Reply.headline`, on the reasoning that the answer's
opening line is already the sentence somebody would use to describe the
exchange. In a 208 pixel rail it is not: "hey" produced a thread called "This
is a crew operations desk assistant". It is the question that gets named, in
five words, identifier first.
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


async def test_a_thread_is_named_from_the_question_that_opened_it(
    memory: Memory,
) -> None:
    await memory.record(
        _reply("t1", "u1", "Who is on reserve at BLR on 2026-09-15?", "12 reserves on call")
    )
    rows = await memory.threads()
    assert rows[0].title == "BLR reserve cover"


async def test_a_later_turn_does_not_rename_the_thread(memory: Memory) -> None:
    await memory.record(_reply("t1", "u1", "Which flights depart DEL?", "First answer"))
    await memory.record(_reply("t1", "u2", "Who is on reserve at BLR?", "Second answer"))
    rows = await memory.threads()
    assert rows[0].title == "DEL flights"


async def test_a_question_with_no_crew_ops_subject_keeps_its_own_words(
    memory: Memory,
) -> None:
    """Out of scope, so there is no topic to name it after. It names itself."""
    await memory.record(_reply("t1", "u1", "what is the weather at BLR", None))
    rows = await memory.threads()
    assert rows[0].title == "What is the weather"


async def test_a_person_can_rename_a_thread(memory: Memory) -> None:
    await memory.record(_reply("t1", "u1", "Which flights depart DEL?", "First"))
    await memory.rename("t1", "  Monday disruption  ")
    rows = await memory.threads()
    assert rows[0].title == "Monday disruption"


async def test_a_name_a_person_typed_survives_the_next_turn(memory: Memory) -> None:
    await memory.record(_reply("t1", "u1", "Which flights depart DEL?", "First"))
    await memory.rename("t1", "Monday disruption")
    await memory.record(_reply("t1", "u2", "Who is on reserve at BLR?", "Second"))
    rows = await memory.threads()
    assert rows[0].title == "Monday disruption"


async def test_renaming_to_nothing_is_refused(memory: Memory) -> None:
    await memory.record(_reply("t1", "u1", "Which flights depart DEL?", "First"))
    assert await memory.rename("t1", "   ") is False
    rows = await memory.threads()
    assert rows[0].title == "DEL flights"


async def test_renaming_a_thread_that_does_not_exist_is_refused(memory: Memory) -> None:
    assert await memory.rename("nope", "Anything") is False


async def test_deleting_a_thread_takes_its_turns_and_its_name(memory: Memory) -> None:
    await memory.record(_reply("t1", "u1", "Which flights depart DEL?", "First"))
    await memory.record(_reply("t2", "u2", "Who is on reserve at BLR?", "Other"))

    assert await memory.delete("t1") is True
    rows = await memory.threads()
    assert [row.thread_id for row in rows] == ["t2"]
    assert await memory.turns("t1") == []

    # And the name goes with it, so a recycled id cannot inherit it.
    await memory.record(_reply("t1", "u3", "What is C-2087's rank?", "Reused"))
    rows = await memory.threads()
    titles = {row.thread_id: row.title for row in rows}
    assert titles["t1"] == "C-2087 rank"


async def test_deleting_a_thread_that_does_not_exist_is_refused(memory: Memory) -> None:
    assert await memory.delete("nope") is False


async def test_deleting_everything_empties_the_log(memory: Memory) -> None:
    """The bulk delete, which is the one action with no partial outcome."""
    await memory.record(_reply("t1", "u1", "Which flights depart DEL?", "First"))
    await memory.record(_reply("t2", "u2", "Who is on reserve at BLR?", "Other"))
    await memory.rename("t1", "Monday disruption")

    assert await memory.delete_all() == 2
    assert await memory.threads() == []
    assert await memory.turns("t1") == []

    # And the names go too, so a recycled id cannot inherit one.
    await memory.record(_reply("t1", "u3", "What is C-2087's rank?", "Reused"))
    rows = await memory.threads()
    assert rows[0].title == "C-2087 rank"


async def test_deleting_everything_when_there_is_nothing(memory: Memory) -> None:
    assert await memory.delete_all() == 0

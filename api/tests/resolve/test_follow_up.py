"""A conversation is a conversation. The second question knows the first.

Thread memory was built and wired: LangGraph's checkpointer holds the message
state, a `turns` table holds every settled `Reply`, and `/api/threads` lists
them. Asking three questions on one thread proved that only two thirds of it
worked.

    turn 1  "Who is on reserve at BLR on 2026-09-15?"   answered
    turn 2  "And what about the next day?"              REFUSED, out of scope
    turn 3  "Which of them are captains?"               answered, in context

Turn 3 is the proof that memory works: the model resolved "them" to the BLR
reserves on 15 Sep and filtered them. Turn 2 never reached the model. Scope
triage judged it on its own words, found no crew, pairing, flight, station or
rule in it, and declined before the graph got anywhere near the history that
would have made sense of it.

So the gate in front of the memory was the defect, not the memory. A question
that names nothing is out of scope as an OPENING line. As a follow-up it is
the most ordinary thing a person says.

Offline there is no model to resolve the reference, so the resolver carries
the previous turn's entities forward and applies what the follow-up changes:
"the next day" moves the date, "which of them are captains" adds a rank. The
previous intent runs again with the merged entities. Nothing is guessed that
the earlier turn did not already establish, and a follow-up with no thread
behind it is still refused.
"""

from __future__ import annotations

import datetime as dt

import pytest

from crewops.resolve.triage import reads_as_followup

SNAPSHOT = dt.datetime(2026, 9, 14, 18, 0, 0)


def _ask(resolver, question: str, *, thread: str = "t-follow", turn: str = "u-1"):
    return resolver.answer(question, thread_id=thread, turn_id=turn, asked_at=SNAPSHOT)


def _text(reply) -> str:
    return f"{reply.headline or ''} {reply.text}"


# ------------------------------------------------------- recognising the shape

FOLLOW_UPS = [
    "And what about the next day?",
    "what about the day after?",
    "How about DEL?",
    "Which of them are captains?",
    "and them?",
    "same for 2026-09-16",
    "what about the first officers",
    "the day before?",
]

OPENERS = [
    "Who is on reserve at BLR on 2026-09-15?",
    "What is the capital of France?",
    "Captain C-1042 calls in sick on 15 Sep.",
    "hello",
]


@pytest.mark.parametrize("question", FOLLOW_UPS)
def test_a_follow_up_is_recognised(question: str) -> None:
    assert reads_as_followup(question), question


@pytest.mark.parametrize("question", OPENERS)
def test_a_standalone_question_is_not_a_follow_up(question: str) -> None:
    assert not reads_as_followup(question), question


# ------------------------------------------------------- carrying a turn over


def test_the_next_day_moves_the_date(resolver) -> None:
    _ask(resolver, "Who is on reserve at BLR on 2026-09-15?", turn="u-1")
    reply = _ask(resolver, "And what about the next day?", turn="u-2")
    assert reply.kind.value == "answer", reply.text
    assert "2026-09-16" in _text(reply), _text(reply)


def test_the_day_before_moves_it_back(resolver) -> None:
    _ask(resolver, "Who is on reserve at BLR on 2026-09-16?", thread="t-back", turn="u-1")
    reply = _ask(resolver, "and the day before?", thread="t-back", turn="u-2")
    assert reply.kind.value == "answer", reply.text
    assert "2026-09-15" in _text(reply), _text(reply)


def test_a_narrowing_follow_up_keeps_the_subject(resolver) -> None:
    _ask(resolver, "Who is on reserve at BLR on 2026-09-15?", thread="t-narrow", turn="u-1")
    reply = _ask(resolver, "Which of them are captains?", thread="t-narrow", turn="u-2")
    assert reply.kind.value == "answer", reply.text
    assert "Captain" in _text(reply), _text(reply)


def test_a_station_follow_up_swaps_the_station(resolver) -> None:
    _ask(resolver, "Which flights depart BLR on 2026-09-15?", thread="t-stn", turn="u-1")
    reply = _ask(resolver, "How about DEL?", thread="t-stn", turn="u-2")
    assert reply.kind.value == "answer", reply.text
    assert "DEL" in _text(reply), _text(reply)


# ----------------------------------------------------------- what must not go


def test_a_follow_up_with_nothing_behind_it_is_still_refused(resolver) -> None:
    reply = _ask(resolver, "And what about the next day?", thread="t-empty", turn="u-1")
    assert reply.kind.value == "abstain", _text(reply)


def test_trivia_mid_thread_is_still_refused(resolver) -> None:
    _ask(resolver, "Who is on reserve at BLR on 2026-09-15?", thread="t-triv", turn="u-1")
    reply = _ask(resolver, "What is the capital of France?", thread="t-triv", turn="u-2")
    assert reply.kind.value == "abstain", _text(reply)


def test_a_fresh_question_mid_thread_does_not_inherit(resolver) -> None:
    """The expensive failure mode for carry-forward: a complete question that
    happens to follow another one must be answered on its own terms, or every
    later turn is contaminated by the first."""
    _ask(resolver, "Who is on reserve at BLR on 2026-09-15?", thread="t-fresh", turn="u-1")
    reply = _ask(resolver, "Which flights depart DEL on 2026-09-17?", thread="t-fresh", turn="u-2")
    assert reply.kind.value == "answer", reply.text
    surface = _text(reply)
    assert "DEL" in surface
    assert "reserve" not in surface.lower(), surface


def test_threads_do_not_leak_into_each_other(resolver) -> None:
    _ask(resolver, "Who is on reserve at BLR on 2026-09-15?", thread="t-a", turn="u-1")
    reply = _ask(resolver, "And what about the next day?", thread="t-b", turn="u-1")
    assert reply.kind.value == "abstain", _text(reply)

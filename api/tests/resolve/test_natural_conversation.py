"""How an ordinary person types, answered in words they can act on.

Three failures a teammate hit in a minute of normal use.

    "What are flights from Delhi to Chennai?"  ->  refused, no shape matched
    "flights from delhi to chennai"            ->  refused
    "Hey, what can you do?"                    ->  refused as out of scope

The first two are a matching gap: the `flights` shape wanted "which flights"
or "flights depart", and "flights from X to Y" is how people actually ask.

The third is worse than a gap. Being asked what it can do and answering "the
question names nothing in the crew operations dataset" is the least helpful
sentence available, and it is the first thing anyone types.

AND THE ANSWER ITSELF HAS TO BE READABLE. There is no nonstop Delhi to Chennai
in this schedule: the network is a BLR hub, DEL only ever departs to BLR. The
literal answer, "0 flight(s) match, 0 seats in total", is true and tells a
person nothing about why or what to do instead. An empty result is a finding,
and it should read like one.
"""

from __future__ import annotations

import datetime as dt

import pytest

SNAPSHOT = dt.datetime(2026, 9, 14, 18, 0, 0)


def _ask(resolver, question: str):
    return resolver.answer(question, thread_id="t-nc", turn_id="u-1", asked_at=SNAPSHOT)


def _text(reply) -> str:
    return f"{reply.headline or ''} {reply.text}"


# --------------------------------------------------------------- route queries

ROUTES = [
    ("plain", "What are flights from Delhi to Chennai?"),
    ("lowercase", "flights from delhi to chennai"),
    ("codes", "flights from DEL to MAA"),
    ("between", "Are there any flights between Delhi and Chennai?"),
]


@pytest.mark.parametrize(("case_id", "question"), ROUTES, ids=[c[0] for c in ROUTES])
def test_a_route_question_is_answered(resolver, case_id: str, question: str) -> None:
    reply = _ask(resolver, question)
    assert reply.kind.value == "answer", f"{case_id}: {reply.text}"


@pytest.mark.parametrize(("case_id", "question"), ROUTES, ids=[c[0] for c in ROUTES])
def test_an_empty_route_says_so_in_words(resolver, case_id: str, question: str) -> None:
    """Verified against flights.json: DEL only ever departs to BLR, so there is
    no nonstop DEL to MAA. Saying "0 flight(s) match" is true and useless."""
    text = _text(_ask(resolver, question)).lower()
    assert "no " in text or "none" in text, text
    assert "del" in text and "maa" in text, "the answer has to name both ends"


def test_a_route_that_exists_still_lists_it(resolver) -> None:
    """The check must not turn every route question into a refusal."""
    reply = _ask(resolver, "What are flights from Bangalore to Goa?")
    assert reply.kind.value == "answer", reply.text
    assert "DX433" in _text(reply)


# ------------------------------------------------------------- what can you do

CAPABILITY = [
    ("hey-what", "Hey, what can you do?"),
    ("what-ask", "What can I ask you?"),
    ("help", "help"),
    ("who-are-you", "What are you?"),
    ("capabilities", "what are your capabilities"),
]


@pytest.mark.parametrize(("case_id", "question"), CAPABILITY, ids=[c[0] for c in CAPABILITY])
def test_being_asked_what_it_does_is_answered_not_refused(
    resolver,
    case_id: str,
    question: str,
) -> None:
    reply = _ask(resolver, question)
    text = _text(reply).lower()
    assert "cannot answer that reliably" not in text, f"{case_id}: refused"
    assert "crew" in text, f"{case_id}: did not say what it is for"
    assert "reserve" in text or "legal" in text or "cover" in text, (
        f"{case_id}: gave no example of a question worth asking"
    )


def test_a_bare_greeting_still_works(resolver) -> None:
    reply = _ask(resolver, "hi")
    assert "cannot answer that reliably" not in _text(reply).lower()


def test_a_greeting_in_front_of_a_question_is_still_a_question(resolver) -> None:
    """A controller under pressure types "hey, who is on reserve at BLR". The
    greeting must not swallow the question."""
    reply = _ask(resolver, "hey, who is on reserve at BLR on 2026-09-15?")
    assert reply.kind.value == "answer", reply.text
    assert "reserve" in _text(reply).lower()


def test_genuine_trivia_is_still_refused(resolver) -> None:
    """Widening "what can you do" must not widen into answering anything."""
    reply = _ask(resolver, "What is the capital of France?")
    assert reply.kind.value == "abstain"

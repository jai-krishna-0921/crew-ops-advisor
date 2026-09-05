"""A list answer has to say who, not just how many.

    "How many captains are based at DEL, and who are they?"
    -> "1 crew match the filter."

Every fact needed was on screen, in the table underneath. The sentence a person
reads first answered half the question and the half it answered was the easy
one. The same shape appeared everywhere a tool returns rows: reserves narrowed
by rank rendered "3 reserve(s) on call for 2026-09-15" and never said captains.

Two rules, and the second is what keeps this honest.

NAME THEM WHEN THERE ARE FEW ENOUGH TO READ. Under a handful of rows, the count
is the least useful sentence available. Fifty-four rows is a different case: a
count plus what they have in common is the answer, and reading out fifty-four
ids is not.

DESCRIBE THE ROWS, NEVER THE FILTER. "Captains based at DEL" is said only when
every returned row IS a captain based at DEL. Echoing the requested filter
would state a constraint as though it were a finding, which is how an empty
result becomes a confident wrong answer. Describing what came back cannot do
that, and every word of it is attested by the payload the verifier checks.
"""

from __future__ import annotations

import datetime as dt

SNAPSHOT = dt.datetime(2026, 9, 14, 18, 0, 0)


def _ask(resolver, question: str, *, thread: str = "t-read", turn: str = "u-1"):
    return resolver.answer(question, thread_id=thread, turn_id=turn, asked_at=SNAPSHOT)


def _text(reply) -> str:
    return f"{reply.headline or ''} {reply.text}"


def test_a_short_crew_list_names_the_crew(resolver) -> None:
    reply = _ask(resolver, "How many captains are based at DEL, and who are they?")
    assert reply.kind.value == "answer", reply.text
    surface = _text(reply)
    assert "C-" in surface, f"named nobody: {surface!r}"
    assert surface.strip() != "1 crew match the filter."


def test_a_short_crew_list_says_what_they_are(resolver) -> None:
    reply = _ask(resolver, "How many captains are based at DEL, and who are they?")
    surface = _text(reply)
    assert "Captain" in surface, surface
    assert "DEL" in surface, surface


def test_a_long_crew_list_stays_a_count(resolver) -> None:
    """Fifty-four ids is not an answer, it is the table read aloud."""
    reply = _ask(resolver, "How many crew are based at BLR?")
    assert reply.kind.value == "answer", reply.text
    surface = _text(reply)
    assert surface.count("C-") <= 8, f"read out the whole roster: {surface!r}"


def test_a_narrowed_reserve_list_says_what_it_narrowed_to(resolver) -> None:
    _ask(resolver, "Who is on reserve at BLR on 2026-09-15?", thread="t-rd", turn="u-1")
    reply = _ask(resolver, "Which of them are captains?", thread="t-rd", turn="u-2")
    assert reply.kind.value == "answer", reply.text
    surface = _text(reply)
    assert "Captain" in surface, surface
    assert "C-" in surface, surface


def test_an_empty_list_does_not_describe_rows_it_does_not_have(resolver) -> None:
    """The failure this guards: echoing the filter back as though it were a
    finding. With no rows there is nothing true to say about them."""
    reply = _ask(resolver, "Which crew are based at GOI?")
    surface = _text(reply)
    if "0 crew" in surface or "No crew" in surface:
        assert "based at GOI" not in surface.replace("Which crew are based at GOI?", "")


def test_the_list_answer_is_still_grounded(resolver) -> None:
    """Naming people adds atoms. Every one has to be attested."""
    for question in (
        "How many captains are based at DEL, and who are they?",
        "How many crew are based at BLR?",
        "Who is on reserve at BLR on 2026-09-15?",
    ):
        reply = _ask(resolver, question)
        assert reply.verification.status.value != "rejected", (
            f"{question}: {[u.atom for u in reply.verification.unattested]}"
        )

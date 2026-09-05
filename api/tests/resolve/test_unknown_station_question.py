"""Two turns of a real session, and both of them answered a different question.

    01  "Who is on reserve at IDR on 2026-09-17, and what are their on-call
         windows?"
        -> "16 crew members on call for 2026-09-17."

    02  "SOrry i mean INR"
        -> "I cannot answer that reliably. The question names nothing in the
            crew operations dataset."

TURN ONE dropped the filter. IDR is not a station, so the entity extractor did
not see it, so the plan carried no base, so the reserve list came back
unfiltered and was reported as the answer. Every figure in it was real. It was
the answer to "who is on reserve", not to "who is on reserve at IDR", and the
question a controller asked had a station in it.

TURN TWO is the same defect wearing a different coat. "Sorry I mean INR" is a
correction: it names one thing and the rest of the question is the turn before
it. Triage read it in isolation, found no crew, pairing, flight, station or
rule, and declined. The thread had all of it.

Both fixes are the same sentence said twice: **a station-shaped token that is
not a station is a finding, not a blank.** Say so, name the eight that exist,
and stop. That is what the reporter asked for, in their words: if there is no
data present, say no data present, do not answer something else.

`INR` is the currency in every cost line in this dataset, so the check is
anchored on a station POSITION ("at INR", "from INR") or on a correction
marker. "INR 18,500" is money and stays money.
"""

from __future__ import annotations

import datetime as dt

import pytest

from crewops.resolve.triage import unknown_stations

SNAPSHOT = dt.datetime(2026, 9, 14, 18, 0, 0)


def _ask(resolver, question: str, *, thread: str = "t-unk", turn: str = "u-1"):
    return resolver.answer(question, thread_id=thread, turn_id=turn, asked_at=SNAPSHOT)


def _text(reply) -> str:
    refusal = reply.abstention.message if reply.abstention else ""
    return f"{reply.headline or ''} {reply.text} {refusal}"


# ------------------------------------------------------- spotting the token

NOT_STATIONS = [
    ("at", "Who is on reserve at IDR on 2026-09-17?", "IDR"),
    ("from", "Which flights depart from LHR on 2026-09-15?", "LHR"),
    ("to", "Are there flights to JFK?", "JFK"),
    ("based", "Which crew are based at AMD?", "AMD"),
    ("closed", "IDR is closed 08:00 to 14:00Z on 17 Sep.", "IDR"),
]


@pytest.mark.parametrize(
    ("case_id", "question", "token"), NOT_STATIONS, ids=[c[0] for c in NOT_STATIONS]
)
def test_a_station_shaped_token_that_is_not_a_station_is_seen(
    case_id: str, question: str, token: str
) -> None:
    assert token in unknown_stations(question), case_id


REAL = [
    "Who is on reserve at BLR on 2026-09-17?",
    "Which flights depart from DEL?",
    "BLR is closed 08:00 to 14:00Z on 17 Sep.",
]


@pytest.mark.parametrize("question", REAL)
def test_a_real_station_is_not_flagged(question: str) -> None:
    assert unknown_stations(question) == ()


NOT_A_STATION_AT_ALL = [
    "The cover costs INR 18,500.",
    "Does C-1042 breach RULE-FDP-01?",
    "What is the FDP limit?",
    "All times are UTC.",
    "Draft the SMS to C-3310.",
]


@pytest.mark.parametrize("question", NOT_A_STATION_AT_ALL)
def test_a_three_letter_word_that_is_not_a_station_reference_is_left_alone(
    question: str,
) -> None:
    """INR is the currency on every cost line in this dataset."""
    assert unknown_stations(question) == (), question


# --------------------------------------------------------- what a user reads


def test_the_reserve_question_says_the_station_does_not_exist(resolver) -> None:
    reply = _ask(resolver, "Who is on reserve at IDR on 2026-09-17?")
    assert reply.kind.value == "abstain", _text(reply)
    surface = _text(reply)
    assert "IDR" in surface
    assert "BLR" in surface, "name the stations that do exist"


def test_it_does_not_answer_the_unfiltered_question_instead(resolver) -> None:
    """The whole of turn one: 16 reserves is a true figure about a question
    nobody asked."""
    reply = _ask(resolver, "Who is on reserve at IDR on 2026-09-17?")
    assert "16 crew" not in _text(reply)


def test_a_real_station_still_answers(resolver) -> None:
    reply = _ask(resolver, "Who is on reserve at BLR on 2026-09-15?")
    assert reply.kind.value == "answer", reply.text


# ------------------------------------------------------------- the correction

CORRECTIONS = [
    "SOrry i mean INR",
    "sorry, I meant INR",
    "no, INR",
    "make that INR",
    "I mean INR",
]


@pytest.mark.parametrize("question", CORRECTIONS)
def test_a_correction_reports_the_station_rather_than_the_scope(
    resolver, question: str
) -> None:
    """"Names nothing in the crew operations dataset" is true of the words and
    useless to the person who typed them."""
    _ask(resolver, "Who is on reserve at BLR on 2026-09-17?", thread="t-fix", turn="u-1")
    reply = _ask(resolver, question, thread="t-fix", turn="u-2")
    surface = _text(reply)
    assert "INR" in surface, surface
    assert "out of scope" not in surface.lower()


def test_a_correction_to_a_real_station_re_runs_the_question(resolver) -> None:
    """The other half of the same behaviour, and the more useful one."""
    _ask(resolver, "Who is on reserve at BLR on 2026-09-15?", thread="t-fix2", turn="u-1")
    reply = _ask(resolver, "sorry, I meant DEL", thread="t-fix2", turn="u-2")
    assert reply.kind.value == "answer", _text(reply)
    assert "DEL" in _text(reply)


def test_a_second_correction_still_reaches_the_question(resolver) -> None:
    """The reported session, all three turns.

        "Who is on reserve at IDR on 2026-09-17?"   IDR is not a station
        "SOrry i mean INR"                          nor is INR
        "sorry, I meant BLR"                        <- and now?

    Only ANSWERED turns were remembered, on the principle that a refusal
    establishes nothing. That is right for a refusal that understood nothing.
    This one understood everything except a single token: the shape, the date
    and the intent were all read correctly and one station was wrong. Throwing
    that away means a controller who mistypes twice has to retype the question,
    which is the opposite of what the correction was for.
    """
    _ask(resolver, "Who is on reserve at IDR on 2026-09-17?", thread="t-twice", turn="u-1")
    _ask(resolver, "SOrry i mean INR", thread="t-twice", turn="u-2")
    reply = _ask(resolver, "sorry, I meant BLR", thread="t-twice", turn="u-3")

    assert reply.kind.value == "answer", _text(reply)
    surface = _text(reply)
    assert "BLR" in surface
    assert "2026-09-17" in surface, "the date came from the first turn"


def test_a_refusal_that_understood_nothing_still_establishes_nothing(resolver) -> None:
    """The rule this narrows, not replaces."""
    _ask(resolver, "What is the capital of France?", thread="t-none", turn="u-1")
    reply = _ask(resolver, "sorry, I meant BLR", thread="t-none", turn="u-2")
    assert reply.kind.value == "abstain", _text(reply)

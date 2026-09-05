"""A desk does not write sentences, and an ops feed does not write English.

The offline shapes were written from `questions.json`, which is prose, so they
read prose and nothing else. Two forms that a real desk produces every day miss
them by punctuation:

TERSE SHORTHAND. A controller types what fits on one line.

    "C-1042 sick, 15 Sep"          `\\bsick (?:at|on)\\b` wants a preposition
    "BLR closed 08:00-14:00Z"      `\\bcloses?\\b` does not match "closed",
                                   and `\\bis closed\\b` wants the verb

A STRUCTURED EVENT. Pasting the disruption straight out of an ops system is the
fastest way to ask, and the identifiers in it are cleaner than any sentence:

    {"type": "SICK_CREW", "crew_id": "C-1042", "pairing_id": "P-2291"}

The entity extractor already reads both perfectly: crew id, pairing id, station,
dates and times all come out. Only the shape matching failed, so a question the
engine could answer exactly was declined for its punctuation.

Widening these patterns is safe now in a way it was not before, because
`match_intent` prefers the highest-priority shape that can actually run. A
broad pattern that cannot fill its arguments yields instead of winning and
then failing.
"""

from __future__ import annotations

import datetime as dt

import pytest

from crewops.resolve.intents import match_intent
from crewops.resolve.triage import canonical_question, extract_entities

SNAPSHOT = dt.datetime(2026, 9, 14, 18, 0, 0)


def _ask(resolver, question: str):
    return resolver.answer(question, thread_id="t-terse", turn_id="u-1", asked_at=SNAPSHOT)


def _intent_for(question: str):
    canonical = canonical_question(question)
    return match_intent(canonical, extract_entities(canonical))


TERSE = [
    ("sick-comma", "C-1042 sick, 15 Sep", "sick_impact"),
    ("sick-bare", "Captain C-1042 sick for P-2291", "sick_impact"),
    ("closed-past", "BLR closed 08:00-14:00Z on 17 Sep", "station_closure"),
    ("closure-noun", "Station closure at BLR, 08:00 to 14:00Z on 17 Sep", "station_closure"),
]


@pytest.mark.parametrize(("case_id", "question", "expected"), TERSE, ids=[c[0] for c in TERSE])
def test_desk_shorthand_reaches_the_right_shape(case_id: str, question: str, expected: str) -> None:
    intent = _intent_for(question)
    assert intent is not None, f"{case_id}: matched nothing"
    assert intent.name == expected, f"{case_id}: went to {intent.name}"


@pytest.mark.parametrize(("case_id", "question", "expected"), TERSE, ids=[c[0] for c in TERSE])
def test_desk_shorthand_is_answered(resolver, case_id: str, question: str, expected: str) -> None:
    reply = _ask(resolver, question)
    assert reply.kind.value == "answer", f"{case_id}: {reply.text}"


STRUCTURED = [
    (
        "sick-event",
        'Captain sick, 15 Sep: {"type": "SICK_CREW", "crew_id": "C-1042", '
        '"pairing_id": "P-2291", "reported_utc": "2026-09-15T05:00:00Z"}',
        "C-1042",
    ),
    (
        "closure-event",
        'BLR closed 08:00-14:00Z, 17 Sep: {"type": "STATION_CLOSURE", "station": "BLR", '
        '"window_utc": {"start": "2026-09-17T08:00:00Z", "end": "2026-09-17T14:00:00Z"}}',
        "BLR",
    ),
]


@pytest.mark.parametrize(
    ("case_id", "question", "expected"), STRUCTURED, ids=[c[0] for c in STRUCTURED]
)
def test_a_pasted_ops_event_is_answered(
    resolver, case_id: str, question: str, expected: str
) -> None:
    """The identifiers in a machine event are cleaner than in any sentence.
    Declining one because it has braces in it is a parsing prejudice."""
    reply = _ask(resolver, question)
    assert reply.kind.value == "answer", f"{case_id}: {reply.text}"
    assert expected in f"{reply.headline or ''} {reply.text}", case_id


def test_a_sick_event_still_names_what_it_uncovers(resolver) -> None:
    reply = _ask(
        resolver,
        '{"type": "SICK_CREW", "crew_id": "C-1042", "pairing_id": "P-2291", '
        '"reported_utc": "2026-09-15T05:00:00Z"}',
    )
    assert reply.kind.value == "answer", reply.text
    assert "P-2291" in f"{reply.headline or ''} {reply.text}"


def test_a_broad_word_does_not_hijack_a_question_it_cannot_answer(resolver) -> None:
    """"sick" now matches on its own, so it must still yield when there is no
    crew id to act on rather than declining a question another shape answers."""
    reply = _ask(resolver, "How many reserves are on call at BLR on 2026-09-15?")
    assert reply.kind.value == "answer", reply.text


# ---------------------------------------------------------- ISO 8601 in a feed


def test_an_iso_timestamp_yields_its_date() -> None:
    """`\\b(\\d{4})-(\\d{2})-(\\d{2})\\b` cannot end on a "T": the boundary needs a
    non-word character and "T" is a word character, so every date inside an
    ISO instant was invisible and the plan silently used the snapshot date."""
    entities = extract_entities('{"reported_utc": "2026-09-15T05:00:00Z"}')
    assert dt.date(2026, 9, 15) in entities.dates


def test_an_iso_timestamp_yields_the_hour_not_the_seconds() -> None:
    """Worse than missing: WRONG. In "05:00:00Z" the hour is preceded by "T",
    so the boundary fails there and matches at the seconds pair instead. The
    extractor reported 00:00 for an event at 05:00 and nothing flagged it."""
    entities = extract_entities('{"reported_utc": "2026-09-15T05:00:00Z"}')
    assert entities.times == ("05:00",), entities.times


def test_a_plain_window_still_reads_both_ends() -> None:
    entities = extract_entities("BLR is closed 08:00 to 14:00Z on 2026-09-17")
    assert entities.times == ("08:00", "14:00"), entities.times


def test_an_iso_window_reads_both_ends() -> None:
    entities = extract_entities(
        '{"window_utc": {"start": "2026-09-17T08:00:00Z", "end": "2026-09-17T14:00:00Z"}}'
    )
    assert entities.times == ("08:00", "14:00"), entities.times
    assert entities.dates == (dt.date(2026, 9, 17),)


# ------------------------------------------------------- counting the reserves

RESERVE_PHRASINGS = [
    ("how-many", "How many reserves are on call at BLR on 2026-09-15?"),
    ("which", "Which reserves are available on 2026-09-15?"),
    ("bare", "reserves at BLR on 2026-09-15"),
    ("standby", "Who is on standby at BLR on 2026-09-15?"),
]


@pytest.mark.parametrize(
    ("case_id", "question"), RESERVE_PHRASINGS, ids=[c[0] for c in RESERVE_PHRASINGS]
)
def test_a_reserve_question_is_answered_however_it_is_asked(
    resolver, case_id: str, question: str
) -> None:
    reply = _ask(resolver, question)
    assert reply.kind.value == "answer", f"{case_id}: {reply.text}"

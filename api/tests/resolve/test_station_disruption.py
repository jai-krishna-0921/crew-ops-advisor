"""A controller states a situation. The system should ask, not shrug.

"Bangalore weather is not suitable" is what a Crew Control desk actually says.
Both answer paths refused it at triage in 4ms:

    I cannot answer that reliably. The question is about weather, which this
    dataset does not model.

True, and useless. There is no weather in the pack, but the operational event
the sentence describes is a station being unusable for a window, and that is
`simulate_station_closure`, which already answers Q19, Q29 and S3 exactly. The
bridge from what a controller says to what the system models is one step long
and nobody was building it.

So the vocabulary a desk uses (weather, fog, go-slow, runway, ATC flow, strike,
congestion) resolves to a closure. If the window and the date are there, run it.
If they are not, say what is missing and give a line that works.

TWO THINGS THIS DELIBERATELY DOES NOT DO.

It never offers to cancel. Cancellation is INR 250,000 a leg and the ops engine
ranks it last in every search on purpose. A system whose opening move is "shall
I cancel?" is proposing the most expensive option on the board, and it would
contradict the argument the cover search exists to make.

It never claims to have weather. The reply says plainly that weather is not
modelled and that a closure window is what it can act on. Offering to model
something adjacent is honest; implying the data exists is not.

Also fixed here: `_closure_bounds` defaulted a missing window to 00:00-23:59 on
the snapshot date, so a bare "BLR is closed" quietly modelled a whole-day
closure on the wrong date and reported it as fact. Same defect as the three in
`test_unmodelled_constraints.py`: a parameter the question never gave, invented
and then answered over.
"""

from __future__ import annotations

import datetime as dt

import pytest

SNAPSHOT = dt.datetime(2026, 9, 14, 18, 0, 0)


def _ask(resolver, question: str):
    return resolver.answer(
        question, thread_id="t-disruption", turn_id="u-1", asked_at=SNAPSHOT
    )


# ------------------------------------------------- fully specified, so it runs

RUNS = [
    ("weather-phrasing", "BLR weather is not suitable, closed 08:00 to 14:00Z on 17 Sep"),
    ("fog-phrasing", "Fog at BLR from 08:00 to 14:00Z on 17 Sep"),
    ("goslow-phrasing", "Go-slow at BLR 08:00 to 14:00Z on 17 Sep"),
]

#: Verified in docs/DATA-MODEL.md and asserted byte for byte in test_disruption.
#: The BLR closure on 17 Sep touches thirteen legs.
EXPECTED_LEGS = ("DX402", "DX422")


@pytest.mark.parametrize(("case_id", "question"), RUNS, ids=[c[0] for c in RUNS])
def test_a_specified_disruption_is_modelled(
    resolver,
    case_id: str,
    question: str,
) -> None:
    reply = _ask(resolver, question)
    assert reply.kind.value == "answer", f"{case_id}: {reply.text}"
    surface = f"{reply.headline or ''} {reply.text}"
    assert "BLR" in surface
    for leg in EXPECTED_LEGS:
        assert leg in surface, f"{case_id}: {leg} is affected and was not named"


# --------------------------------------------- underspecified, so it asks well

ASKS = [
    ("bare-weather", "Bangalore weather is not suitable"),
    ("fogged-in", "BLR is fogged in this morning"),
    ("go-slow", "We have a go-slow at BLR today"),
    ("runway", "Runway closed at HYD"),
    ("bare-closure", "BLR is closed"),
]


@pytest.mark.parametrize(("case_id", "question"), ASKS, ids=[c[0] for c in ASKS])
def test_an_unspecified_disruption_asks_for_the_window(
    resolver,
    case_id: str,
    question: str,
) -> None:
    reply = _ask(resolver, question)
    assert reply.kind.value == "abstain", (
        f"{case_id}: answered without being told the window.\n  {reply.text}"
    )
    blob = f"{reply.text} {' '.join(reply.abstention.missing)} " + " ".join(
        reply.abstention.suggestions
    )
    assert "window" in blob.lower(), f"{case_id}: did not ask for the window"
    assert "08:00" in blob, f"{case_id}: gave no worked example to copy"


def test_the_refusal_does_not_pretend_to_have_weather(resolver) -> None:
    reply = _ask(resolver, "Bangalore weather is not suitable")
    assert "weather" in reply.text.lower()
    assert "not model" in reply.text.lower() or "do not have" in reply.text.lower()


def test_it_never_opens_by_offering_to_cancel(resolver) -> None:
    """Cancellation is the most expensive option in the book and the engine
    ranks it last. It must never be the first thing suggested."""
    for _, question in ASKS + RUNS:
        reply = _ask(resolver, question)
        blob = f"{reply.headline or ''} {reply.text}".lower()
        assert "shall i cancel" not in blob
        assert "should i cancel" not in blob


# ------------------------------------------------ genuinely out of scope still

REFUSED = [
    ("weather-question", "What is the weather at BLR tomorrow?"),
    ("fuel", "What is the fuel price this week?"),
    ("booking", "How many tickets were sold on DX401?"),
]


@pytest.mark.parametrize(("case_id", "question"), REFUSED, ids=[c[0] for c in REFUSED])
def test_a_real_out_of_scope_question_is_still_refused(
    resolver,
    case_id: str,
    question: str,
) -> None:
    reply = _ask(resolver, question)
    assert reply.kind.value == "abstain", case_id


def test_q16_is_not_hijacked_by_the_word_disruption(resolver) -> None:
    """Q16 asks for "the disruption-risk score for C-1042". That is a crew
    attribute, not a station going down.

    The first version of this vocabulary matched the bare word "disruption"
    and took a shipped Tier 1 question with it: the intent won on priority,
    then abstained because no station was named. Two fixes, both here: the word
    left the self-asserting set, and the intent pattern now requires one of the
    eight station codes to be present at all.
    """
    reply = _ask(
        resolver, "What is the disruption-risk score for C-1042 and what drives it?"
    )
    assert reply.kind.value == "answer", reply.text
    assert "0.78" in f"{reply.headline or ''} {reply.text}"


def test_the_shipped_closure_question_still_answers(resolver) -> None:
    reply = _ask(resolver, "BLR is closed 08:00-14:00Z on 17 Sep. Which flights are affected?")
    assert reply.kind.value == "answer", reply.text
    assert "DX402" in f"{reply.headline or ''} {reply.text}"

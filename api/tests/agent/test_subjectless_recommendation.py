"""A recommendation has to be about something.

Asked cold, with no thread behind it:

    "What are my options, cheapest first?"

the agent answered:

    "Your cheapest cover for C-5417's seat on P-2213 (2026-09-19) is a reserve
     callout of C-4809 at INR 9,500."

Every figure in that is real and the grounding check passes, because it is a
true answer. It is a true answer to a question nobody asked. The model found a
gap in the week and reported on it, and a controller reading that line acts on
a seat they were not asking about.

The offline path refuses this: `cover_options` declares a `cover_target` and
the question names none, so it says which argument is missing. The agent had no
equivalent gate, and rule 4 in CLAUDE.md is explicit that an unresolvable
question returns a refusal saying what was missing.

Deliberately narrow. It fires only when the shape needs a SUBJECT (a cover
target, or the duty a callout is for), the question names no identifier at all,
and the thread has nothing behind it. With any of those three untrue the
question goes to the model, because a wrong refusal here is unrecoverable and a
wrong forward is caught downstream.
"""

from __future__ import annotations

import pytest

from crewops.agent.graph import subjectless_ask

SUBJECTLESS = [
    "What are my options, cheapest first?",
    "Who should I call?",
    "Give me the ranked resolution options.",
    "Draft the callout.",
]

HAS_A_SUBJECT = [
    "What are my options for P-2291, cheapest first?",
    "Who should I call for C-1042's duty on 15 Sep?",
    "Draft the callout to C-3310 for P-2291.",
]

NOT_A_RECOMMENDATION = [
    "Who is on reserve at BLR on 2026-09-15?",
    "How many crew are rated for ATR72?",
    "Which flights depart DEL on 2026-09-15?",
    "What can you do?",
    "A crew is released at 15:30Z on 16 Sep. What is the earliest they may report next?",
]


@pytest.mark.parametrize("question", SUBJECTLESS)
def test_a_subjectless_recommendation_is_caught(question: str) -> None:
    assert subjectless_ask(question, has_history=False) is not None, question


@pytest.mark.parametrize("question", SUBJECTLESS)
def test_a_thread_with_history_is_left_to_the_model(question: str) -> None:
    """Turn six of a conversation about P-2291 is not subjectless. The
    checkpointer has the pairing and the model resolves it."""
    assert subjectless_ask(question, has_history=True) is None, question


@pytest.mark.parametrize("question", HAS_A_SUBJECT)
def test_naming_the_subject_passes(question: str) -> None:
    assert subjectless_ask(question, has_history=False) is None, question


@pytest.mark.parametrize("question", NOT_A_RECOMMENDATION)
def test_an_ordinary_question_is_untouched(question: str) -> None:
    assert subjectless_ask(question, has_history=False) is None, question


def test_the_refusal_says_what_to_add() -> None:
    hint = subjectless_ask("What are my options, cheapest first?", has_history=False)
    assert hint is not None
    assert "pairing" in hint.lower(), hint


# ------------------------------------------------- an unknown station, in both modes

"""Same question, same refusal, whichever engine answers.

With `list_reserves` now refusing an unknown station, the agent relayed the
failure and dropped the reason:

    "The reserve lookup for that station on that date failed, so I could not
     retrieve any reserve crew or on-call windows."

The tool said exactly why: "IDR is not a station in this dataset ... This
network serves BLR, BOM, CCU, COK, DEL, GOI, HYD, MAA." The offline path says
that. The agent said "it failed", which tells a controller nothing they can act
on and reads like an outage rather than a typo.

Asking the model more nicely is the weaker fix. There is nothing clever to do
with a station that does not exist, so the refusal is structural and both
modes give the same answer for the same reason. It also costs a round trip
less, because the turn ends before the model is called at all.
"""


def test_an_unknown_station_is_refused_before_any_spend() -> None:
    from crewops.agent.graph import unknown_station_ask

    hint = unknown_station_ask("Who is on reserve at IDR on 2026-09-17?")
    assert hint is not None
    assert "IDR" in hint
    assert "BLR" in hint, "name the stations that do exist"


def test_a_real_station_is_untouched() -> None:
    from crewops.agent.graph import unknown_station_ask

    assert unknown_station_ask("Who is on reserve at BLR on 2026-09-17?") is None


def test_money_is_not_a_station() -> None:
    from crewops.agent.graph import unknown_station_ask

    assert unknown_station_ask("What does the cover cost in INR 18,500 terms?") is None


def test_a_refused_turn_still_joins_the_conversation() -> None:
    """Refusing before the model is right, and it cannot cost the thread.

    Route-node refusals never reach the model, so nothing about them entered
    the checkpointer, so the thread looked empty to the next turn. The reported
    session then went:

        "at IDR"             refused, IDR is not a station
        "SOrry i mean INR"   refused, nor is INR
        "sorry, I meant BLR" -> "Dataset confirmed. Snapshot is 2026-09-14..."

    The model had no history to correct against and answered about the
    dataset. Offline gets this right because the resolver keeps a recognised
    turn even when it refuses it. A refused turn is still part of the
    conversation, so the question and the refusal go into `messages` and the
    next turn sees both.

    Driven through the compiled graph and read back out of the checkpointer,
    because that is where the defect was: not in what the node returned, but
    in what survived the turn.
    """
    import asyncio
    import datetime as dt

    from langchain_core.messages import HumanMessage
    from langgraph.checkpoint.memory import InMemorySaver

    from crewops.agent.graph import build_graph
    from crewops.agent.state import new_turn_state
    from tests.fakes.model import script
    from tests.fakes.tools import FakeTools

    graph = build_graph(
        tools=FakeTools(), model=script(), checkpointer=InMemorySaver()
    )
    config = {"configurable": {"thread_id": "t-refused"}}
    state = new_turn_state(
        question="Who is on reserve at IDR on 2026-09-17?",
        thread_id="t-refused",
        turn_id="u-1",
        asked_at=dt.datetime(2026, 9, 14, 18, 0, 0),
        as_of=None,
        started_at=0.0,
    )
    asyncio.run(graph.ainvoke(state, config=config))

    kept = graph.get_state(config).values.get("messages") or []
    assert any(isinstance(m, HumanMessage) for m in kept), (
        "the thread has to remember what was asked, or a correction has "
        "nothing to correct"
    )

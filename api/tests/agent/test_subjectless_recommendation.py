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

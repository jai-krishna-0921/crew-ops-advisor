"""A greeting is not an out of scope question.

"Hey" currently lands in the same branch as "what is the capital of France" and
comes back as "I cannot answer that reliably. The question names nothing in the
crew operations dataset." Refusing a greeting reads as broken, and it is the
first thing anyone types into a chat box.

The refusal for actual trivia is deliberate and stays exactly as it is. This is
only about the opening move of a conversation, which is not a question about
the dataset and should not be answered as though it were one.

The case that decides the implementation is the last one in this file: a
greeting in front of a real question is a real question.
"""

from __future__ import annotations

import pytest

from crewops.contracts import AbstentionReason
from crewops.resolve.triage import triage_question

GREETINGS = [
    "Hey",
    "hey",
    "Hi",
    "hi there",
    "Hello",
    "hello!",
    "Hey there",
    "good morning",
    "Good afternoon",
    "yo",
    "hiya",
    "thanks",
    "Thank you",
    "thanks!",
    "ok thanks",
]


@pytest.mark.parametrize("text", GREETINGS)
def test_a_greeting_is_recognised_as_a_greeting(text: str) -> None:
    verdict = triage_question(text)
    assert verdict.in_scope is False
    assert verdict.abstention_reason is AbstentionReason.GREETING, (
        f"{text!r} was classified {verdict.abstention_reason}, so the controller "
        f"gets a refusal card instead of a welcome: {verdict.reason!r}"
    )


def test_the_greeting_reply_says_what_the_system_can_do() -> None:
    """A greeting's answer is a capability statement, not an apology."""
    reason = triage_question("Hey").reason
    assert "cannot" not in reason.lower(), f"reads as a refusal: {reason!r}"
    lowered = reason.lower()
    assert any(word in lowered for word in ("crew", "flight", "duty", "roster")), (
        f"does not tell the controller what to ask about: {reason!r}"
    )


# ------------------------------------------------------- what must not change


def test_a_greeting_in_front_of_a_real_question_is_a_real_question() -> None:
    """The case that decides the implementation.

    A controller types the way they speak. "Hey, who is on reserve at BLR"
    must be answered, not greeted.
    """
    verdict = triage_question("Hey, who is on reserve at BLR on 2026-09-15?")
    assert verdict.in_scope is True, (
        f"a real question was swallowed by the greeting branch: {verdict.reason!r}"
    )


def test_thanks_after_an_answer_with_a_follow_up_is_a_follow_up() -> None:
    verdict = triage_question("thanks, and what about C-3310?")
    assert verdict.in_scope is True


def test_trivia_is_still_refused_as_out_of_scope() -> None:
    """The deliberate refusal. A greeting branch must not soften this."""
    verdict = triage_question("What is the capital of France?")
    assert verdict.in_scope is False
    assert verdict.abstention_reason is AbstentionReason.OUT_OF_SCOPE


def test_an_empty_question_is_still_underspecified_not_a_greeting() -> None:
    assert triage_question("   ").abstention_reason is AbstentionReason.UNDERSPECIFIED


def test_a_word_containing_a_greeting_is_not_a_greeting() -> None:
    """`hi` inside `which` must not match, so matching is on whole tokens."""
    verdict = triage_question("Which flights depart DEL on 2026-09-15?")
    assert verdict.in_scope is True

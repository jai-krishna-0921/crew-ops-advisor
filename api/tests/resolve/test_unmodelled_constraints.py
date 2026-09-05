"""A constraint the plan cannot express is an abstention, not a filter to drop.

The offline resolver matches a question against a fixed set of shapes. When the
shape matches but the question carries a constraint the shape has no argument
for, the constraint was silently discarded and the answer rendered over the
unfiltered set, confidently and with a grounding check that passed, because
every figure in it was genuinely computed. It was simply the answer to a
different question.

Three found by asking Tier 1 questions that are not in the shipped 38:

    "How many crew are not rated for A320?"
        -> find_crew(aircraft_type="A320") -> "123 crew match the filter."
        The word "not" reaches nothing. 123 is the count of crew who ARE rated
        for A320. The answer is 27.

    "How many flights does VT-DXF operate during the week?"
        -> find_flights(limit=200) -> "147 flight(s) match, 20034 seats."
        The tail is not an extractable entity, so no filter was applied at all
        and the whole schedule was reported as the answer. The answer is 14.

    "Which certifications expire before 2026-09-20?"
        -> find_expiring_certifications(within_days=9, as_of=2026-09-20)
        The date was read as the anchor of a forward window. The question asked
        backwards. The answer is C-2087's licence and C-5417's recurrent
        training.

All three are the same defect wearing different clothes, and all three break
rule 4 of the project's own CLAUDE.md: abstain over guess. A narrow resolver is
fine and intended. A narrow resolver that answers anyway is the exact failure
this submission argues against, and it is worse than the agent being absent,
because the figure is real and checkable and about the wrong question.

The fix is a completeness check between matching a shape and running it: if the
question carries a constraint no planned call encodes, decline and say which
constraint was not modelled.
"""

from __future__ import annotations

import datetime as dt

import pytest

SNAPSHOT = dt.datetime(2026, 9, 14, 18, 0, 0)

#: (id, question, the constraint the plan cannot express)
UNMODELLED = [
    ("negated-rating", "How many crew are not rated for A320?", "not"),
    ("negated-base", "Which crew are not based at BLR?", "not"),
    ("excluding", "List the flights on 2026-09-16 excluding DX401.", "excluding"),
    ("unconsumed-tail", "How many flights does VT-DXF operate during the week?", "VT-DXF"),
]


def _ask(resolver, question: str):
    return resolver.answer(
        question, thread_id="t-unmodelled", turn_id="u-1", asked_at=SNAPSHOT
    )


@pytest.mark.parametrize(
    ("case_id", "question", "constraint"),
    UNMODELLED,
    ids=[c[0] for c in UNMODELLED],
)
def test_an_unmodelled_constraint_abstains(
    resolver,
    case_id: str,
    question: str,
    constraint: str,
) -> None:
    reply = _ask(resolver, question)
    assert reply.kind.value == "abstain", (
        f"{case_id}: answered over the unfiltered set instead of declining.\n"
        f"  question  {question}\n"
        f"  headline  {reply.headline}\n"
        f"  the {constraint!r} constraint reached no tool argument"
    )


def test_the_refusal_names_the_constraint_it_could_not_model(resolver) -> None:
    reply = _ask(resolver, "How many crew are not rated for A320?")
    blob = f"{reply.headline or ''} {reply.text} {' '.join(reply.abstention.missing)}"
    assert "not" in blob.lower(), "the refusal has to say what it could not model"


# --------------------------------------------------------------- no regressions
#
# The shapes the resolver is built for must still answer. A completeness check
# that abstains on everything is not a fix, it is the same bug with better
# manners.

#: Verbatim from the shipped questions.json, because the baseline that matters
#: is "do not break what already works". A paraphrase is a different question to
#: a pattern matcher, and that brittleness is a separate finding.
STILL_ANSWERS = [
    ("Which flights depart DEL on 2026-09-15?", "DX402"),
    ("What is C-2210's base and rating?", "DEL"),
    ("Which crew are assigned to pairing P-2291, and in what roles?", "C-1042"),
    ("What is C-3310's reserve on-call window and reachability?", "C-3310"),
]


@pytest.mark.parametrize(("question", "expected"), STILL_ANSWERS)
def test_a_supported_shape_still_answers(
    resolver,
    question: str,
    expected: str,
) -> None:
    reply = _ask(resolver, question)
    assert reply.kind.value == "answer", f"{question}\n  -> {reply.text}"
    assert expected in f"{reply.headline or ''} {reply.text}"

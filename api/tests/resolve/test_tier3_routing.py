"""Tier 3 offline: route to the shape that can actually run.

Two defects, both found by asking Tier 3 questions in a controller's own words
rather than in the wording `questions.json` happens to use.

ONE, AN INTENT THAT CANNOT RUN STILL WINS. `cover_options` matches on
"recovery plan" and carries no requirements, so the shipped Q35, "BLR closes
08:00-14:00Z on 17 Sep. Outline the recovery plan across affected pairings.",
selects it at priority 90 over `station_closure` at 81. Nothing in the question
names a pairing or a flight, so the planned `find_cover_options` call has no
target and the tool refuses it. The user sees "Every lookup this question
needed failed", which reads like a crash rather than a decision, and the
closure simulation that answers the question sat one priority level down the
whole time.

The rule that fixes it is general: prefer the highest-priority intent that can
be EXECUTED. Priority orders shapes that are all runnable; it was never meant
to pick one that cannot fill its own arguments. When nothing is runnable the
top match still wins, so the missing-argument hint is still the best one
available.

TWO, THE COVER SHAPE ONLY READS ITS OWN PHRASING. "Produce ranked resolution
options" matches. None of these do, and every one of them is a controller
asking the same thing:

    "What are my options, cheapest first?"
    "Give me the best three ways to cover C-1042 on P-2291."
    "The captain on P-2293 is unavailable. Who should I call?"
    "How do I cover P-2291 now?"

Same class of gap as the Tier 2 paraphrases, one tier up.
"""

from __future__ import annotations

import datetime as dt
import json

import pytest

from crewops.domain import DATA_DIR
from crewops.resolve.intents import match_intent
from crewops.resolve.triage import canonical_question, extract_entities

SNAPSHOT = dt.datetime(2026, 9, 14, 18, 0, 0)


def _ask(resolver, question: str):
    return resolver.answer(question, thread_id="t-t3", turn_id="u-1", asked_at=SNAPSHOT)


def _text(reply) -> str:
    return f"{reply.headline or ''} {reply.text}"


def _intent_for(question: str):
    canonical = canonical_question(question)
    return match_intent(canonical, extract_entities(canonical))


# ------------------------------------------- one: prefer what can be executed

Q35 = "BLR closes 08:00-14:00Z on 17 Sep. Outline the recovery plan across affected pairings."


def test_a_closure_recovery_question_reaches_the_closure_shape() -> None:
    intent = _intent_for(Q35)
    assert intent is not None
    assert intent.name == "station_closure", (
        f"{intent.name} won on priority and cannot fill its own arguments"
    )


def test_a_closure_recovery_question_is_answered(resolver) -> None:
    reply = _ask(resolver, Q35)
    assert reply.kind.value == "answer", reply.text
    assert "BLR" in _text(reply)


def test_a_failed_lookup_is_not_how_this_declines(resolver) -> None:
    """A tool refusing an empty argument is our routing bug, not a finding."""
    reply = _ask(resolver, Q35)
    if reply.kind.value == "abstain":
        assert reply.abstention is not None
        assert reply.abstention.reason.value != "tool_error", reply.text


def test_a_cover_question_that_names_its_target_still_wins() -> None:
    """Falling through must not demote the shape when it CAN run."""
    intent = _intent_for(
        "Captain C-1042 is out for pairing P-2291 (15-16 Sep). "
        "Produce ranked resolution options with costs and reasoning."
    )
    assert intent is not None and intent.name == "cover_options"


# ------------------------------------------------- two: how a desk asks for it

PHRASINGS = [
    (
        "options-cheapest",
        "First Officer C-4806 cannot fly P-2293. What are my options, cheapest first?",
    ),
    (
        "best-ways",
        "Give me the best three ways to cover Captain C-1042 on P-2291, "
        "with the trade-offs of each.",
    ),
    (
        "who-to-call",
        "The captain on P-2293 is unavailable. Who should I call and what will it cost me?",
    ),
    ("how-do-i", "C-1042 is out. How do I cover P-2291 now?"),
    (
        "rank-covers",
        "Captain C-1526 calls in sick for P-2295 (19-20 Sep). Rank the legal covers with cost.",
    ),
]


@pytest.mark.parametrize(("case_id", "question"), PHRASINGS, ids=[c[0] for c in PHRASINGS])
def test_a_desk_phrasing_reaches_a_cover_search(case_id: str, question: str) -> None:
    intent = _intent_for(question)
    assert intent is not None, f"{case_id}: matched no shape at all"
    assert intent.tier == 3, f"{case_id}: routed to a tier {intent.tier} shape"


@pytest.mark.parametrize(("case_id", "question"), PHRASINGS, ids=[c[0] for c in PHRASINGS])
def test_a_desk_phrasing_gets_ranked_options(resolver, case_id: str, question: str) -> None:
    reply = _ask(resolver, question)
    assert reply.kind.value == "answer", f"{case_id}: {reply.text}"
    assert reply.recommendation is not None, f"{case_id}: answered without a recommendation"
    assert reply.recommendation.options, f"{case_id}: ranked nothing"
    assert reply.recommendation.options[0].legal, (
        f"{case_id}: rank 1 is {reply.recommendation.options[0].crew_id} and is not legal"
    )


# ------------------------------- generalisation: the other two 2-day pairings

TWO_DAY = [("P-2293", "C-5566", "17"), ("P-2295", "C-1526", "19")]


@pytest.mark.parametrize(("pairing", "captain", "day"), TWO_DAY, ids=[p[0] for p in TWO_DAY])
def test_the_other_two_day_pairings_cover_too(
    resolver, pairing: str, captain: str, day: str
) -> None:
    """P-2291 is the anchor every test and every doc uses. P-2293 and P-2295
    are the same two-day VT-DXC structure and are asked about nowhere, so they
    are the check that the search generalises rather than having been fitted."""
    reply = _ask(
        resolver,
        f"Captain {captain} is out for pairing {pairing}. Produce ranked resolution options.",
    )
    assert reply.kind.value == "answer", reply.text
    rec = reply.recommendation
    assert rec is not None and rec.options, "no ranked options"
    assert rec.options[0].legal
    assert rec.rejected, "a search that rejects nothing has not shown its work"
    for option in rec.options:
        assert option.legality.per_day, f"{option.crew_id} judged without a per-day breakdown"
        if option.legal:
            assert len(option.legality.per_day) == 2, (
                f"{option.crew_id} offered as legal for {pairing} on "
                f"{len(option.legality.per_day)} of 2 days"
            )


# ------------------------------------------------------------- no regressions


@pytest.fixture(scope="module")
def shipped() -> list[dict]:
    return json.loads((DATA_DIR / "questions.json").read_text(encoding="utf-8"))


def test_no_shipped_question_stops_answering(resolver, shipped: list[dict]) -> None:
    abstaining = {
        q["question_id"] for q in shipped if _ask(resolver, q["prompt"]).kind.value != "answer"
    }
    known = {"Q15", "Q25", "Q26", "Q27", "Q30", "Q32", "Q33", "Q37", "Q38"}
    assert abstaining <= known, f"newly abstaining: {sorted(abstaining - known)}"

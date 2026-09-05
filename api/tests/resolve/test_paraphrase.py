"""The same question in different words is the same question.

The offline resolver matches fixed shapes, and those shapes were written from
`questions.json`, so they match the shipped wording and very little else.
Rewording five shipped Tier 2 questions, it answered **none** of them, while
the agent answered all five. A judge who rephrases a question they have just
seen work gets a refusal.

Two different causes, and only one of them is about wording.

WORDING. Four of the five have a working shape that the paraphrase misses by a
synonym:

    Q18  "does any rule breach"        vs  "would ... break any rule"
    Q24  "cover the FULL pairing"      vs  "legal for the whole of"
    Q19  "BLR is closed"               vs  "Bangalore shuts"
    Q22  "legally operate"             vs  "allowed to fly"

The fix is a synonym fold in `canonical_question`, which already rewrites
`C1042` to `C-1042` and `bangalore` to `BLR` for exactly this reason. One table,
applied once, and every intent and the tier classifier benefit. Adding patterns
per intent instead would mean doing it again for the next synonym, and the one
after that.

A MISSING SHAPE. The fifth is not a wording problem at all. **Q23 is a shipped
question with no intent**: "A crew is released at 15:30Z on 16 Sep. What is the
earliest they may report next?" matches nothing and abstains, even though
`earliest_report` exists as a tool and answers it exactly. So it is one of the
five deterministic Tier 2 abstentions, and it did not have to be.

Nothing here rewrites an answer. `canonical_question` rewrites the *question*
only, so no value can reach a controller that a tool did not produce, which is
the same guarantee the crew-id and station folds already rely on.
"""

from __future__ import annotations

import datetime as dt
import json

import pytest

from crewops.domain import DATA_DIR

SNAPSHOT = dt.datetime(2026, 9, 14, 18, 0, 0)


def _ask(resolver, question: str):
    return resolver.answer(question, thread_id="t-para", turn_id="u-1", asked_at=SNAPSHOT)


# --------------------------------------------------------------- the shape gap


def test_q23_has_an_intent_at_all(resolver) -> None:
    """A shipped question answered by an existing tool and reached by nothing."""
    reply = _ask(
        resolver,
        "A crew is released at 15:30Z on 16 Sep. What is the earliest they may report next?",
    )
    assert reply.kind.value == "answer", reply.text
    assert "03:30" in f"{reply.headline or ''} {reply.text}"


def test_the_rest_shape_reads_other_phrasings_too(resolver) -> None:
    reply = _ask(
        resolver,
        "A crew finished duty at 15:30Z on 16 Sep. What is the soonest they can start again?",
    )
    assert reply.kind.value == "answer", reply.text
    assert "03:30" in f"{reply.headline or ''} {reply.text}"


def test_the_rest_answer_leads_with_the_time(resolver) -> None:
    """A controller reads the first line and acts on it.

    The generic renderer led with "Apply RULE-REST-04 forwards: Resolved from
    the release time given, ...", which is the trace label. Correct, grounded,
    and it buries the one thing being asked for behind a sentence about method.
    """
    reply = _ask(
        resolver,
        "A crew is released at 15:30Z on 16 Sep. What is the earliest they may report next?",
    )
    headline = reply.headline or ""
    assert "03:30" in headline, f"the time is not in the first line: {headline!r}"
    assert not headline.startswith("Apply"), headline


# ------------------------------------------------------------------- synonyms

PARAPHRASES = [
    (
        "break-vs-breach",
        "Would C-2087 break any rule if they covered P-2291 from 15 Sep?",
        "RULE-DUTY-02",
    ),
    (
        "whole-vs-full",
        "Is reserve C-3305 legal for the whole of pairing P-2291, both days?",
        "C-3305",
    ),
    ("shuts-vs-closed", "Bangalore shuts 08:00 to 14:00Z on 17 Sep. What does that hit?", "DX402"),
    ("allowed-vs-legally", "Is C-5417 allowed to fly their VT-DXB duty on 19 Sep?", "RULE-CERT-06"),
]


@pytest.mark.parametrize(
    ("case_id", "question", "expected"),
    PARAPHRASES,
    ids=[c[0] for c in PARAPHRASES],
)
def test_a_reworded_question_reaches_the_same_shape(
    resolver,
    case_id: str,
    question: str,
    expected: str,
) -> None:
    reply = _ask(resolver, question)
    assert reply.kind.value == "answer", f"{case_id}: {reply.text}"
    assert expected in f"{reply.headline or ''} {reply.text}", case_id


# ------------------------------------------------------------- no regressions


@pytest.fixture(scope="module")
def shipped() -> list[dict]:
    return json.loads((DATA_DIR / "questions.json").read_text(encoding="utf-8"))


def test_no_shipped_question_stops_answering(resolver, shipped: list[dict]) -> None:
    """The baseline before this change: eleven abstain, and Q23 is one of them.

    Folding synonyms rewrites every question on its way in, so a careless entry
    could break a shape that works. This is the check that it did not, and it
    tightens as shapes are added rather than staying at the old number.
    """
    abstaining = {
        q["question_id"] for q in shipped if _ask(resolver, q["prompt"]).kind.value != "answer"
    }
    known = {"Q15", "Q25", "Q26", "Q27", "Q30", "Q32", "Q33", "Q35", "Q37", "Q38"}
    assert abstaining <= known, f"newly abstaining: {sorted(abstaining - known)}"

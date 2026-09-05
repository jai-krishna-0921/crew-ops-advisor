"""The tier floor is what arms `tier_guard`, so under-classifying disarms it.

`tier_guard` refuses a Tier 2 or Tier 3 answer whose tool calls were all in
`RETRIEVAL_ONLY`: retrieval establishes what is, not what follows. That is the
guard which stops the system degrading into a fluent lookup with a confident
tone. It reads the tier from `classify_tier`, so a question classified Tier 1
is never checked at all.

Asking Tier 2 questions in wording that is not the shipped wording, five of
nine came back Tier 1, and one of them showed exactly the failure the guard
exists to prevent:

    "Is C-2087's licence valid for a duty on 2026-09-19?"
    -> classified tier 1, matched `crew_detail`, answered with a crew dump:
       rank, base, duty hours, risk score, and a certifications list in which
       "licence: valid to 2026-09-18" appears.

A human can infer "no" from that. The system never said no, never cited
RULE-CERT-06, and never stated a verdict. It answered a legality question with
a lookup, which is precisely what `tier_guard` forbids, and the guard could not
see it because triage had called the question Tier 1.

The markers were keyed to shipped phrasings. `\\bearliest they may report\\b` is
Q23 word for word; "soonest they can start again" matched nothing. `\\blegal\\b`
missed "allowed to", `\\bbreach\\b` missed "break any rule", and nothing at all
matched "valid for a duty on".

THE RISK IN THE OTHER DIRECTION IS REAL and is why the second half of this file
exists. Over-classifying a genuine Tier 1 lookup would make `tier_guard` refuse
a correct answer, turning this fix into a new source of abstentions. No shipped
Tier 1 question may move.
"""

from __future__ import annotations

import json

import pytest

from crewops.domain import DATA_DIR
from crewops.resolve import classify_tier

#: Tier 2 asks what follows from a change. None of these is shipped wording.
TIER2_SHAPES = [
    ("break-a-rule", "Would C-2087 break any rule if they covered P-2291 from 15 Sep?"),
    ("rule-break-noun", "Does covering P-2291 with C-2087 cause a rule break?"),
    ("allowed-to", "Is C-5417 allowed to fly their VT-DXB duty on 19 Sep?"),
    ("permitted-to", "Is C-2210 permitted to operate out of BLR on 16 Sep?"),
    ("valid-on", "Is C-2087's licence valid for a duty on 2026-09-19?"),
    (
        "soonest-start",
        "A crew finished duty at 15:30Z on 16 Sep. What is the soonest they can start again?",
    ),
    ("when-next-fly", "When can a crew released at 22:15Z on 15 Sep next fly?"),
    ("threshold-duty", "Which crew have more than 50 duty hours in the 7 days ending 2026-09-14?"),
    ("what-happens-if", "What happens if DX433 on 2026-09-18 is cancelled?"),
    ("knock-on", "What is the knock-on effect of grounding VT-DXF on 18 Sep?"),
]


@pytest.mark.parametrize(("case_id", "question"), TIER2_SHAPES, ids=[c[0] for c in TIER2_SHAPES])
def test_a_consequence_question_is_not_classified_as_a_lookup(case_id: str, question: str) -> None:
    tier = classify_tier(question)
    assert tier >= 2, (
        f"{case_id}: classified tier {tier}, so tier_guard never runs and a "
        f"retrieval-only answer to it would pass unchecked.\n  {question}"
    )


# --------------------------------------------------------- no over-classifying


@pytest.fixture(scope="module")
def shipped() -> list[dict]:
    return json.loads((DATA_DIR / "questions.json").read_text(encoding="utf-8"))


def test_no_shipped_lookup_is_promoted_out_of_tier_1(shipped: list[dict]) -> None:
    """The expensive direction of this mistake.

    A Tier 1 lookup classified as Tier 2 gets refused by `tier_guard` unless a
    simulation tool ran, which for a lookup it never will. That converts
    correct answers into abstentions, so this must stay empty.
    """
    promoted = [
        q["question_id"] for q in shipped if q["tier"] == 1 and classify_tier(q["prompt"]) > 1
    ]
    assert not promoted, f"tier 1 questions promoted: {', '.join(promoted)}"


def test_q26_is_recognised_as_a_consequence_question(shipped: list[dict]) -> None:
    """Q26 is declared Tier 2 and classified Tier 1: a threshold over a duty
    window is a computation, not a field read."""
    q26 = next(q for q in shipped if q["question_id"] == "Q26")
    assert classify_tier(q26["prompt"]) >= 2, q26["prompt"]


def test_every_shipped_question_classifies_at_or_below_its_declared_tier(
    shipped: list[dict],
) -> None:
    """The floor may sit below the declared tier (the model can raise it) but
    it must never sit above, which would over-constrain the answer."""
    above = [
        (q["question_id"], q["tier"], classify_tier(q["prompt"]))
        for q in shipped
        if classify_tier(q["prompt"]) > q["tier"]
    ]
    assert not above, above

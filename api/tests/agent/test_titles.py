"""A conversation's name, in five words or fewer.

THE TITLE COMES FROM THE QUESTION, NOT FROM THE ANSWER. This reverses the
earlier decision recorded in `test_thread_titles.py`, and the reason is what
the reversal produced on screen. Naming a thread from `Reply.headline` meant
typing "hey" and getting a conversation called "This is a crew operations desk
assistant", which describes the product rather than the exchange. A headline is
written to be read once, at the top of an answer, at whatever length the answer
needs. A name is read fifty times, in a rail 208 pixels wide.

Two rules fall out of that width.

**Five words.** Anything longer is truncated by the rail, and a name the reader
never sees the end of is not a name.

**The identifier goes first.** "C-1042 duty hours" survives truncation with the
crew id intact; "Duty hours for C-104…" does not, and the id is the token
somebody is scanning the list for. Dates go last, because a date is context
rather than subject.

Nothing here calls a model. The mapping is a lookup over the question's own
words, so it is the same offline as it is with a key configured, it costs
nothing, and it is reproducible: the same question always yields the same name.
A title is language rather than a figure, so a model would be *allowed* to
write one, but an extra round trip per thread buys nothing a table cannot do.

The table below is the whole of `questions.json`. It is the specification.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from crewops.agent.titles import title_for
from crewops.contracts import AbstentionReason

#: Every question in the dataset, with the name its conversation should carry.
#: Derived by reading each prompt and asking what a controller scanning a list
#: of thirty threads would need to see to find this one again.
EXPECTED: dict[str, str] = {
    "Q01": "BLR reserve cover",
    "Q02": "C-1042 duty hours",
    "Q03": "DEL flights",
    "Q04": "Certifications 15 Sep",
    "Q05": "DX412 aircraft",
    "Q06": "C-3310 reserve cover",
    "Q07": "C-2210 qualification",
    "Q08": "P-2291 roster",
    "Q09": "BLR to BOM flights",
    "Q10": "Flights 16 Sep",
    "Q11": "DEL captains",
    "Q12": "Block time",
    "Q13": "C-2087 flight hours",
    "Q14": "BLR network",
    "Q15": "VT-DXB senior cabin crew",
    "Q16": "C-1042 risk score",
    "Q17": "C-1042 on P-2291 absence impact",
    "Q18": "C-2087 on P-2291 legality",
    "Q19": "BLR closure",
    "Q20": "DX401 delay impact",
    "Q21": "C-2210 on P-2291 legality",
    "Q22": "C-5417 legality",
    "Q23": "Minimum rest 16 Sep",
    "Q24": "C-3305 on P-2291 cover options",
    "Q25": "DX404 cancellation impact",
    "Q26": "Duty hours 15 Sep",
    "Q27": "VT-DXE absence impact",
    "Q28": "C-5837 on P-2291 legality",
    "Q29": "HYD closure",
    "Q30": "Cancellation impact",
    "Q31": "C-1042 on P-2291 ranked options",
    "Q32": "VT-DXA ranked options",
    "Q33": "VT-DXA ranked options",
    "Q34": "C-5417 ranked options",
    "Q35": "BLR ranked options",
    "Q36": "C-3310 on P-2291 callout notice",
    "Q37": "VT-DXF ranked options",
    "Q38": "Morning brief",
}

_DATA = (
    Path(__file__).resolve().parents[3]
    / "data"
    / "crew-ops-advisor-dataset"
    / "data"
    / "questions.json"
)


def _prompts() -> dict[str, str]:
    payload = json.loads(_DATA.read_text())
    rows = payload if isinstance(payload, list) else next(iter(payload.values()))
    return {row["question_id"]: row["prompt"] for row in rows}


@pytest.mark.parametrize("question_id", sorted(EXPECTED))
def test_every_dataset_question_gets_the_name_it_should(question_id: str) -> None:
    prompt = _prompts()[question_id]
    assert title_for(prompt) == EXPECTED[question_id], (
        f"{question_id}: {prompt!r}"
    )


@pytest.mark.parametrize("question_id", sorted(EXPECTED))
def test_no_title_runs_past_five_words(question_id: str) -> None:
    """The rail truncates, so the cap is the product requirement."""
    title = title_for(_prompts()[question_id])
    assert len(title.split()) <= 5, f"{question_id}: {title!r}"


def test_a_greeting_is_named_a_greeting() -> None:
    """The case in the bug report: "hey" was named after the capability blurb."""
    title = title_for("hey", abstention_reason=AbstentionReason.GREETING)
    assert title == "Greeting"


def test_a_question_outside_the_dataset_keeps_its_own_words() -> None:
    """There is no topic to name, so the question names itself, tidily.

    A trailing preposition is dropped rather than left dangling: "What is the
    weather at" reads as a truncation bug, "What is the weather" reads as a
    title.
    """
    assert title_for("What is the weather at BLR?") == "What is the weather"


def test_an_empty_question_still_produces_something() -> None:
    assert title_for("   ") == "New conversation"


def test_the_same_question_always_produces_the_same_name() -> None:
    """No model, no sampling, no drift between two identical threads."""
    prompt = "Captain C-1042 is out for pairing P-2291. Rank the options."
    assert title_for(prompt) == title_for(prompt)


def test_a_title_starts_with_the_identifier_it_is_about() -> None:
    """The rail truncates from the right, so the scannable token goes left."""
    title = title_for(
        "As of the snapshot, how many duty hours has C-1042 accrued in the 7 "
        "calendar days ending 2026-09-14?"
    )
    assert title.startswith("C-1042"), title

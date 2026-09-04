"""One sentence, once.

`headline_of` selects the leading sentence of an answer and `_body_after` is
supposed to take that sentence back out of the body, so an interface renders
it as a heading and not again immediately underneath.

It only ever did that when the answer contained a line break. A single
paragraph answer, which is most of them, kept its opening sentence in both
places. The greeting made it unmissable: a heading reading "This is a crew
operations desk assistant" sitting on top of a paragraph that opens with the
same eight words.

The distinction that decides the implementation is the last test in this file.
When there is no sentence end inside the headline budget, `headline_of` cuts
on a word boundary instead. Removing a cut like that from the body would leave
the answer opening halfway through a clause, so it stays.
"""

from __future__ import annotations

from crewops.agent.reply import _body_after, headline_of
from crewops.contracts import Abstention, AbstentionReason

#: The greeting, verbatim from `resolve/triage.py`. One line, two sentences.
GREETING = (
    "This is a crew operations desk assistant. Ask about crew, flights, "
    "pairings, rosters, duty and flight hour limits, certifications, reserve "
    "cover or the impact of a disruption."
)

#: The real answer to "How many duty hours has C-1042 accrued". One paragraph,
#: four sentences, well over the headline budget.
LONG_ANSWER = (
    "C-1042 (A. Nair, Captain, BLR, A320) has accrued 20.93 duty hours in the 7 days "
    "ending 2026-09-14. The duty clocks report headroom of 39.07h (39h04m) under "
    "RULE-DUTY-02, whose limit is 60h. That leaves room for a further duty period "
    "before the weekly ceiling binds."
)


def test_a_single_paragraph_does_not_repeat_its_headline() -> None:
    """The defect, on a real answer.

    A short line is its own headline and leaves no body, which was already
    handled. The break is the paragraph long enough that the headline has to
    be a slice of it, because then the slice stayed where it was.
    """
    headline = headline_of(LONG_ANSWER)
    assert headline is not None

    body = _body_after(LONG_ANSWER, headline)
    assert body.startswith("The duty clocks report")
    assert headline not in body, (
        "the heading sentence is still in the body, so it renders twice"
    )


def test_a_greeting_states_the_capability_once() -> None:
    """The case in the screenshot: heading, then the same words again."""
    abstention = Abstention(reason=AbstentionReason.GREETING, message=GREETING)
    headline = headline_of("", abstention=abstention)
    assert headline == "This is a crew operations desk assistant"

    body = _body_after(GREETING, headline)
    assert body.startswith("Ask about crew")
    assert "desk assistant" not in body


def test_the_body_keeps_every_figure_the_headline_did_not_take() -> None:
    """Trimming the lead sentence must not cost the answer its numbers."""
    body = _body_after(LONG_ANSWER, headline_of(LONG_ANSWER))
    assert "39.07h" in body
    assert "RULE-DUTY-02" in body
    assert "60h" in body


def test_a_headline_and_the_body_under_it_still_reconstruct_the_answer() -> None:
    """Nothing is dropped, it only moves. Both halves together are the whole."""
    headline = headline_of(LONG_ANSWER) or ""
    body = _body_after(LONG_ANSWER, headline)
    for figure in ("20.93", "2026-09-14", "39.07h", "39h04m", "RULE-DUTY-02", "60h"):
        assert figure in f"{headline} {body}", f"{figure} was lost"


def test_a_one_line_answer_that_is_its_own_headline_leaves_no_body() -> None:
    text = "C-3310's reachability is 45 minutes."
    assert _body_after(text, headline_of(text)) == ""


def test_a_multi_line_answer_keeps_its_body() -> None:
    text = "12 crew are on reserve at BLR.\nCaptains: C-3305, C-3310."
    assert _body_after(text, headline_of(text)) == "Captains: C-3305, C-3310."


def test_a_long_first_line_does_not_repeat_its_lead_sentence() -> None:
    """The half of the defect the single paragraph fix did not reach.

    The multi-line branch only ever recognised the case where the headline is
    the WHOLE first line. When that line runs past the 200 character budget
    the headline is a slice of it instead, the branch stopped matching, and
    the body kept the line entire. On screen that is the same sentence in two
    consecutive paragraphs, which is what a real Tier 1 answer produced.
    """
    lead = (
        "C-1042 has accrued 20.93 duty hours in the 7 calendar days ending "
        "2026-09-14 (window 2026-09-08 to 2026-09-14, inclusive). Headroom "
        "under RULE-DUTY-02 is 39.07 hours (39h04m), computed as 60 minus 20.93."
    )
    assert len(lead) > 200, "the fixture only exercises the bug over the budget"
    text = f"{lead}\nThe legality check confirms this."

    headline = headline_of(text)
    assert headline is not None
    assert headline.endswith("inclusive)")

    body = _body_after(text, headline)
    assert headline not in body, "the lead sentence renders twice"
    assert body.startswith("Headroom under RULE-DUTY-02")
    assert "The legality check confirms this." in body
    assert "39.07" in body and "39h04m" in body


def test_a_body_that_does_not_open_with_the_headline_is_left_alone() -> None:
    """A model may write a heading that is not a slice of what follows."""
    text = "The pairing is covered. C-3310 takes both days."
    assert _body_after(text, "Something else entirely") == text


# ------------------------------------------------------- what must not change


def test_a_sentence_that_will_not_fit_produces_no_headline_at_all() -> None:
    """The case that decides the implementation.

    With no sentence end inside the 200 character budget there is nothing to
    select, and what used to happen instead was a cut on the nearest word
    boundary. That is a fragment, and a fragment is wrong in every interface
    that consumes it: the terminal printed "...(max 60 duty hours in" in a
    bold panel, and the web, which renders the headline as the answer's first
    paragraph, printed the fragment and then the whole sentence again
    underneath it.

    A HEADLINE IS A SENTENCE OR IT IS NOTHING. When there is not one, the
    answer is simply prose with no lead, which every interface already handles
    because an answer can have no headline for other reasons.
    """
    text = "Covering P-2291 means " + "checking every duty day in the window " * 8
    assert len(text) > 200

    assert headline_of(text) is None
    assert _body_after(text, None) == text, "with no headline the body is the answer"

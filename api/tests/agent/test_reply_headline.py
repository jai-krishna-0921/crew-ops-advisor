"""What a controller reads first, and reads only once.

Two defects live here, both cosmetic in the sense that no figure is wrong and
both unmissable in the sense that they are the first thing on the screen.

The headline is a slice of the answer, never invented. Taking a slice means
deciding where a sentence ends, and this dataset writes crew names as an
initial and a surname: `A. Nair`. Splitting on ". " truncated
`C-1042 (A. Nair, Captain, BLR, A320) has accrued...` to `C-1042 (A`, which is
what a judge would have seen at the top of the answer.

The second is duplication. `headline_of` takes the first line, so for a one
line answer the headline is the whole answer, and every interface then prints
it twice: once large, once again immediately underneath.
"""

from __future__ import annotations

from crewops.agent.reply import _body_after, headline_of

#: The real answer to "How many duty hours has C-1042 accrued". Over 200
#: characters, so the headline has to be cut somewhere.
LONG_ANSWER = (
    "C-1042 (A. Nair, Captain, BLR, A320) has accrued 20.93 duty hours in the 7 days "
    "ending 2026-09-14. The duty clocks report headroom of 39.07h (39h04m) under "
    "RULE-DUTY-02, whose limit is 60h. That leaves room for a further duty period "
    "before the weekly ceiling binds."
)


def test_a_headline_does_not_break_at_a_crew_name_initial() -> None:
    """`A. Nair` is a name, not the end of a sentence."""
    headline = headline_of(LONG_ANSWER)
    assert headline is not None
    assert headline != "C-1042 (A"
    assert not headline.endswith("(A"), f"truncated at the initial: {headline!r}"
    assert len(headline) > 40, f"headline is uselessly short: {headline!r}"


def test_a_headline_is_always_a_slice_and_never_invented() -> None:
    """The whole design of `headline_of`: it selects, it does not write."""
    headline = headline_of(LONG_ANSWER)
    assert headline is not None
    assert headline in LONG_ANSWER, f"{headline!r} is not a substring of the answer"


def test_a_headline_stays_within_its_budget() -> None:
    assert len(headline_of(LONG_ANSWER) or "") <= 200


def test_a_short_answer_is_its_own_headline_untouched() -> None:
    text = "12 crew are on reserve at BLR on 2026-09-15."
    assert headline_of(text) == text


def test_a_one_line_answer_is_not_rendered_twice() -> None:
    """The duplication a controller sees as a title above an identical answer."""
    text = "C-3310's reachability is 45 minutes."
    headline = headline_of(text)
    assert headline == text
    assert _body_after(text, headline) == "", (
        "A one line answer whose headline is the whole answer must leave an "
        "empty body, or every interface prints the sentence twice."
    )


def test_a_multi_line_answer_keeps_its_body() -> None:
    """The fix must not eat the answer when there genuinely is one."""
    text = "12 crew are on reserve at BLR.\nCaptains: C-3305, C-3310."
    headline = headline_of(text)
    assert headline == "12 crew are on reserve at BLR."
    assert _body_after(text, headline) == "Captains: C-3305, C-3310."


def test_a_long_single_paragraph_keeps_its_full_text_as_the_body() -> None:
    """Here the headline is a slice, so the body must still carry everything.

    Emptying it would drop the sentence the headline was cut out of, and with
    it every figure after the first full stop.
    """
    body = _body_after(LONG_ANSWER, headline_of(LONG_ANSWER))
    assert "39.07h" in body
    assert "RULE-DUTY-02" in body


def test_an_abstention_headline_still_reads_as_a_sentence() -> None:
    """Abstentions split on ". " too, and carry no crew initials, but pin it."""
    from crewops.contracts import Abstention, AbstentionReason

    abstention = Abstention(
        reason=AbstentionReason.UNDERSPECIFIED,
        message="I cannot answer that reliably. The question named no date.",
        missing=["a date"],
    )
    assert headline_of("", abstention=abstention) == "I cannot answer that reliably"

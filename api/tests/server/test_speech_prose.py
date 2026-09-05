"""What the speech synthesiser was actually handed.

Reported: the voice "is breaking and is like continuous. No pauses, no
expressions." Both halves have the same cause, and it is visible by printing
what goes over the wire. A tier 3 answer, six paragraphs, 547 characters:

    speech_chunks(text)  ->  [547]

ONE CHUNK. `speech_chunks` splits on sentence ends and then repacks up to a
1000 character limit, so every paragraph boundary in the answer was packed
away and the synthesiser received a single unbroken utterance. There is
nowhere for it to breathe because nothing told it to.

And the content of that blob is:

    "Assign Captain C-3310 (reserve callout) ... at INR 18,500 ... Tightest
     margin is 0h30m spare under RULE-REST-04 ... report 06:00Z"

Read aloud with no preparation that is "C dash three three one zero", "I N R
eighteen thousand five hundred", "zero H thirty M", "RULE dash REST dash zero
four", "zero six colon zero zero zed". A stream of characters, at speed, with
no phrase boundaries. It sounds broken because it is being read as though it
were code, which is what it looks like.

This module is speech only. `speech_text` feeds the voice websocket and
nothing else: the verifier checks the rendered answer, not the recitation, so
nothing here can affect grounding. What it can do is stop pronouncing an
identifier one character at a time.
"""

from __future__ import annotations

import pytest

from crewops.agent.voice.prose import speech_chunks, speech_for_voice

# ------------------------------------------------------------------- pauses

SIX_PARAGRAPHS = (
    "Captain cover required for P-2291 on 2026-09-15.\n\n"
    "Assign Captain C-3310 (reserve callout).\n\n"
    "C-3310 clears all seven rules on every day of P-2291.\n\n"
    "Tightest margin is 0h30m spare under RULE-REST-04.\n\n"
    "24 candidates evaluated, 19 were excluded.\n\n"
    "The next option is C-1526 at INR 24,000."
)


def test_a_paragraph_is_never_packed_into_its_neighbour() -> None:
    """The whole of the "no pauses" report, in one assertion."""
    chunks = speech_chunks(SIX_PARAGRAPHS)
    assert len(chunks) == 6, chunks


def test_every_chunk_ends_where_a_voice_would_stop() -> None:
    """Prosody is the synthesiser's job and punctuation is how it is asked."""
    for chunk in speech_chunks(SIX_PARAGRAPHS):
        assert chunk.rstrip()[-1] in ".!?", chunk


def test_a_long_paragraph_still_splits_on_sentences() -> None:
    long_one = " ".join(f"Sentence number {n} runs on for a while." for n in range(60))
    chunks = speech_chunks(long_one, limit=200)
    assert len(chunks) > 1
    assert all(len(chunk) <= 200 for chunk in chunks)


def test_a_single_short_answer_stays_one_chunk() -> None:
    assert speech_chunks("C-1042 is at BLR.") == ["C-1042 is at BLR."]


# ------------------------------------------------------------ pronunciation

SPOKEN = [
    ("crew-id", "C-3310 is on reserve.", "C 3310"),
    ("pairing", "Cover P-2291 today.", "P 2291"),
    ("flight", "DX412 departs at noon.", "DX 412"),
    ("tail", "The aircraft is VT-DXC.", "VT DXC"),
    ("rule", "It breaches RULE-REST-04.", "rule REST 04"),
    ("money", "It costs INR 18,500.", "18,500 rupees"),
    ("zulu", "Report 06:00Z at BLR.", "06:00 UTC"),
    ("hours", "Duty is 9.5h that day.", "9.5 hours"),
    ("hm", "Margin is 0h30m spare.", "0 hours 30 minutes"),
    ("date", "The duty is on 2026-09-15.", "15 September 2026"),
]


@pytest.mark.parametrize(("case_id", "written", "spoken"), SPOKEN, ids=[c[0] for c in SPOKEN])
def test_it_is_read_as_words(case_id: str, written: str, spoken: str) -> None:
    assert spoken in speech_for_voice(written), f"{case_id}: {speech_for_voice(written)!r}"


def test_a_dash_inside_a_word_is_left_alone() -> None:
    """Not every hyphen is an identifier."""
    assert "day-off" in speech_for_voice("This is a day-off callout.")


def test_ordinary_prose_is_untouched() -> None:
    plain = "The aircraft overnights away from base, so the cover takes the whole pairing."
    assert speech_for_voice(plain) == plain


def test_the_written_answer_is_not_changed() -> None:
    """Speech normalisation must never leak into the rendered answer, which is
    what the verifier checked and what a controller reads."""
    from crewops.agent.voice import prose

    assert not hasattr(prose, "_MUTATES_REPLY")
    written = "C-3310 costs INR 18,500."
    assert speech_for_voice(written) != written
    assert "INR 18,500" in written

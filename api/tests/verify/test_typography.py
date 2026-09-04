"""The guard must not fire on a correct answer that is typed prettily.

Language models write typographically. They reach for a non-breaking hyphen in
`C-3310` so the identifier does not wrap, curly quotes around a possessive, an
en dash in a `06:00-18:00` range. All of that is the same answer.

Before this was fixed the extractor scanned for an ASCII hyphen, did not find
one in `C‑3310`, and fell through to the bare integer `3310`. A number that
appears in no tool output cannot be attested, so a correct answer was rejected
and the turn abstained. It cost four of sixteen Tier 1 questions.

This is not a loosening of the check. Invariant 3 still holds exactly: `C-3310`
is not `C-3301`, and no fuzzy matching is introduced. The fold is one character
to one character, so every span offset the scanner reports stays valid, and all
it does is let the scanner recognise the identifier that is genuinely written
there.
"""

from __future__ import annotations

import pytest

from crewops.verify.extract import extract_atoms

#: Every dash a model reaches for instead of ASCII hyphen-minus.
DASHES: tuple[tuple[str, str], ...] = (
    ("‐", "HYPHEN"),
    ("‑", "NON-BREAKING HYPHEN"),
    ("‒", "FIGURE DASH"),
    ("–", "EN DASH"),
    ("—", "EM DASH"),
    ("−", "MINUS SIGN"),
)


def kinds_of(text: str) -> dict[str, str]:
    """Canonical value by kind, for asserting on what was recognised."""
    return {atom.kind: atom.canon for atom in extract_atoms(text)}


def test_ascii_is_the_baseline() -> None:
    """The control. If this ever breaks, the rest of the file is meaningless."""
    atoms = extract_atoms("C-3310 is on call")
    assert [(a.text, a.kind) for a in atoms] == [("C-3310", "identifier")]


@pytest.mark.parametrize(("dash", "name"), DASHES)
def test_a_crew_id_survives_every_dash_a_model_might_type(dash: str, name: str) -> None:
    """The bug, parametrised over the whole family it belongs to."""
    atoms = extract_atoms(f"C{dash}3310 is on call")
    kinds = [a.kind for a in atoms]
    assert "identifier" in kinds, (
        f"{name} (U+{ord(dash):04X}) in C{dash}3310 was not recognised as an "
        f"identifier. Extracted {[(a.text, a.kind) for a in atoms]} instead. "
        "A bare number attests against nothing, so this rejects a correct answer."
    )
    assert [a.canon for a in atoms if a.kind == "identifier"] == ["C-3310"]


@pytest.mark.parametrize(("dash", "name"), DASHES)
def test_a_rule_id_survives_every_dash(dash: str, name: str) -> None:
    """Rule ids carry two hyphens, so they break the same way, twice over."""
    text = f"This breaches RULE{dash}DUTY{dash}02 on the second day."
    assert kinds_of(text).get("rule_id") == "RULE-DUTY-02", (
        f"{name} broke rule id recognition: {[(a.text, a.kind) for a in extract_atoms(text)]}"
    )


def test_the_sentence_that_actually_failed() -> None:
    """Q06, verbatim, as the model wrote it. It answered correctly.

    The reachability figure is real and attestable. The turn abstained anyway,
    because `3310` was extracted as a number rather than as part of the crew id.
    """
    drafted = "C‑3310’s reserve on‑call window is recorded, and reachability is 45 minutes."
    atoms = extract_atoms(drafted)
    canons = {(a.kind, a.canon) for a in atoms}
    assert ("identifier", "C-3310") in canons, (
        f"Extracted {sorted((a.kind, a.canon) for a in atoms)}, which does not "
        "include the crew id the sentence is about."
    )
    assert not any(a.kind == "number" and a.canon == "3310" for a in atoms), (
        "The crew id's digits are still leaking out as a standalone number."
    )


def test_curly_quotes_do_not_split_a_possessive_identifier() -> None:
    """`C-3310's` with a right single quotation mark is still about C-3310."""
    assert kinds_of("C-3310’s window opens at 06:00").get("identifier") == "C-3310"


def test_an_en_dash_range_still_yields_both_times() -> None:
    """`06:00-18:00` is how an on-call window gets written."""
    times = [a.canon for a in extract_atoms("On call 06:00–18:00.") if a.kind == "time"]
    assert times == ["06:00", "18:00"], f"got {times}"


def test_a_non_breaking_space_does_not_hide_a_currency_amount() -> None:
    """Models put a narrow no-break space between amount and unit."""
    text = "The callout costs INR 18,500."
    assert any(a.kind == "currency" for a in extract_atoms(text)), (
        f"Extracted {[(a.text, a.kind) for a in extract_atoms(text)]}"
    )


def test_the_fold_does_not_invent_an_identifier() -> None:
    """The other half of the guarantee: this must not create matches.

    Folding is only allowed to recover an identifier that was genuinely
    written. Ordinary prose containing a dash must not start producing
    identifier atoms, or the fold would be laundering rather than normalising.
    """
    atoms = extract_atoms("The crew—all of them—were rested.")
    assert not [a for a in atoms if a.kind == "identifier"], (
        f"The fold invented {[(a.text, a.kind) for a in atoms]} out of prose."
    )


def test_distinct_identifiers_stay_distinct_after_folding() -> None:
    """Invariant 3 is untouched: there is still no fuzzy matching."""
    assert kinds_of("C‑3310 is on call")["identifier"] == "C-3310"
    assert kinds_of("C‑3301 is on call")["identifier"] == "C-3301"

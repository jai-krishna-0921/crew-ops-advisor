"""How a controller types, versus how the dataset is written.

The offline path matches a question against fixed shapes, and those shapes
expect the dataset's spelling: `C-1042`, `BLR`, `2026-09-15`. A controller with
a radio in one hand types `C1042`, `bangalore`, and sometimes `reserver`.

Every one of these was a real abstention:

    "How many duty hours has C1042 accrued?"        no hyphen
    "who is on reserve in bangalore"                station name, not code

The agent path already survives all of it, because a language model reads
`C1042` as a crew id without being told. That is exactly why this belongs on
the deterministic side: the offline path is the one that has to be rigid, and
it is the one that runs when there is no key, no network and no budget.

Normalisation happens before intent matching and before entity extraction. It
rewrites the *question*, never the answer, so nothing here can put a value in
front of a controller that a tool did not produce.
"""

from __future__ import annotations

import pytest

from crewops.resolve.triage import canonical_question

# ------------------------------------------------------------------ crew ids


@pytest.mark.parametrize(
    ("typed", "expected"),
    [
        ("C1042", "C-1042"),
        ("c1042", "C-1042"),
        ("c-1042", "C-1042"),
        ("C 1042", "C-1042"),
        ("P2291", "P-2291"),
        ("p2291", "P-2291"),
        ("DX412", "DX412"),
        ("dx412", "DX412"),
        ("DX 412", "DX412"),
    ],
)
def test_identifiers_reach_their_dataset_spelling(typed: str, expected: str) -> None:
    assert expected in canonical_question(f"tell me about {typed} please")


def test_an_already_correct_identifier_is_untouched() -> None:
    """Normalisation must be idempotent: it runs on both paths."""
    once = canonical_question("Is C-1042 legal for P-2291 on 2026-09-15?")
    assert canonical_question(once) == once
    assert "C-1042" in once and "P-2291" in once


# ------------------------------------------------------------------- stations


@pytest.mark.parametrize(
    ("typed", "code"),
    [
        ("bangalore", "BLR"),
        ("Bengaluru", "BLR"),
        ("delhi", "DEL"),
        ("New Delhi", "DEL"),
        ("mumbai", "BOM"),
        ("chennai", "MAA"),
        ("kolkata", "CCU"),
        ("hyderabad", "HYD"),
        ("kochi", "COK"),
        ("goa", "GOI"),
    ],
)
def test_station_names_become_station_codes(typed: str, code: str) -> None:
    assert code in canonical_question(f"who is on reserve at {typed} tomorrow")


def test_only_the_eight_stations_in_the_dataset_are_mapped() -> None:
    """An alias for a station this airline does not serve is not a station.

    Mapping it would turn "who is on reserve at heathrow" from an honest
    refusal into a lookup against the wrong place.
    """
    assert "LHR" not in canonical_question("who is on reserve at heathrow")


# ------------------------------------------------------------------- what must not change


def test_it_does_not_invent_an_identifier_from_ordinary_prose() -> None:
    """The dangerous direction. A stray letter and number is not a crew id."""
    for text in ("the A320 has 4 sectors", "gate C 12", "terminal 2", "flight level 350"):
        out = canonical_question(text)
        assert "C-12" not in out, f"{text!r} became {out!r}"
        assert "-" not in out.replace("A320", "").replace("flight level", ""), out


def test_a_date_is_not_mangled() -> None:
    text = "Who is on reserve at BLR on 2026-09-15?"
    assert "2026-09-15" in canonical_question(text)


def test_rule_ids_survive() -> None:
    assert "RULE-DUTY-02" in canonical_question("explain RULE-DUTY-02")


def test_empty_and_whitespace_are_safe() -> None:
    assert canonical_question("") == ""
    assert canonical_question("   ").strip() == ""


def test_a_very_long_question_does_not_blow_up() -> None:
    out = canonical_question("Who is on reserve at bangalore? " * 500)
    assert "BLR" in out


# ------------------------------------------------- end to end on the offline path


class TestThroughTheResolver:
    """The abstentions this was written to remove."""

    @pytest.fixture(scope="class")
    def advisor(self) -> object:
        from crewops.agent import Advisor
        from crewops.agent.factory import load_tools

        return Advisor(load_tools())

    async def _ask(self, advisor: object, question: str) -> object:
        return await advisor.ask(question, force_mode="deterministic")  # type: ignore[attr-defined]

    async def test_a_crew_id_without_its_hyphen_is_answered(self, advisor: object) -> None:
        reply = await self._ask(advisor, "How many duty hours has C1042 accrued?")
        assert reply.kind.value != "abstain", reply.headline  # type: ignore[attr-defined]

    async def test_a_station_by_name_is_answered(self, advisor: object) -> None:
        reply = await self._ask(advisor, "Who is on reserve at bangalore on 2026-09-15?")
        assert reply.kind.value != "abstain", reply.headline  # type: ignore[attr-defined]

    async def test_an_unknown_crew_id_still_abstains(self, advisor: object) -> None:
        """Normalisation must not turn a refusal into a wrong answer."""
        reply = await self._ask(advisor, "How many duty hours has C9999 accrued?")
        assert reply.kind.value == "abstain"  # type: ignore[attr-defined]

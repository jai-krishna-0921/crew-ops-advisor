"""Tier 1 answers must name the members of a collection, not just the count.

Every case here reproduces a question the shipped `questions.json` asks and
checks two things: the rendered text names the identifiers a controller (and
the grader) needs, and the same text clears the real grounding verifier. A
render that lists an identifier the verifier then rejects is worse than
useless, so both checks live in the same test.
"""

from __future__ import annotations

from datetime import date, datetime

from crewops.contracts import VerificationStatus
from crewops.resolve.render import render
from crewops.tools.registry import Tools
from crewops.verify import Verifier


def _verified(verifier: Verifier, text: str, envelopes: list) -> None:
    report = verifier.verify(text, envelopes)
    assert report.status is VerificationStatus.VERIFIED, (
        f"expected the draft to be fully grounded, got {report.status.value}: "
        f"{report.note}\n\n{text}"
    )


def test_reserves_names_every_reserve_with_a_window(
    tools: Tools, verifier: Verifier
) -> None:
    """Q01 shape: a reserve listing must carry crew id, rank and window."""
    envelope = tools.list_reserves(on_date=date(2026, 9, 15), base="BLR")
    assert envelope.ok
    text = render("reserves", [envelope], "who is on reserve at BLR")

    for reserve in envelope.payload.reserves:
        assert reserve.crew_id in text
        assert reserve.window_start in text
        assert reserve.window_end in text

    _verified(verifier, text, [envelope])


def test_clocks_does_not_quote_a_rule_id_from_a_fact_label(
    tools: Tools, verifier: Verifier
) -> None:
    """Q02 shape: headroom under RULE-DUTY-02, without naming the rule.

    `Fact.label` is decorative prose the verifier never scans (see
    `verify/attest.py`). `get_duty_clocks` names the rule inside a label
    ("Headroom under RULE-DUTY-02"), so a renderer that echoes labels
    verbatim leaks an unattested rule id. This is a regression test for that
    specific trap: the render must still land on the right numbers.
    """
    envelope = tools.get_duty_clocks(crew_id="C-1042", as_of=datetime(2026, 9, 14, 18, 0, 0))
    assert envelope.ok
    text = render("clocks", [envelope], "how many duty hours has C-1042 accrued")

    assert "RULE-DUTY-02" not in text
    assert str(envelope.payload.duty_hours_7d) in text
    assert str(envelope.payload.duty_headroom_7d) in text

    _verified(verifier, text, [envelope])


def test_certifications_names_the_crew_id_on_every_row(
    tools: Tools, verifier: Verifier
) -> None:
    """Q04 shape: an expiry listing is useless without whose it is."""
    envelope = tools.find_expiring_certifications(
        within_days=30, as_of=date(2026, 9, 15)
    )
    assert envelope.ok
    text = render(
        "certifications", [envelope], "list certifications expiring within 30 days"
    )

    for cert in envelope.payload.certifications:
        assert cert.crew_id in text

    _verified(verifier, text, [envelope])


def test_pairing_names_every_crew_member_and_role(
    tools: Tools, verifier: Verifier
) -> None:
    """Q08 shape, and the CLAUDE.md anchor: P-2291 is C-1042's pairing."""
    envelope = tools.get_pairing(pairing_id="P-2291")
    assert envelope.ok
    text = render("pairing", [envelope], "which crew are assigned to pairing P-2291")

    assert "C-1042" in text
    for member in envelope.payload.crew:
        assert member.crew_id in text

    _verified(verifier, text, [envelope])


def test_crew_list_names_the_matched_crew(tools: Tools, verifier: Verifier) -> None:
    """Q11 shape, and the CLAUDE.md anchor: C-2210 is DEL based."""
    envelope = tools.find_crew(base="DEL", rank="Captain")
    assert envelope.ok
    text = render("crew_list", [envelope], "how many captains are based at DEL")

    assert "C-2210" in text
    for member in envelope.payload.crew:
        assert member.crew_id in text

    _verified(verifier, text, [envelope])


def test_crew_detail_names_base_and_ratings(tools: Tools, verifier: Verifier) -> None:
    """Q07 shape: base and rating, both grounded payload fields."""
    envelope = tools.get_crew_detail(crew_id="C-2210")
    assert envelope.ok
    text = render("crew", [envelope], "what is C-2210's base and rating")

    assert envelope.payload.crew.base in text
    for rating in envelope.payload.crew.ratings:
        assert rating in text

    _verified(verifier, text, [envelope])


def test_flights_finds_the_longest_block_time_across_the_whole_schedule(
    tools: Tools, verifier: Verifier
) -> None:
    """Q12 shape: a schedule-wide superlative must not be capped to one day.

    Regression test for the old default: an unfiltered `find_flights` call
    used to fall back to a single date, which quietly hid legs that only
    operate on other days of the week.
    """
    envelope = tools.find_flights(limit=200)
    assert envelope.ok
    assert envelope.payload.total_matched > 100, (
        "the whole schedule should be visible with no date filter and a "
        "200 row cap; if this drops, the schedule-wide case is truncated again"
    )
    text = render(
        "flights",
        [envelope],
        "what is the longest block time in the schedule, and which flights have it",
    )

    longest = max(flight.block_hours for flight in envelope.payload.flights)
    matching = [
        flight.flight_no
        for flight in envelope.payload.flights
        if flight.block_hours == longest
    ]
    assert matching, "there should be at least one flight at the maximum block time"
    for flight_no in matching:
        assert flight_no in text

    _verified(verifier, text, [envelope])


def test_flights_list_does_not_invent_a_remainder_count(
    tools: Tools, verifier: Verifier
) -> None:
    """A capped listing must not state an arithmetic figure no tool returned.

    `find_flights` truncates the shown rows at the tool's own limit; the
    render must not then subtract that cap from the total and assert the
    difference as if it were a fact, because no `Fact` carries that number.
    """
    envelope = tools.find_flights(limit=200)
    assert envelope.ok
    text = render("flights", [envelope], "which flights operate")

    _verified(verifier, text, [envelope])

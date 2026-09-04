"""The grounding check, tested adversarially and then tested for false alarms.

Both halves matter. A guard that never fires is decoration; a guard that fires
on correct answers is worse, because it kills the demo and teaches everyone to
switch it off.
"""

from __future__ import annotations

from datetime import date

import pytest

from crewops.contracts import (
    Citation,
    Fact,
    Provenance,
    ToolEnvelope,
    TraceStep,
    VerificationStatus,
)
from crewops.verify import Verifier, VerifierPolicy, extract_atoms
from crewops.verify.allowlist import ALLOWLIST_SIZE, SAFE_UPPERCASE_TOKENS
from tests.fakes import FakeTools


def fact(
    key: str,
    value: object,
    unit: str,
    *,
    derivation: str | None = None,
) -> Fact:
    return Fact(
        key=key,
        label=key,
        value=value,  # type: ignore[arg-type]
        unit=unit,  # type: ignore[arg-type]
        provenance=Provenance.COMPUTED if derivation else Provenance.DATASET,
        source="test",
        derivation=derivation,
    )


@pytest.fixture
def envelopes() -> list[ToolEnvelope]:
    """A realistic turn: the P-2291 pairing plus a C-2087 legality check."""
    tools = FakeTools()
    return [
        tools.get_pairing(pairing_id="P-2291"),
        tools.check_legality(crew_id="C-2087", pairing_id="P-2291"),
    ]


CORRECT = (
    "C-2087 cannot cover P-2291. On 2026-09-15 the 7 day duty total reaches "
    "61.33h against a 60.00h limit under RULE-DUTY-02, over by 1h20m. The same "
    "rule breaches again on 2026-09-16 at 61.08h."
)


class TestItDoesNotFireOnCorrectAnswers:
    """The half that keeps the system usable."""

    def test_the_anchor_answer_verifies(self, envelopes: list[ToolEnvelope]) -> None:
        report = Verifier().verify(CORRECT, envelopes)
        assert report.status is VerificationStatus.VERIFIED, report.unattested

    @pytest.mark.parametrize(
        "rendering",
        [
            "The 7 day total is 61.33h against a 60h limit.",
            "The 7 day total is 61.33 hours against a 60 hour limit.",
            "The excess is 1h20m.",
            "The excess is 1.33h.",
            "The excess is 1 hour 20 minutes.",
            "The excess is 80 minutes.",
        ],
    )
    def test_every_legitimate_rendering_of_the_same_fact_passes(
        self, envelopes: list[ToolEnvelope], rendering: str
    ) -> None:
        report = Verifier().verify(rendering, envelopes)
        assert report.status is VerificationStatus.VERIFIED, report.unattested

    def test_partial_dates_match_full_ones(
        self, envelopes: list[ToolEnvelope]
    ) -> None:
        report = Verifier().verify("Day 1 is 15 Sep.", envelopes)
        assert report.status is VerificationStatus.VERIFIED, report.unattested

    def test_prose_with_no_figures_is_skipped(
        self, envelopes: list[ToolEnvelope]
    ) -> None:
        report = Verifier().verify(
            "That candidate is not available and I would look elsewhere.", envelopes
        )
        assert report.status is VerificationStatus.SKIPPED
        assert report.checked_atoms == 0


class TestItFiresOnWrongOnes:
    """One token changed in each. Every one must be caught."""

    @pytest.mark.parametrize(
        ("wrong", "atom"),
        [
            # A duty figure off by four hundredths of an hour.
            (CORRECT.replace("61.33h", "61.3h"), "61.3h"),
            # A crew id with two digits transposed.
            (CORRECT.replace("C-2087", "C-2078"), "C-2078"),
            # A pairing that does not exist.
            (CORRECT.replace("P-2291", "P-2292"), "P-2292"),
            # A date shifted by one day.
            (CORRECT.replace("2026-09-15", "2026-09-14"), "2026-09-14"),
            # A limit that is not the limit.
            (CORRECT.replace("60.00h", "65.00h"), "65.00h"),
            # An excess that does not follow.
            (CORRECT.replace("1h20m", "1h50m"), "1h50m"),
            # A rule that does not exist.
            (CORRECT.replace("RULE-DUTY-02", "RULE-DUTY-08"), "RULE-DUTY-08"),
        ],
    )
    def test_one_wrong_token_is_rejected(
        self, envelopes: list[ToolEnvelope], wrong: str, atom: str
    ) -> None:
        report = Verifier().verify(wrong, envelopes)
        assert report.status is VerificationStatus.REJECTED
        caught = {item.atom for item in report.unattested}
        assert any(atom.rstrip("h") in found or found in atom for found in caught), (
            f"expected {atom!r} among {caught}"
        )

    def test_a_wrong_cost_is_rejected(self) -> None:
        tools = FakeTools()
        envelopes = [tools.find_cover_options(pairing_id="P-2291")]
        good = "Assign reserve C-3310 at INR 18,500."
        bad = "Assign reserve C-3310 at INR 18,000."
        assert Verifier().verify(good, envelopes).status is VerificationStatus.VERIFIED
        rejected = Verifier().verify(bad, envelopes)
        assert rejected.status is VerificationStatus.REJECTED
        # The currency atom may be captured with or without its INR prefix.
        # What matters is that the wrong figure was caught, not how it was spelled.
        assert any("18,000" in item.atom for item in rejected.unattested), (
            f"expected the wrong cost among {[i.atom for i in rejected.unattested]}"
        )

    def test_an_invented_station_is_rejected(
        self, envelopes: list[ToolEnvelope]
    ) -> None:
        report = Verifier().verify("The pairing operates out of XYZ.", envelopes)
        assert report.status is VerificationStatus.REJECTED
        assert "XYZ" in {item.atom for item in report.unattested}

    def test_a_real_station_still_needs_attesting(self) -> None:
        """HYD exists. Saying flights depart it is still a claim about the data."""
        tools = FakeTools()
        envelopes = [tools.get_crew_detail(crew_id="C-1042")]
        report = Verifier().verify("C-1042 is based at HYD.", envelopes)
        assert report.status is VerificationStatus.REJECTED
        assert "HYD" in {item.atom for item in report.unattested}

    def test_a_failed_lookup_attests_nothing_not_even_its_arguments(self) -> None:
        tools = FakeTools()
        envelope = tools.get_crew_detail(crew_id="C-9999")
        assert envelope.ok is False
        report = Verifier().verify("C-9999 is available.", [envelope])
        assert report.status is VerificationStatus.REJECTED
        assert "C-9999" in {item.atom for item in report.unattested}

    def test_an_invented_number_with_no_tools_at_all_is_rejected(self) -> None:
        report = Verifier().verify("There are 42 reserves at BLR.", [])
        assert report.status is VerificationStatus.REJECTED
        assert {"42", "BLR"} <= {item.atom for item in report.unattested}


class TestAttestationChannels:
    def test_a_successful_call_attests_its_own_arguments(self) -> None:
        tools = FakeTools()
        envelopes = [tools.list_reserves(on_date=date(2026, 9, 15), base="BLR")]
        report = Verifier().verify(
            "Reserves at BLR on 2026-09-15.", envelopes
        )
        assert report.status is VerificationStatus.VERIFIED, report.unattested

    def test_a_derivation_attests_its_own_operands(self) -> None:
        envelope = ToolEnvelope(
            tool="check_legality",
            ok=True,
            facts=[
                fact(
                    "duty",
                    61.33,
                    "hours",
                    derivation="51.83h prior + 9.50h added = 61.33h against a "
                    "60.00h limit",
                )
            ],
        )
        report = Verifier().verify(
            "51.83h of prior duty plus 9.50h of cover reaches 61.33h.", [envelope]
        )
        assert report.status is VerificationStatus.VERIFIED, report.unattested

    def test_a_list_length_attests_a_spelled_out_count(self) -> None:
        tools = FakeTools()
        envelopes = [tools.simulate_absence(crew_id="C-1042", from_date=date(2026, 9, 15))]
        report = Verifier().verify("All three legs are uncrewed.", envelopes)
        assert report.status is VerificationStatus.VERIFIED, report.unattested

    def test_strict_mode_reports_more_than_permissive_mode(self) -> None:
        """Strict mode drops the payload channel, so it can only be stricter."""
        tools = FakeTools()
        envelopes = [tools.get_pairing(pairing_id="P-2291")]
        text = "P-2291 runs 2 duty days on VT-DXC."
        permissive = Verifier().verify(text, envelopes)
        strict = Verifier(
            VerifierPolicy(require_fact_attestation=True)
        ).verify(text, envelopes)
        assert strict.attested_atoms <= permissive.attested_atoms

    def test_the_note_names_the_payload_only_count(
        self, envelopes: list[ToolEnvelope]
    ) -> None:
        report = Verifier().verify(CORRECT, envelopes)
        assert report.note is not None
        assert "atoms attested" in report.note


class TestAllowlist:
    def test_it_stays_small(self) -> None:
        """A permissive allowlist quietly destroys the guarantee.

        Raising this number is allowed. Raising it without adding the written
        justification in `allowlist.py` is not, and this test is the speed bump.
        """
        assert ALLOWLIST_SIZE == 4

    def test_no_real_station_is_allowlisted(self) -> None:
        from crewops.resolve.triage import STATIONS

        assert not (SAFE_UPPERCASE_TOKENS & STATIONS)

    def test_the_rule_count_is_safe_in_a_rules_sentence(self) -> None:
        report = Verifier().verify("All seven rules were checked.", [])
        assert report.status is VerificationStatus.SKIPPED

    def test_seven_outside_a_rules_sentence_still_needs_attesting(self) -> None:
        report = Verifier().verify("Seven crew are affected.", [])
        assert report.status is VerificationStatus.REJECTED

    def test_a_numbered_list_is_not_a_stream_of_unattested_integers(self) -> None:
        text = "1. Call the reserve.\n2. Confirm the report time.\n3. Notify the desk."
        report = Verifier().verify(text, [])
        assert report.status is VerificationStatus.SKIPPED, report.unattested

    def test_a_year_inside_an_attested_date_is_safe(self) -> None:
        envelope = ToolEnvelope(
            tool="get_pairing", ok=True, facts=[fact("d", "2026-09-15", "date")]
        )
        report = Verifier().verify("The 2026 schedule week.", [envelope])
        assert report.status is VerificationStatus.VERIFIED, report.unattested

    def test_a_year_with_no_attested_date_is_not_safe(self) -> None:
        report = Verifier().verify("The 2026 schedule week.", [])
        assert report.status is VerificationStatus.REJECTED


class TestReportShape:
    def test_unattested_atoms_carry_their_sentence(self) -> None:
        report = Verifier().verify(
            "The pairing is fine. C-9999 covers it at INR 1,234.", []
        )
        assert report.status is VerificationStatus.REJECTED
        for item in report.unattested:
            assert item.context
            assert item.kind in {
                "number",
                "identifier",
                "date",
                "currency",
                "rule_id",
                "station",
            }

    def test_the_report_is_capped(self) -> None:
        text = " ".join(f"C-{9000 + n}" for n in range(40))
        report = Verifier(VerifierPolicy(report_cap=5)).verify(text, [])
        assert len(report.unattested) == 5
        assert report.checked_atoms == 40

    def test_duplicate_unattested_atoms_are_reported_once(self) -> None:
        report = Verifier().verify("C-9999 and C-9999 again.", [])
        assert len(report.unattested) == 1

    def test_the_verifier_is_deterministic(
        self, envelopes: list[ToolEnvelope]
    ) -> None:
        first = Verifier().verify(CORRECT, envelopes)
        second = Verifier().verify(CORRECT, envelopes)
        assert first.model_dump() == second.model_dump()


class TestExtractorEdges:
    def test_a_currency_amount_is_one_atom_not_three(self) -> None:
        kinds = [atom.kind for atom in extract_atoms("The cost is INR 18,500.")]
        assert kinds == ["currency"]

    def test_a_tail_number_does_not_yield_a_station(self) -> None:
        atoms = extract_atoms("Aircraft VT-DXB operates it.")
        assert [atom.canon for atom in atoms] == ["VT-DXB"]

    def test_an_aircraft_type_is_an_identifier_not_a_number(self) -> None:
        atoms = extract_atoms("An A320 and an ATR72.")
        assert {atom.canon for atom in atoms} == {"A320", "ATR72"}

    def test_a_timestamp_yields_both_a_date_and_a_clock_time(self) -> None:
        kinds = {atom.kind for atom in extract_atoms("Report 2026-09-15T06:00:00Z.")}
        assert kinds == {"date", "time"}

    def test_trace_prose_is_re_scanned(self) -> None:
        envelope = ToolEnvelope(
            tool="get_duty_clocks",
            ok=True,
            trace=[TraceStep(label="Duty clock", detail="C-1042 has 20.93h of 60.00h")],
            citations=[Citation(file="duty_clocks.json", pointer="C-1042")],
        )
        report = Verifier().verify("C-1042 has used 20.93h.", [envelope])
        assert report.status is VerificationStatus.VERIFIED, report.unattested

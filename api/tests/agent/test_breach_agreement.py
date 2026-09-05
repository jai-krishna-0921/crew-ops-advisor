"""An answer may not lead with a pass when the tools computed a breach.

This is the guard for the worst failure this system can produce, and it exists
because Q20 produced it.

    "VT-DXA is delayed 90 minutes before DX401 on 16 Sep. Does the rostered
     crew breach any limit if they fly all four legs?"

`simulate_delay` returned exactly the right answer: `breach = True`, FDP 12.75h
against a 12.0h limit for four sectors. Six `check_legality` calls on the
*scheduled* pairing returned pass, because as scheduled it does pass. The model
then led with:

    "The scheduled pairing P-2203 passes all seven rules for every rostered
     crew member"

and corrected itself four sentences later. A controller reads the first line
and acts on it, so that answer dispatches a crew into an FDP breach.

Nothing already in the system catches this. The verifier attests values, and
every value in that headline is real. `verdict_guard` checks that a rules tool
*ran*, and six of them did. What was missing is a check that the answer
**agrees** with what the tools computed, which is a relation, not a value, and
`verify/CLAUDE.md` says in as many words that relations are the guards' job.

Failing here costs an abstention. The rubric is explicit that a verdict
inversion is worse.
"""

from __future__ import annotations

import pytest

from crewops.agent.guards import breach_agreement_guard
from crewops.contracts import Fact, Provenance, ToolEnvelope

BREACH_DERIVATION = (
    "RULE-FDP-01: the delayed duty runs 12.75h against a 12.0h limit for 4 "
    "sectors, so the rostered crew cannot legally complete DX404."
)


def envelope(*, tool: str = "simulate_delay", breach: bool, ok: bool = True) -> ToolEnvelope:
    return ToolEnvelope(
        tool=tool,
        ok=ok,
        args={},
        payload={"breach": breach},
        facts=[
            Fact(
                key="P-2203.2026-09-16.breach",
                label="Breach",
                value=breach,
                unit="boolean",
                derivation=BREACH_DERIVATION if breach else "",
                source="rules",
                provenance=Provenance.COMPUTED,
            )
        ],
    )


#: The headline the model actually produced. The killer.
LED_WITH_PASS = (
    "The scheduled pairing P-2203 passes all seven rules for every rostered crew member.\n"
    "But that check evaluates the pairing as scheduled. It does not model the 90 minute "
    "delay, which runs the duty to 12.75h against a 12.0h limit, so RULE-FDP-01 is breached."
)

#: The same facts, ordered so a controller acts correctly.
LED_WITH_BREACH = (
    "Yes. RULE-FDP-01 is breached: the delayed duty runs 12.75h against a 12.0h limit "
    "for 4 sectors.\n"
    "As scheduled the pairing passes all seven rules, but the 90 minute delay changes that."
)


def test_it_fires_when_the_answer_leads_with_a_pass_over_a_computed_breach() -> None:
    failure = breach_agreement_guard(LED_WITH_PASS, [envelope(breach=True)])
    assert failure is not None, (
        "A computed breach was reported as a pass in the first line. This is the "
        "verdict inversion the guard exists for."
    )
    assert failure.guard == "breach_agreement"
    assert "12.75" in failure.reason or "RULE-FDP-01" in failure.reason, (
        f"the repair prompt must name the breach it is correcting: {failure.reason!r}"
    )


def test_it_does_not_fire_when_the_answer_leads_with_the_breach() -> None:
    """The correct answer contains the word 'passes' too. Ordering is the point."""
    assert breach_agreement_guard(LED_WITH_BREACH, [envelope(breach=True)]) is None


def test_it_does_not_fire_when_nothing_breached() -> None:
    """A genuine all-clear must not be blocked."""
    draft = "The pairing passes all seven rules for every rostered crew member."
    assert breach_agreement_guard(draft, [envelope(breach=False)]) is None


def test_a_failed_envelope_establishes_no_breach() -> None:
    """Invariant 4 of the verifier, applied here: a failed call attests nothing."""
    draft = "The pairing passes all seven rules."
    assert breach_agreement_guard(draft, [envelope(breach=True, ok=False)]) is None


def test_no_envelopes_is_not_a_breach() -> None:
    assert breach_agreement_guard("The pairing passes all seven rules.", []) is None


@pytest.mark.parametrize(
    "headline",
    [
        "The pairing passes all seven rules.",
        "No rule is breached by this assignment.",
        "The crew are within all limits on both days.",
        "C-3187 is legal to operate all four legs.",
        "This assignment breaches no limit.",
    ],
)
def test_every_way_of_saying_all_clear_is_caught(headline: str) -> None:
    draft = f"{headline}\nThe delay runs the duty to 12.75h against a 12.0h limit."
    assert breach_agreement_guard(draft, [envelope(breach=True)]) is not None, (
        f"an all-clear lead slipped past the guard: {headline!r}"
    )


def test_it_runs_as_part_of_the_guard_suite() -> None:
    """A guard nothing calls is decoration."""
    from crewops.agent.guards import run_guards

    failure = run_guards(draft=LED_WITH_PASS, tier=2, envelopes=[envelope(breach=True)])
    assert failure is not None
    assert failure.guard == "breach_agreement"


# ---------------------------------------------- the shape the guard could not see

"""A LegalityReport was invisible to it.

The guard reads a `breach` fact and a payload dict's `breach` flag. Those are
what `simulate_delay` returns. The most common breach in the whole system does
not look like either: `check_legality` returns a typed `LegalityReport` whose
`overall` is `Verdict.BREACH`, with the per-rule detail in `per_day`. Neither
the fact scan nor the dict scan sees it, so `computed_breaches` returned an
empty list for the exact tool whose job is to compute breaches.

Which is how, on a scorecard run, Q24 came back with a verdict inversion:

    "Is reserve C-3305 legal to cover the full pairing P-2291, both days?"

C-3305 is the day-two breach anchor. `check_legality` said BREACH. Nothing
between that answer and the screen was looking at it.
"""

import datetime as dt  # noqa: E402

from crewops.agent.guards import computed_breaches  # noqa: E402
from crewops.contracts import (  # noqa: E402
    DayLegality,
    LegalityReport,
    RuleTrace,
    Verdict,
)


def _legality(verdict: Verdict) -> ToolEnvelope:
    trace = RuleTrace(
        rule_id="RULE-DUTY-02",
        title="Maximum 60 duty hours in any 7 consecutive days",
        verdict=verdict,
        duty_date=dt.date(2026, 9, 16),
        observed=61.5,
        limit=60.0,
        unit="hours",
        margin=-1.5,
        margin_human="1.5 hours over",
        arithmetic="50.0 prior + 11.5 projected = 61.5 against a 60.0 limit",
    )
    return ToolEnvelope(
        tool="check_legality",
        ok=True,
        args={"crew_id": "C-3305", "pairing_id": "P-2291"},
        payload=LegalityReport(
            crew_id="C-3305",
            assignment_ref="P-2291",
            assignment_kind="pairing",
            overall=verdict,
            per_day=[
                DayLegality(
                    duty_date=dt.date(2026, 9, 16),
                    verdict=verdict,
                    traces=[trace],
                )
            ],
            rules_checked=["RULE-DUTY-02"],
        ),
    )


def test_a_legality_report_breach_is_seen() -> None:
    assert computed_breaches([_legality(Verdict.BREACH)]), (
        "check_legality is the tool that computes breaches and the guard was blind to it"
    )


def test_a_legality_report_pass_is_not_a_breach() -> None:
    assert computed_breaches([_legality(Verdict.PASS)]) == []


def test_a_failed_legality_call_establishes_nothing() -> None:
    envelope = _legality(Verdict.BREACH).model_copy(update={"ok": False})
    assert computed_breaches([envelope]) == []


LEADS_THAT_INVERT = [
    "Yes, C-3305 is legal to cover the full pairing P-2291 on both days.",
    "C-3305 is legal for P-2291.",
    "C-3305 can legally cover both days of P-2291.",
    "C-3305 may cover P-2291; no rule is breached.",
    "Both days are within limits.",
]


@pytest.mark.parametrize("lead", LEADS_THAT_INVERT)
def test_an_inverted_verdict_is_refused(lead: str) -> None:
    failure = breach_agreement_guard(lead, [_legality(Verdict.BREACH)])
    assert failure is not None, lead


def test_leading_with_the_breach_is_still_accepted() -> None:
    good = (
        "C-3305 breaches RULE-DUTY-02 on 2026-09-16, 61.5 hours against a 60.0 "
        "limit. Day one is legal; the second day is not."
    )
    assert breach_agreement_guard(good, [_legality(Verdict.BREACH)]) is None


def test_a_clean_pass_is_still_accepted() -> None:
    good = "C-3310 is legal to cover P-2291 on both days. All seven rules pass."
    assert breach_agreement_guard(good, [_legality(Verdict.PASS)]) is None

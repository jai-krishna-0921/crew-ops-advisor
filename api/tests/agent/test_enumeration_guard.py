"""The same six covers, three times over.

A tier 3 answer renders the ranked options as cards, a cost comparison across
them, and the prose above both. The prose said this:

    "If you would rather not burn the reserve, the next options are day-off
     callouts C-1526, C-3983 or C-5566 at INR 24,000 each, all legal with no
     delay. The DEL-based reserve C-2210 is legal but costs INR 41,200 and
     delays the first departure by 3.0h... Cancelling all 6 legs costs
     INR 1,500,000..."

Five of the six options, with their costs, immediately above six cards
carrying the same five options with the same costs, under a bar chart
comparing the same five costs. `prompts.py` already says in as many words "do
not enumerate the ranked options and their costs", and the model does it
anyway, because listing everything it was given feels like being thorough.

Telling it again is not the fix. This is a structural property of the answer,
deterministically checkable, which is what `guards.py` is for: the same place
that already refuses an answer leading with a pass over a computed breach, or
a tier 3 verdict built only from retrieval tools.

TWO NAMED OPTIONS, NOT MORE. The recommendation itself, and one alternative,
which is what a controller asks for when the first choice is unavailable. The
offline renderer independently arrived at the same shape and names exactly
two, so the bar is set where a good answer already sits rather than at a
number chosen to make this pass.

Rejects are not options. Naming the closest exclusion is the reasoning a
controller wants and the offline path does it too, so it is not counted.
"""

from __future__ import annotations

import pytest

from crewops.agent.guards import enumeration_guard


@pytest.fixture(scope="module")
def envelopes():
    from crewops.agent.factory import load_tools

    envelope = load_tools().find_cover_options(
        pairing_id="P-2291", include_rejected=True
    )
    assert envelope.ok, envelope.error
    return [envelope]


ENUMERATED = (
    "Call out C-3310 at INR 18,500. If you would rather not burn the reserve, "
    "the next options are day-off callouts C-1526, C-3983 or C-5566 at INR "
    "24,000 each. The DEL-based reserve C-2210 is legal but costs INR 41,200."
)

DISCIPLINED = (
    "Call out Captain C-3310 (D. Reddy) for P-2291 at INR 18,500. It clears "
    "all seven rules on both duty days and the tightest margin is 0h30m under "
    "RULE-REST-04. If the reserve is wanted elsewhere, C-1526 is the next "
    "option at INR 24,000."
)

ONLY_THE_PICK = (
    "Call out Captain C-3310 for P-2291 at INR 18,500, the cheapest legal "
    "cover, clearing all seven rules on both days."
)


def test_an_enumerated_answer_is_sent_back(envelopes) -> None:
    failure = enumeration_guard(ENUMERATED, envelopes)
    assert failure is not None
    assert "C-3983" in failure.reason or "options" in failure.reason


def test_one_alternative_is_allowed(envelopes) -> None:
    """The shape the offline renderer produces has to keep passing."""
    assert enumeration_guard(DISCIPLINED, envelopes) is None


def test_naming_only_the_recommendation_is_allowed(envelopes) -> None:
    assert enumeration_guard(ONLY_THE_PICK, envelopes) is None


def test_the_offline_prose_passes_its_own_guard(envelopes) -> None:
    """Measured, not assumed: run the deterministic renderer's own output
    through the guard rather than trusting a paraphrase of it."""
    import asyncio

    from crewops.agent.advisor import Advisor
    from crewops.agent.factory import load_tools

    advisor = Advisor(load_tools())
    reply = asyncio.run(
        advisor.ask(
            "Captain C-1042 is out for P-2291, what should I do?",
            force_mode="deterministic",
        )
    )
    assert reply.kind.value == "answer", reply.text
    assert enumeration_guard(f"{reply.headline}\n{reply.text}", reply.tool_calls) is None


def test_a_reject_named_for_its_reason_does_not_count(envelopes) -> None:
    """"C-1017 was the closest exclusion" is reasoning, not enumeration."""
    draft = (
        "Call out C-3310 at INR 18,500. C-1526 is the next option. C-1017, "
        "C-2087 and C-3305 were the closest exclusions, all on RULE-REST-04."
    )
    assert enumeration_guard(draft, envelopes) is None


def test_it_does_nothing_without_a_recommendation() -> None:
    assert enumeration_guard("Anything at all, C-1, C-2, C-3, C-4.", []) is None


def test_a_short_option_list_is_never_flagged() -> None:
    """With two options on screen there is nothing to over-enumerate."""
    from crewops.agent.factory import load_tools

    envelope = load_tools().find_cover_options(pairing_id="P-2291", max_options=2)
    draft = "C-3310 at INR 18,500, or C-1526 at INR 24,000."
    assert enumeration_guard(draft, [envelope]) is None


# ------------------------------------------- verbosity is not worth an answer

"""Failing a correct answer over style is the wrong trade.

With the guard blocking, four runs of the same question gave three good
answers (121 to 181 words, at most two options named, down from 211 words and
five) and one abstention. The abstention had nothing to do with enumeration:
the policy repair spent the single repair budget, the rewrite then quoted a
figure the verifier could not attest, and there was no budget left to fix it.

A verdict inversion is dangerous and abstaining beats it. Re-listing options
that are already on screen is untidy. Trading a correct answer for a tidy
refusal inverts the scoring principle this whole system is built on, so a
style guard asks once and then accepts what it gets.
"""


def test_the_enumeration_guard_is_not_fatal(envelopes) -> None:
    failure = enumeration_guard(ENUMERATED, envelopes)
    assert failure is not None
    assert failure.fatal is False, (
        "a verbose answer is worse than a terse one and better than no answer"
    )


def test_the_safety_guards_are_still_fatal() -> None:
    """The distinction has to hold in the direction that matters."""
    import datetime as dt

    from crewops.agent.guards import breach_agreement_guard
    from crewops.contracts import (
        DayLegality,
        LegalityReport,
        RuleTrace,
        ToolEnvelope,
        Verdict,
    )

    trace = RuleTrace(
        rule_id="RULE-DUTY-02",
        title="Maximum 60 duty hours in any 7 consecutive days",
        verdict=Verdict.BREACH,
        duty_date=dt.date(2026, 9, 16),
        arithmetic="61.5 against a 60.0 limit",
    )
    envelope = ToolEnvelope(
        tool="check_legality",
        ok=True,
        args={},
        payload=LegalityReport(
            crew_id="C-3305",
            assignment_ref="P-2291",
            assignment_kind="pairing",
            overall=Verdict.BREACH,
            per_day=[
                DayLegality(
                    duty_date=dt.date(2026, 9, 16),
                    verdict=Verdict.BREACH,
                    traces=[trace],
                )
            ],
            rules_checked=["RULE-DUTY-02"],
        ),
    )
    failure = breach_agreement_guard("C-3305 is legal for P-2291.", [envelope])
    assert failure is not None
    assert failure.fatal is True

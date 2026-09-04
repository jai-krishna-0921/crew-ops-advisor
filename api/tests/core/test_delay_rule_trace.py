"""A delay that breaches FDP must say so in its rule traces, not only in prose.

Q20 asks whether a 90 minute delay pushes the rostered crew over a limit. The
answer is yes: 12.75h against a 12.0h FDP limit for four sectors.
`simulate_delay` computes that correctly and reports it as a `Fact` and in
`breach_detail`.

What it did not do was emit a `RuleTrace`. So the assembled `Reply` carried 31
PASS traces, from the `check_legality` calls on the pairing *as scheduled*, and
zero BREACH traces, for a question whose answer is a breach. Anything reading
the structured verdict rather than the prose therefore concluded the assignment
was legal. The evaluation harness does exactly that, and so does the rule trace
panel a controller reads.

The fix is the one this repository's rules demand: when the guard fires, add
the missing fact to the tool output. Never loosen the check.
"""

from __future__ import annotations

import datetime as dt

import pytest

from crewops.contracts import RuleTrace, Verdict
from crewops.domain import load_world
from crewops.tools.registry import Tools


@pytest.fixture(scope="module")
def tools() -> Tools:
    from crewops.agent.factory import default_data_dir

    return Tools(load_world(default_data_dir()))


def traces_of(payload: object) -> list[RuleTrace]:
    from crewops.agent.reply import _walk_for

    return list(_walk_for(payload, RuleTrace))


def test_a_breaching_delay_emits_a_breach_rule_trace(tools: Tools) -> None:
    """Q20, exactly: VT-DXA delayed 90 minutes before DX401 on 16 Sep."""
    envelope = tools.simulate_delay(
        flight_number="DX401",
        delay_minutes=90,
        on_date=dt.date(2026, 9, 16),
        mode="pre_departure",
    )
    assert envelope.ok, envelope.error

    fdp = [t for t in traces_of(envelope.payload) if t.rule_id == "RULE-FDP-01"]
    assert fdp, (
        "simulate_delay computed a breach but emitted no RULE-FDP-01 rule trace, "
        "so the assembled Reply reports only the passes from other tools."
    )
    trace = fdp[0]
    assert trace.verdict is Verdict.BREACH
    assert trace.observed == 12.75
    assert trace.limit == 12.0
    assert trace.duty_date == dt.date(2026, 9, 16)
    assert "12.75" in trace.arithmetic and "12.0" in trace.arithmetic


def test_a_delay_that_stays_legal_emits_a_pass_not_silence(tools: Tools) -> None:
    """The trace records the evaluation either way.

    A rule that was checked and passed is evidence. Emitting nothing would
    leave a controller unable to tell "checked, fine" from "never checked".
    """
    envelope = tools.simulate_delay(
        flight_number="DX401",
        delay_minutes=10,
        on_date=dt.date(2026, 9, 16),
        mode="pre_departure",
    )
    assert envelope.ok, envelope.error
    fdp = [t for t in traces_of(envelope.payload) if t.rule_id == "RULE-FDP-01"]
    assert fdp, "a delay that does not breach still evaluated RULE-FDP-01"
    assert fdp[0].verdict is Verdict.PASS

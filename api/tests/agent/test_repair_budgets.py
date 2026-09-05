"""A style rewrite must not spend the budget grounding needs.

The enumeration guard works: the prose stopped reciting the option cards. The
scorecard then moved the wrong way, agent abstentions 4 to 8, and the mechanism
is visible in `_guard_outcome`. Both repairs came out of one counter, so a turn
that was asked to stop enumerating had used its only pass, and the rewrite
quoting one unattestable figure had nothing left to correct it with. The answer
was refused for a reason unrelated to the figure.

The two are not the same kind of failure and should not share a purse.

  GROUNDING   a figure has nothing behind it. One pass, then decline, and
              that ceiling is deliberate: it is the "never two, never a silent
              pass through" rule and it is what stops a turn negotiating with
              the verifier until something sticks.

  STYLE       the answer is correct and says too much. One pass, then accept
              it as it is. It can never cause a refusal, so it can never loop.

Separating them restores the grounding pass without loosening it: a turn still
gets exactly one correction for an unattested figure, whether or not a guard
asked for a rewrite first.
"""

from __future__ import annotations

import datetime as dt

from crewops.agent.config import AgentConfig
from crewops.agent.graph import _guard_outcome
from crewops.agent.guards import GuardFailure
from crewops.contracts import AbstentionReason

CONFIG = AgentConfig(max_repairs=1)

STYLE = GuardFailure(
    guard="enumeration",
    reason="Names five of the ranked options.",
    required_tools=(),
    abstention_reason=AbstentionReason.UNDERSPECIFIED,
    fatal=False,
)

SAFETY = GuardFailure(
    guard="breach_agreement",
    reason="Leads with a pass over a computed breach.",
    required_tools=("check_legality",),
    abstention_reason=AbstentionReason.CONFLICTING_DATA,
    fatal=True,
)


def _state(**changes: object) -> dict:
    return {"timings": {}, "started_at": 0.0, **changes}


def test_a_style_rewrite_leaves_the_grounding_pass_alone() -> None:
    """The whole defect, in one assertion."""
    outcome = _guard_outcome(_state(), STYLE, 0, 0.0, CONFIG)
    assert outcome.get("pending_guard") is not None
    assert outcome.get("repairs") is None, (
        "a style rewrite must not consume the grounding budget"
    )


def test_a_style_guard_asks_once(monkeypatch) -> None:
    """It may not loop either. Asked and answered, it accepts what it gets."""
    spent = _state(style_repairs=1)
    outcome = _guard_outcome(spent, STYLE, 0, 0.0, CONFIG)
    assert outcome.get("pending_guard") is None
    assert outcome.get("abstention") is None, "verbosity is never a refusal"


def test_a_safety_guard_still_spends_the_one_budget() -> None:
    outcome = _guard_outcome(_state(), SAFETY, 0, 0.0, CONFIG)
    assert outcome.get("pending_guard") is not None


def test_a_safety_guard_out_of_budget_still_declines() -> None:
    """The ceiling that matters is untouched."""
    outcome = _guard_outcome(_state(), SAFETY, 1, 0.0, CONFIG)
    assert outcome.get("pending_guard") is None
    abstention = outcome.get("abstention")
    assert abstention is not None
    assert abstention.reason is AbstentionReason.CONFLICTING_DATA


def test_the_two_counters_are_independent() -> None:
    """A turn that has already been asked to stop enumerating still gets its
    grounding correction, which is the abstention this recovers."""
    outcome = _guard_outcome(_state(style_repairs=1), SAFETY, 0, 0.0, CONFIG)
    assert outcome.get("pending_guard") is not None


def test_the_state_declares_the_counter() -> None:
    from crewops.agent.state import TurnState, new_turn_state

    assert "style_repairs" in TurnState.__annotations__
    fresh = new_turn_state(
        question="q",
        thread_id="t",
        turn_id="u",
        asked_at=dt.datetime(2026, 9, 14, 18, 0, 0),
        as_of=None,
        started_at=0.0,
    )
    assert fresh["style_repairs"] == 0

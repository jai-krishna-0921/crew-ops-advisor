"""RULE-REST-04 as a tool, not as arithmetic the model is trusted to do.

Q23 asks "a crew is released at 15:30Z on 16 Sep, what is the earliest they may
report next". The answer is 2026-09-17T03:30:00Z: twelve hours of rest.

`LegalityEngine.earliest_next_report` has computed that all along. Nothing
exposed it as a tool, so the agent had nothing to call. It reached for
`explain_rule`, `get_world_summary` and `get_watchlist`, all retrieval, and
`tier_guard` refused the answer because retrieval establishes what is, not what
follows.

That refusal was correct. The alternative was the model adding twelve hours to
a timestamp itself, which is exactly the arithmetic this system exists to keep
out of a model. The gap was a missing tool, and the guard is what surfaced it.
"""

from __future__ import annotations

import datetime as dt

import pytest

from crewops.domain import load_world
from crewops.tools.registry import Tools


@pytest.fixture(scope="module")
def tools() -> Tools:
    from crewops.agent.factory import default_data_dir

    return Tools(load_world(default_data_dir()))


def test_the_earliest_report_after_a_release(tools: Tools) -> None:
    """Q23, exactly."""
    envelope = tools.earliest_report(released_at="2026-09-16T15:30:00Z")
    assert envelope.ok, envelope.error
    assert isinstance(envelope.payload, dict)
    assert envelope.payload["earliest_report"] == dt.datetime(2026, 9, 17, 3, 30)
    assert envelope.payload["rest_hours"] == 12.0
    assert envelope.payload["rule_id"] == "RULE-REST-04"


def test_it_carries_the_answer_as_an_attestable_fact(tools: Tools) -> None:
    """A figure the answer states must be on a Fact, or the verifier rejects it."""
    envelope = tools.earliest_report(released_at="2026-09-16T15:30:00Z")
    rendered = " ".join(f"{f.key} {f.value} {f.derivation or ''}" for f in envelope.facts)
    assert "03:30" in rendered or "2026-09-17T03:30" in rendered, (
        f"the computed time is not attestable from the facts: {rendered}"
    )


def test_it_shows_its_arithmetic(tools: Tools) -> None:
    """Explainability is mandatory, and a bare timestamp explains nothing."""
    envelope = tools.earliest_report(released_at="2026-09-16T15:30:00Z")
    from crewops.agent.reply import _walk_for
    from crewops.contracts import RuleTrace

    traces = list(_walk_for(envelope.payload, RuleTrace))
    assert traces, "no rule trace, so a controller cannot challenge the number"
    assert traces[0].rule_id == "RULE-REST-04"
    assert "12" in traces[0].arithmetic


def test_it_accepts_a_naive_timestamp_too(tools: Tools) -> None:
    """The dataset is entirely UTC and a controller will not always type the Z."""
    with_z = tools.earliest_report(released_at="2026-09-16T15:30:00Z")
    without = tools.earliest_report(released_at="2026-09-16T15:30:00")
    assert without.ok, without.error
    assert without.payload["earliest_report"] == with_z.payload["earliest_report"]


def test_it_can_resolve_the_release_from_a_crew_member(tools: Tools) -> None:
    """The other half of the question shape: "when can C-1042 fly again"."""
    envelope = tools.earliest_report(crew_id="C-1042")
    assert envelope.ok, envelope.error
    assert envelope.payload["earliest_report"] is not None


def test_an_unparseable_timestamp_fails_loudly(tools: Tools) -> None:
    envelope = tools.earliest_report(released_at="tomorrow morning")
    assert not envelope.ok
    assert "tomorrow morning" in (envelope.error or "")


def test_naming_neither_a_time_nor_a_crew_member_is_an_error(tools: Tools) -> None:
    envelope = tools.earliest_report()
    assert not envelope.ok


def test_it_is_not_classified_as_retrieval(tools: Tools) -> None:
    """It computes a consequence, so a Tier 2 answer may rest on it alone."""
    from crewops.contracts.tools import RETRIEVAL_ONLY, TOOL_NAMES

    assert "earliest_report" in TOOL_NAMES
    assert "earliest_report" not in RETRIEVAL_ONLY


def test_it_counts_as_having_evaluated_the_rules(tools: Tools) -> None:
    """Otherwise the guards refuse the answer it just computed.

    "They may report at 03:30Z" is a verdict, and this tool is what produced
    it. Classifying the tool as neither legality nor consequence bearing left
    `verdict_guard` unable to see that a rules engine had run, so it rejected a
    correct, fully grounded answer.
    """
    from crewops.contracts.tools import REQUIRED_FOR

    assert "earliest_report" in REQUIRED_FOR["legality_claim"]
    assert "earliest_report" in REQUIRED_FOR["consequence_claim"]

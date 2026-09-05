"""Showing your rejects must not be graded as claiming a breach.

Q37 asks for the cheapest legal way to cover the VT-DXF First Officer on 20
Sep. The agent answered it correctly: C-3316 on a reserve callout at INR
18,500, rank 1, which is the shipped key exactly. The scorecard recorded
`primary_recall 1.0`, `full_recall 1.0`, `missed []`, `grounded true`, and then
graded it **wrong** and flagged it **unsafe**:

    verdict inverted: key says legal=True, answer asserts legal=False

Nothing in the answer said that. `produced_verdict` read `reply.rule_traces`,
and `collect_rule_traces` walks a payload recursively, so it had picked up the
breaching `RuleTrace` of every one of the twenty-one *rejected* candidates. One
BREACH anywhere made the whole reply "asserts legal=False".

So the grader punished the answer for being thorough. `find_cover_options` is
called with `include_rejected=True` on purpose: a controller trusts a system
that shows its rejects, because it proves the search was real. Grading that as
an operational error pushes in exactly the wrong direction, towards answers
that hide their working.

`expected_verdict` was already hardened against this and says so in its own
docstring: read only a top level `legal` or `breach` field, "so that a Tier 3
answer carrying both legal options and rejected candidates is never mistaken
for a verdict question". The produced side needed the same rule. When a cover
search ran, the verdict of the answer is whether a legal option exists, which
the `Recommendation` states directly. The rejected candidates' traces are
evidence about other people, not a verdict about this assignment.

This is a grader defect, not an agent defect. The production `breach_agreement`
guard reads the typed `.breach` Fact channel and the payload flag, neither of
which a rejected candidate sets, so it was never fooled the same way.
"""

from __future__ import annotations

import datetime as dt

import pytest

from crewops.agent.reply import collect_rule_traces
from crewops.contracts import Verdict
from crewops.contracts.evidence import VerificationReport, VerificationStatus
from crewops.contracts.reply import AnswerMode, Reply, ReplyKind
from crewops.domain import load_world
from crewops.eval.grading import produced_verdict
from crewops.tools.registry import Tools

ASKED = dt.datetime(2026, 9, 14, 18, 0, 0)


def _reply(**fields: object) -> Reply:
    return Reply(
        thread_id="t",
        turn_id="u",
        question="q",
        asked_at=ASKED,
        kind=ReplyKind.ANSWER,
        mode=AnswerMode.AGENT,
        verification=VerificationReport(status=VerificationStatus.VERIFIED),
        **fields,  # type: ignore[arg-type]
    )


@pytest.fixture(scope="module")
def q37_envelope():
    """The real Q37 cover search: five legal options, twenty-one rejections."""
    tools = Tools(load_world())
    envelope = tools.find_cover_options(
        registration="VT-DXF",
        on_date=dt.date(2026, 9, 20),
        role="First Officer",
        include_rejected=True,
    )
    assert envelope.ok, envelope.error
    return envelope


def test_the_search_really_does_carry_breaching_traces(q37_envelope) -> None:
    """The premise of the bug. If this stops holding, the rest is vacuous."""
    traces = collect_rule_traces([q37_envelope])
    assert any(trace.verdict is Verdict.BREACH for trace in traces), (
        "no rejected candidate carried a breach, so this test proves nothing"
    )
    assert q37_envelope.payload.options, "the search found no legal option"


def test_a_search_that_found_a_legal_option_reads_as_legal(q37_envelope) -> None:
    reply = _reply(
        headline="Cheapest legal cover is C-3316 on a reserve callout at INR 18,500.",
        rule_traces=collect_rule_traces([q37_envelope]),
        recommendation=q37_envelope.payload,
    )
    assert produced_verdict(reply) is True


def test_a_search_that_found_nothing_reads_as_not_legal(q37_envelope) -> None:
    empty = q37_envelope.payload.model_copy(update={"options": []})
    reply = _reply(
        headline="No legal option was found.",
        rule_traces=collect_rule_traces([q37_envelope]),
        recommendation=empty,
    )
    assert produced_verdict(reply) is False


def test_a_breach_with_no_cover_search_still_reads_as_not_legal(q37_envelope) -> None:
    """The legality question shape is untouched: no recommendation, so the
    rule traces are the verdict, which is what they are for."""
    reply = _reply(
        headline="C-2087 breaches RULE-DUTY-02 on 2026-09-16.",
        rule_traces=collect_rule_traces([q37_envelope]),
    )
    assert produced_verdict(reply) is False

"""Assemble the one `Reply` every interface renders.

Nothing downstream of a `Reply` may compute a figure, so a `Reply` has to be
self contained: the facts, the rule traces, the impact report and the
recommendation are lifted straight off the envelopes rather than re-derived.

This module is deterministic and does not import a model client.
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Sequence
from datetime import datetime
from typing import Any, Final

from crewops.agent.tabulate import tabulate
from crewops.contracts import (
    Abstention,
    AnswerMode,
    Citation,
    Confidence,
    Fact,
    ImpactReport,
    Recommendation,
    Reply,
    ReplyKind,
    RuleTrace,
    Table,
    Tier,
    Timings,
    ToolEnvelope,
    TraceStep,
    VerificationReport,
    VerificationStatus,
)

__all__ = ["build_reply", "collect_facts", "collect_rule_traces", "headline_of"]


def build_reply(
    state: dict[str, Any],
    *,
    question: str,
    thread_id: str,
    turn_id: str,
    asked_at: datetime,
    total_ms: int,
    mode: AnswerMode = AnswerMode.AGENT,
) -> Reply:
    """Turn a finished turn's state into the settled answer."""
    envelopes: list[ToolEnvelope] = list(state.get("envelopes") or [])
    abstention: Abstention | None = state.get("abstention")
    verification: VerificationReport = state.get("verification") or VerificationReport(
        status=VerificationStatus.SKIPPED,
        note="The turn produced no answer to ground.",
    )
    draft = str(state.get("draft") or "")
    tier_value = state.get("tier")
    tier: Tier | None = tier_value if tier_value in (1, 2, 3) else None
    timings_raw: dict[str, int] = dict(state.get("timings") or {})

    kind = ReplyKind.ABSTAIN if abstention is not None else ReplyKind.ANSWER
    text = abstention.message if abstention is not None else draft

    impact = _first_payload(envelopes, ImpactReport)
    recommendation = _first_payload(envelopes, Recommendation)
    headline = headline_of(text, abstention=abstention)

    return Reply(
        thread_id=thread_id,
        turn_id=turn_id,
        question=question,
        asked_at=asked_at,
        kind=kind,
        mode=mode,
        tier=tier,
        headline=headline,
        text=_body_after(text, headline),
        facts=collect_facts(envelopes),
        traces=collect_traces(envelopes),
        rule_traces=collect_rule_traces(envelopes),
        tables=collect_tables(envelopes),
        impact=impact,
        recommendation=recommendation,
        citations=collect_citations(envelopes),
        tool_calls=envelopes,
        abstention=abstention,
        confidence=_confidence(verification, abstention),
        verification=verification,
        timings=Timings(
            total_ms=total_ms,
            plan_ms=timings_raw.get("plan_ms", 0),
            tools_ms=timings_raw.get("tools_ms", 0),
            verify_ms=timings_raw.get("verify_ms", 0),
            model_calls=int(state.get("model_calls", 0)),
            tool_calls=len(envelopes),
        ),
        caveats=_caveats(envelopes, verification),
        follow_ups=_follow_ups(envelopes, abstention),
    )


#: Longest headline a controller should have to read before acting.
_HEADLINE_MAX: Final = 200

#: Shortest slice worth calling a headline. Below this the cut has almost
#: certainly landed on an abbreviation rather than a sentence end.
_HEADLINE_MIN: Final = 40

#: A sentence end that is not somebody's initial.
#:
#: Crew in this dataset are written as an initial and a surname, `A. Nair`, so
#: a plain split on ". " truncated
#: `C-1042 (A. Nair, Captain, BLR, A320) has accrued...` to `C-1042 (A`. The
#: lookbehind refuses a full stop that follows a single capital, which is what
#: an initial looks like and what the end of a real sentence rarely does.
_SENTENCE_END: Final = re.compile(r"(?<![A-Z])[.!?](?=\s|$)")


def _first_sentence(text: str, *, minimum: int = _HEADLINE_MIN) -> str:
    """The leading sentence, or a word-boundary slice when there is not one.

    `minimum` guards against cutting on an abbreviation in a long answer, where
    a very short leading "sentence" is nearly always a mistake. An abstention
    passes 0, because its first sentence is the refusal itself ("I cannot
    answer that reliably") and is meant to be short.
    """
    match = _SENTENCE_END.search(text, minimum)
    if match and match.end() <= _HEADLINE_MAX:
        return text[: match.start()].strip()
    if len(text) <= _HEADLINE_MAX:
        return text.strip()
    # No usable sentence end in budget. Cut on a word boundary rather than
    # mid-token, and stay a slice: the headline is never invented.
    head, _, _ = text[:_HEADLINE_MAX].rpartition(" ")
    return (head or text[:_HEADLINE_MAX]).strip()


def headline_of(text: str, *, abstention: Abstention | None = None) -> str | None:
    """The first line a controller reads. Never invented, always a slice."""
    if abstention is not None:
        return _first_sentence(abstention.message.strip(), minimum=0) or None
    stripped = text.strip()
    if not stripped:
        return None
    first = stripped.split("\n", 1)[0].strip().lstrip("#").strip()
    if len(first) > _HEADLINE_MAX:
        return _first_sentence(first) or None
    return first or None


def _body_after(text: str, headline: str | None) -> str:
    """The answer with its own headline removed.

    `headline_of` takes the first line rather than inventing one, so leaving
    that line in the body makes every interface print it twice, once large and
    once again immediately underneath.

    Two cases, and the difference matters. When the headline is the *whole*
    answer, the body is empty and the interface renders one line. When the
    headline is a *slice* of a longer paragraph, the body keeps everything,
    because dropping it would take every figure after the first full stop with
    it.
    """
    if not headline:
        return text
    stripped = text.strip()
    first, sep, rest = stripped.partition("\n")
    if not sep:
        return "" if stripped.lstrip("#").strip() == headline else text
    if first.strip().lstrip("#").strip() != headline:
        return text
    return rest.strip() or ""


def collect_facts(envelopes: Sequence[ToolEnvelope]) -> list[Fact]:
    """Every fact from every successful call, deduplicated by key."""
    seen: dict[str, Fact] = {}
    for envelope in envelopes:
        if not envelope.ok:
            continue
        for fact in envelope.facts:
            seen.setdefault(fact.key, fact)
        for trace in _rule_traces_in(envelope):
            for fact in trace.inputs:
                seen.setdefault(fact.key, fact)
    return list(seen.values())


def collect_traces(envelopes: Sequence[ToolEnvelope]) -> list[TraceStep]:
    steps: list[TraceStep] = []
    for envelope in envelopes:
        if envelope.ok:
            steps.extend(envelope.trace)
    return steps


def collect_rule_traces(envelopes: Sequence[ToolEnvelope]) -> list[RuleTrace]:
    """Every rule evaluation the turn touched, in the order it happened."""
    traces: list[RuleTrace] = []
    seen: set[tuple[str, str, str]] = set()
    for envelope in envelopes:
        if not envelope.ok:
            continue
        for trace in _rule_traces_in(envelope):
            key = (trace.rule_id, str(trace.duty_date), trace.arithmetic)
            if key in seen:
                continue
            seen.add(key)
            traces.append(trace)
    return traces


def collect_citations(envelopes: Sequence[ToolEnvelope]) -> list[Citation]:
    seen: dict[tuple[str, str], Citation] = {}
    for envelope in envelopes:
        if not envelope.ok:
            continue
        for citation in envelope.citations:
            seen.setdefault((citation.file, citation.pointer), citation)
    return list(seen.values())


def collect_tables(envelopes: Sequence[ToolEnvelope]) -> list[Table]:
    """Every result set in this turn, as a table.

    A payload that IS a table passes through. A payload that is a result set of
    some other shape (reserves, crew, flights, a roster, expiring certificates)
    is projected into one by `tabulate`, which copies fields and computes
    nothing. Before that projection existed these reached the screen as prose,
    and a twelve row result set rendered as a ninety word sentence.
    """
    tables: list[Table] = []
    for envelope in envelopes:
        if not envelope.ok:
            continue
        if isinstance(envelope.payload, Table):
            tables.append(envelope.payload)
            continue
        projected = tabulate(envelope.payload)
        if projected is not None:
            tables.append(projected)
    return tables


def _rule_traces_in(envelope: ToolEnvelope) -> Iterable[RuleTrace]:
    """Walk a payload for RuleTrace objects, however deeply they are nested."""
    yield from _walk_for(envelope.payload, RuleTrace)


def _walk_for(node: object, wanted: type[Any], depth: int = 0) -> Iterable[Any]:
    if depth > 8 or node is None:
        return
    if isinstance(node, wanted):
        yield node
        return
    if isinstance(node, str | bytes | int | float | bool):
        return
    if isinstance(node, dict):
        for value in node.values():
            yield from _walk_for(value, wanted, depth + 1)
        return
    if isinstance(node, list | tuple | set):
        for item in node:
            yield from _walk_for(item, wanted, depth + 1)
        return
    fields = getattr(node, "model_fields", None)
    if fields:
        for name in fields:
            yield from _walk_for(getattr(node, name, None), wanted, depth + 1)


def _first_payload(envelopes: Sequence[ToolEnvelope], wanted: type[Any]) -> Any:
    for envelope in envelopes:
        if envelope.ok and isinstance(envelope.payload, wanted):
            return envelope.payload
    return None


def _confidence(
    verification: VerificationReport, abstention: Abstention | None
) -> Confidence:
    if abstention is not None:
        return Confidence.LOW
    if verification.status is VerificationStatus.REPAIRED:
        return Confidence.MEDIUM
    if verification.status is VerificationStatus.SKIPPED:
        return Confidence.MEDIUM
    return Confidence.HIGH


def _caveats(
    envelopes: Sequence[ToolEnvelope], verification: VerificationReport
) -> list[str]:
    """Limits of this specific answer, stated up front rather than discovered."""
    caveats: list[str] = []
    failed = [envelope.tool for envelope in envelopes if not envelope.ok]
    if failed:
        caveats.append(
            "These lookups failed and their results are not in this answer: "
            + ", ".join(sorted(set(failed)))
            + ". A failed lookup is not a finding of 'none'."
        )
    if any(envelope.truncated for envelope in envelopes):
        caveats.append(
            "A tool result was capped for the prompt budget. The full result is "
            "in the evidence drawer."
        )
    if verification.status is VerificationStatus.REPAIRED:
        caveats.append(
            "This answer needed one correction pass before every figure in it "
            "could be traced to a tool result."
        )
    return caveats


def _follow_ups(
    envelopes: Sequence[ToolEnvelope], abstention: Abstention | None
) -> list[str]:
    if abstention is not None:
        return abstention.suggestions[:3]
    tools_used = {envelope.tool for envelope in envelopes if envelope.ok}
    suggestions: list[str] = []
    if "simulate_absence" in tools_used and "find_cover_options" not in tools_used:
        suggestions.append("What are my ranked options to cover this")
    if "find_cover_options" in tools_used and "draft_notification" not in tools_used:
        suggestions.append("Draft the callout notification for the top option")
    if "check_legality" in tools_used:
        suggestions.append("Show the full rule trace for every day")
    return suggestions[:3]

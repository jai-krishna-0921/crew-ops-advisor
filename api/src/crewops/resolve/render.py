"""Deterministic answer templates for the offline path.

Every line these templates emit is assembled from `Fact` values and from prose
that deterministic code authored (`RuleTrace.arithmetic`, `ImpactReport.
explanation`, `CoverOption.reasoning`). Nothing here composes a new figure, and
nothing here does arithmetic, so the output passes the same verifier the agent
path is held to. That is the point: it proves the facts come from the tools.

No em dashes, here or in anything these functions produce.
"""

from __future__ import annotations

from collections.abc import Sequence

from crewops.contracts import (
    CoverOption,
    Fact,
    ImpactReport,
    LegalityReport,
    Recommendation,
    RuleTrace,
    ToolEnvelope,
    Verdict,
    Watchlist,
)

__all__ = ["render"]

_VERDICT_WORD = {
    Verdict.PASS: "legal",
    Verdict.BREACH: "a breach",
    Verdict.NOT_APPLICABLE: "not applicable",
    Verdict.INSUFFICIENT_DATA: "undetermined, the data was insufficient",
}


def render(template: str, envelopes: Sequence[ToolEnvelope], question: str) -> str:
    """Render the answer for one matched intent."""
    usable = [envelope for envelope in envelopes if envelope.ok]
    if not usable:
        return ""
    renderer = {
        "legality": _render_legality,
        "impact": _render_impact,
        "recommendation": _render_recommendation,
        "notification": _render_notification,
        "watchlist": _render_watchlist,
    }.get(template, _render_generic)
    body = renderer(usable, question)
    return body.strip()


# --------------------------------------------------------------------- tier 2


def _render_legality(envelopes: Sequence[ToolEnvelope], _question: str) -> str:
    report = _payload(envelopes, LegalityReport)
    if report is None:
        return _render_generic(envelopes, _question)

    lines: list[str] = []
    verdict = _VERDICT_WORD.get(report.overall, str(report.overall.value))
    lines.append(
        f"{report.crew_id} on {report.assignment_ref}: {verdict} "
        f"({report.overall.value})."
    )

    for day in sorted(report.per_day, key=lambda item: item.duty_date):
        word = _VERDICT_WORD.get(day.verdict, day.verdict.value)
        lines.append(f"\n{day.duty_date}: {word}.")
        for trace in day.traces:
            if trace.verdict in (Verdict.PASS, Verdict.NOT_APPLICABLE) and not trace.arithmetic:
                continue
            lines.append(f"  {_trace_line(trace)}")

    if report.overall is Verdict.BREACH and len(report.per_day) > 1:
        lines.append(
            "\nA candidate has to be legal on every day of the assignment. "
            "Passing one day and breaching another is not a legal option."
        )
    if report.rules_checked:
        lines.append("\nRules checked: " + ", ".join(report.rules_checked) + ".")
    return "\n".join(lines)


def _render_impact(envelopes: Sequence[ToolEnvelope], question: str) -> str:
    report = _payload(envelopes, ImpactReport)
    if report is None:
        return _render_generic(envelopes, question)

    lines = [report.explanation.strip()] if report.explanation else []

    if report.uncrewed_flights:
        legs = ", ".join(flight.flight_no for flight in report.uncrewed_flights)
        lines.append(f"\nUncrewed: {legs}.")
    if report.pairings_broken:
        lines.append("Pairings broken: " + ", ".join(report.pairings_broken) + ".")
    for fact in report.facts:
        if fact.key.endswith("passengers_affected") or fact.unit == "count":
            lines.append(f"{fact.label}: {fact.rendered()}.")
            break

    if report.downstream_risks:
        lines.append("\nDownstream:")
        for risk in report.downstream_risks:
            subject = risk.crew_id or risk.flight_no or risk.pairing_id or "unnamed"
            rule = f" [{risk.rule_id}]" if risk.rule_id else ""
            lines.append(f"  {subject}{rule}: {risk.detail} ({risk.severity.value})")

    return "\n".join(lines)


# --------------------------------------------------------------------- tier 3


def _render_recommendation(envelopes: Sequence[ToolEnvelope], question: str) -> str:
    recommendation = _payload(envelopes, Recommendation)
    if recommendation is None:
        return _render_generic(envelopes, question)

    lines: list[str] = []
    if recommendation.situation:
        lines.append(recommendation.situation.strip())

    if not recommendation.options:
        lines.append(
            "\nNo legal option was found. Every candidate the search reached was "
            "excluded by a rule."
        )
    else:
        lines.append("\nRanked options:")
        for option in recommendation.options:
            lines.append(_option_line(option))

    if recommendation.rejected:
        lines.append("\nRejected, with the rule that excluded each:")
        for option in recommendation.rejected[:8]:
            breach = option.legality.breaches
            why = breach[0].rule_id if breach else "no legal path"
            lines.append(f"  {option.crew_id} ({option.crew_rank}): {why}")

    if recommendation.ranking_basis:
        lines.append(f"\nRanked by: {recommendation.ranking_basis}")
    if recommendation.candidates_evaluated:
        lines.append(f"Candidates evaluated: {recommendation.candidates_evaluated}.")
    if recommendation.notification_draft:
        lines.append("\nDraft notification:\n" + recommendation.notification_draft)
    return "\n".join(lines)


def _option_line(option: CoverOption) -> str:
    parts = [
        f"  {option.rank}. {option.action}",
        f"     {option.crew_rank}, base {option.crew_base}, {option.coverage_summary}",
        f"     Cost INR {option.cost.total_inr:,.0f}",
    ]
    for line in option.cost.line_items:
        parts.append(f"       {line.label}: INR {line.amount_inr:,.0f} ({line.basis})")
    if option.delay_minutes:
        parts.append(f"     Delay introduced: {option.delay_minutes} minutes")
    if option.reasoning:
        parts.append(f"     {option.reasoning}")
    for tradeoff in option.tradeoffs:
        parts.append(f"     Trade-off: {tradeoff}")
    return "\n".join(parts)


def _render_notification(envelopes: Sequence[ToolEnvelope], question: str) -> str:
    for envelope in envelopes:
        if envelope.tool != "draft_notification":
            continue
        if isinstance(envelope.payload, str):
            return envelope.payload
        for fact in envelope.facts:
            if fact.unit == "text" and isinstance(fact.value, str):
                return fact.value
        text = getattr(envelope.payload, "text", None)
        if isinstance(text, str):
            return text
    return _render_generic(envelopes, question)


def _render_watchlist(envelopes: Sequence[ToolEnvelope], question: str) -> str:
    watchlist = _payload(envelopes, Watchlist)
    if watchlist is None:
        return _render_generic(envelopes, question)
    lines = [watchlist.headline.strip()] if watchlist.headline else []
    lines.append(f"\nWatchlist for {watchlist.for_date}:")
    for alert in watchlist.alerts:
        subject = alert.crew_id or alert.flight_no or alert.pairing_id or ""
        rule = f" [{alert.rule_id}]" if alert.rule_id else ""
        lines.append(
            f"  {alert.severity.value.upper()}: {alert.title}"
            f"{f' ({subject})' if subject else ''}{rule}"
        )
        lines.append(f"    {alert.detail}")
    if watchlist.scanned:
        scanned = ", ".join(f"{value} {key}" for key, value in watchlist.scanned.items())
        lines.append(f"\nScanned: {scanned}.")
    return "\n".join(lines)


# --------------------------------------------------------------------- tier 1


def _render_generic(envelopes: Sequence[ToolEnvelope], _question: str) -> str:
    """Facts and traces, in the order the tools produced them.

    Plain, but every line is a `Fact` the tool emitted, which is exactly what
    the offline path is meant to demonstrate.
    """
    lines: list[str] = []
    for envelope in envelopes:
        for step in envelope.trace:
            lines.append(f"{step.label}: {step.detail}")
        for fact in envelope.facts:
            lines.append(_fact_line(fact))
        rows = _rows_of(envelope)
        if rows:
            lines.append(rows)
    return "\n".join(line for line in lines if line)


def _fact_line(fact: Fact) -> str:
    unit = "" if fact.unit in ("text", "count", "boolean") else f" {fact.unit}"
    base = f"{fact.label}: {fact.rendered()}{unit}"
    if fact.derivation:
        return f"{base}  [{fact.derivation}]"
    return base


def _rows_of(envelope: ToolEnvelope) -> str:
    payload = envelope.payload
    if not isinstance(payload, list) or not payload:
        return ""
    lines = [f"\n{len(payload)} results:"]
    for item in payload[:25]:
        if hasattr(item, "model_dump"):
            fields = item.model_dump(mode="json")
            lines.append("  " + ", ".join(f"{k}={v}" for k, v in fields.items() if v is not None))
        else:
            lines.append(f"  {item}")
    if len(payload) > 25:
        lines.append(f"  ... and {len(payload) - 25} more")
    return "\n".join(lines)


def _trace_line(trace: RuleTrace) -> str:
    word = _VERDICT_WORD.get(trace.verdict, trace.verdict.value)
    parts = [f"{trace.rule_id} {word}"]
    if trace.arithmetic:
        parts.append(trace.arithmetic)
    if trace.margin_human:
        parts.append(trace.margin_human)
    return ": ".join(parts[:2]) + (f" ({parts[2]})" if len(parts) > 2 else "")


def _payload[T](envelopes: Sequence[ToolEnvelope], wanted: type[T]) -> T | None:
    for envelope in envelopes:
        if isinstance(envelope.payload, wanted):
            return envelope.payload
    return None

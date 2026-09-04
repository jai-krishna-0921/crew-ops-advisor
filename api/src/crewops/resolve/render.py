"""Deterministic answer templates for the offline path.

Every line these templates emit is assembled from `Fact` values and from prose
that deterministic code authored (`RuleTrace.arithmetic`, `ImpactReport.
explanation`, `CoverOption.reasoning`). Nothing here composes a new figure, and
nothing here does arithmetic, so the output passes the same verifier the agent
path is held to. That is the point: it proves the facts come from the tools.

No em dashes, here or in anything these functions produce.
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from typing import Any

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
from crewops.tools import payloads as P  # noqa: N812  short alias, mirrors tools/registry.py

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
        "reserves": _render_reserves,
        "clocks": _render_clocks,
        "certifications": _render_certifications,
        "pairing": _render_pairing,
        "crew": _render_crew_detail,
        "crew_list": _render_crew_list,
        "flights": _render_flights,
        "roster": _render_roster,
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
#
# Every function below renders the members of a collection, not just the
# count. A controller scanning at 6am needs the identifiers on screen, and so
# does anything grading the answer: the count alone repeats a `Fact` that is
# already attested, but a crew id or a flight number sitting only inside a
# payload is invisible until a line here prints it. Printing a payload field
# verbatim is always safe: the verifier's payload channel walks the same
# `envelope.payload` these functions read, so nothing rendered from it can
# come back unattested. What is not safe, and what these functions avoid, is
# echoing a `Fact.label` wholesale: a label is decorative prose the verifier
# never scans, so a label that happens to spell out "RULE-DUTY-02" or "28
# days" leaks an unattested rule id or number into the draft. Every number
# below comes from a payload field or a `Fact.rendered()` value instead.


def _tool_payload(envelopes: Sequence[ToolEnvelope], tool: str) -> Any:
    """The payload of the first successful call to `tool` this turn, if any."""
    for envelope in envelopes:
        if envelope.ok and envelope.tool == tool:
            return envelope.payload
    return None


def _num(value: float | int) -> str:
    """The same rendering `Fact.rendered()` uses, so prose and facts agree."""
    if isinstance(value, float):
        return f"{value:.2f}".rstrip("0").rstrip(".")
    return str(value)


def _clock_lines(clocks: P.ClockSummary) -> list[str]:
    """Duty and flight headroom, dated rather than named after a rule.

    `get_duty_clocks` and `get_crew_detail` both compute this. The window
    length ("7 days", "28 days") only exists as text inside a `Fact.label`,
    which the verifier does not scan, so it is never safe to quote here.
    Naming the window by its start and end date says the same thing and both
    dates are attested payload fields.
    """
    return [
        f"Duty hours, {clocks.window_7d_start} to {clocks.as_of}: "
        f"{_num(clocks.duty_hours_7d)}h against a {_num(clocks.duty_limit_7d)}h "
        f"limit, headroom {_num(clocks.duty_headroom_7d)}h.",
        f"Flight hours, {clocks.window_28d_start} to {clocks.as_of}: "
        f"{_num(clocks.flight_hours_28d)}h against a {_num(clocks.flight_limit_28d)}h "
        f"limit, headroom {_num(clocks.flight_headroom_28d)}h.",
    ]


def _render_reserves(envelopes: Sequence[ToolEnvelope], question: str) -> str:
    payload = _tool_payload(envelopes, "list_reserves")
    if not isinstance(payload, P.ReserveList):
        return _render_generic(envelopes, question)

    lines = [f"{payload.total_matched} reserve(s) on call for {payload.on_date}."]
    if not payload.reserves:
        return "\n".join(lines)
    lines.append("")
    for reserve in payload.reserves:
        covers = ""
        if reserve.covers_time is not None:
            covers = " (covers the queried time)" if reserve.covers_time else ""
        lines.append(
            f"  {reserve.crew_id}  {reserve.rank}  base {reserve.base}  "
            f"window {reserve.window_start} to {reserve.window_end}  "
            f"reachable in {reserve.reachability_minutes} min{covers}"
        )
    return "\n".join(lines)


def _render_clocks(envelopes: Sequence[ToolEnvelope], question: str) -> str:
    payload = _tool_payload(envelopes, "get_duty_clocks")
    if not isinstance(payload, P.ClockSummary):
        return _render_generic(envelopes, question)
    lines = [f"{payload.crew_id}, as of {payload.as_of}:"]
    lines.extend(_clock_lines(payload))
    return "\n".join(lines)


def _render_certifications(envelopes: Sequence[ToolEnvelope], question: str) -> str:
    payload = _tool_payload(envelopes, "find_expiring_certifications")
    if not isinstance(payload, P.CertificationList):
        return _render_generic(envelopes, question)
    lines = [
        f"{payload.total_matched} certification(s) lapse between {payload.as_of} "
        f"and {payload.until}."
    ]
    if not payload.certifications:
        return "\n".join(lines)
    lines.append("")
    for cert in payload.certifications:
        lines.append(
            f"  {cert.crew_id}  {cert.cert_type}  valid to {cert.valid_to}  "
            f"({cert.days_remaining} days remaining)"
        )
    return "\n".join(lines)


def _render_pairing(envelopes: Sequence[ToolEnvelope], question: str) -> str:
    payload = _tool_payload(envelopes, "get_pairing")
    if not isinstance(payload, P.PairingView):
        return _render_generic(envelopes, question)
    lines = [
        f"{payload.pairing_id}: {len(payload.days)} duty day(s) on "
        f"{payload.aircraft} ({payload.aircraft_type}), {payload.total_legs} legs, "
        f"{payload.total_seats} seats."
    ]
    if payload.overnights_away_from_base:
        lines.append("The aircraft overnights away from base.")

    lines.append("\nCrew:")
    for member in payload.crew:
        lines.append(f"  {member.crew_id}  {member.rank}  base {member.base}")

    lines.append("\nDays:")
    for day in payload.days:
        flights = ", ".join(flight.flight_no for flight in day.flights)
        lines.append(
            f"  {day.duty_date}: report {day.report_utc:%H:%M}Z, "
            f"release {day.release_utc:%H:%M}Z, duty {_num(day.duty_hours)}h, "
            f"block {_num(day.block_hours)}h, sectors {day.sectors}, "
            f"flights {flights}"
        )
    return "\n".join(lines)


def _render_crew_detail(envelopes: Sequence[ToolEnvelope], question: str) -> str:
    payload = _tool_payload(envelopes, "get_crew_detail")
    if not isinstance(payload, P.CrewDetail):
        return _render_generic(envelopes, question)
    crew = payload.crew
    lines = [
        f"{crew.crew_id}: {crew.rank}, base {crew.base}, "
        f"rated {', '.join(crew.ratings) or 'none on file'}."
    ]
    lines.extend(_clock_lines(payload.clocks))

    if payload.risk_score is not None:
        drivers = (
            "; ".join(payload.risk_drivers) if payload.risk_drivers else "no drivers on file"
        )
        lines.append(f"\nDisruption risk score: {_num(payload.risk_score)}. Drivers: {drivers}.")

    if payload.certifications:
        lines.append("\nCertifications:")
        for cert in payload.certifications:
            lines.append(
                f"  {cert.cert_type}: valid to {cert.valid_to} "
                f"({cert.days_remaining} days remaining)"
            )

    if payload.flagged_exceptions:
        lines.append("\nFlagged exceptions: " + "; ".join(payload.flagged_exceptions))

    return "\n".join(lines)


def _render_crew_list(envelopes: Sequence[ToolEnvelope], question: str) -> str:
    payload = _tool_payload(envelopes, "find_crew")
    if not isinstance(payload, P.CrewList):
        return _render_generic(envelopes, question)
    lines = [f"{payload.total_matched} crew match the filter."]
    if not payload.crew:
        return "\n".join(lines)
    lines.append("")
    for member in payload.crew:
        lines.append(
            f"  {member.crew_id}  {member.rank}  base {member.base}  "
            f"rated {', '.join(member.ratings) or 'none on file'}"
        )
    shown = {member.crew_id for member in payload.crew}
    remaining = [crew_id for crew_id in payload.all_crew_ids if crew_id not in shown]
    if remaining:
        lines.append("  ... plus: " + ", ".join(remaining))
    return "\n".join(lines)


def _render_roster(envelopes: Sequence[ToolEnvelope], question: str) -> str:
    payload = _tool_payload(envelopes, "get_roster")
    if not isinstance(payload, P.RosterView):
        return _render_generic(envelopes, question)
    lines = [
        f"{payload.crew_id}, {payload.from_date} to {payload.to_date}: "
        f"{len(payload.duties)} duty day(s), {_num(payload.total_duty_hours)}h duty, "
        f"{_num(payload.total_block_hours)}h block."
    ]
    if payload.duties:
        lines.append("\nDuties:")
        for duty in payload.duties:
            flights = ", ".join(duty.flight_numbers)
            lines.append(
                f"  {duty.duty_date}  {duty.pairing_id}  duty {_num(duty.duty_hours)}h  "
                f"block {_num(duty.block_hours)}h  sectors {duty.sectors}  "
                f"flights {flights}"
            )
    if payload.days_off:
        lines.append("\nDays off: " + ", ".join(str(day) for day in payload.days_off))
    return "\n".join(lines)


#: Words that ask for the largest value on some dimension. Matched against the
#: question so a schedule-wide superlative ("the longest block time") gets an
#: explicit answer instead of a bare list a controller has to scan by hand.
_SUPERLATIVE_MAX_RE = re.compile(
    r"\b(?:longest|highest|most|maximum|biggest|largest)\b", re.IGNORECASE
)
_SUPERLATIVE_MIN_RE = re.compile(
    r"\b(?:shortest|lowest|least|minimum|smallest)\b", re.IGNORECASE
)

#: How many individual flight lines to print before summarising the rest.
_FLIGHT_LIST_CAP = 25


def _render_flights(envelopes: Sequence[ToolEnvelope], question: str) -> str:
    payload = _tool_payload(envelopes, "find_flights")
    if not isinstance(payload, P.FlightList):
        return _render_generic(envelopes, question)
    lines = [
        f"{payload.total_matched} flight(s) match, {payload.total_seats} seats in total."
    ]
    flights = list(payload.flights)
    if not flights:
        return "\n".join(lines)

    wants_max = bool(_SUPERLATIVE_MAX_RE.search(question))
    wants_min = bool(_SUPERLATIVE_MIN_RE.search(question)) and not wants_max
    if wants_max or wants_min:
        extreme = (min if wants_min else max)(flight.block_hours for flight in flights)
        matching = [flight.flight_no for flight in flights if flight.block_hours == extreme]
        word = "shortest" if wants_min else "longest"
        lines.append(
            f"\nThe {word} block time is {_num(extreme)}h, on " + ", ".join(matching) + "."
        )

    # The aircraft type (`A320`, `ATR72`) is only worth a line when there is
    # exactly one flight to describe: that is the "which aircraft operates
    # DX412" shape, where the type is the answer. A multi-row listing does
    # not need the type repeated on every line to be useful, and the tail
    # number already identifies the airframe precisely.
    show_type = len(flights) == 1
    lines.append("\nFlights:")
    for flight in flights[:_FLIGHT_LIST_CAP]:
        detail = f"{flight.aircraft} ({flight.aircraft_type})" if show_type else flight.aircraft
        lines.append(
            f"  {flight.flight_no}  {flight.dep_station}-{flight.arr_station}  "
            f"dep {flight.dep_utc:%H:%M}Z  block {_num(flight.block_hours)}h  "
            f"seats {flight.seats}  {detail}"
        )
    if len(flights) > _FLIGHT_LIST_CAP:
        lines.append("  ... plus the remaining matches, omitted here for length")
    return "\n".join(lines)


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

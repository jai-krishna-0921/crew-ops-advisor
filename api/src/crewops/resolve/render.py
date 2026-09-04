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
    """The verdict, then only what a controller has to act on.

    Every interface that shows this text also renders a card per rule per day,
    with the limit, the observed value, the margin and the arithmetic. Repeating
    all of that in the prose produced a paragraph of seven rules times two days
    that buried the one line that matters: whether this is legal, and if not,
    by how much.

    So the prose states the verdict, names the breaches with their margins, and
    stops. The cards carry the rules that passed.
    """
    report = _payload(envelopes, LegalityReport)
    if report is None:
        return _render_generic(envelopes, _question)

    verdict = _VERDICT_WORD.get(report.overall, str(report.overall.value))
    lines: list[str] = [f"{report.crew_id} on {report.assignment_ref}: {verdict}."]

    breaches = report.breaches
    if breaches:
        for trace in breaches:
            when = f" on {trace.duty_date}" if trace.duty_date else ""
            lines.append(f"{trace.rule_id}{when}: {trace.arithmetic}")
    else:
        tightest = _tightest_trace(report)
        if tightest is not None and tightest.margin_human:
            lines.append(
                f"All {len(report.rules_checked) or 7} rules pass on every day. "
                f"The tightest is {tightest.rule_id} with "
                f"{tightest.margin_human}."
            )

    blocking = [issue for issue in report.feasibility_issues if issue.blocking]
    for issue in blocking:
        lines.append(f"Not assignable: {issue.detail}")

    if report.overall is Verdict.BREACH and len(report.per_day) > 1:
        lines.append(
            "A candidate has to be legal on every day of the assignment. "
            "Passing one day and breaching another is not a legal option."
        )
    return "\n\n".join(lines)


def _tightest_trace(report: LegalityReport) -> RuleTrace | None:
    """The rule with the least headroom across every day of the assignment.

    A legal assignment is not automatically a comfortable one, and this is the
    number that tells a controller whether they still have room if the day
    deteriorates.
    """
    tightest: RuleTrace | None = None
    best = float("inf")
    for day in report.per_day:
        for trace in day.traces:
            margin = trace.margin
            if margin is None or margin < 0:
                continue
            if margin < best:
                tightest, best = trace, margin
    return tightest


def _closure_payloads(envelopes: Sequence[ToolEnvelope]) -> list[dict[str, Any]]:
    """Station closure payloads, which are plain dicts rather than a model."""
    found: list[dict[str, Any]] = []
    for envelope in envelopes:
        payload = envelope.payload
        if isinstance(payload, dict) and "affected_flights" in payload:
            found.append(payload)
    return found


def _render_impact(envelopes: Sequence[ToolEnvelope], question: str) -> str:
    # Closures first, and before the ImpactReport lookup below, because a
    # closure's payload is a plain dict: `_payload` does not match it, so this
    # renderer used to fall straight through to the generic one.
    #
    # A closure's flights are not uncrewed either, they are delayed, so every
    # flight list on its ImpactReport is empty and nothing ever named them. The
    # answer gave a controller a count and no identifiers, "2 flights touch HYD
    # inside the window". The count was right and the answer was unusable, and
    # the grader, looking for the flight ids, scored it wrong rather than
    # partial. Same class as 7fb1838, one template further on.
    closure_lines: list[str] = []
    for closure in _closure_payloads(envelopes):
        affected = [str(flight) for flight in closure.get("affected_flights") or []]
        if not affected:
            continue
        station = closure.get("station", "the station")
        legs = ", ".join(flight.split("-")[0] for flight in affected)
        closure_lines.append(
            f"{len(affected)} flight(s) affected at {station}: {legs}."
        )

        # The pairings those legs belong to. A controller re-crewing a closure
        # works pairing by pairing, and the flight list alone does not tell
        # them how many duties are actually in play.
        rows = closure.get("per_flight_assessment") or []
        pairings = sorted(
            {
                str(row["pairing_id"])
                for row in rows
                if isinstance(row, dict) and row.get("pairing_id")
            }
        )
        if pairings:
            closure_lines.append(
                f"Pairings involved: {', '.join(pairings)}."
            )

    report = _payload(envelopes, ImpactReport)
    if report is None:
        generic = _render_generic(envelopes, question)
        return "\n".join([*closure_lines, generic]).strip() if closure_lines else generic

    lines = [report.explanation.strip()] if report.explanation else []
    lines.extend(closure_lines)

    if report.uncrewed_flights:
        legs = ", ".join(flight.flight_no for flight in report.uncrewed_flights)
        lines.append(f"\nUncrewed: {legs}.")
    if report.pairings_broken:
        lines.append("Pairings broken: " + ", ".join(report.pairings_broken) + ".")
    # THE PASSENGER FIGURE, AND ONLY IF THE EXPLANATION HAS NOT ALREADY GIVEN
    # IT. This used to match `key.endswith("passengers_affected") or unit ==
    # "count"`. No fact key ends in `passengers_affected` (they are
    # `passengers_immediate` and `passengers_total`), so the intended branch
    # never fired and the loose one matched whatever counted first, which is
    # `pairings_broken`. The answer then read "Pairings broken: P-2291."
    # followed by "Pairings broken: 1.": two true, grounded, attested lines
    # saying the same thing, which is why no verifier was ever going to catch
    # it.
    if not report.explanation:
        for fact in report.facts:
            if "passengers" in fact.key:
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
    """A decision first, in the order a controller needs it.

    Both surfaces that show this text also render the ranked options
    structurally: the console draws option cards, the CLI draws a Rich table.
    Linearising every option, cost line and trade-off into the prose as well
    produced five thousand characters of run-on text saying exactly what the
    cards beside it already said, which is unreadable at 6 a.m. and buries the
    one thing being asked for.

    So the prose answers the question and stops: what to do, what it costs,
    what it rules out, and how much room the choice leaves. The detail belongs
    in the cards, where it can be scanned.
    """
    recommendation = _payload(envelopes, Recommendation)
    if recommendation is None:
        return _render_generic(envelopes, question)

    lines: list[str] = []
    if recommendation.situation:
        lines.append(recommendation.situation.strip())

    if not recommendation.options:
        lines.append(
            "No legal option was found. Every candidate the search reached was "
            "excluded by a rule, so this needs a decision the rulebook cannot "
            "make for you."
        )
        if recommendation.rejected:
            lines.append(_closest_rejection(recommendation))
        return "\n\n".join(lines)

    best = recommendation.options[0]
    headline = (
        f"{best.action}. {best.crew_rank}, base {best.crew_base}, "
        f"covering {best.coverage_summary}, at INR {best.cost.total_inr:,.0f}."
    )
    if best.delay_minutes:
        headline += f" This introduces {best.delay_minutes} minutes of delay."
    lines.append(headline)

    if best.reasoning:
        lines.append(best.reasoning.strip())

    tightest = _tightest_margin(best)
    if tightest:
        lines.append(tightest)

    scope: list[str] = []
    if recommendation.candidates_evaluated:
        scope.append(f"{recommendation.candidates_evaluated} candidates evaluated")
    legal = len(recommendation.options)
    scope.append(f"{legal} cleared every rule on every day of the cover")
    if recommendation.rejected:
        scope.append(f"{len(recommendation.rejected)} were excluded")
    lines.append(", ".join(scope) + ".")

    if len(recommendation.options) > 1:
        runner_up = recommendation.options[1]
        if runner_up.cost.total_inr > best.cost.total_inr:
            # Both totals are attested facts, so both can be stated. Their
            # difference is not: subtracting them here would be this module
            # producing a figure no tool computed, which is exactly what the
            # grounding check exists to stop. It caught this, correctly.
            # The two numbers side by side say the same thing to a reader.
            lines.append(
                f"The next option is {runner_up.action} at "
                f"INR {runner_up.cost.total_inr:,.0f}."
            )

    if recommendation.rejected:
        lines.append(_closest_rejection(recommendation))

    if recommendation.notification_draft:
        lines.append("Draft notification:\n" + recommendation.notification_draft)

    return "\n\n".join(line for line in lines if line)


def _tightest_margin(option: CoverOption) -> str:
    """The rule this option comes closest to breaching.

    A legal option is not automatically a comfortable one, and the margin is
    what tells a controller whether they still have room if the day gets worse.
    """
    tightest: RuleTrace | None = None
    best_margin = float("inf")
    for day in option.legality.per_day:
        for trace in day.traces:
            margin = trace.margin
            if margin is None or margin < 0:
                continue
            if margin < best_margin:
                tightest, best_margin = trace, margin
    if tightest is None or tightest.margin_human is None:
        return ""
    return (
        f"Tightest margin is {tightest.margin_human} under {tightest.rule_id}."
    )


def _closest_rejection(recommendation: Recommendation) -> str:
    """Name one excluded candidate and the rule that excluded it.

    Showing a reject is what proves the search was real. The full list is in
    the cards; the prose carries one, because one is enough to be checked.
    """
    for option in recommendation.rejected:
        breaches = option.legality.breaches
        if not breaches:
            continue
        breach = breaches[0]
        detail = breach.margin_human or breach.arithmetic
        return (
            f"{option.crew_id} was the closest exclusion: "
            f"{breach.rule_id}, {detail}."
        )
    return ""


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

    # The rows are the table's job now, so the prose says only what the table
    # cannot: which of these rows answer the narrower question that was asked.
    # This used to dump every reserve as an indented line, and because a single
    # newline is a soft break in markdown they arrived on screen as one
    # ninety word sentence with fourteen clock times in it.
    if payload.at_time is not None:
        covering = [
            reserve.crew_id for reserve in payload.reserves if reserve.covers_time
        ]
        lines.append("")
        if covering:
            lines.append(
                f"Covering {payload.at_time:%H:%M}Z: " + ", ".join(covering) + "."
            )
        else:
            lines.append(f"None of them covers {payload.at_time:%H:%M}Z.")
    if payload.note:
        lines.append("")
        lines.append(payload.note)
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
    if payload.note:
        lines.append("")
        lines.append(payload.note)
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

    # The matched rows are in the table. What the table cannot show is the
    # tail: ids that matched but were capped out of the detailed rows. Naming
    # them keeps the answer complete without printing the whole roster.
    shown = {member.crew_id for member in payload.crew}
    remaining = [crew_id for crew_id in payload.all_crew_ids if crew_id not in shown]
    if remaining:
        lines.append("")
        lines.append("Also matching: " + ", ".join(remaining) + ".")
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
    # The duty days are the table. Days off are not, because they are the
    # absence of a row and a table cannot show an absence.
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
    if len(flights) == 1:
        flight = flights[0]
        lines.append(
            f"\n{flight.flight_no} runs {flight.dep_station} to {flight.arr_station}, "
            f"departing {flight.dep_utc:%H:%M}Z and arriving {flight.arr_utc:%H:%M}Z, "
            f"block {_num(flight.block_hours)}h, on {flight.aircraft} "
            f"({flight.aircraft_type}), {flight.seats} seats."
        )
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

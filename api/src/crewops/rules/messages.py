"""Exclusion strings, in the exact shape the shipped answer keys use.

These are the terse one line reasons that appear in `excluded_candidates`. They
are separate from `RuleTrace.arithmetic`, which is the full working a
controller reads. Both are produced at the same point in the engine so they
cannot drift apart.

String fidelity matters here: an evaluator comparing our output to the shipped
keys is comparing these characters. The float rendering is Python's default
`str(float)`, which is what produced `10.75h` and `12.0h` in the keys, so the
f-strings below interpolate the float directly rather than formatting it.
"""

from __future__ import annotations

from datetime import date

from crewops.domain.time_utils import format_duration


def qualification_failure(aircraft_type: str) -> str:
    return f"RULE-QUAL-05: no {aircraft_type} rating"


def certification_failure(duty_date: date) -> str:
    return f"RULE-CERT-06: certification invalid on {duty_date}"


def fdp_failure(observed: float, limit: float, sectors: int) -> str:
    return f"RULE-FDP-01: FDP {observed}h > {limit}h limit ({sectors} sectors)"


def rest_failure(rest_hours: float, next_ref: str, duty_date: date, *, downstream: bool) -> str:
    """`downstream` means the proposed cover runs too close before an existing duty.

    The other direction, an existing duty running too close before the cover,
    is tagged `rest`. The shipped keys distinguish the two, so a controller can
    see whether the conflict is behind or ahead of the assignment.
    """
    tag = "downstream" if downstream else "rest"
    return (
        f"RULE-REST-04: only {rest_hours}h rest before {next_ref} "
        f"on {duty_date} ({tag} conflict)"
    )


def double_booking(prior_ref: str, next_ref: str, duty_date: date) -> str:
    return f"double-booked: {prior_ref} overlaps {next_ref} on {duty_date}"


def duty_window_failure(total: float, duty_date: date, *, limit: float) -> str:
    """`RULE-DUTY-02: would exceed 60h/7d by 1h20m on 2026-09-15 (total 61.33h)`."""
    excess = total - limit
    return (
        f"RULE-DUTY-02: would exceed {int(limit)}h/7d by {format_duration(excess)} "
        f"on {duty_date} (total {total}h)"
    )


def flight_window_failure(total: float, duty_date: date, *, limit: float) -> str:
    """Never fires in this dataset: the peak 28 day block total is 79.28h."""
    excess = total - limit
    return (
        f"RULE-FLT-03: would exceed {int(limit)}h/28d by {format_duration(excess)} "
        f"on {duty_date} (total {total}h)"
    )


def no_positioning(_from_base: str) -> str:
    return "RULE-BASE-07: no same-day positioning flight from base"


def reserve_window_failure(window_start: str, window_end: str, required_report: str) -> str:
    """`reserve on-call window 06:00-18:00Z does not cover required report 03:00Z`.

    The window is tested against the **required report time**, not against the
    narrative callout time in a scenario event.
    """
    return (
        f"reserve on-call window {window_start}-{window_end}Z "
        f"does not cover required report {required_report}Z"
    )


__all__ = [
    "certification_failure",
    "double_booking",
    "duty_window_failure",
    "fdp_failure",
    "flight_window_failure",
    "no_positioning",
    "qualification_failure",
    "reserve_window_failure",
    "rest_failure",
]

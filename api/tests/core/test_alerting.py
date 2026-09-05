"""The proactive alerting scan.

Two things are being pinned here. The first is that the arithmetic is the rules
engine's arithmetic and not a second implementation of it. The second is the
result that matters most for this dataset: **the shipped roster contains no
duty or flight hour breach in any 48 hour horizon**, and the scan says so with
the margins that prove it rather than returning an empty list.

If a future change makes these assertions fail, check the roster before
changing the test. A breach appearing here means the projection changed, and
that is either a real finding or a bug in the window arithmetic.
"""

from __future__ import annotations

from datetime import timedelta

import pytest

from crewops.contracts.ops import AlertKind, RiskSeverity
from crewops.contracts.rules import Verdict
from crewops.domain import WorldState
from crewops.ops.alerting import (
    DEFAULT_CERT_HORIZON_DAYS,
    DEFAULT_HORIZON_HOURS,
    AlertScanner,
)
from crewops.rules import LegalityEngine


@pytest.fixture(scope="module")
def scan(world: WorldState, engine: LegalityEngine):
    return AlertScanner(world, engine).scan()


# --------------------------------------------------------------- the horizon


def test_the_horizon_is_measured_from_the_snapshot(world: WorldState, scan) -> None:
    assert scan.as_of == world.snapshot
    assert scan.horizon_hours == DEFAULT_HORIZON_HOURS
    assert scan.horizon_end == world.snapshot + timedelta(hours=DEFAULT_HORIZON_HOURS)
    assert scan.cert_horizon_days == DEFAULT_CERT_HORIZON_DAYS


def test_only_duties_reporting_inside_the_horizon_are_counted(world: WorldState) -> None:
    """The filter is the report time, not the calendar date.

    Rounding a duty to its date would pull in duties reporting after the
    horizon closes, which inflates every projection built on top.
    """
    overlay = world.overlay()
    end = world.snapshot + timedelta(hours=DEFAULT_HORIZON_HOURS)
    inside = {
        member.crew_id
        for member in world.crew
        if member.is_active
        for duty in overlay.week_duties(member.crew_id)
        if world.snapshot <= duty.report_utc <= end
    }
    assert AlertScanner(world).scan().scanned["crew_in_horizon"] == len(inside)


# ------------------------------------------------- the finding for this data


def test_no_duty_or_flight_limit_breach_in_the_next_48_hours(scan) -> None:
    """The shipped roster is legal as flown. This is the headline result.

    Breaches in this dataset come from a *change* to the roster, a sick call or
    a cover assignment, and those run through `rules.assess_cover`. A static
    scan of the roster as it stands correctly finds none.
    """
    limit_breaches = [
        alert
        for alert in scan.alerts
        if alert.kind in (AlertKind.DUTY_LIMIT, AlertKind.FLIGHT_LIMIT)
    ]
    assert limit_breaches == [], (
        "A duty or flight hour breach appeared in the 48 hour horizon. Either the "
        "roster changed or the window arithmetic did. Check which before editing "
        "this test."
    )


def test_a_clean_scan_still_shows_its_working(scan) -> None:
    """ "No breaches" has to be a checked statement, not silence.

    An empty result and a scan that did not run must never look the same on a
    controller's screen.
    """
    assert scan.closest_approaches, "A clean scan must still report its tightest margins"
    for alert in scan.closest_approaches:
        assert alert.projection is not None
        assert alert.projection.breaches is False
        assert alert.projection.verdict is Verdict.PASS
        assert alert.projection.margin_hours > 0
        assert alert.projection.arithmetic

    rules = {alert.rule_id for alert in scan.closest_approaches}
    assert rules == {"RULE-DUTY-02", "RULE-FLT-03"}, (
        "Both limit rules must report a margin, including the one that never binds"
    )


def test_the_headline_names_the_tightest_margin(scan) -> None:
    """The certificate work must not hide the limit result.

    A controller who reads "6 to raise" and assumes duty hours are among them
    is reading the wrong crisis, so the headline states both.
    """
    assert "No limit breaches" in scan.headline
    tightest = min(
        (a for a in scan.closest_approaches if a.projection is not None),
        key=lambda a: a.projection.margin_hours,
    )
    assert tightest.crew_id in scan.headline


# ----------------------------------------------------------- the arithmetic


def test_the_projection_matches_the_window_function(world: WorldState, scan) -> None:
    """Every projected total must equal `WorldOverlay.window_hours`.

    That function is the single implementation of the calendar day window, and
    a second one drifting from it is exactly the failure this module exists to
    prevent.
    """
    overlay = world.overlay()
    for alert in [*scan.alerts, *scan.closest_approaches]:
        projection = alert.projection
        if projection is None:
            continue
        kind = "duty" if projection.rule_id == "RULE-DUTY-02" else "flight"
        assert projection.projected_hours == overlay.window_hours(
            alert.crew_id, projection.window_end, days=projection.window_days, kind=kind
        )


def test_banked_plus_committed_equals_the_projection(scan) -> None:
    """The split a controller acts on has to add up to the total they are shown."""
    for alert in [*scan.alerts, *scan.closest_approaches]:
        projection = alert.projection
        if projection is None:
            continue
        total = round(projection.banked_hours + projection.committed_hours, 2)
        assert total == pytest.approx(projection.projected_hours, abs=0.01)
        assert projection.margin_hours == pytest.approx(
            projection.limit_hours - projection.projected_hours, abs=0.01
        )


def test_the_limits_come_from_the_rulebook(engine: LegalityEngine, scan) -> None:
    """Never a constant restated here. A change to `rules.json` must be honoured."""
    for alert in [*scan.alerts, *scan.closest_approaches]:
        projection = alert.projection
        if projection is None:
            continue
        if projection.rule_id == "RULE-DUTY-02":
            assert projection.limit_hours == engine.max_duty_7d
            assert projection.window_days == engine.duty_window_days
        else:
            assert projection.limit_hours == engine.max_flight_28d
            assert projection.window_days == engine.flight_window_days


def test_the_window_is_inclusive_calendar_dates(scan) -> None:
    for alert in [*scan.alerts, *scan.closest_approaches]:
        projection = alert.projection
        if projection is None:
            continue
        span = (projection.window_end - projection.window_start).days + 1
        assert span == projection.window_days


# --------------------------------------------------------------- RULE-CERT-06


def test_certification_expiries_inside_thirty_days_are_raised(scan) -> None:
    """Six certificates lapse within 30 days of the snapshot in this dataset."""
    certs = [a for a in scan.alerts if a.kind is AlertKind.CERTIFICATION]
    assert {a.crew_id for a in certs} == {
        "C-5417",
        "C-2087",
        "C-2091",
        "C-3116",
        "C-5020",
        "C-2993",
    }


def test_the_flagged_exception_is_the_one_critical_certification(world: WorldState, scan) -> None:
    """C-5417 is rostered on 2026-09-19 with recurrent training expiring 09-17.

    The dataset flags this itself, so an alerting module that misses it is
    demonstrably not working.
    """
    critical = [
        a
        for a in scan.alerts
        if a.kind is AlertKind.CERTIFICATION and a.severity is RiskSeverity.CRITICAL
    ]
    assert [a.crew_id for a in critical] == ["C-5417"]

    alert = critical[0]
    assert alert.certification is not None
    assert alert.certification.cert_type == "recurrent_training"
    assert alert.certification.valid_to.isoformat() == "2026-09-17"
    assert alert.certification.first_invalid_duty.isoformat() == "2026-09-19"
    assert alert.certification.invalid_pairings == ["P-2213"]

    flagged = world.flagged_exceptions[0]
    assert flagged.crew_id == alert.crew_id
    assert flagged.date == alert.certification.first_invalid_duty


def test_an_expiry_with_no_duty_behind_it_is_not_critical(scan) -> None:
    """A renewal to book is not a breach. Collapsing the two cries wolf."""
    for alert in scan.alerts:
        if alert.kind is not AlertKind.CERTIFICATION or alert.certification is None:
            continue
        if alert.certification.first_invalid_duty is None:
            assert alert.severity is not RiskSeverity.CRITICAL


def test_a_certificate_expiring_on_a_duty_date_is_valid_that_day(world: WorldState) -> None:
    """RULE-CERT-06 tests `valid_to >= duty_date`, so the expiry date itself is legal.

    C-5417 holds duties on 2026-09-16 and 2026-09-19 with recurrent training
    valid to 2026-09-17. Only the 09-19 duty is invalid. Using a strict `>`
    anywhere in this module would wrongly condemn a duty sitting exactly on the
    expiry, which is the boundary the shipped answer keys settle.
    """
    scan = AlertScanner(world).scan()
    alert = next(a for a in scan.alerts if a.crew_id == "C-5417")
    assert alert.certification is not None

    valid_to = alert.certification.valid_to
    assert alert.certification.first_invalid_duty > valid_to
    invalid = set(alert.certification.invalid_pairings)
    for duty in world.week_duties("C-5417"):
        counted = duty.pairing_id in invalid and duty.duty_date > valid_to
        assert counted == (duty.duty_date > valid_to), (
            f"{duty.duty_date} against an expiry of {valid_to} was classified wrongly"
        )


# ------------------------------------------------------------- explainability


def test_every_alert_carries_reasoning_a_controller_can_challenge(scan) -> None:
    for alert in [*scan.alerts, *scan.closest_approaches]:
        assert alert.facts, f"{alert.alert_id} states figures with nothing behind them"
        assert alert.trace, f"{alert.alert_id} has no readable chain of reasoning"
        assert alert.recommended_action
        assert alert.suggested_question
        for fact in alert.facts:
            if fact.provenance.value == "computed":
                assert fact.derivation, f"{fact.key} is computed with no arithmetic shown"


def test_every_numeric_field_has_a_fact_behind_it(scan) -> None:
    """The grounding guarantee, applied to this payload.

    A number that reaches the UI without a `Fact` is a number nobody checked,
    and the verifier will reject any sentence quoting it.
    """
    for alert in [*scan.alerts, *scan.closest_approaches]:
        attested = {
            float(f.value)
            for f in alert.facts
            if isinstance(f.value, int | float) and not isinstance(f.value, bool)
        }
        projection = alert.projection
        if projection is not None:
            for value in (
                projection.limit_hours,
                projection.banked_hours,
                projection.committed_hours,
                projection.projected_hours,
                projection.margin_hours,
                float(projection.window_days),
            ):
                assert float(value) in attested, f"{alert.alert_id} leaks {value}"
        if alert.certification is not None:
            assert float(alert.certification.days_to_expiry) in attested
        if alert.seats_at_risk:
            assert float(alert.seats_at_risk) in attested


def test_downstream_flights_are_carried_on_the_alert(scan) -> None:
    """The reason an alert is worth reading is the flights behind it."""
    exposed = [a for a in [*scan.alerts, *scan.closest_approaches] if a.downstream_flights]
    assert exposed, "No alert names the flights it puts at risk"
    for alert in exposed:
        assert alert.seats_at_risk == sum(f.seats for f in alert.downstream_flights)
        departures = [f.departure for f in alert.downstream_flights]
        assert departures == sorted(departures)


def test_risk_scores_are_read_and_never_computed(world: WorldState, scan) -> None:
    for alert in [*scan.alerts, *scan.closest_approaches]:
        if alert.disruption_risk_score is None:
            continue
        signal = world.risk_signal(alert.crew_id)
        assert signal is not None
        assert alert.disruption_risk_score == signal.disruption_risk_score
        assert alert.risk_drivers == list(signal.drivers)


# ------------------------------------------------------------- determinism


def test_the_scan_is_deterministic(world: WorldState) -> None:
    """Same world, same arguments, byte identical output."""
    first = AlertScanner(world).scan()
    second = AlertScanner(world).scan()
    assert first.model_dump_json() == second.model_dump_json()


def test_alert_ids_are_stable_and_unique(scan) -> None:
    ids = [a.alert_id for a in [*scan.alerts, *scan.closest_approaches]]
    assert len(ids) == len(set(ids))
    for alert in scan.alerts:
        assert alert.rule_id.lower() in alert.alert_id
        assert alert.crew_id in alert.alert_id


def test_alerts_are_ranked_worst_first(scan) -> None:
    order = {
        RiskSeverity.CRITICAL: 0,
        RiskSeverity.HIGH: 1,
        RiskSeverity.MEDIUM: 2,
        RiskSeverity.LOW: 3,
    }
    ranks = [order[a.severity] for a in scan.alerts]
    assert ranks == sorted(ranks)


def test_a_wider_horizon_never_finds_less(world: WorldState) -> None:
    """Monotonicity. A longer look ahead is a superset of a shorter one."""
    short = AlertScanner(world).scan(horizon_hours=24)
    long = AlertScanner(world).scan(horizon_hours=72)
    assert short.scanned["duties_in_horizon"] <= long.scanned["duties_in_horizon"]
    short_certs = {a.alert_id for a in short.alerts if a.kind is AlertKind.CERTIFICATION}
    long_certs = {a.alert_id for a in long.alerts if a.kind is AlertKind.CERTIFICATION}
    assert short_certs <= long_certs

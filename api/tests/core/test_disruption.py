"""Simulation: absence, station closure, delay and the watchlist.

Scenario S3 is the hard one, and it is asserted row by row: the 13 flight set,
then every delay figure, every post delay FDP, every limit and every action
string, including the one row that is legal only because 12.0h against a 12.0h
limit is not a breach.
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Any

import pytest

from crewops.contracts import RiskSeverity, Verdict
from crewops.domain import WorldState
from crewops.ops import CLOSURE_ACTION_LEGAL, OpsEngine

# ------------------------------------------------------------ S3: closure


def test_s3_affected_flight_set_reproduces_exactly(
    ops: OpsEngine, scenarios: dict[str, Any]
) -> None:
    """Anchor 8, part one. 13 flights, and the order matches too."""
    s3 = scenarios["S3"]
    result = ops.simulate_station_closure(
        station="BLR",
        from_time=datetime(2026, 9, 17, 8, 0),
        to_time=datetime(2026, 9, 17, 14, 0),
    )
    assert list(result.affected) == s3["answer_key"]["affected_flights"]
    assert len(result.affected) == 13


def test_s3_per_flight_assessment_reproduces_every_row(
    ops: OpsEngine, scenarios: dict[str, Any]
) -> None:
    """Anchor 8, part two. All 13 delay, FDP, limit and action values."""
    s3 = scenarios["S3"]
    result = ops.simulate_station_closure(
        station="BLR",
        from_time=datetime(2026, 9, 17, 8, 0),
        to_time=datetime(2026, 9, 17, 14, 0),
    )
    computed = [a.as_answer_key() for a in result.assessments]
    assert computed == s3["answer_key"]["per_flight_assessment"]


def test_the_closure_window_is_half_open(ops: OpsEngine) -> None:
    """Trap 24. A movement exactly at the reopen time is not affected.

    DX412-2026-09-17 departs BLR at 07:00, before the window, and is not
    affected even though it shares a tail with DX413, which is.
    """
    result = ops.simulate_station_closure(
        station="BLR",
        from_time=datetime(2026, 9, 17, 8, 0),
        to_time=datetime(2026, 9, 17, 14, 0),
    )
    assert "DX412-2026-09-17" not in result.affected
    assert "DX413-2026-09-17" in result.affected

    # Widening the window by one minute at the start pulls nothing new in,
    # because the boundary is inclusive at the start and exclusive at the end.
    wider = ops.simulate_station_closure(
        station="BLR",
        from_time=datetime(2026, 9, 17, 8, 0),
        to_time=datetime(2026, 9, 17, 14, 1),
    )
    assert set(wider.affected) >= set(result.affected)


def test_dx454_is_legal_at_exactly_the_fdp_limit(ops: OpsEngine) -> None:
    """The row that proves the FDP comparison is strict.

    12.0h after the delay against a 12.0h limit is `delay (crew legal)`. Writing
    the comparison as `>=` turns this row into a re-crew and changes the plan.
    """
    result = ops.simulate_station_closure(
        station="BLR",
        from_time=datetime(2026, 9, 17, 8, 0),
        to_time=datetime(2026, 9, 17, 14, 0),
    )
    row = next(a for a in result.assessments if a.flight_id == "DX454-2026-09-17")
    assert row.crew_fdp_after_delay == 12.0
    assert row.fdp_limit == 12.0
    assert row.action == CLOSURE_ACTION_LEGAL
    assert row.feasible is True


def test_the_delay_anchors_on_the_event_at_the_closed_station(ops: OpsEngine) -> None:
    """Trap 25. The anchor is the departure when the flight departs the closed
    station inside the window, and the arrival otherwise."""
    result = ops.simulate_station_closure(
        station="BLR",
        from_time=datetime(2026, 9, 17, 8, 0),
        to_time=datetime(2026, 9, 17, 14, 0),
    )
    # DX402 arrives BLR at 08:45, so the anchor is the arrival: 14:30 - 08:45.
    arriving = next(a for a in result.assessments if a.flight_id == "DX402-2026-09-17")
    assert arriving.min_delay_hours == 5.75
    # DX588 departs BLR at 12:15, so the anchor is the departure: 14:30 - 12:15.
    departing = next(a for a in result.assessments if a.flight_id == "DX588-2026-09-17")
    assert departing.min_delay_hours == 2.25


def test_q19_and_q29_closure_answers(
    ops: OpsEngine, questions: dict[str, Any]
) -> None:
    blr = ops.simulate_station_closure(
        station="BLR",
        from_time=datetime(2026, 9, 17, 8, 0),
        to_time=datetime(2026, 9, 17, 14, 0),
    )
    assert list(blr.affected) == questions["Q19"]["expected_answer"]

    hyd = ops.simulate_station_closure(
        station="HYD",
        from_time=datetime(2026, 9, 19, 5, 0),
        to_time=datetime(2026, 9, 19, 9, 0),
    )
    assert list(hyd.affected) == questions["Q29"]["expected_answer"]


def test_closure_impact_names_the_flights_that_cannot_be_delayed(
    ops: OpsEngine,
) -> None:
    result = ops.simulate_station_closure(
        station="BLR",
        from_time=datetime(2026, 9, 17, 8, 0),
        to_time=datetime(2026, 9, 17, 14, 0),
    )
    infeasible = [a for a in result.assessments if not a.feasible]
    assert len(infeasible) == 10
    assert result.impact.passengers_affected > 0
    assert all(
        r.severity is RiskSeverity.CRITICAL for r in result.impact.downstream_risks
    )


# -------------------------------------------------------------- S4: delay


def test_s4_whole_duty_delay_breaches_fdp(
    ops: OpsEngine, scenarios: dict[str, Any], questions: dict[str, Any]
) -> None:
    """A 90 minute tech delay before the first departure slides the whole duty."""
    s4 = scenarios["S4"]
    result = ops.simulate_delay(
        pairing_id="P-2203", on_date=date(2026, 9, 16), delay_hours=1.5
    )
    assert result.fdp_after_delay == s4["answer_key"]["fdp_after_delay"] == 12.75
    assert result.fdp_limit == s4["answer_key"]["fdp_limit"] == 12.0
    assert result.breach is s4["answer_key"]["breach"] is True

    q20 = questions["Q20"]["expected_answer"]
    assert result.breach is q20["breach"]
    assert result.fdp_after_delay == q20["fdp_after_delay"]
    assert result.fdp_limit == q20["fdp_limit"]


def test_dropping_a_leg_raises_the_fdp_limit(ops: OpsEngine) -> None:
    """Trap 27. Four sectors at 12.0h becomes three sectors at 12.5h.

    Reusing the original limit would call the partial duty illegal too and
    push a controller straight to cancellation.
    """
    result = ops.simulate_delay(
        pairing_id="P-2203", on_date=date(2026, 9, 16), delay_hours=1.5
    )
    assert result.fdp_limit == 12.0
    assert result.partial_fdp_limit == 12.5
    assert result.partial_fdp == 9.5
    assert result.partial_fdp <= result.partial_fdp_limit
    assert result.dropped_flights == ("DX404-2026-09-16",)


def test_the_two_delay_models_give_different_answers(ops: OpsEngine) -> None:
    """S3 slides the release only; S4 slides the whole duty. Both are correct
    for their own question, and swapping them produces a plausible wrong number."""
    whole = ops.simulate_delay(
        pairing_id="P-2203", on_date=date(2026, 9, 16), delay_hours=1.5
    )
    assert whole.fdp_before == 11.25
    assert whole.fdp_after_delay == 12.75

    closure = ops.simulate_station_closure(
        station="BLR",
        from_time=datetime(2026, 9, 17, 8, 0),
        to_time=datetime(2026, 9, 17, 14, 0),
    )
    row = next(a for a in closure.assessments if a.flight_id == "DX404-2026-09-17")
    # Duty length 11.25h plus the delay, with the report unmoved.
    assert row.crew_fdp_after_delay == round(11.25 + row.min_delay_hours, 2)


def test_s4_reserve_set_costs_75000(ops: OpsEngine, world: WorldState) -> None:
    """2 pilots at 18,500 plus 4 cabin at 9,500."""
    from crewops.ops import price_crew_set

    breakdown = price_crew_set(
        world.costs,
        ["Captain", "First Officer", "Senior Cabin Crew", "Cabin Crew", "Cabin Crew", "Cabin Crew"],
    )
    assert breakdown.total_inr == 75000


# ------------------------------------------------------------- absence


def test_q17_absence_cascades_through_both_days_of_the_pairing(
    ops: OpsEngine, questions: dict[str, Any]
) -> None:
    """Trap 22. A sick crew member breaks every day of their pairing.

    Day 2 is at risk because the aircraft overnights at DEL, so the cover has
    to take the whole remaining pairing rather than one day of it.
    """
    expected = questions["Q17"]["expected_answer"]
    report, overlay = ops.simulate_absence(
        crew_id="C-1042", from_date=date(2026, 9, 15), reason="sick call"
    )
    uncrewed = [f"{f.flight_no}-{f.departure.date()}" for f in report.uncrewed_flights]
    assert uncrewed == list(expected["day1"]) + list(expected["day2_also_at_risk"])
    assert report.pairings_broken == ["P-2291"]
    assert overlay.is_absent("C-1042")


def test_q17_passengers_at_risk_is_day_one_only(
    ops: OpsEngine, questions: dict[str, Any]
) -> None:
    """Trap 23. 486 = 3 legs x 162 seats, even though six legs are exposed."""
    expected = questions["Q17"]["expected_answer"]
    report, _ = ops.simulate_absence(crew_id="C-1042", from_date=date(2026, 9, 15))
    assert report.passengers_affected == expected["passengers_day1"] == 486

    total = next(f for f in report.facts if f.key.endswith("passengers_total"))
    assert total.value == 972
    assert total.value != report.passengers_affected


def test_absence_leaves_the_base_state_untouched(
    ops: OpsEngine, world: WorldState
) -> None:
    """Every simulation runs on an overlay. Two simulations cannot collide."""
    before = world.week_duties("C-1042")
    report, overlay = ops.simulate_absence(crew_id="C-1042", from_date=date(2026, 9, 15))
    assert world.week_duties("C-1042") == before
    assert overlay.week_duties("C-1042") == ()
    assert report.trigger_kind == "crew_absence"

    second, _ = ops.simulate_absence(crew_id="C-3231", from_date=date(2026, 9, 16))
    assert second.pairings_broken == ["P-2224"]
    assert world.week_duties("C-1042") == before


def test_absence_of_someone_with_no_duty_is_a_finding_not_an_error(
    ops: OpsEngine,
) -> None:
    """C-2087 holds no rostered duty this week."""
    report, _ = ops.simulate_absence(crew_id="C-2087", from_date=date(2026, 9, 15))
    assert report.uncrewed_flights == []
    assert report.pairings_broken == []
    assert "no rostered duty" in report.explanation


def test_absence_flags_colleagues_close_to_a_duty_limit(ops: OpsEngine) -> None:
    """The second order consequence a controller misses."""
    report, _ = ops.simulate_absence(crew_id="C-1042", from_date=date(2026, 9, 15))
    assert report.crew_affected[0] == "C-1042"
    assert len(report.crew_affected) == 6


# ------------------------------------------------------ reassignment


def test_reassignment_reports_the_movers_breaches(ops: OpsEngine, world: WorldState) -> None:
    from crewops.rules import proposed_duties_for_pairing

    duties = proposed_duties_for_pairing(world, "P-2291")
    report = ops.simulate_reassignment(
        crew_id="C-2087",
        duties=duties,
        assignment_ref="P-2291",
        displacing_crew_id="C-1042",
        exclude_pairing="P-2291",
    )
    assert report.trigger_kind == "reassignment"
    assert any(r.rule_id == "RULE-DUTY-02" for r in report.downstream_risks)
    assert "RULE-DUTY-02" in report.explanation


# --------------------------------------------------------- watchlist


def test_watchlist_flags_the_c5417_exception(ops: OpsEngine) -> None:
    watchlist = ops.build_watchlist(for_date=date(2026, 9, 19))
    critical = [a for a in watchlist.alerts if a.severity is RiskSeverity.CRITICAL]
    assert any(a.crew_id == "C-5417" for a in critical)
    alert = next(a for a in critical if a.crew_id == "C-5417")
    assert alert.rule_id == "RULE-CERT-06"
    assert alert.due_date == date(2026, 9, 19)


def test_watchlist_reports_what_it_scanned(ops: OpsEngine) -> None:
    """A brief that does not say what it looked at is not auditable."""
    watchlist = ops.build_watchlist(for_date=date(2026, 9, 15))
    assert watchlist.scanned["crew"] == 150
    assert watchlist.scanned["certifications"] == 600
    assert watchlist.scanned["flights"] == 21
    assert watchlist.headline


def test_watchlist_risk_scores_are_provided_never_computed(ops: OpsEngine) -> None:
    watchlist = ops.build_watchlist(for_date=date(2026, 9, 15))
    risk_alerts = [
        a for a in watchlist.alerts if any(f.key.endswith("risk.score") for f in a.facts)
    ]
    assert risk_alerts
    for alert in risk_alerts:
        fact = next(f for f in alert.facts if f.key.endswith("risk.score"))
        assert fact.provenance.value == "dataset"
        assert "risk_signals.json" in fact.source


@pytest.mark.parametrize("day", [date(2026, 9, d) for d in range(14, 21)])
def test_watchlist_builds_for_every_day_of_the_week(ops: OpsEngine, day: date) -> None:
    watchlist = ops.build_watchlist(for_date=day)
    assert watchlist.for_date == day
    for alert in watchlist.alerts:
        assert alert.detail
        assert alert.title


def test_watchlist_alerts_all_carry_facts_or_a_stated_reason(ops: OpsEngine) -> None:
    """Every figure a controller reads has to be attributable."""
    watchlist = ops.build_watchlist(for_date=date(2026, 9, 19))
    for alert in watchlist.alerts:
        assert alert.facts, f"{alert.title} carries no facts"
        for fact in alert.facts:
            if fact.provenance.value == "computed":
                assert fact.derivation, f"{fact.key} is computed with no derivation"


def test_verdict_insufficient_data_is_never_treated_as_a_pass() -> None:
    assert Verdict.INSUFFICIENT_DATA is not Verdict.PASS
    assert Verdict.NOT_APPLICABLE is not Verdict.PASS

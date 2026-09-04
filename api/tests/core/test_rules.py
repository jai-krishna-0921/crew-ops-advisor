"""The legality kernel, against the shipped answer keys.

The comparison directions are load-bearing. Each one below flips a headline
answer if it is written the other way round, so each one gets its own test.
"""

from __future__ import annotations

from datetime import date, datetime

import pytest

from crewops.contracts import Verdict
from crewops.domain import WorldState, load_world
from crewops.rules import (
    FDP_BASE_HOURS,
    MAX_DUTY_HOURS_7D,
    MAX_FLIGHT_HOURS_28D,
    MIN_REST_HOURS,
    LegalityEngine,
    fdp_limit,
    proposed_duties_for_pairing,
)


@pytest.fixture(scope="module")
def world() -> WorldState:
    return load_world()


@pytest.fixture(scope="module")
def engine(world: WorldState) -> LegalityEngine:
    return LegalityEngine(world)


# ------------------------------------------------------------- RULE-FDP-01


@pytest.mark.parametrize(
    ("sectors", "limit"),
    [(1, 13.0), (2, 13.0), (3, 12.5), (4, 12.0), (5, 11.5), (6, 11.0), (8, 10.0)],
)
def test_fdp_limit_reduces_half_an_hour_per_sector_beyond_the_second(
    sectors: int, limit: float
) -> None:
    assert fdp_limit(sectors) == limit


def test_fdp_breach_is_strictly_greater_than(engine: LegalityEngine) -> None:
    """A 12.0h FDP against a 12.0h limit is legal.

    DX454-2026-09-17 in scenario S3 is rated 'delay (crew legal)' at exactly
    12.0h against a 12.0h limit. Writing this as `>=` flips that row.
    """
    at_limit = engine.check_fdp(
        crew_id="C-1042",
        duty_date=date(2026, 9, 17),
        sectors=4,
        report=datetime(2026, 9, 17, 1, 30),
        release=datetime(2026, 9, 17, 13, 30),
    )
    assert at_limit.observed == 12.0
    assert at_limit.limit == 12.0
    assert at_limit.verdict is Verdict.PASS

    over = engine.check_fdp(
        crew_id="C-1042",
        duty_date=date(2026, 9, 17),
        sectors=4,
        report=datetime(2026, 9, 17, 1, 30),
        release=datetime(2026, 9, 17, 13, 45),
    )
    assert over.verdict is Verdict.BREACH
    assert "12.25" in over.arithmetic


def test_fdp_trace_writes_out_the_arithmetic(engine: LegalityEngine) -> None:
    trace = engine.check_fdp(
        crew_id="C-1042",
        duty_date=date(2026, 9, 15),
        sectors=3,
        report=datetime(2026, 9, 15, 6, 0),
        release=datetime(2026, 9, 15, 15, 30),
    )
    assert trace.observed == 9.5
    assert trace.limit == 12.5
    assert "9.50" in trace.arithmetic
    assert "12.50" in trace.arithmetic
    assert "3 sectors" in trace.arithmetic


# ------------------------------------------------------------ RULE-DUTY-02


def test_duty_02_breach_is_strictly_greater_than(engine: LegalityEngine) -> None:
    exactly_at_limit = engine.check_duty_window(
        crew_id="C-1042", duty_date=date(2026, 9, 15), total=60.0, prior=50.5, added=9.5
    )
    assert exactly_at_limit.verdict is Verdict.PASS
    assert MAX_DUTY_HOURS_7D == 60.0

    over = engine.check_duty_window(
        crew_id="C-2087", duty_date=date(2026, 9, 15), total=61.33, prior=51.83, added=9.5
    )
    assert over.verdict is Verdict.BREACH
    assert over.margin is not None and over.margin < 0
    assert "51.83" in over.arithmetic
    assert "61.33" in over.arithmetic
    assert "60.00" in over.arithmetic


# ------------------------------------------------------------ RULE-REST-04


def test_rest_breach_is_strictly_less_than(engine: LegalityEngine) -> None:
    """Exactly 12.0h rest is legal."""
    assert MIN_REST_HOURS == 12.0
    exact = engine.check_rest(
        crew_id="C-1042",
        release=datetime(2026, 9, 16, 15, 30),
        next_report=datetime(2026, 9, 17, 3, 30),
        prior_ref="P-2291",
        next_ref="P-2293",
        duty_date=date(2026, 9, 17),
    )
    assert exact.observed == 12.0
    assert exact.verdict is Verdict.PASS

    short = engine.check_rest(
        crew_id="C-1042",
        release=datetime(2026, 9, 16, 15, 30),
        next_report=datetime(2026, 9, 17, 3, 15),
        prior_ref="P-2291",
        next_ref="P-2293",
        duty_date=date(2026, 9, 17),
    )
    assert short.verdict is Verdict.BREACH


def test_earliest_next_report_is_release_plus_twelve(engine: LegalityEngine) -> None:
    """Q23: released 15:30Z on 16 Sep, earliest next report is 03:30Z on 17 Sep."""
    assert engine.earliest_next_report(datetime(2026, 9, 16, 15, 30)) == datetime(
        2026, 9, 17, 3, 30
    )


# ------------------------------------------------------------ RULE-QUAL-05


def test_c2091_is_atr_only_and_fails_qualification_for_a320(
    engine: LegalityEngine, world: WorldState
) -> None:
    member = world.require_crew("C-2091")
    assert member.ratings == ("ATR72",)

    on_a320 = engine.check_qualification(
        crew_id="C-2091", aircraft_type="A320", duty_date=date(2026, 9, 15)
    )
    assert on_a320.verdict is Verdict.BREACH

    on_atr = engine.check_qualification(
        crew_id="C-2091", aircraft_type="ATR72", duty_date=date(2026, 9, 16)
    )
    assert on_atr.verdict is Verdict.PASS


# ------------------------------------------------------------ RULE-CERT-06


def test_certification_valid_to_equal_to_duty_date_is_valid_that_day(
    engine: LegalityEngine,
) -> None:
    """C-5417's recurrent_training expires 2026-09-17: legal on the 17th."""
    on_expiry = engine.check_certifications(crew_id="C-5417", duty_date=date(2026, 9, 17))
    assert on_expiry.verdict is Verdict.PASS

    after = engine.check_certifications(crew_id="C-5417", duty_date=date(2026, 9, 18))
    assert after.verdict is Verdict.BREACH


def test_c5417_is_the_flagged_roster_exception(engine: LegalityEngine, world: WorldState) -> None:
    """Anchor 7: legal on their 16 Sep duty, illegal on their 19 Sep duty."""
    assert len(world.flagged_exceptions) == 1
    flagged = world.flagged_exceptions[0]
    assert flagged.crew_id == "C-5417"
    assert flagged.date == date(2026, 9, 19)
    assert flagged.rule == "RULE-CERT-06"

    dates = [d.duty_date for d in world.week_duties("C-5417")]
    assert date(2026, 9, 16) in dates
    assert date(2026, 9, 19) in dates

    assert engine.check_certifications(crew_id="C-5417", duty_date=date(2026, 9, 16)).verdict is (
        Verdict.PASS
    )
    breach = engine.check_certifications(crew_id="C-5417", duty_date=date(2026, 9, 19))
    assert breach.verdict is Verdict.BREACH
    assert "recurrent_training" in breach.arithmetic
    assert "2026-09-17" in breach.arithmetic


def test_valid_from_is_never_consulted(world: WorldState) -> None:
    """One record has valid_from > valid_to. Reading it would ground a flying crew."""
    broken = [c for c in world.certifications if c.valid_from > c.valid_to]
    assert len(broken) == 1
    assert broken[0].crew_id == "C-2087"
    source = (world.data_dir.parent.parent.parent / "api/src/crewops/rules/engine.py").read_text(
        encoding="utf-8"
    )
    assert ".valid_from" not in source


# ------------------------------------------------------------- RULE-FLT-03


def test_flight_window_never_binds_anywhere_in_this_dataset(world: WorldState) -> None:
    """Max 79.28h against a 100h limit. Implemented, never exercised as a breach."""
    ov = world.overlay()
    peak = max(
        ov.window_hours(c.crew_id, day, days=28, kind="flight")
        for c in world.crew
        for day in world.window_dates_of_week()
    )
    assert peak == pytest.approx(79.28, abs=0.01)
    assert peak < MAX_FLIGHT_HOURS_28D
    assert FDP_BASE_HOURS == 13.0


# ------------------------------------------------- multi day cover assessment


def test_c2087_breaches_duty_02_on_both_days_of_p2291(
    engine: LegalityEngine, world: WorldState
) -> None:
    """Anchor 2. The cumulative add is why day 2 breaches as well as day 1."""
    duties = proposed_duties_for_pairing(world, "P-2291")
    result = engine.assess_cover(
        world.overlay(), crew_id="C-2087", duties=duties, exclude_pairing="P-2291"
    )
    assert result.ok is False
    assert result.issues == (
        "RULE-DUTY-02: would exceed 60h/7d by 1h20m on 2026-09-15 (total 61.33h)",
        "RULE-DUTY-02: would exceed 60h/7d by 1h05m on 2026-09-16 (total 61.08h)",
    )
    assert result.report.overall is Verdict.BREACH
    assert result.report.first_breach_date == date(2026, 9, 15)
    assert len(result.report.per_day) == 2


def test_c3305_passes_day_one_and_breaches_day_two(
    engine: LegalityEngine, world: WorldState
) -> None:
    """Anchor 3. A candidate must be legal on every day of the cover."""
    duties = proposed_duties_for_pairing(world, "P-2291")
    result = engine.assess_cover(
        world.overlay(), crew_id="C-3305", duties=duties, exclude_pairing="P-2291"
    )
    assert result.issues == (
        "RULE-DUTY-02: would exceed 60h/7d by 8h15m on 2026-09-16 (total 68.25h)",
    )
    day1, day2 = sorted(result.report.per_day, key=lambda d: d.duty_date)
    assert day1.duty_date == date(2026, 9, 15)
    assert day1.verdict is Verdict.PASS
    assert day2.verdict is Verdict.BREACH

    duty02 = next(t for t in day1.traces if t.rule_id == "RULE-DUTY-02")
    assert duty02.observed == 59.5
    duty02_day2 = next(t for t in day2.traces if t.rule_id == "RULE-DUTY-02")
    assert duty02_day2.observed == 68.25
    assert duty02_day2.margin_human == "8h15m over the limit"


def test_c3310_covers_p2291_cleanly(engine: LegalityEngine, world: WorldState) -> None:
    """Anchor 4, the legality half."""
    duties = proposed_duties_for_pairing(world, "P-2291")
    result = engine.assess_cover(
        world.overlay(), crew_id="C-3310", duties=duties, exclude_pairing="P-2291"
    )
    assert result.ok is True
    assert result.issues == ()
    assert result.report.overall is Verdict.PASS


def test_c5837_hits_a_downstream_rest_conflict(engine: LegalityEngine, world: WorldState) -> None:
    """Q28. The cover collides with the candidate's own later duty, not an earlier one."""
    duties = proposed_duties_for_pairing(world, "P-2291")
    result = engine.assess_cover(world.overlay(), crew_id="C-5837", duties=duties)
    assert result.issues == (
        "RULE-REST-04: only 10.75h rest before P-2204 on 2026-09-17 (downstream conflict)",
    )


def test_qualification_failure_short_circuits_every_other_reason(
    engine: LegalityEngine, world: WorldState
) -> None:
    """Trap 9. C-1042 covering an ATR pairing shows only the rating failure.

    If the kernel emitted every reason, the text would not match the shipped
    exclusion strings even where the verdict is right.
    """
    duties = proposed_duties_for_pairing(world, "P-2224")
    result = engine.assess_cover(world.overlay(), crew_id="C-1042", duties=duties)
    assert result.issues == ("RULE-QUAL-05: no ATR72 rating",)
    assert result.short_circuited is True


def test_every_day_carries_all_seven_rules(engine: LegalityEngine, world: WorldState) -> None:
    """Silence about a rule is not compliance with it."""
    duties = proposed_duties_for_pairing(world, "P-2291")
    result = engine.assess_cover(
        world.overlay(), crew_id="C-3310", duties=duties, exclude_pairing="P-2291"
    )
    for day in result.report.per_day:
        assert {t.rule_id for t in day.traces} == set(result.report.rules_checked)
        assert len(result.report.rules_checked) == 7


def test_unknown_crew_is_insufficient_data_not_a_pass(
    engine: LegalityEngine, world: WorldState
) -> None:
    duties = proposed_duties_for_pairing(world, "P-2291")
    result = engine.assess_cover(world.overlay(), crew_id="C-9999", duties=duties)
    assert result.ok is False
    assert result.report.overall is Verdict.INSUFFICIENT_DATA
    assert result.report.overall is not Verdict.PASS


def test_the_cumulative_add_is_what_makes_day_two_breach(
    engine: LegalityEngine, world: WorldState
) -> None:
    """Trap 7, stated as an assertion so nobody removes the cumulative term.

    C-3305 day 2: base 48.00h + 9.50h (day 1 cover) + 10.75h (day 2 cover)
    = 68.25h. Counting only day 2's own duty would give 58.75h and pass.
    """
    ov = world.overlay()
    base_day2 = ov.window_hours("C-3305", date(2026, 9, 16), days=7, kind="duty")
    assert base_day2 == 48.0
    assert round(base_day2 + 9.5 + 10.75, 2) == 68.25
    assert round(base_day2 + 10.75, 2) == 58.75

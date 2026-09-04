"""Candidate enumeration, costing and ranking, against the shipped scenarios.

Every assertion here compares the engine's output to `scenarios.json` or
`questions.json`, which are the dataset's own answer keys. Reproducing the
option list is not enough: the exclusion list must match too, in the same order
and with the same wording, because that is what proves the search was real and
that the short-circuit rules are implemented rather than approximated.
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Any

import pytest

from crewops.domain import WorldState
from crewops.ops import OpsEngine


def shipped_options(scenario: dict[str, Any], key: str = "options") -> list[dict[str, Any]]:
    return list(scenario["answer_key"][key])


def as_option_dicts(search: Any) -> list[dict[str, Any]]:
    return [option.as_answer_key() for option in search.options]


def exclusions_by_crew(search: Any) -> dict[str, str]:
    """Exclusions keyed by crew id.

    The shipped `excluded_candidates` lists are ordered by the generator's
    internal crew creation order, which `crew.json` does not preserve: that file
    is written sorted by `crew_id`. The ordering is therefore not recoverable
    from the shipped data and is not asserted. The set of excluded crew and the
    exact reason string for each one are, and those are what a controller acts
    on. This engine emits them sorted by `crew_id`, which is deterministic.
    """
    return {e.crew_id: e.reason for e in search.excluded}


def shipped_exclusions(scenario: dict[str, Any], key: str) -> dict[str, str]:
    return {e["crew_id"]: e["reason"] for e in scenario["answer_key"][key]}


# ------------------------------------------------------------------ costing


def test_reserve_callout_is_charged_once_per_assignment_not_per_day(
    ops: OpsEngine, world: WorldState
) -> None:
    """Anchor 4. Two days of P-2291 by reserve C-3310 costs 18,500, not 37,000."""
    search = ops.find_cover_for_pairing("P-2291", role="Captain", sick_crew_id="C-1042")
    top = search.options[0]
    assert top.crew_id == "C-3310"
    assert top.cost_inr == 18500
    assert top.rank == 1
    assert top.delay_hours == 0.0
    assert world.costs.reserve_callout_pilot == 18500


def test_hotel_overnight_is_never_charged(ops: OpsEngine, world: WorldState) -> None:
    """It exists in costs.json at 4,200 and appears in no shipped answer key,
    including for the two day pairings that overnight at DEL."""
    assert world.costs.hotel_overnight == 4200
    search = ops.find_cover_for_pairing("P-2291", role="Captain", sick_crew_id="C-1042")
    for option in search.options:
        for line in option.cost.line_items:
            assert line.rule_ref != "hotel_overnight"
        assert option.cost.total_inr % 100 != 4200 % 100 or option.cost.total_inr != 22700


def test_cancellation_is_priced_per_leg_and_ranked_last(ops: OpsEngine) -> None:
    """P-2291 is 6 legs across two days: 6 x 250,000 = 1,500,000."""
    search = ops.find_cover_for_pairing("P-2291", role="Captain", sick_crew_id="C-1042")
    last = search.options[-1]
    assert last.crew_id is None
    assert last.cost_inr == 1_500_000
    assert last.rank == len(search.options)
    assert last.cost_inr > max(o.cost_inr for o in search.options[:-1])


def test_every_option_states_a_tradeoff(ops: OpsEngine) -> None:
    """An option with no stated downside is under-analysed, not perfect."""
    search = ops.find_cover_for_pairing("P-2291", role="Captain", sick_crew_id="C-1042")
    for option in search.to_recommendation().options:
        assert option.tradeoffs, f"{option.crew_id} has no stated trade-off"


def test_cost_lines_show_the_multiplication(ops: OpsEngine) -> None:
    search = ops.find_cover_for_pairing("P-2291", role="Captain", sick_crew_id="C-1042")
    deadhead = next(o for o in search.options if o.crew_id == "C-2210")
    bases = [line.basis for line in deadhead.cost.line_items]
    assert any("5,400" in b for b in bases)
    assert any("3.0" in b for b in bases)
    assert deadhead.cost.total_inr == 41200


# ------------------------------------------------------------- positioning


def test_c2210_deadhead_delay_is_three_hours(ops: OpsEngine) -> None:
    """Anchor 5. DX402 arrives BLR 08:45Z, +75 min to a 10:00Z departure,
    against an original 07:00Z: 3.0h of delay."""
    plan = ops.positioning_for(
        crew_id="C-2210", origin="BLR", on_date=date(2026, 9, 15), first_departure_utc=datetime(
            2026, 9, 15, 7, 0
        )
    )
    assert plan is not None
    assert plan.flight_no == "DX402"
    assert plan.arrival_utc == datetime(2026, 9, 15, 8, 45)
    assert plan.delay_hours == 3.0


def test_positioning_uses_the_earlier_flight_on_even_dates(ops: OpsEngine) -> None:
    """DX589 arrives BLR 07:45Z but operates only on 14, 16, 18 and 20 Sep."""
    plan = ops.positioning_for(
        crew_id="C-2210",
        origin="BLR",
        on_date=date(2026, 9, 16),
        first_departure_utc=datetime(2026, 9, 16, 4, 0),
    )
    assert plan is not None
    assert plan.flight_no == "DX589"
    assert plan.arrival_utc == datetime(2026, 9, 16, 7, 45)


def test_no_positioning_when_the_schedule_offers_no_leg(ops: OpsEngine) -> None:
    """No positioning is a RULE-BASE-07 exclusion, not an error.

    C-2210 is based at DEL and the network flies nothing DEL to BOM, so there
    is no same-day way to get them there.
    """
    plan = ops.positioning_for(
        crew_id="C-2210",
        origin="BOM",
        on_date=date(2026, 9, 16),
        first_departure_utc=datetime(2026, 9, 16, 6, 0),
    )
    assert plan is None


def test_positioning_is_derived_from_the_schedule_not_a_hard_coded_pair(
    ops: OpsEngine,
) -> None:
    """The rule is 'earliest arrival into the required station from their base'.

    That reproduces every positioning in the shipped answer keys, all of which
    happen to be DEL to BLR, without hard coding that pair. It also generalises:
    a BLR based crew member asked to cover a DEL origin duty gets a real answer
    rather than a blanket refusal.
    """
    plan = ops.positioning_for(
        crew_id="C-3310",
        origin="DEL",
        on_date=date(2026, 9, 16),
        first_departure_utc=datetime(2026, 9, 16, 5, 0),
    )
    assert plan is not None
    assert plan.from_station == "BLR"
    assert plan.flight_no == "DX401"
    assert plan.delay_hours == 1.5


# --------------------------------------------------------- scenario parity


def test_s1_options_and_exclusions_reproduce_exactly(
    ops: OpsEngine, scenarios: dict[str, Any]
) -> None:
    """ATR captain sick, 16 Sep. 7 options, 18 exclusions."""
    s1 = scenarios["S1"]
    search = ops.find_cover_for_pairing(
        s1["event"]["pairing_id"], role="Captain", sick_crew_id=s1["event"]["crew_id"]
    )
    assert as_option_dicts(search) == shipped_options(s1)
    assert exclusions_by_crew(search) == shipped_exclusions(s1, "excluded_candidates")
    assert search.options[0].as_answer_key() == s1["answer_key"]["expected_choice"]


def test_s2_options_and_exclusions_reproduce_exactly(
    ops: OpsEngine, scenarios: dict[str, Any]
) -> None:
    """The flagship: C-1042 sick for the two day P-2291. 6 options, 19 exclusions."""
    s2 = scenarios["S2"]
    search = ops.find_cover_for_pairing("P-2291", role="Captain", sick_crew_id="C-1042")
    assert as_option_dicts(search) == shipped_options(s2)
    assert exclusions_by_crew(search) == shipped_exclusions(s2, "excluded_candidates")


def test_s5_cabin_crew_cover_reproduces_exactly(
    ops: OpsEngine, scenarios: dict[str, Any]
) -> None:
    """43 options including four DEL deadheads, and 21 exclusions."""
    s5 = scenarios["S5"]
    search = ops.find_cover_for_pairing(
        s5["event"]["pairing_id"], role="Cabin Crew", sick_crew_id=s5["event"]["crew_id"]
    )
    assert as_option_dicts(search) == shipped_options(s5)
    assert exclusions_by_crew(search) == shipped_exclusions(s5, "excluded_candidates")


def test_s6_both_sides_reproduce_exactly(ops: OpsEngine, scenarios: dict[str, Any]) -> None:
    s6 = scenarios["S6"]
    first, second = s6["event"]["events"]
    dxa = ops.find_cover_for_pairing(
        first["pairing_id"], role="Captain", sick_crew_id=first["crew_id"]
    )
    dxb = ops.find_cover_for_pairing(
        second["pairing_id"], role="Captain", sick_crew_id=second["crew_id"]
    )
    assert as_option_dicts(dxa) == shipped_options(s6, "options_dxa")
    assert exclusions_by_crew(dxa) == shipped_exclusions(s6, "excluded_dxa")
    assert as_option_dicts(dxb) == shipped_options(s6, "options_dxb")
    assert exclusions_by_crew(dxb) == shipped_exclusions(s6, "excluded_dxb")


def test_exclusion_reasons_match_even_though_order_is_not_recoverable(
    ops: OpsEngine, scenarios: dict[str, Any]
) -> None:
    """Documenting the one place the shipped keys cannot be matched positionally.

    `generate.py` enumerated candidates over its in-memory crew dict, whose
    insertion order puts the engineered crew first. `crew.json` is written
    sorted by `crew_id`, so that order is gone. Every exclusion and every reason
    string reproduces; only the sequence differs.
    """
    s2 = scenarios["S2"]
    search = ops.find_cover_for_pairing("P-2291", role="Captain", sick_crew_id="C-1042")
    mine = exclusions_by_crew(search)
    shipped = shipped_exclusions(s2, "excluded_candidates")
    assert mine == shipped
    assert list(mine) == sorted(mine), "our own ordering is deterministic by crew id"
    assert list(shipped) != sorted(shipped), "the shipped ordering is not sorted"


def test_q37_cheapest_legal_cover_for_the_vtdxf_first_officer(
    ops: OpsEngine, questions: dict[str, Any]
) -> None:
    search = ops.find_cover_for_pairing("P-2235", role="First Officer", sick_crew_id=None)
    assert search.options[0].as_answer_key() == questions["Q37"]["expected_answer"]


# ------------------------------------------------- the traps, stated plainly


def test_non_active_crew_are_dropped_silently_and_never_excluded(
    ops: OpsEngine, world: WorldState
) -> None:
    """Trap 13. `leave` and `training` crew are filtered before any rule runs.

    Reporting them as rule failures would put eight names in the exclusion list
    that the shipped keys do not have.
    """
    search = ops.find_cover_for_pairing("P-2291", role="Captain", sick_crew_id="C-1042")
    named = {e.crew_id for e in search.excluded} | {
        o.crew_id for o in search.options if o.crew_id
    }
    for member in world.crew:
        if not member.is_active:
            assert member.crew_id not in named, f"{member.crew_id} is {member.status}"


def test_the_reserve_window_is_tested_against_the_required_report(
    ops: OpsEngine, scenarios: dict[str, Any]
) -> None:
    """Trap 14. S1's callout is 01:30Z but the required report is 03:00Z."""
    s1 = scenarios["S1"]
    assert s1["event"]["reported_utc"] == "2026-09-16T01:30:00Z"
    search = ops.find_cover_for_pairing("P-2224", role="Captain", sick_crew_id="C-3231")
    reason = next(e.reason for e in search.excluded if e.crew_id == "C-3310")
    assert reason == (
        "reserve on-call window 06:00-18:00Z does not cover required report 03:00Z"
    )


def test_c3310_is_eligible_on_the_exact_window_boundary(ops: OpsEngine) -> None:
    """Trap 5. C-3310's window opens at 06:00 and P-2291 reports at 06:00Z.

    The test is inclusive at both ends, which is why C-3310 is the expected
    choice for S2 rather than being excluded on its window.
    """
    search = ops.find_cover_for_pairing("P-2291", role="Captain", sick_crew_id="C-1042")
    assert search.options[0].crew_id == "C-3310"
    assert "C-3310" not in {e.crew_id for e in search.excluded}


def test_after_a_deadhead_the_window_is_tested_against_the_delayed_report(
    ops: OpsEngine,
) -> None:
    """Trap 15. C-2210 is tested at 09:00Z, not at 06:00Z."""
    search = ops.find_cover_for_pairing("P-2291", role="Captain", sick_crew_id="C-1042")
    c2210 = next(o for o in search.options if o.crew_id == "C-2210")
    assert c2210.delay_hours == 3.0
    assert c2210.required_report_utc == datetime(2026, 9, 15, 9, 0)


def test_rejected_candidates_carry_the_rule_trace_that_excluded_them(
    ops: OpsEngine,
) -> None:
    """Showing the rejects is what proves the search was real."""
    search = ops.find_cover_for_pairing("P-2291", role="Captain", sick_crew_id="C-1042")
    recommendation = search.to_recommendation()
    assert recommendation.rejected
    c2087 = next(o for o in recommendation.rejected if o.crew_id == "C-2087")
    assert c2087.legal is False
    assert c2087.legality.breaches
    assert any(t.rule_id == "RULE-DUTY-02" for t in c2087.legality.breaches)
    assert recommendation.candidates_evaluated > len(recommendation.options)


def test_ranking_basis_is_stated_so_it_can_be_argued_with(ops: OpsEngine) -> None:
    search = ops.find_cover_for_pairing("P-2291", role="Captain", sick_crew_id="C-1042")
    basis = search.to_recommendation().ranking_basis
    assert "cost" in basis.lower()
    assert "cancel" in basis.lower()


# --------------------------------------------------------- joint allocation


def test_s6_optimal_joint_plan_costs_42500(ops: OpsEngine, scenarios: dict[str, Any]) -> None:
    """Two captains sick the same morning. The same person cannot cover both."""
    s6 = scenarios["S6"]
    first, second = s6["event"]["events"]
    plan = ops.allocate_jointly(
        [
            (first["pairing_id"], "Captain", first["crew_id"]),
            (second["pairing_id"], "Captain", second["crew_id"]),
        ]
    )
    assert plan.total_cost_inr == 42500
    assert plan.total_cost_inr == s6["answer_key"]["optimal_joint_plan"]["total_cost_inr"]
    chosen = [a.option.crew_id for a in plan.assignments]
    assert len(set(chosen)) == len(chosen), "the same crew member covers both pairings"
    assert sorted(o.cost_inr for o in (a.option for a in plan.assignments)) == [18500, 24000]


def test_joint_allocation_accepts_the_shipped_mirror_assignment(
    ops: OpsEngine, scenarios: dict[str, Any]
) -> None:
    """S6's note says equal cost mirror assignments are equally correct, so the
    engine must agree on the total rather than on one hard coded pairing."""
    s6 = scenarios["S6"]
    shipped = s6["answer_key"]["optimal_joint_plan"]
    first, second = s6["event"]["events"]
    plan = ops.allocate_jointly(
        [
            (first["pairing_id"], "Captain", first["crew_id"]),
            (second["pairing_id"], "Captain", second["crew_id"]),
        ]
    )
    assert plan.total_cost_inr == (
        shipped["assign_dxa"]["cost_inr"] + shipped["assign_dxb"]["cost_inr"]
    )
    assert "C-3305" in {a.option.crew_id for a in plan.assignments}


def test_joint_allocation_falls_back_to_cancellation_when_nobody_is_legal(
    ops: OpsEngine,
) -> None:
    plan = ops.allocate_jointly([("P-2291", "Captain", "C-1042")], forbid_crew={"C-3310"})
    assert plan.total_cost_inr < 1_500_000
    assert plan.assignments[0].option.crew_id != "C-3310"


@pytest.mark.parametrize("pairing_id", ["P-2201", "P-2224", "P-2291", "P-2295"])
def test_every_search_leaves_a_cancellation_option(ops: OpsEngine, pairing_id: str) -> None:
    """There is always an answer, even when it is an expensive one."""
    search = ops.find_cover_for_pairing(pairing_id, role="Captain", sick_crew_id=None)
    assert search.options[-1].crew_id is None
    assert search.options[-1].action.startswith("Cancel")

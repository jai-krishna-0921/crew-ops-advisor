"""Pricing a cover option from `costs.json`.

Three things about this rate card catch people out, and all three are settled
by the shipped answer keys rather than by the problem statement:

1. **Callout is charged once per assignment, not per duty day.** Covering the
   two day P-2291 with reserve C-3310 costs 18,500, not 37,000.
2. **`hotel_overnight` (4,200) is never charged**, in any shipped answer key,
   including for the two day pairings that overnight at DEL. It is carried in
   the rate card and deliberately not applied. Charging it would move every
   multi day cover price away from the keys.
3. **There is no overtime rate**, despite the problem-statement PDF describing
   `costs.json` as "callout, overtime, deadhead and penalty rates".

Cancellation is priced **per leg** and is always ranked last regardless of
cost, which is a ranking decision rather than a pricing one. See `ranking.py`.
"""

from __future__ import annotations

from crewops.contracts.ops import CostBreakdown, CostLine
from crewops.domain import Costs, Crew
from crewops.rules import Positioning


def _inr(amount: float) -> str:
    return f"INR {amount:,.0f}"


def price_cover(
    costs: Costs,
    crew: Crew,
    *,
    is_reserve: bool,
    positioning: Positioning | None = None,
    duty_days: int = 1,
) -> CostBreakdown:
    """The full price of putting this crew member on this assignment."""
    lines: list[CostLine] = []

    callout = costs.callout(is_reserve=is_reserve, is_pilot=crew.is_pilot)
    key = costs.callout_key(is_reserve=is_reserve, is_pilot=crew.is_pilot)
    source = "reserve callout" if is_reserve else "day-off callout"
    lines.append(
        CostLine(
            label=f"{source.capitalize()} for a {crew.rank}",
            amount_inr=float(callout),
            basis=(
                f"1 assignment x {_inr(callout)} = {_inr(callout)} "
                f"(charged once for the whole cover, not per duty day; "
                f"{duty_days} duty day{'s' if duty_days != 1 else ''})"
            ),
            rule_ref=key,
        )
    )

    if positioning is not None:
        lines.append(
            CostLine(
                label=f"Deadhead positioning {positioning.from_station} to "
                f"{positioning.to_station}",
                amount_inr=float(costs.deadhead_positioning),
                basis=(
                    f"1 positioning on {positioning.flight_no} x "
                    f"{_inr(costs.deadhead_positioning)} = "
                    f"{_inr(costs.deadhead_positioning)}"
                ),
                rule_ref="deadhead_positioning",
            )
        )
        if positioning.delay_hours > 0:
            delay_cost = round(positioning.delay_hours * costs.delay_cost_per_duty_hour)
            lines.append(
                CostLine(
                    label="Delay to the first departure",
                    amount_inr=float(delay_cost),
                    basis=(
                        f"{positioning.delay_hours}h x "
                        f"{_inr(costs.delay_cost_per_duty_hour)}/h = {_inr(delay_cost)}"
                    ),
                    rule_ref="delay_cost_per_duty_hour",
                )
            )

    total = float(sum(line.amount_inr for line in lines))
    note = (
        "hotel_overnight is in costs.json at "
        f"{_inr(costs.hotel_overnight)} but is charged in no shipped answer key, "
        "including for the DEL overnight, so it is not applied here."
        if duty_days > 1
        else None
    )
    return CostBreakdown(line_items=lines, total_inr=total, note=note)


def price_cancellation(costs: Costs, *, legs: int) -> CostBreakdown:
    """Cancellation is per leg. Six legs of P-2291 is 1,500,000, not 250,000."""
    total = costs.cancellation_per_flight * legs
    return CostBreakdown(
        line_items=[
            CostLine(
                label=f"Cancel {legs} flight{'s' if legs != 1 else ''}",
                amount_inr=float(total),
                basis=(
                    f"{legs} leg{'s' if legs != 1 else ''} x "
                    f"{_inr(costs.cancellation_per_flight)}/leg = {_inr(total)}"
                ),
                rule_ref="cancellation_per_flight",
            )
        ],
        total_inr=float(total),
        note="Priced per leg, not per pairing.",
    )


def price_crew_set(costs: Costs, ranks: list[str], *, is_reserve: bool = True) -> CostBreakdown:
    """A whole complement called out at once, as in the S4 partial re-crew.

    Two pilots plus four cabin crew from reserve is
    `2 x 18,500 + 4 x 9,500 = 75,000`.
    """
    lines: list[CostLine] = []
    pilots = [r for r in ranks if r in {"Captain", "First Officer"}]
    cabin = [r for r in ranks if r not in {"Captain", "First Officer"}]
    for group, is_pilot in ((pilots, True), (cabin, False)):
        if not group:
            continue
        rate = costs.callout(is_reserve=is_reserve, is_pilot=is_pilot)
        lines.append(
            CostLine(
                label=f"{len(group)} x {'pilot' if is_pilot else 'cabin crew'} callout",
                amount_inr=float(rate * len(group)),
                basis=f"{len(group)} x {_inr(rate)} = {_inr(rate * len(group))}",
                rule_ref=costs.callout_key(is_reserve=is_reserve, is_pilot=is_pilot),
            )
        )
    return CostBreakdown(
        line_items=lines, total_inr=float(sum(line.amount_inr for line in lines))
    )


__all__ = ["price_cancellation", "price_cover", "price_crew_set"]

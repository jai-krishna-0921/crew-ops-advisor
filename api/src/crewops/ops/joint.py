"""Allocating scarce cover across simultaneous gaps.

Two captains calling in sick on the same morning is not two independent
problems. There is one reserve captain whose window covers both early reports,
and assigning them to one pairing removes them from the other. The allocation
minimises total cost across all gaps with a distinctness constraint.

Ties are real and are not broken arbitrarily in the shipped key: S6's own note
says equal cost mirror assignments, swapping which pairing each candidate
covers, are equally correct. So `alternatives` carries the other optimal plans
rather than pretending there is one right answer.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from itertools import product

from crewops.ops.candidates import CoverSearch, RankedOption


@dataclass(frozen=True)
class Assignment:
    """One gap and the option chosen to fill it."""

    assignment_ref: str
    option: RankedOption


@dataclass(frozen=True)
class JointPlan:
    """The cheapest legal allocation across every gap, plus the equal cost ties."""

    assignments: tuple[Assignment, ...]
    total_cost_inr: int
    alternatives: tuple[tuple[Assignment, ...], ...] = ()
    note: str = ""

    @property
    def crew_used(self) -> tuple[str, ...]:
        return tuple(a.option.crew_id for a in self.assignments if a.option.crew_id)


#: How many combinations to enumerate before falling back to a greedy pass.
#: Two gaps of 13 options each is 169 pairs; the guard exists so that a future
#: caller with many gaps degrades rather than hangs.
MAX_COMBINATIONS = 200_000


def allocate(searches: Sequence[CoverSearch]) -> JointPlan:
    """Minimise total cost across the gaps, never using the same person twice.

    Cancellation is always available for every gap, so a plan always exists.
    """
    if not searches:
        raise ValueError("Joint allocation needs at least one gap to fill")

    choices = [_viable(search) for search in searches]
    total_combinations = 1
    for group in choices:
        total_combinations *= len(group)
    if total_combinations > MAX_COMBINATIONS:
        return _greedy(searches, choices)

    best_cost: int | None = None
    best: list[tuple[Assignment, ...]] = []
    for combination in product(*choices):
        used = [o.crew_id for o in combination if o.crew_id]
        if len(set(used)) != len(used):
            continue
        cost = sum(o.cost_inr for o in combination)
        if best_cost is None or cost < best_cost:
            best_cost = cost
            best = [_assignments(searches, combination)]
        elif cost == best_cost:
            best.append(_assignments(searches, combination))

    if best_cost is None:  # pragma: no cover - cancellation always makes this reachable
        return _greedy(searches, choices)

    note = (
        f"{len(best)} allocations tie at INR {best_cost:,}. "
        "Equal cost mirror assignments, swapping which gap each candidate "
        "covers, are equally correct."
        if len(best) > 1
        else "One allocation is strictly cheapest."
    )
    return JointPlan(
        assignments=best[0],
        total_cost_inr=best_cost,
        alternatives=tuple(best[1:]),
        note=note,
    )


def _viable(search: CoverSearch) -> list[RankedOption]:
    """Every legal crew option plus cancellation, which is always the fallback."""
    crew_options = [o for o in search.options if o.crew_id is not None]
    cancellation = [o for o in search.options if o.crew_id is None]
    return crew_options + cancellation


def _assignments(
    searches: Sequence[CoverSearch], combination: Sequence[RankedOption]
) -> tuple[Assignment, ...]:
    return tuple(
        Assignment(assignment_ref=search.assignment_ref, option=option)
        for search, option in zip(searches, combination, strict=True)
    )


def _greedy(
    searches: Sequence[CoverSearch], choices: Sequence[list[RankedOption]]
) -> JointPlan:
    """Fallback for a gap count the exhaustive search cannot enumerate.

    Fills the most constrained gap first, which is the order a controller would
    work in. It is a heuristic and says so.
    """
    order = sorted(range(len(searches)), key=lambda i: len(choices[i]))
    taken: set[str] = set()
    chosen: dict[int, RankedOption] = {}
    for index in order:
        for option in choices[index]:
            if option.crew_id is None or option.crew_id not in taken:
                chosen[index] = option
                if option.crew_id:
                    taken.add(option.crew_id)
                break
    picked = [chosen[i] for i in range(len(searches))]
    return JointPlan(
        assignments=_assignments(searches, picked),
        total_cost_inr=sum(o.cost_inr for o in picked),
        note=(
            "Greedy allocation, most constrained gap first: the number of "
            "combinations exceeded the exhaustive search limit, so this is a "
            "good plan rather than a proven optimal one."
        ),
    )


__all__ = ["MAX_COMBINATIONS", "Assignment", "JointPlan", "allocate"]

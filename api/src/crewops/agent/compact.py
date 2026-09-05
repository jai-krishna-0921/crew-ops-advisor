"""What the model is shown of a tool payload, when the payload is enormous.

MEASURED, NOT GUESSED. `find_cover_options(pairing_id="P-2291",
include_rejected=True)` serialises to 223,156 characters. The budget handed to
the model is 6,000. Every tier 3 turn therefore gave the model rank 1, part of
rank 2, and the string "...[truncated]", and then asked it to write about five
options and a cancellation.

That single fact explains three separate complaints:

    "A tool result was capped for the prompt budget."   every recommendation
    "This answer needed one correction pass ..."        most of them
    36 seconds, budget exceeded                         some of them

The correction pass is the tell. Writing from a blob that stops inside option
two, the model reaches for the `facts` channel and the rejected count, gets a
figure slightly wrong, and the verifier sends it back. One repair is one extra
model round trip, which on a slow provider is most of the 30 second budget.

RAISING THE CAP WOULD BE THE WRONG FIX. 223KB of per-rule per-day arithmetic
buries the prompt and costs more time than it saves. The model does not need
the traces: the interface renders them structurally beside the prose, the
verifier checks them from the full envelope, and `prompts.py` already tells the
model not to restate a table it was handed. What the model needs is every
option's identity, verdict, price and reason. Complete, and small.

So a large payload is COMPACTED rather than CUT. Nothing goes that the prose
has to name. What goes is exactly what the prose must never say.

The full envelope is untouched everywhere else: the verifier attests against
it, the HTTP layer serves it, and the evidence drawer renders it.
"""

from __future__ import annotations

from typing import Any, Final

from crewops.contracts import (
    CoverOption,
    JointPlan,
    LegalityReport,
    Recommendation,
    Verdict,
)

__all__ = ["compacts", "model_view"]


def _dump(value: Any) -> Any:
    return value.model_dump(mode="json") if hasattr(value, "model_dump") else value


def _legality(report: LegalityReport | None) -> dict[str, Any]:
    """The verdict and the rules that bind it, never the working.

    A breach with no rule named is not an explanation, and the arithmetic
    behind it is drawn on screen as its own card. Both halves of that matter:
    keeping the rule ids is what lets the prose say WHY, and dropping the
    traces is what stops it reciting fourteen calculations it was told not to.
    """
    if report is None:
        return {}
    breaches = [
        {
            "rule_id": trace.rule_id,
            "duty_date": str(trace.duty_date) if trace.duty_date else None,
            "margin": trace.margin_human,
        }
        for trace in report.breaches
    ]
    return {
        "overall": report.overall.value,
        "days_checked": len(report.per_day),
        "rules_checked": list(report.rules_checked),
        "breaches": breaches,
    }


def _option(option: CoverOption) -> dict[str, Any]:
    return {
        "rank": option.rank,
        "kind": option.kind.value,
        "action": option.action,
        "crew_id": option.crew_id,
        "crew_name": option.crew_name,
        "crew_base": option.crew_base,
        "crew_rank": option.crew_rank,
        "legal": option.legal,
        "cost_inr": option.cost.total_inr,
        "coverage_summary": option.coverage_summary,
        "covered_flights": list(option.covered_flights),
        "uncovered_flights": list(option.uncovered_flights),
        "reachable": option.reachable,
        "reachability_minutes": option.reachability_minutes,
        "delay_minutes": option.delay_minutes,
        "reasoning": option.reasoning,
        "tradeoffs": list(option.tradeoffs),
        "legality": _legality(option.legality),
    }


def _rejected(option: CoverOption) -> dict[str, Any]:
    """A reject is worth carrying only for the reason it was rejected.

    When a rule bound, the rule id and the margin ARE the reason, and the
    sentence version of it is the single largest thing left in this view: 19
    rejects times a full sentence each. When nothing bound, the exclusion was
    a feasibility issue (out of base, unreachable in time, wrong rating) and
    the sentence is the only place that says so, so it stays.
    """
    legality = _legality(option.legality)
    breaches = legality.get("breaches", [])
    view: dict[str, Any] = {
        "crew_id": option.crew_id,
        "crew_rank": option.crew_rank,
        "crew_base": option.crew_base,
        "breaches": breaches,
    }
    if not breaches:
        view["reason"] = option.reasoning
    return view


def _recommendation(payload: Recommendation) -> dict[str, Any]:
    view: dict[str, Any] = {
        "situation": payload.situation,
        "ranking_basis": payload.ranking_basis,
        "candidates_evaluated": payload.candidates_evaluated,
        "covering_for": payload.covering_for,
        "role": payload.role,
        "options": [_option(option) for option in payload.options],
        "rejected": [_rejected(option) for option in payload.rejected],
    }
    if payload.notification_draft:
        view["notification_draft"] = payload.notification_draft
    if payload.joint_plan is not None:
        view["joint_plan"] = _joint(payload.joint_plan)
    if payload.impact is not None:
        view["impact"] = _dump(payload.impact)
    return view


def _joint(plan: JointPlan) -> dict[str, Any]:
    return {
        "objective": plan.objective,
        "feasible": plan.feasible,
        "gaps_covered": list(plan.gaps_covered),
        "gaps_uncovered": list(plan.gaps_uncovered),
        "total_inr": plan.total_cost.total_inr,
        "contention": list(plan.contention),
        "why_infeasible": plan.why_infeasible,
        "assignments": [_option(option) for option in plan.assignments],
    }


def _report(payload: LegalityReport) -> dict[str, Any]:
    """A legality report keeps its verdict per day and loses the working.

    The one figure the prose is entitled to quote from a breach is the margin,
    and `margin` survives in `_legality`. Everything else on a `RuleTrace` is
    the calculation, which the rule cards draw in full.
    """
    view = _legality(payload)
    view["crew_id"] = payload.crew_id
    view["assignment_ref"] = payload.assignment_ref
    view["per_day"] = [
        {"duty_date": str(day.duty_date), "verdict": day.verdict.value}
        for day in payload.per_day
    ]
    view["is_legal"] = payload.overall is Verdict.PASS
    return view


#: The payload types `model_view` knows how to shrink. A type that is not here
#: is returned unchanged and falls back to the raw cap, which is the right
#: default: a compaction nobody wrote is a place for the model's view and the
#: screen's view to drift apart silently.
_COMPACTED: Final = (Recommendation, JointPlan, LegalityReport)


def compacts(payload: Any) -> bool:
    """True when `model_view` will shrink this payload rather than pass it on.

    The caller needs to know which of the two budgets applies, and asking the
    question directly is clearer than comparing the result against the input.
    """
    return isinstance(payload, _COMPACTED)


def model_view(payload: Any) -> Any:
    """The payload as the model should see it.

    Only the shapes that are actually large are compacted. Everything else is
    returned as it was, because a compaction nobody needed is a place for the
    model's view and the screen's view to drift apart.
    """
    if isinstance(payload, Recommendation):
        return _recommendation(payload)
    if isinstance(payload, JointPlan):
        return _joint(payload)
    if isinstance(payload, LegalityReport):
        return _report(payload)
    return _dump(payload)

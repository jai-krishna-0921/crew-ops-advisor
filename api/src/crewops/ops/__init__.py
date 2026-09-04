"""The operations engine: search, costing, ranking, simulation, watchlist.

No language model is reachable from this package. Read `CLAUDE.md` in this
directory before editing: the enumeration order, the cumulative duty add and
the two delay models are load-bearing against the shipped answer keys.
"""

from crewops.ops.candidates import (
    RANKING_BASIS,
    RULES_CHECKED,
    CandidateSearcher,
    CoverSearch,
    ExcludedCandidate,
    RankedOption,
    option_to_cover_option,
)
from crewops.ops.costing import price_cancellation, price_cover, price_crew_set
from crewops.ops.disruption import (
    CLOSURE_ACTION_INFEASIBLE,
    CLOSURE_ACTION_LEGAL,
    REOPEN_TURNAROUND_MINUTES,
    ClosureAssessment,
    ClosureResult,
    DelayResult,
    DisruptionSimulator,
)
from crewops.ops.engine import OpsEngine
from crewops.ops.joint import Assignment, JointPlan, allocate
from crewops.ops.positioning import (
    POSITIONING_LEAD_MINUTES,
    plan_positioning,
    positioning_options,
)
from crewops.ops.watchlist import (
    CERT_HORIZON_DAYS,
    CRITICAL_HEADROOM_HOURS,
    HIGH_RISK_THRESHOLD,
    TIGHT_HEADROOM_HOURS,
    WatchlistBuilder,
)

__all__ = [
    "CERT_HORIZON_DAYS",
    "CLOSURE_ACTION_INFEASIBLE",
    "CLOSURE_ACTION_LEGAL",
    "CRITICAL_HEADROOM_HOURS",
    "HIGH_RISK_THRESHOLD",
    "POSITIONING_LEAD_MINUTES",
    "RANKING_BASIS",
    "REOPEN_TURNAROUND_MINUTES",
    "RULES_CHECKED",
    "TIGHT_HEADROOM_HOURS",
    "Assignment",
    "CandidateSearcher",
    "ClosureAssessment",
    "ClosureResult",
    "CoverSearch",
    "DelayResult",
    "DisruptionSimulator",
    "ExcludedCandidate",
    "JointPlan",
    "OpsEngine",
    "RankedOption",
    "WatchlistBuilder",
    "allocate",
    "option_to_cover_option",
    "plan_positioning",
    "positioning_options",
    "price_cancellation",
    "price_cover",
    "price_crew_set",
]

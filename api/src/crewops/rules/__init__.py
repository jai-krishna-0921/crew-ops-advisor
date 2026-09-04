"""The legality kernel. Seven rules, deterministic, no language model, ever.

Read `CLAUDE.md` in this directory before editing anything here. The comparison
directions and the cumulative add are load-bearing, and each has a test whose
only job is to stop someone "simplifying" it.
"""

from crewops.rules.engine import (
    CoverAssessment,
    LegalityEngine,
    Positioning,
    ProposedDuty,
    proposed_duties_for_pairing,
    proposed_duty_from_flights,
)
from crewops.rules.limits import (
    DUTY_WINDOW_DAYS,
    EPSILON,
    FDP_BASE_HOURS,
    FDP_FREE_SECTORS,
    FDP_REDUCTION_PER_EXTRA_SECTOR,
    FLIGHT_WINDOW_DAYS,
    MAX_DUTY_HOURS_7D,
    MAX_FLIGHT_HOURS_28D,
    MIN_REST_HOURS,
    RULE_TITLES,
    fdp_limit,
)

__all__ = [
    "DUTY_WINDOW_DAYS",
    "EPSILON",
    "FDP_BASE_HOURS",
    "FDP_FREE_SECTORS",
    "FDP_REDUCTION_PER_EXTRA_SECTOR",
    "FLIGHT_WINDOW_DAYS",
    "MAX_DUTY_HOURS_7D",
    "MAX_FLIGHT_HOURS_28D",
    "MIN_REST_HOURS",
    "RULE_TITLES",
    "CoverAssessment",
    "LegalityEngine",
    "Positioning",
    "ProposedDuty",
    "fdp_limit",
    "proposed_duties_for_pairing",
    "proposed_duty_from_flights",
]

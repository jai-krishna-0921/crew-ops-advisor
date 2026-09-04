"""The seven rules' constants and the one formula that is not a constant.

Values are the shipped `rules.json` params, restated here so the arithmetic is
readable at the point of use. `LegalityEngine` reads the live values off the
loaded `RuleBook` and falls back to these, so a change to `rules.json` is
honoured rather than silently ignored.
"""

from __future__ import annotations

#: RULE-FDP-01
FDP_BASE_HOURS = 13.0
FDP_REDUCTION_PER_EXTRA_SECTOR = 0.5
FDP_FREE_SECTORS = 2

#: RULE-DUTY-02
MAX_DUTY_HOURS_7D = 60.0
DUTY_WINDOW_DAYS = 7

#: RULE-FLT-03
MAX_FLIGHT_HOURS_28D = 100.0
FLIGHT_WINDOW_DAYS = 28

#: RULE-REST-04
MIN_REST_HOURS = 12.0

#: Float slack, matching the reference implementation that produced the answer
#: keys. Comparisons are `observed > limit + EPSILON` and `rest < limit -
#: EPSILON`, so a value sitting exactly on a limit is legal in both directions.
EPSILON = 1e-6

RULE_TITLES: dict[str, str] = {
    "RULE-FDP-01": "Maximum flight duty period",
    "RULE-DUTY-02": "Maximum duty hours per 7 calendar days",
    "RULE-FLT-03": "Maximum block hours per 28 calendar days",
    "RULE-REST-04": "Minimum rest between duties",
    "RULE-QUAL-05": "Aircraft type rating",
    "RULE-CERT-06": "Certification validity",
    "RULE-BASE-07": "Base and deadhead positioning",
}


def fdp_limit(
    sectors: int,
    *,
    base_hours: float = FDP_BASE_HOURS,
    reduction: float = FDP_REDUCTION_PER_EXTRA_SECTOR,
    free_sectors: int = FDP_FREE_SECTORS,
) -> float:
    """`13.0 - 0.5 * max(0, sectors - 2)`.

    Dropping a leg from a duty **raises** this limit, which is why a partial
    re-crew has to recompute it rather than reuse the original: four sectors at
    12.0h becomes three sectors at 12.5h.
    """
    return base_hours - reduction * max(0, sectors - free_sectors)


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
    "fdp_limit",
]

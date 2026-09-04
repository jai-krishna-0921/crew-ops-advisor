"""Intent matching for the offline path.

Pattern matching over the question shapes in the shipped `questions.json`. It
is deliberately narrow: when nothing matches, it abstains cleanly rather than
guessing. This is demo insurance and a proof that the facts come from code
rather than from the model, not a second product, and it must not grow into
one.

Each `Intent` names the tools it will run and the entities it needs. A rule
that matches but is missing a required entity produces a *specific* abstention
("name the crew member") instead of a generic one, which is more useful than
anything a fuzzy match could have produced.
"""

from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Any, Final

from crewops.resolve.triage import Entities

__all__ = ["INTENTS", "Intent", "PlannedCall", "match_intent"]


@dataclass(frozen=True, slots=True)
class PlannedCall:
    """One tool call the offline planner intends to make."""

    tool: str
    args: dict[str, Any]


@dataclass(frozen=True, slots=True)
class Intent:
    """A question shape the offline path knows how to answer."""

    name: str
    tier: int
    patterns: tuple[re.Pattern[str], ...]
    build: Callable[[Entities, datetime], list[PlannedCall]]
    requires: tuple[str, ...] = ()
    missing_hint: str = ""
    template: str = "generic"
    priority: int = 0
    facts_needed: tuple[str, ...] = field(default_factory=tuple)

    def matches(self, question: str) -> bool:
        return any(pattern.search(question) for pattern in self.patterns)

    def missing(self, entities: Entities) -> list[str]:
        gaps: list[str] = []
        for requirement in self.requires:
            if requirement == "crew_id" and not entities.crew_ids:
                gaps.append("a crew id, for example C-1042")
            elif requirement == "pairing_id" and not entities.pairing_ids:
                gaps.append("a pairing id, for example P-2291")
            elif requirement == "date" and not entities.dates:
                gaps.append("a date inside 2026-09-14 to 2026-09-20")
            elif requirement == "station" and not entities.stations:
                gaps.append("a station code, for example BLR")
            elif requirement == "rule_id" and not entities.rule_ids:
                gaps.append("a rule id, for example RULE-DUTY-02")
            elif requirement == "flight" and not entities.flight_numbers:
                gaps.append("a flight number, for example DX412")
        return gaps


def _rx(*sources: str) -> tuple[re.Pattern[str], ...]:
    return tuple(re.compile(source, re.IGNORECASE) for source in sources)


def _first_date(entities: Entities, snapshot: datetime) -> date:
    return entities.dates[0] if entities.dates else snapshot.date()


def _report_time(entities: Entities, day: date) -> datetime | None:
    if not entities.times:
        return None
    hour, minute = entities.times[0].split(":")
    return datetime(day.year, day.month, day.day, int(hour), int(minute))


# ---------------------------------------------------------------------------
# The intents, most specific first. `priority` breaks ties when two match.
# ---------------------------------------------------------------------------

INTENTS: Final[tuple[Intent, ...]] = (
    # ------------------------------------------------------------- tier 3
    Intent(
        name="draft_notification",
        tier=3,
        priority=95,
        patterns=_rx(r"\bdraft\b.*\b(?:notification|callout|message|sms)\b"),
        requires=("crew_id",),
        template="notification",
        build=lambda e, s: [
            PlannedCall(
                "draft_notification",
                {
                    "crew_id": e.crew_ids[0],
                    **({"pairing_id": e.pairing_ids[0]} if e.pairing_ids else {}),
                    **(
                        {"flight_numbers": list(e.flight_numbers)}
                        if e.flight_numbers and not e.pairing_ids
                        else {}
                    ),
                },
            )
        ],
    ),
    Intent(
        name="cover_options",
        tier=3,
        priority=90,
        patterns=_rx(
            r"\bwhat should (?:i|we|the desk|crew control)\b",
            r"\branked (?:resolution )?options?\b",
            r"\bresolution options?\b",
            r"\bcheapest legal\b",
            r"\bcheapest way\b",
            r"\boptimal (?:joint )?(?:crewing )?plan\b",
            r"\brecovery plan\b",
            r"\bresolve\b.*\bassignment\b",
            r"\bwhat do i do\b",
            r"\bproduce ranked\b",
        ),
        template="recommendation",
        build=lambda e, s: [
            PlannedCall(
                "find_cover_options",
                {
                    **({"pairing_id": e.pairing_ids[0]} if e.pairing_ids else {}),
                    **(
                        {"flight_numbers": list(e.flight_numbers)}
                        if e.flight_numbers and not e.pairing_ids
                        else {}
                    ),
                    **({"exclude_crew_ids": list(e.crew_ids)} if e.crew_ids else {}),
                    "include_rejected": True,
                },
            )
        ],
    ),
    # ------------------------------------------------------------- tier 2
    Intent(
        name="station_closure",
        tier=2,
        priority=80,
        patterns=_rx(
            r"\bis closed\b", r"\bcloses?\b.*\d{2}:\d{2}", r"\bstation closure\b"
        ),
        requires=("station",),
        template="impact",
        build=lambda e, s: [
            PlannedCall(
                "simulate_station_closure",
                {
                    "station": e.stations[0],
                    "from_time": _closure_bounds(e, s)[0],
                    "to_time": _closure_bounds(e, s)[1],
                },
            )
        ],
    ),
    Intent(
        name="sick_impact",
        tier=2,
        priority=75,
        patterns=_rx(
            r"\bcalls? in sick\b",
            r"\bcalled in sick\b",
            r"\bis sick\b",
            r"\bsick (?:at|on)\b",
            r"\bwhich flights are (?:now |immediately )?uncrewed\b",
            r"\bgoes? unavailable\b",
        ),
        requires=("crew_id",),
        template="impact",
        # Two calls, because a sick call is a situation rather than a question.
        # A controller told that a captain is sick at 01:30Z needs to know both
        # what broke and who can take it, and the answer keys are written for
        # the controller rather than for the sentence: S1, S2 and S6 never say
        # "what should I do" and all three expect `options` and
        # `excluded_candidates`.
        #
        # Measured: the cover search alone takes S1 from wrong at 15% to
        # partial at 88%, with the option crew matching the key exactly, and
        # keeping `simulate_absence` for the uncovered legs takes it to 100%.
        # `for_crew_id` rather than `exclude_crew_ids`: it is the argument that
        # returns the key's option set, because it prices the cover against the
        # duty the sick crew was holding.
        build=lambda e, s: [
            PlannedCall(
                "simulate_absence",
                {"crew_id": e.crew_ids[0], "from_date": _first_date(e, s)},
            ),
            PlannedCall(
                "find_cover_options",
                {
                    "for_crew_id": e.crew_ids[0],
                    "on_date": _first_date(e, s),
                    **({"pairing_id": e.pairing_ids[0]} if e.pairing_ids else {}),
                    "include_rejected": True,
                },
            ),
        ],
    ),
    Intent(
        name="legality",
        tier=2,
        priority=70,
        patterns=_rx(
            r"\bdoes (?:any|anyone|it|the|that)\b.*\bbreach\b",
            r"\bbreach(?:es|ed)?\b",
            r"\bcan\b.*\blegally\b",
            r"\blegally (?:cover|operate|fly|take)\b",
            r"\bis (?:it|this|that) legal\b",
            r"\blegal\?",
            r"\bcover the full\b",
            r"\bcover the pairing\b",
            r"\bis proposed to cover\b",
        ),
        requires=("crew_id",),
        template="legality",
        build=lambda e, s: [
            PlannedCall(
                "check_legality",
                {
                    "crew_id": e.crew_ids[0],
                    **({"pairing_id": e.pairing_ids[0]} if e.pairing_ids else {}),
                    **(
                        {"flight_numbers": list(e.flight_numbers)}
                        if e.flight_numbers and not e.pairing_ids
                        else {}
                    ),
                    **({"on_date": e.dates[0]} if e.dates and not e.pairing_ids else {}),
                },
            )
        ],
    ),
    Intent(
        name="reassignment",
        tier=2,
        priority=65,
        patterns=_rx(r"\bif i move\b", r"\bmove\b.*\bonto\b", r"\breassign\b"),
        requires=("crew_id",),
        template="impact",
        build=lambda e, s: [
            PlannedCall(
                "simulate_reassignment",
                {
                    "crew_id": e.crew_ids[0],
                    **({"pairing_id": e.pairing_ids[0]} if e.pairing_ids else {}),
                    **(
                        {"flight_numbers": list(e.flight_numbers)}
                        if e.flight_numbers and not e.pairing_ids
                        else {}
                    ),
                },
            )
        ],
    ),
    # ------------------------------------------------------------- tier 1
    Intent(
        name="reserves",
        tier=1,
        priority=60,
        patterns=_rx(
            r"\bwho(?:'s| is| are)? on reserve\b",
            r"\breserve (?:crew|captains?|pool)\b",
            r"\blist reserves\b",
            r"\bon-?call windows?\b",
        ),
        template="reserves",
        build=lambda e, s: [
            PlannedCall(
                "list_reserves",
                {
                    "on_date": _first_date(e, s),
                    **({"base": e.stations[0]} if e.stations else {}),
                    **({"rank": _rank_in(e)} if _rank_in(e) else {}),
                    **(
                        {"at_time": _report_time(e, _first_date(e, s))}
                        if e.times
                        else {}
                    ),
                },
            )
        ],
    ),
    Intent(
        name="duty_clocks",
        tier=1,
        priority=55,
        patterns=_rx(
            r"\bduty hours\b",
            r"\bheadroom\b",
            r"\bflight hours\b",
            r"\bhours (?:has|does).*\b(?:left|accrued)\b",
            r"\bduty clock\b",
        ),
        requires=("crew_id",),
        template="clocks",
        build=lambda e, s: [
            PlannedCall("get_duty_clocks", {"crew_id": e.crew_ids[0]}),
        ],
    ),
    Intent(
        name="expiring_certifications",
        tier=1,
        priority=50,
        patterns=_rx(
            r"\bcertifications?\b.*\bexpir",
            r"\bexpir\w*\b.*\bcertification",
            r"\blicence\w*\b.*\bexpir",
            r"\bwhose licence expires\b",
        ),
        template="certifications",
        build=lambda e, s: [
            PlannedCall(
                "find_expiring_certifications",
                {
                    "within_days": _window_days(e),
                    "as_of": _first_date(e, s),
                },
            )
        ],
    ),
    Intent(
        name="pairing",
        tier=1,
        priority=45,
        patterns=_rx(
            r"\bwhich crew are assigned\b",
            r"\bcrew (?:on|for) pairing\b",
            r"\bpairing P-\d+\b",
            r"\bin what roles\b",
        ),
        requires=("pairing_id",),
        template="pairing",
        build=lambda e, s: [PlannedCall("get_pairing", {"pairing_id": e.pairing_ids[0]})],
    ),
    Intent(
        name="rule",
        tier=1,
        priority=44,
        patterns=_rx(r"\bwhat (?:is|does) RULE-", r"\bexplain RULE-", r"\bRULE-[A-Z]"),
        requires=("rule_id",),
        template="rule",
        build=lambda e, s: [PlannedCall("explain_rule", {"rule_id": e.rule_ids[0]})],
    ),
    Intent(
        name="watchlist",
        tier=1,
        priority=42,
        patterns=_rx(r"\bwatchlist\b", r"\bmorning brief\w*\b", r"\bstanding brief"),
        template="watchlist",
        build=lambda e, s: [PlannedCall("get_watchlist", {"for_date": _first_date(e, s)})],
    ),
    Intent(
        name="flights",
        tier=1,
        priority=40,
        patterns=_rx(
            r"\bwhich flights\b",
            r"\bflights (?:depart|leave|arrive|operate|fly)\b",
            r"\bhow many flights\b",
            r"\bdeparting\b",
            r"\bschedule\b",
            r"\bwhich aircraft (?:operates|flies|is (?:on|flying|operating))\b",
            r"\bwhat aircraft (?:operates|flies|is (?:on|flying|operating))\b",
            r"\bhow many seats\b",
        ),
        template="flights",
        build=lambda e, s: [PlannedCall("find_flights", _flight_filters(e, s))],
    ),
    Intent(
        name="crew_detail",
        tier=1,
        priority=35,
        patterns=_rx(
            r"\bwhat is C-\d+",
            r"\bC-\d+'s\b",
            r"\breachability\b",
            r"\bbase and rating\b",
            r"\brisk score\b",
            r"\bdisruption-?risk\b",
        ),
        requires=("crew_id",),
        template="crew",
        build=lambda e, s: [PlannedCall("get_crew_detail", {"crew_id": e.crew_ids[0]})],
    ),
    Intent(
        name="roster",
        tier=1,
        priority=32,
        patterns=_rx(r"\broster(?:ed)?\b", r"\bassignments? (?:for|of) C-\d+"),
        requires=("crew_id",),
        template="roster",
        build=lambda e, s: [PlannedCall("get_roster", {"crew_id": e.crew_ids[0]})],
    ),
    Intent(
        name="find_crew",
        tier=1,
        priority=30,
        patterns=_rx(
            r"\bhow many (?:captains?|first officers?|cabin crew|crew)\b",
            r"\bwho (?:are|is) (?:the )?(?:captains?|first officers?)\b",
            r"\blist (?:the )?crew\b",
            r"\bcrew (?:based|are based) (?:at|in)\b",
        ),
        template="crew_list",
        build=lambda e, s: [
            PlannedCall(
                "find_crew",
                {
                    **({"base": e.stations[0]} if e.stations else {}),
                    **({"rank": _rank_in(e)} if _rank_in(e) else {}),
                    **(
                        {"aircraft_type": e.aircraft_types[0]}
                        if e.aircraft_types
                        else {}
                    ),
                },
            )
        ],
    ),
    Intent(
        name="world_summary",
        tier=1,
        priority=10,
        patterns=_rx(
            r"\bwhat (?:data|dataset)\b",
            r"\bwhich stations\b",
            r"\bnetwork serve\b",
            r"\bsnapshot\b",
            r"\bwhat can you (?:do|answer)\b",
            r"\bhow many (?:crew|pairings|rules|stations)\b",
        ),
        template="world",
        build=lambda _e, _s: [PlannedCall("get_world_summary", {})],
    ),
)


def match_intent(question: str) -> Intent | None:
    """The best matching intent, or None. Highest priority wins."""
    candidates = [intent for intent in INTENTS if intent.matches(question)]
    if not candidates:
        return None
    return max(candidates, key=lambda intent: intent.priority)


# --------------------------------------------------------------- small helpers

def _rank_in(entities: Entities) -> str | None:
    return entities.rank


def _window_days(entities: Entities) -> int:
    for value in entities.numbers:
        if 1 <= value <= 365 and float(value).is_integer():
            return int(value)
    return 30


#: `find_flights` defaults to a 100 row cap. The dataset holds 147 flights
#: total, so a schedule-wide query (no date, route or flight number to narrow
#: it) needs a wider cap or it silently drops rows, which is exactly the kind
#: of question that asks for a superlative ("the longest block time in the
#: schedule") across every leg, not just the ones that fit under 100.
_SCHEDULE_WIDE_LIMIT = 200


def _flight_filters(entities: Entities, _snapshot: datetime) -> dict[str, Any]:
    filters: dict[str, Any] = {}
    if entities.dates:
        filters["on_date"] = entities.dates[0]
    if entities.flight_numbers:
        filters["flight_numbers"] = list(entities.flight_numbers)
    if len(entities.stations) >= 2:
        filters["origin"] = entities.stations[0]
        filters["destination"] = entities.stations[1]
    elif entities.stations:
        filters["origin"] = entities.stations[0]
    if entities.aircraft_types:
        filters["aircraft_type"] = entities.aircraft_types[0]
    if not filters:
        # Nothing narrows this: the question is about the whole schedule, not
        # about "today" (the snapshot date is a demo convenience, not a
        # meaning of an unqualified "which flights"). Widen the cap instead of
        # guessing a date, so a schedule-wide question sees every leg.
        filters["limit"] = _SCHEDULE_WIDE_LIMIT
    return filters


def _closure_bounds(entities: Entities, snapshot: datetime) -> tuple[datetime, datetime]:
    day = _first_date(entities, snapshot)
    times = entities.times
    start = times[0] if times else "00:00"
    end = times[1] if len(times) > 1 else "23:59"
    start_h, start_m = (int(part) for part in start.split(":"))
    end_h, end_m = (int(part) for part in end.split(":"))
    return (
        datetime(day.year, day.month, day.day, start_h, start_m),
        datetime(day.year, day.month, day.day, end_h, end_m),
    )

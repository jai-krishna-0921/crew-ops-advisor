"""Deterministic triage: is this in scope, and which tier is it.

Used by both answer paths. The agent graph's `route` node calls it to short
circuit an out of scope question before spending anything on a model, and the
offline resolver calls it to pick an intent. One classifier, two consumers, no
drift between what the two modes consider answerable.

It is deliberately asymmetric. It abstains only when it is *confident* the
question is outside crew operations on this dataset. Anything ambiguous passes
through to the model, which has more context and can abstain later with a
better reason. A triage step that wrongly refuses is worse than one that
wrongly forwards, because the forward still gets checked downstream.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Final

from crewops.contracts import AbstentionReason

__all__ = [
    "STATIONS",
    "Entities",
    "Triage",
    "extract_entities",
    "triage_question",
]

#: The eight stations the network serves. From `flights.json`, hub BLR.
STATIONS: Final[frozenset[str]] = frozenset(
    {"BLR", "BOM", "CCU", "COK", "DEL", "GOI", "HYD", "MAA"}
)

_CREW_RE: Final = re.compile(r"\bC-\d{2,6}\b", re.IGNORECASE)
_PAIRING_RE: Final = re.compile(r"\bP-\d{2,6}\b", re.IGNORECASE)
_FLIGHT_RE: Final = re.compile(r"\bDX\d{2,4}\b", re.IGNORECASE)
_TAIL_RE: Final = re.compile(r"\bVT-[A-Z]{2,4}\b", re.IGNORECASE)
_RULE_RE: Final = re.compile(r"\bRULE-[A-Z]{2,8}-\d{1,3}\b", re.IGNORECASE)
_ISO_DATE_RE: Final = re.compile(r"\b(\d{4})-(\d{2})-(\d{2})\b")
_LOOSE_DATE_RE: Final = re.compile(
    r"\b(\d{1,2})\s+"
    r"(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Sept|Oct|Nov|Dec)[a-z]*\.?"
    r"(?:\s+(\d{4}))?\b",
    re.IGNORECASE,
)
_TIME_RE: Final = re.compile(r"\b(\d{1,2}):(\d{2})\s*Z?\b")
_AIRCRAFT_RE: Final = re.compile(r"\b(A\d{3}|ATR\s?\d{2})\b", re.IGNORECASE)

_MONTHS: Final[dict[str, int]] = {
    "jan": 1, "feb": 2, "mar": 3, "apr": 4, "may": 5, "jun": 6,
    "jul": 7, "aug": 8, "sep": 9, "sept": 9, "oct": 10, "nov": 11, "dec": 12,
}  # fmt: skip

#: The year the whole dataset lives in. Used only to resolve a bare "15 Sep".
DATASET_YEAR: Final = 2026

# ---------------------------------------------------------------------------
# Vocabulary. Presence of a crew-ops term is what keeps a question in scope.
# ---------------------------------------------------------------------------

_IN_SCOPE_TERMS: Final[frozenset[str]] = frozenset(
    {
        "crew", "captain", "captains", "officer", "cabin", "pilot", "roster",
        "rostered", "pairing", "pairings", "duty", "duties", "flight", "flights",
        "leg", "legs", "sector", "sectors", "reserve", "reserves", "standby",
        "oncall", "on-call", "callout", "sick", "absence", "cover", "covering",
        "uncrewed", "legal", "legality", "breach", "breaches", "rule", "rules",
        "limit", "limits", "rest", "certification", "certifications", "licence",
        "license", "medical", "recurrent", "training", "expiry", "expiring",
        "expires", "rating", "ratings", "qualified", "qualification", "base",
        "deadhead", "position", "positioning", "schedule", "block", "hours",
        "headroom", "fdp", "cost", "cancel", "cancellation", "delay", "delayed",
        "closure", "closed", "passenger", "passengers", "seats", "aircraft",
        "tail", "station", "brief", "briefing", "watchlist", "risk", "notify",
        "notification", "swap", "reassign", "reassignment", "snapshot",
        "seniority", "reachability", "recommend", "option", "options", "plan",
    }
)

#: Confidently out of scope. Each of these names a domain the dataset does not
#: model at all, so no amount of tool calling could produce a grounded answer.
_OUT_OF_SCOPE_TERMS: Final[frozenset[str]] = frozenset(
    {
        "weather", "wind", "turbulence", "storm", "fog", "visibility", "metar",
        "taf", "maintenance", "mel", "engine", "hydraulic", "airworthiness",
        "fuel", "catering", "baggage", "cargo", "booking", "ticket", "fare",
        "revenue", "loyalty", "salary", "payroll", "contract", "union",
        "recruitment", "hiring", "shareholder", "stock", "competitor",
        "covid", "immigration", "visa", "customs", "security", "screening",
    }
)

#: Tier 3 asks for a decision, not a fact.
_TIER3_MARKERS: Final[tuple[re.Pattern[str], ...]] = (
    re.compile(r"\bwhat should (?:i|we|the desk|crew control)\b", re.IGNORECASE),
    re.compile(r"\b(?:ranked|rank) (?:resolution )?options?\b", re.IGNORECASE),
    re.compile(r"\brecommend(?:ation|ations|ed)?\b", re.IGNORECASE),
    re.compile(r"\bbest (?:option|way|plan)\b", re.IGNORECASE),
    re.compile(r"\bcheapest\b", re.IGNORECASE),
    re.compile(r"\boptimal\b", re.IGNORECASE),
    re.compile(r"\bresolve\b", re.IGNORECASE),
    re.compile(r"\brecovery plan\b", re.IGNORECASE),
    re.compile(r"\bdraft the (?:callout )?notification\b", re.IGNORECASE),
    re.compile(r"\bwhat do i do\b", re.IGNORECASE),
    re.compile(r"\bhow (?:do|should) (?:i|we) (?:fix|cover|handle)\b", re.IGNORECASE),
)

#: Tier 2 asks what follows from a change.
_TIER2_MARKERS: Final[tuple[re.Pattern[str], ...]] = (
    re.compile(r"\bif\b.*\b(?:breach|legal|affect|uncrewed|impact)\b", re.IGNORECASE),
    re.compile(r"\bcalls? in sick\b", re.IGNORECASE),
    re.compile(r"\bcalled in sick\b", re.IGNORECASE),
    re.compile(r"\bis sick\b", re.IGNORECASE),
    re.compile(r"\bsick (?:at|on)\b", re.IGNORECASE),
    re.compile(r"\bcan\b.*\b(?:legally|cover|operate)\b", re.IGNORECASE),
    re.compile(r"\bdoes (?:any|anyone|it|the)\b.*\bbreach\b", re.IGNORECASE),
    re.compile(r"\bbreach(?:es|ed)?\b", re.IGNORECASE),
    re.compile(r"\blegal(?:ly)?\b", re.IGNORECASE),
    re.compile(r"\bis closed\b|\bcloses\b|\bclosure\b", re.IGNORECASE),
    re.compile(r"\b(?:is|are)\s+(?:delayed|cancelled|canceled)\b", re.IGNORECASE),
    re.compile(r"\bwhat is the (?:operational )?consequence\b", re.IGNORECASE),
    re.compile(r"\bwhich flights are (?:now )?uncrewed\b", re.IGNORECASE),
    re.compile(r"\bearliest they may report\b", re.IGNORECASE),
    re.compile(r"\bat risk\b", re.IGNORECASE),
)


@dataclass(frozen=True, slots=True)
class Entities:
    """Everything a question names that the dataset can resolve."""

    crew_ids: tuple[str, ...] = ()
    pairing_ids: tuple[str, ...] = ()
    flight_numbers: tuple[str, ...] = ()
    tails: tuple[str, ...] = ()
    rule_ids: tuple[str, ...] = ()
    stations: tuple[str, ...] = ()
    dates: tuple[date, ...] = ()
    times: tuple[str, ...] = ()
    aircraft_types: tuple[str, ...] = ()
    numbers: tuple[float, ...] = ()

    #: Exact rank named in the question. Rank equals role exactly in this
    #: dataset, so `Senior Cabin Crew` never stands in for `Cabin Crew`.
    rank: str | None = None

    def any_identifier(self) -> bool:
        return bool(
            self.crew_ids or self.pairing_ids or self.flight_numbers or self.tails
        )


@dataclass(frozen=True, slots=True)
class Triage:
    """The verdict. `tier` is meaningful only when `in_scope` is true."""

    in_scope: bool
    tier: int
    reason: str
    entities: Entities = field(default_factory=Entities)
    abstention_reason: AbstentionReason | None = None


def _dedupe(values: list[str]) -> tuple[str, ...]:
    seen: dict[str, None] = {}
    for value in values:
        seen.setdefault(value, None)
    return tuple(seen)


def extract_entities(question: str) -> Entities:
    """Everything the question names, normalised to dataset spelling."""
    dates: list[date] = []
    for match in _ISO_DATE_RE.finditer(question):
        try:
            dates.append(date(int(match.group(1)), int(match.group(2)), int(match.group(3))))
        except ValueError:
            continue
    for match in _LOOSE_DATE_RE.finditer(question):
        month = _MONTHS.get(match.group(2).lower())
        if month is None:
            continue
        year = int(match.group(3)) if match.group(3) else DATASET_YEAR
        try:
            dates.append(date(year, month, int(match.group(1))))
        except ValueError:
            continue

    times = [f"{int(m.group(1)):02d}:{m.group(2)}" for m in _TIME_RE.finditer(question)]
    stations = [
        token for token in re.findall(r"\b[A-Z]{3}\b", question) if token in STATIONS
    ]
    numbers = [
        float(raw.replace(",", ""))
        for raw in re.findall(r"\b\d[\d,]*(?:\.\d+)?\b", question)
    ]

    ordered_dates: list[date] = []
    for value in dates:
        if value not in ordered_dates:
            ordered_dates.append(value)

    return Entities(
        crew_ids=_dedupe([m.group(0).upper() for m in _CREW_RE.finditer(question)]),
        pairing_ids=_dedupe([m.group(0).upper() for m in _PAIRING_RE.finditer(question)]),
        flight_numbers=_dedupe([m.group(0).upper() for m in _FLIGHT_RE.finditer(question)]),
        tails=_dedupe([m.group(0).upper() for m in _TAIL_RE.finditer(question)]),
        rule_ids=_dedupe([m.group(0).upper() for m in _RULE_RE.finditer(question)]),
        stations=_dedupe(stations),
        dates=tuple(ordered_dates),
        times=_dedupe(times),
        aircraft_types=_dedupe(
            [m.group(0).upper().replace(" ", "") for m in _AIRCRAFT_RE.finditer(question)]
        ),
        numbers=tuple(numbers),
        rank=rank_in(question),
    )


#: Ordered longest first: "senior cabin crew" must win over "cabin crew".
_RANK_WORDS: Final[tuple[tuple[str, str], ...]] = (
    ("senior cabin crew", "Senior Cabin Crew"),
    ("cabin crew", "Cabin Crew"),
    ("first officer", "First Officer"),
    ("captain", "Captain"),
)


def rank_in(question: str) -> str | None:
    """The exact rank a question names, in the dataset's own spelling."""
    lowered = question.lower()
    for needle, rank in _RANK_WORDS:
        if needle in lowered:
            return rank
    return None


def triage_question(question: str) -> Triage:
    """Classify a question without spending anything.

    Returns `in_scope=False` only when the question is confidently outside
    crew operations on this dataset. Everything else goes forward.
    """
    entities = extract_entities(question)
    words = set(re.findall(r"[a-z][a-z-]+", question.lower()))

    if not question.strip():
        return Triage(
            in_scope=False,
            tier=1,
            reason="Empty question.",
            entities=entities,
            abstention_reason=AbstentionReason.UNDERSPECIFIED,
        )

    out_of_scope_hits = sorted(words & _OUT_OF_SCOPE_TERMS)
    in_scope_hits = words & _IN_SCOPE_TERMS

    # A question is only refused up front when it names a domain the dataset
    # does not model AND names nothing this system can compute over. "Is the
    # weather going to break C-1042's duty limit" stays in scope; "what is the
    # weather at BLR" does not.
    if out_of_scope_hits and not in_scope_hits and not entities.any_identifier():
        return Triage(
            in_scope=False,
            tier=1,
            reason=(
                f"The question is about {out_of_scope_hits[0]}, which this dataset "
                "does not model."
            ),
            entities=entities,
            abstention_reason=AbstentionReason.OUT_OF_SCOPE,
        )

    if not in_scope_hits and not entities.any_identifier() and not entities.stations:
        return Triage(
            in_scope=False,
            tier=1,
            reason=(
                "The question names nothing in the crew operations dataset: no "
                "crew, pairing, flight, station, rule or duty concept."
            ),
            entities=entities,
            abstention_reason=AbstentionReason.OUT_OF_SCOPE,
        )

    return Triage(
        in_scope=True,
        tier=classify_tier(question),
        reason="In scope for crew operations.",
        entities=entities,
    )


def classify_tier(question: str) -> int:
    """The tier floor. The model may raise it; it may not go below it."""
    for pattern in _TIER3_MARKERS:
        if pattern.search(question):
            return 3
    for pattern in _TIER2_MARKERS:
        if pattern.search(question):
            return 2
    return 1


def as_of_or_snapshot(value: datetime | None, fallback: datetime) -> datetime:
    """Small helper so callers do not repeat the same two line dance."""
    return value if value is not None else fallback

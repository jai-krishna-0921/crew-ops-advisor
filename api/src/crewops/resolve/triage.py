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
    "canonical_question",
    "day_shift",
    "extract_entities",
    "reads_as_followup",
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
#: The trailing boundary was `\\b`, which cannot end on a "T": "T" is a word
#: character, so `2026-09-15T05:00:00Z` carried no date at all and the plan
#: quietly fell back to the snapshot. An ops feed writes every instant that
#: way. `(?![\\d-])` ends the date without demanding what follows it be a
#: separator, while still refusing to bite into a longer number.
_ISO_DATE_RE: Final = re.compile(r"\b(\d{4})-(\d{2})-(\d{2})(?![\d-])")
_LOOSE_DATE_RE: Final = re.compile(
    r"\b(\d{1,2})\s+"
    r"(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Sept|Oct|Nov|Dec)[a-z]*\.?"
    r"(?:\s+(\d{4}))?\b",
    re.IGNORECASE,
)
#: Not missing, WRONG, which is worse. In `T05:00:00Z` the leading `\\b` fails
#: at the hour (preceded by "T") and succeeds at the seconds pair, so an
#: event reported at 05:00 was extracted as 00:00 and nothing flagged it.
#: Anchor on "not preceded by a digit or a colon", swallow an optional
#: seconds field, and the whole instant is consumed in one match.
_TIME_RE: Final = re.compile(r"(?<![\d:])(\d{1,2}):(\d{2})(?::\d{2})?\s*Z?(?![\d:])")
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

#: What a Crew Control desk says when a station stops working, in two groups.
#:
#: SELF ASSERTING. Naming one of these at a station IS the report: "fog at BLR"
#: is not a question about fog. No qualifier needed.
_ASSERTS_DISRUPTION: Final[re.Pattern[str]] = re.compile(
    r"\b(?:"
    r"fog(?:ged|gy)?|mist|storm|thunderstorm|snow|monsoon|cyclone|wind\s?shear"
    r"|go[\s-]?slow|strike|industrial\s+action|walkout|congestion"
    r"|shutdown|unusable|unserviceable|blocked"
    # "disruption" is deliberately absent. It is a generic operations noun,
    # and Q16 asks for "the disruption-risk score for C-1042", which is a
    # crew attribute and has nothing to do with a station going down.
    r"|below\s+minima|socked\s+in|diverted"
    r")\b",
    re.IGNORECASE,
)

#: NEUTRAL. A runway, ATC or the weather can be mentioned without anything being
#: wrong, so one of these counts only next to a word saying conditions are bad.
#: This is what keeps "what is the weather at BLR tomorrow" out of scope, which
#: it should be: there is no weather in this dataset and there is no honest
#: answer to give.
_NEUTRAL_CONDITION: Final[re.Pattern[str]] = re.compile(
    r"\b(?:weather|visibility|minima|runway|taxiway|apron|airfield|airport"
    r"|atc|flow\s+control|slot|slots)\b",
    re.IGNORECASE,
)

#: Words that turn a neutral mention into an assertion that things are bad.
_UNSUITABLE_RE: Final[re.Pattern[str]] = re.compile(
    r"\b(?:not\s+suitable|unsuitable|unusable|below\s+minima|bad|poor|severe"
    r"|closed?|shut|restricted|blocked|disrupt(?:ed|ion)"
    r"|delays?|delayed|holding|stopped|halted|suspended)\b",
    re.IGNORECASE,
)

#: What the intent table matches on. A station code has to be present, because
#: the whole point is to turn the report into a closure window *somewhere*.
#: Without the lookahead the vocabulary alone matched Q16 and hijacked it.
STATION_DISRUPTION_RE: Final[re.Pattern[str]] = re.compile(
    r"(?=.*\b(?:" + "|".join(sorted(STATIONS)) + r")\b)"
    r".*(?:"
    + _ASSERTS_DISRUPTION.pattern
    + "|"
    + _NEUTRAL_CONDITION.pattern
    + ")",
    re.IGNORECASE | re.DOTALL,
)


def reads_as_station_disruption(question: str, entities: Entities) -> bool:
    """Is this a controller stating that a station has stopped working?

    A station this system knows has to be named, because the whole point is to
    turn the report into a closure window somewhere. Then either the condition
    asserts itself, or a neutral one is qualified as bad.
    """
    if not entities.stations:
        return False
    if _ASSERTS_DISRUPTION.search(question):
        return True
    return bool(
        _NEUTRAL_CONDITION.search(question) and _UNSUITABLE_RE.search(question)
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
    re.compile(r"\bat risk\b", re.IGNORECASE),
    # WRITTEN AS SHAPES, NOT AS SHIPPED PHRASINGS.
    #
    # The markers above were lifted from questions.json, so they matched those
    # questions and nothing else. `\bearliest they may report\b` was Q23 word
    # for word and "soonest they can start again" fell through to tier 1, which
    # disarms `tier_guard` on a rest calculation. Five of nine reworded tier 2
    # questions came back tier 1 that way.
    #
    # Permission asked in any of its ordinary words.
    re.compile(
        r"\b(?:allowed|permitted|entitled|cleared|eligible)\s+to\b", re.IGNORECASE
    ),
    # Breaking a rule, without using the word "breach".
    re.compile(
        r"\bbreak(?:s|ing)?\b[^.?!]{0,20}\brules?\b|\brule\s+break\b|\bviolat",
        re.IGNORECASE,
    ),
    # Validity as of a date is a RULE-CERT-06 question, not a field read.
    re.compile(r"\bvalid\s+(?:for|on|at|until|through)\b", re.IGNORECASE),
    # Looking forward to the next legal duty, however it is phrased.
    re.compile(
        # 60 rather than 40: "When can a crew released at 22:15Z on 15 Sep
        # next fly?" puts 44 characters between the two halves.
        r"\b(?:earliest|soonest|when)\b[^.?!]{0,60}"
        r"\b(?:report|start|fly|operate|next\s+duty|resume)\b",
        re.IGNORECASE,
    ),
    # A threshold over a window is a computation over the clocks. Q26 is
    # declared tier 2 and was classified tier 1 for exactly this reason.
    re.compile(
        r"\b(?:more|less|fewer|greater|above|below|over|under|at\s+least)\b"
        r"[^.?!]{0,20}\b\d+(?:\.\d+)?\b[^.?!]{0,20}\bhours?\b"
        r"|\b\d+(?:\.\d+)?\s+or\s+(?:more|fewer|less)\b",
        re.IGNORECASE,
    ),
    # Consequence framing.
    re.compile(
        r"\bwhat\s+happens\s+if\b|\bknock[\s-]?on\b|\bcascade\b"
        r"|\bdownstream\b|\bripple\b|\bgrounding\b|\bgrounded\b",
        re.IGNORECASE,
    ),
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

    #: What was absent, as a noun, for the "what was missing" panel.
    #:
    #: Both answer paths used to pass `reason` here, so the console rendered
    #: the same sentence twice: once as the answer and again under WHAT WAS
    #: MISSING. A refusal that repeats itself reads as a system with one
    #: sentence rather than one that knows what it lacked.
    missing: tuple[str, ...] = ()


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


#: Openers and pleasantries. Matched as whole tokens, never as substrings, so
#: the `hi` in `which` and the `yo` in `beyond` do not count.
_GREETING_TOKENS: Final[frozenset[str]] = frozenset(
    {
        "hey", "hi", "hiya", "hello", "yo", "howdy", "greetings",
        "good", "morning", "afternoon", "evening", "day",
        "thanks", "thank", "you", "thx", "ta", "cheers", "ok", "okay",
        "please", "there", "team", "again", "much", "so", "very",
    }
)

#: A greeting is short. Anything longer is a sentence that happens to open
#: politely, and the length cap is a cheap second guard behind the token check.
_GREETING_MAX_TOKENS: Final = 4


#: Being asked what it does. Answered rather than refused: it is the first
#: thing anyone types, and "the question names nothing in the crew operations
#: dataset" is the least useful sentence available in reply to it.
_CAPABILITY_RE: Final[re.Pattern[str]] = re.compile(
    r"\bwhat\s+(?:can|could)\s+(?:you|i|we)\b"
    r"|\bwhat\s+(?:do|are)\s+you\b"
    r"|\bwhat\s+(?:are\s+)?your\s+capabilit"
    r"|\bwhat\s+(?:kind|sort)\s+of\s+questions?\b"
    r"|\bhow\s+(?:do|can)\s+i\s+use\b"
    r"|\bwho\s+are\s+you\b"
    r"|^\s*help\s*[?.!]?\s*$"
    r"|\bwhat\s+(?:is|are)\s+this\b",
    re.IGNORECASE,
)


def is_capability_question(question: str) -> bool:
    """Is the user asking what this system is for?"""
    return bool(_CAPABILITY_RE.search(question))


#: A question that continues the one before it rather than starting something.
#:
#: Two families, and both have to be present in the pattern or half of a normal
#: conversation is refused.
#:
#: ONE, AN EXPLICIT CONTINUATION. "And what about the next day", "how about
#: DEL", "same for 17 Sep". The opener carries the whole meaning: the subject
#: is whatever was just discussed.
#:
#: TWO, A BARE PRONOUN SUBJECT. "Which of them are captains", "and them",
#: "who are they". There is no noun in the sentence at all, which is exactly
#: why triage found nothing in the dataset and declined.
#:
#: Deliberately anchored at the start for the first family. "What about" in the
#: middle of a full question ("Cover P-2291, and what about the cost?") names
#: its own subject and does not need the previous turn.
_FOLLOW_UP_RE: Final = re.compile(
    r"^\s*(?:and\s+|but\s+|ok(?:ay)?[,\s]+|so\s+)?"
    r"(?:what|how)\s+about\b"
    r"|^\s*(?:and\s+)?same\s+(?:for|on|at)\b"
    r"|^\s*(?:and\s+)?(?:what|how)\s+if\b"
    r"|\bwhich\s+of\s+(?:them|those|these)\b"
    r"|^\s*(?:and\s+)?(?:them|those|they)\b"
    r"|^\s*(?:and\s+)?who\s+are\s+they\b"
    r"|^\s*(?:and\s+)?the\s+(?:next|previous|following|day\s+before|day\s+after)\b",
    re.IGNORECASE,
)

#: Words that move the previous turn's date. `_DAY_FORWARD` and `_DAY_BACK` are
#: the only arithmetic a follow-up is allowed to do, because they are the only
#: two a controller means unambiguously.
_DAY_FORWARD: Final = re.compile(
    r"\bnext day\b|\bfollowing day\b|\bday after\b|\btomorrow\b", re.IGNORECASE
)
_DAY_BACK: Final = re.compile(
    r"\bprevious day\b|\bday before\b|\bprior day\b|\byesterday\b", re.IGNORECASE
)


def reads_as_followup(question: str) -> bool:
    """True when the question only makes sense after another one.

    Turn 2 of every real conversation. "And what about the next day?" names no
    crew, pairing, flight, station or rule, so scope triage declined it before
    the graph reached the history that would have resolved it. That refusal was
    correct about the words and wrong about the situation.
    """
    return bool(_FOLLOW_UP_RE.search(question))


def day_shift(question: str) -> int:
    """How far a follow-up moves the previous turn's date: +1, -1 or 0.

    The only arithmetic a follow-up is allowed to do, because these are the
    only two moves a controller means unambiguously. "The week after" and
    "later" are not here on purpose: guessing a span is how a carried-forward
    date becomes a wrong answer nobody typed.
    """
    if _DAY_FORWARD.search(question):
        return 1
    if _DAY_BACK.search(question):
        return -1
    return 0


def _is_greeting(question: str) -> bool:
    """True when the whole question is an opener or a thank you.

    Deliberately strict: **every** token must be a pleasantry. That is what
    keeps "hey, who is on reserve at BLR" a real question, which is how a
    controller under pressure actually types. A greeting in front of a question
    is a question.
    """
    tokens = re.findall(r"[a-z]+", question.lower())
    if not tokens or len(tokens) > _GREETING_MAX_TOKENS:
        return False
    return all(token in _GREETING_TOKENS for token in tokens)


#: Station names to the eight codes this airline actually serves.
#:
#: Deliberately closed. An alias for a station outside the network would turn
#: "who is on reserve at heathrow" from an honest refusal into a lookup against
#: the wrong place, which is worse than not understanding the word.
_STATION_ALIASES: Final[dict[str, str]] = {
    "bangalore": "BLR",
    "bengaluru": "BLR",
    "delhi": "DEL",
    "new delhi": "DEL",
    "mumbai": "BOM",
    "bombay": "BOM",
    "chennai": "MAA",
    "madras": "MAA",
    "kolkata": "CCU",
    "calcutta": "CCU",
    "hyderabad": "HYD",
    "kochi": "COK",
    "cochin": "COK",
    "goa": "GOI",
}

_STATION_ALIAS_RE: Final = re.compile(
    r"\b(" + "|".join(sorted(_STATION_ALIASES, key=len, reverse=True)) + r")\b",
    re.IGNORECASE,
)

#: `C1042`, `c 1042` and `C-1042` are the same crew member. The four digit tail
#: is what keeps this from firing on prose: gate `C 12` and terminal `2` have
#: too few digits to be an identifier in this dataset, where every crew and
#: pairing id carries exactly four.
_LOOSE_CREW_RE: Final = re.compile(r"\b([CP])[\s-]?(\d{4})\b", re.IGNORECASE)

#: `DX 412` and `dx412` are the same leg.
_LOOSE_FLIGHT_RE: Final = re.compile(r"\b(DX)[\s-]?(\d{3,4})\b", re.IGNORECASE)


#: Ways of saying the same operational thing. Folded before matching, so one
#: table serves every intent and the tier classifier, instead of each intent
#: growing its own synonyms and then needing them again for the next wording.
#:
#: Rewording five shipped tier 2 questions, the resolver answered none of them
#: while the agent answered all five. Four missed by a synonym alone.
#:
#: Each entry is a word-for-word equivalence in this domain, never a change of
#: meaning, and the *question* is all that is rewritten: `Reply.question` keeps
#: what the controller typed, so nothing here can put a value on screen that a
#: tool did not produce.
_SYNONYMS: Final[tuple[tuple[re.Pattern[str], str], ...]] = tuple(
    (re.compile(pattern, re.IGNORECASE), replacement)
    for pattern, replacement in (
        # Breaking a rule is breaching one.
        (r"\bbreak(?:s|ing)?\s+(?:any\s+|a\s+|the\s+)?rules?\b", "breach"),
        (r"\brule\s+break(?:s|ing)?\b", "rule breach"),
        (r"\bviolat(?:e|es|ing|ion)\b", "breach"),
        # Permission, however it is asked.
        (r"\b(?:allowed|permitted|cleared|entitled)\s+to\b", "legally"),
        # A station stopping work.
        (r"\bshuts?\s+down\b", "is closed"),
        (r"\bshuts\b", "is closed"),
        # Forward-looking rest.
        (r"\bsoonest\b", "earliest"),
        (r"\b(?:finished|finishes|ends?|ended)\s+(?:their\s+)?duty\b", "is released"),
        (r"\bcame?\s+off\s+duty\b", "is released"),
        (r"\bsign(?:s|ed)?\s+off\b", "is released"),
        (r"\bstart\s+(?:work\s+)?again\b", "report next"),
        (r"\bfly\s+again\b", "report next"),
        # A whole multi-day pairing.
        (r"\bthe\s+whole\s+of\s+(?:the\s+)?pairing\b", "the full pairing"),
        (r"\bthe\s+entire\s+pairing\b", "the full pairing"),
    )
)


def canonical_question(question: str) -> str:
    """Rewrite a question into the spelling the dataset uses.

    The offline path matches fixed shapes, and those shapes expect `C-1042`,
    `BLR` and an ISO date. A controller types `C1042` and `bangalore`. The
    agent path reads both without being told, which is precisely why this
    belongs here: the deterministic path is the one that has to be rigid, and
    it is the one that runs with no key, no network and no budget.

    Only the *question* is rewritten, never the answer, so nothing here can put
    a value in front of a controller that a tool did not produce. Idempotent,
    because both the resolver and the graph's triage call it.
    """
    if not question.strip():
        return question

    text = _LOOSE_CREW_RE.sub(lambda m: f"{m.group(1).upper()}-{m.group(2)}", question)
    text = _LOOSE_FLIGHT_RE.sub(lambda m: f"{m.group(1).upper()}{m.group(2)}", text)
    text = _STATION_ALIAS_RE.sub(lambda m: _STATION_ALIASES[m.group(1).lower()], text)
    for pattern, replacement in _SYNONYMS:
        text = pattern.sub(replacement, text)
    return text


def triage_question(question: str) -> Triage:
    """Classify a question without spending anything.

    Returns `in_scope=False` only when the question is confidently outside
    crew operations on this dataset. Everything else goes forward.
    """
    question = canonical_question(question)
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

    if _is_greeting(question):
        return Triage(
            in_scope=False,
            tier=1,
            reason=(
                "This is a crew operations desk assistant. Ask about crew, "
                "flights, pairings, rosters, duty and flight hour limits, "
                "certifications, reserve cover or the impact of a disruption."
            ),
            entities=entities,
            abstention_reason=AbstentionReason.GREETING,
        )

    out_of_scope_hits = sorted(words & _OUT_OF_SCOPE_TERMS)
    in_scope_hits = words & _IN_SCOPE_TERMS

    # A question is only refused up front when it names a domain the dataset
    # does not model AND names nothing this system can compute over. "Is the
    # weather going to break C-1042's duty limit" stays in scope; "what is the
    # weather at BLR" does not.
    if is_capability_question(question):
        return Triage(
            in_scope=False,
            tier=1,
            reason=(
                "I am a decision aid for an airline Crew Control desk. I answer "
                "from one week of dCortex Air's schedule out of BLR: 147 flights, "
                "150 crew, 39 pairings, 16 reserves and seven duty rules. Ask me "
                "who is on reserve, whether a crew member is legal for a duty, "
                "what breaks when someone calls in sick or a station closes, and "
                "what the ranked ways to cover a gap cost. Every figure comes "
                "from the data with its arithmetic shown, and when I cannot "
                "answer reliably I say so and say what was missing."
            ),
            entities=entities,
            # GREETING, not OUT_OF_SCOPE. The reason decides the tone: a
            # greeting is answered and carries no "I cannot", which is right
            # here because nothing is missing. The user has not asked for
            # anything yet, they have asked what there is to ask for.
            abstention_reason=AbstentionReason.GREETING,
        )

    # A STATED DISRUPTION IS NOT AN OUT OF SCOPE QUESTION.
    #
    # "BLR weather is not suitable" names weather, which is not modelled, and
    # was refused in 4ms. But the controller is not asking about weather: they
    # are saying a station has stopped working, and that is a closure window,
    # which is modelled exactly. The refusal was true and useless.
    #
    # "What is the weather at BLR tomorrow" still falls through to the refusal
    # below, because it asks about the weather itself rather than asserting a
    # condition. `reads_as_station_disruption` is what separates them.
    if reads_as_station_disruption(question, entities):
        return Triage(
            in_scope=True,
            tier=2,
            reason="A station is reported unusable, which is a closure window.",
            entities=entities,
        )

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
            missing=(
                f"{out_of_scope_hits[0].capitalize()} data. This dataset covers "
                "crew, flights, pairings, duty clocks, certifications and the "
                "seven rules, for one week out of BLR.",
            ),
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

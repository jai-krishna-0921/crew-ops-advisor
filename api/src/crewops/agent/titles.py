"""What a conversation is called in the rail.

THE NAME COMES FROM THE QUESTION, NOT FROM THE ANSWER, which reverses an
earlier decision. Naming a thread from `Reply.headline` meant that typing "hey"
produced a conversation called "This is a crew operations desk assistant": the
product described, not the exchange. A headline is written to be read once, at
the top of an answer, at whatever length that answer needs. A name is read
fifty times, in a rail the reader has dragged down to 208 pixels.

Two rules follow from that width, and both are load bearing.

**Five words.** Past that the rail truncates, and a name whose end nobody ever
sees is not a name.

**The identifier leads.** Truncation eats the right hand side, so "C-1042 duty
hours" keeps the crew id and "Duty hours for C-104…" loses it, and the id is
precisely the token somebody is scanning thirty rows for. Dates go last for the
same reason inverted: a date is context, not subject.

NO MODEL IS INVOLVED. A title is language rather than a figure, so under this
repository's rule a model would be permitted to write one, and it is still the
wrong trade. This runs identically with no API key, costs nothing, and returns
the same name for the same question every time, where a model would hand two
identical threads two different names. The mapping below is a lookup over the
question's own vocabulary, checked in `tests/agent/test_titles.py` against all
38 questions in the dataset.
"""

from __future__ import annotations

import re
from typing import Final

from crewops.contracts import AbstentionReason
from crewops.resolve.triage import Entities, extract_entities, rank_in

__all__ = ["title_for"]

#: The cap. Everything else in this module exists to fit inside it.
_MAX_WORDS: Final = 5

#: What the conversation is *about*, in the order the question is read.
#:
#: First match wins, so this is a priority list rather than a set. The order
#: was tuned against the dataset's own 38 prompts and every reordering costs
#: something: an action ("rank the options") outranks a subject ("duty hours")
#: because when a controller asks for both, the decision is what they came for.
_TOPICS: Final[tuple[tuple[re.Pattern[str], str], ...]] = tuple(
    (re.compile(pattern, re.IGNORECASE), label)
    for pattern, label in (
        (
            # `rank` is a noun in this dataset before it is a verb: "what is
            # C-2087's rank" is a lookup, not a request for a ranking.
            r"\branked\b|\brank(?:ing)? (?:the )?(?:resolution )?options?\b"
            r"|\brecommend|\boptimal\b|\bcheapest\b"
            r"|\bbest (?:option|way|plan)\b|\brecovery plan\b|\bwhat should\b"
            r"|\bresolve\b",
            "ranked options",
        ),
        (r"\bnotif(?:y|ication)\b|\bcallout (?:notice|message)\b", "callout notice"),
        (r"\bclos(?:e|ed|es|ure)\b|\bshut\b", "closure"),
        (r"\bcancel", "cancellation impact"),
        (r"\bdelay", "delay impact"),
        (r"\bsick\b|\babsen(?:ce|t)\b|\bunavailable\b|\bis out\b", "absence impact"),
        (r"\bbreach|\blegal(?:ly|ity)?\b|\bcompl(?:y|iant)\b", "legality"),
        (r"\bcover|\bbackfill\b|\breplace", "cover options"),
        (r"\bduty hours?\b|\bduty limit\b|RULE-DUTY", "duty hours"),
        (r"\bflight hours?\b|\bblock hours?\b|RULE-FLT", "flight hours"),
        (r"\brest\b|\breleased\b|\breport next\b|RULE-REST", "minimum rest"),
        (
            r"\bcertificat|\brecurrent\b|\btraining\b|\blicen[cs]e\b|\bmedical\b"
            r"|\bexpir",
            "certifications",
        ),
        (
            r"\brating\b|\bqualif|\btype[- ]rated\b|RULE-QUAL|\bbase\b",
            "qualification",
        ),
        (r"\breserve|\bon[- ]call\b|\bstandby\b|\breachab", "reserve cover"),
        (r"\bdisruption[- ]risk\b|\brisk\b", "risk score"),
        (r"\bbrief", "morning brief"),
        # Rank sits here, below every subject and above the generic ones: a
        # question that names a rank AND a topic is about the topic ("Captain
        # C-1042 calls in sick" is an absence), but one that names only a rank
        # is about those people.
        (r"", ""),  # placeholder, replaced below by the rank rule
        (r"\broster|\bassign|\bpairing|\brole", "roster"),
        (r"\bblock time\b", "block time"),
        (r"\bseats?\b|\baircraft\b|\btail number\b", "aircraft"),
        (r"\bstations?\b|\bnetwork\b|\bnonstop\b", "network"),
        (r"\bflights?\b|\bdepart|\barriv|\bsector|\bleg\b", "flights"),
        (r"\brank\b", "rank"),
        (r"\bcrew\b|\bpilot\b", "crew"),
        (r"\brules?\b", "rules"),
    )
)

#: Where the rank rule sits in `_TOPICS`. Held as an index rather than folded
#: into the table because its label depends on the question.
_RANK_SLOT: Final = next(i for i, (_, label) in enumerate(_TOPICS) if label == "")

#: A rank as it appears in a title: lowercase, and plural where the question
#: asked about a group.
_RANK_LABEL: Final[dict[str, str]] = {
    "Captain": "captains",
    "First Officer": "first officers",
    "Cabin Crew": "cabin crew",
    "Senior Cabin Crew": "senior cabin crew",
}

_MONTH_NAMES: Final = (
    "Jan", "Feb", "Mar", "Apr", "May", "Jun",
    "Jul", "Aug", "Sep", "Oct", "Nov", "Dec",
)  # fmt: skip

#: Words a title must not end on. A trailing preposition reads as a truncation
#: bug; the same title without it reads as a title.
_DANGLING: Final[frozenset[str]] = frozenset(
    {
        "a", "an", "the", "of", "at", "on", "in", "for", "to", "and", "or",
        "is", "are", "was", "with", "by", "from", "that", "this", "their",
        "its", "has", "have", "how", "what", "which", "who", "does", "do",
    }
)


def title_for(
    question: str, *, abstention_reason: AbstentionReason | None = None
) -> str:
    """Name a conversation from the question that opened it."""
    if abstention_reason is AbstentionReason.GREETING:
        return "Greeting"

    text = " ".join(question.split())
    if not text:
        return "New conversation"

    entities = extract_entities(text)
    topic = _topic(text)
    if topic is None:
        return _own_words(text)

    lead = _lead(entities)
    trail = _trail(entities, lead)
    return _cap(" ".join(part for part in (lead, topic, trail) if part))


# --------------------------------------------------------------------- parts


def _topic(text: str) -> str | None:
    """What the conversation is about, or None when nothing in scope matches."""
    for index, (pattern, label) in enumerate(_TOPICS):
        if index == _RANK_SLOT:
            rank = rank_in(text)
            if rank is not None:
                return _RANK_LABEL[rank]
            continue
        if pattern.search(text):
            return label
    return None


def _lead(entities: Entities) -> str:
    """The identifier a reader scans for, most specific first.

    Crew before pairing because a controller thinks in people; both before the
    flight and the tail, which are how the work is labelled rather than who is
    doing it. A crew id paired with a pairing id keeps both, because "is
    C-2087 legal" and "is C-2087 legal on P-2291" are different questions and
    the rail should not make them look alike.
    """
    if entities.crew_ids:
        if entities.pairing_ids:
            return f"{entities.crew_ids[0]} on {entities.pairing_ids[0]}"
        return entities.crew_ids[0]
    if entities.pairing_ids:
        return entities.pairing_ids[0]
    if entities.flight_numbers:
        return entities.flight_numbers[0]
    if entities.tails:
        return entities.tails[0]
    if entities.rule_ids:
        return entities.rule_ids[0]
    if len(entities.stations) >= 2:
        return f"{entities.stations[0]} to {entities.stations[1]}"
    if entities.stations:
        return entities.stations[0]
    return ""


def _trail(entities: Entities, lead: str) -> str:
    """A date, and only when nothing more specific already leads.

    "C-1042 duty hours 15 Sep" spends a fifth of the rail restating what the
    crew id already pins down. A date earns its place only when it is the sole
    thing distinguishing one thread from another.
    """
    if lead or not entities.dates:
        return ""
    day = entities.dates[0]
    return f"{day.day} {_MONTH_NAMES[day.month - 1]}"


# -------------------------------------------------------------------- tidying


def _own_words(text: str) -> str:
    """No topic matched, so the question names itself.

    This is the out of scope path ("what is the weather at BLR"). Naming it
    after its own opening words is honest: there is no crew operations subject
    to name it after, and pretending otherwise would put a title on the thread
    that the thread does not contain.
    """
    words = text.split()[:_MAX_WORDS]
    while words and words[-1].strip(".,;:?!").lower() in _DANGLING:
        words.pop()
    if not words:
        return "New conversation"
    tidy = " ".join(words).strip(".,;:?!")
    return tidy[:1].upper() + tidy[1:]


def _cap(title: str) -> str:
    """Five words, first letter up, nothing dangling off the end."""
    words = title.split()[:_MAX_WORDS]
    while len(words) > 1 and words[-1].lower() in _DANGLING:
        words.pop()
    tidy = " ".join(words)
    return tidy[:1].upper() + tidy[1:]

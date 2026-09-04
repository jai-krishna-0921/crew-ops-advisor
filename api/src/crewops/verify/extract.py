"""Pull every checkable atom out of a piece of prose.

An atom is anything the model could get factually wrong: a number, a duration,
a money amount, a date, a time, an identifier, a station code, a rule id or an
aircraft type. Prose that contains none of those has nothing to check.

The scanner runs every pattern over the whole string, then resolves overlaps by
taking the earliest match and, at equal start, the longest one. That ordering
is what stops `INR 18,500` from also yielding the bare numbers `18` and `500`,
and what stops `VT-DXB` from yielding the station `DXB`.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Final, Literal

from crewops.verify.normalise import (
    canonical_currency,
    canonical_date,
    canonical_duration_minutes,
    canonical_identifier,
    canonical_number,
    canonical_time,
    spelled_number,
)

__all__ = ["CONTRACT_KIND", "Atom", "AtomKind", "extract_atoms", "sentences_of"]

AtomKind = Literal[
    "number",
    "duration",
    "currency",
    "date",
    "time",
    "identifier",
    "station",
    "rule_id",
    "aircraft",
]

#: `UnattestedAtom.kind` in the contract is a narrower set than the one the
#: scanner works in. This maps the internal kind onto the reported kind.
CONTRACT_KIND: Final[dict[AtomKind, str]] = {
    "number": "number",
    "duration": "number",
    "currency": "currency",
    "date": "date",
    "time": "date",
    "identifier": "identifier",
    "station": "station",
    "rule_id": "rule_id",
    "aircraft": "identifier",
}


@dataclass(frozen=True, slots=True)
class Atom:
    """One checkable token, with everything the report needs to explain it."""

    text: str
    kind: AtomKind
    canon: str
    start: int
    end: int
    sentence: str

    @property
    def contract_kind(self) -> str:
        return CONTRACT_KIND[self.kind]

    @property
    def key(self) -> tuple[str, str]:
        return (self.kind, self.canon)


_MONTH_WORD = (
    r"Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|Jun(?:e)?|Jul(?:y)?"
    r"|Aug(?:ust)?|Sep(?:t)?(?:ember)?|Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?"
)

# Order matters only for readability. Overlap is resolved by span, not by
# position in this list.
_PATTERNS: Final[tuple[tuple[AtomKind, re.Pattern[str]], ...]] = (
    ("rule_id", re.compile(r"\bRULE-[A-Z]{2,8}-\d{1,3}\b")),
    ("identifier", re.compile(r"\b[CP]-\d{2,6}\b")),
    ("identifier", re.compile(r"\bVT-[A-Z]{2,4}\b")),
    ("identifier", re.compile(r"\bDX\d{2,4}(?:-\d{4}-\d{2}-\d{2})?\b")),
    ("aircraft", re.compile(r"\b(?:A\d{3}|ATR\s?\d{2}|B\d{3})\b")),
    (
        "currency",
        re.compile(r"(?:INR|₹|Rs\.?)\s*\d[\d,]*(?:\.\d+)?", re.IGNORECASE),
    ),
    (
        "currency",
        re.compile(r"\b\d[\d,]*(?:\.\d+)?\s*(?:INR|rupees?)\b", re.IGNORECASE),
    ),
    (
        "date",
        re.compile(r"\b\d{4}-\d{2}-\d{2}(?:[T ]\d{2}:\d{2}(?::\d{2})?Z?)?"),
    ),
    (
        "date",
        re.compile(
            rf"\b\d{{1,2}}(?:st|nd|rd|th)?\s+(?:{_MONTH_WORD})\.?(?:,?\s+\d{{4}})?\b",
            re.IGNORECASE,
        ),
    ),
    (
        "date",
        re.compile(
            rf"\b(?:{_MONTH_WORD})\.?\s+\d{{1,2}}(?:st|nd|rd|th)?(?:,?\s+\d{{4}})?\b",
            re.IGNORECASE,
        ),
    ),
    ("date", re.compile(r"\b\d{1,2}/\d{1,2}/\d{4}\b")),
    # `61.33h`, `61h20m`, `13 hours`, `61 hours 20 minutes`.
    # The unit suffix cannot use `\b` on its own: in `61.33h` there is no word
    # boundary before the `h`, and in `1h20m` there is none after it either.
    # A negative lookahead for a letter does the job without matching `1 hub`.
    (
        "duration",
        re.compile(
            r"(?<![\w.])(?P<dh>\d+(?:\.\d+)?)\s*(?:hours|hour|hrs|hr|h)(?![A-Za-z])"
            r"(?:\s*(?:and\s+)?(?P<dm>\d+)\s*(?:minutes|minute|mins|min|m)(?![A-Za-z]))?",
            re.IGNORECASE,
        ),
    ),
    (
        "duration",
        re.compile(
            r"(?<![\w.])(?P<mm>\d+(?:\.\d+)?)\s*(?:minutes|minute|mins|min)(?![A-Za-z])",
            re.IGNORECASE,
        ),
    ),
    ("time", re.compile(r"\b\d{1,2}:\d{2}(?::\d{2})?\s*Z?\b")),
    ("number", re.compile(r"\b\d+(?:\.\d+)?\s*%")),
    ("station", re.compile(r"\b[A-Z]{3}\b")),
    (
        "number",
        re.compile(
            r"\b(?:zero|one|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve)\b",
            re.IGNORECASE,
        ),
    ),
    ("number", re.compile(r"\b\d[\d,]*(?:\.\d+)?\b")),
)

#: List enumerators and markdown furniture. Blanked out before scanning so a
#: numbered list does not read as a stream of unattested integers. The text is
#: replaced with spaces rather than deleted so every offset stays valid.
_MARKUP_RE: Final = re.compile(
    r"^[ \t]*(?:[-*+]\s+|\d{1,2}[.)]\s+|#{1,6}\s+|>\s+)",
    re.MULTILINE,
)

_SENTENCE_SPLIT_RE: Final = re.compile(r"(?<=[.!?:;])\s+|\n+")


def sentences_of(text: str) -> list[tuple[int, int, str]]:
    """Sentence spans as `(start, end, text)`, covering the whole string."""
    spans: list[tuple[int, int, str]] = []
    cursor = 0
    for match in _SENTENCE_SPLIT_RE.finditer(text):
        end = match.start()
        if end > cursor:
            spans.append((cursor, end, text[cursor:end].strip()))
        cursor = match.end()
    if cursor < len(text):
        spans.append((cursor, len(text), text[cursor:].strip()))
    if not spans:
        spans.append((0, len(text), text.strip()))
    return spans


def _blank_markup(text: str) -> str:
    """Replace list and heading markers with spaces, preserving offsets."""
    return _MARKUP_RE.sub(lambda m: " " * len(m.group(0)), text)


def _canonicalise(kind: AtomKind, match: re.Match[str]) -> tuple[AtomKind, str] | None:
    raw = match.group(0)
    if kind == "rule_id":
        value = canonical_identifier(raw)
        return ("rule_id", value) if value else None
    if kind in ("identifier", "aircraft"):
        value = canonical_identifier(raw)
        return (kind, value) if value else None
    if kind == "station":
        value = canonical_identifier(raw)
        return ("station", value) if value else None
    if kind == "currency":
        digits = re.search(r"\d[\d,]*(?:\.\d+)?", raw)
        value = canonical_currency(digits.group(0)) if digits else None
        return ("currency", value) if value else None
    if kind == "duration":
        named = match.groupdict()
        if named.get("dh") is not None:
            total = canonical_duration_minutes(hours=named["dh"], minutes=named.get("dm"))
        else:
            total = canonical_duration_minutes(minutes=named.get("mm"))
        return ("duration", str(total)) if total is not None else None
    if kind == "date":
        if re.search(r"\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}", raw):
            # A full timestamp is two atoms in one span. The date is the one
            # that carries the risk of being wrong by a day; the clock time is
            # emitted separately below by the caller.
            day = canonical_date(raw)
            return ("date", day) if day else None
        day = canonical_date(raw)
        return ("date", day) if day else None
    if kind == "time":
        clock = canonical_time(raw)
        return ("time", clock) if clock else None
    # number
    stripped = raw.rstrip("%").strip()
    spelled = spelled_number(stripped)
    if spelled is not None:
        return ("number", str(spelled))
    value = canonical_number(stripped)
    return ("number", value) if value else None


def extract_atoms(text: str) -> list[Atom]:
    """Every checkable atom in `text`, left to right, without overlaps."""
    if not text or not text.strip():
        return []
    scan_target = _blank_markup(text)
    sentence_spans = sentences_of(text)

    candidates: list[tuple[int, int, AtomKind, re.Match[str]]] = []
    for kind, pattern in _PATTERNS:
        for match in pattern.finditer(scan_target):
            candidates.append((match.start(), match.end(), kind, match))

    # Earliest start wins; at equal start the longer span wins. That is what
    # makes `INR 18,500` one currency atom rather than a currency atom plus two
    # stray integers.
    candidates.sort(key=lambda item: (item[0], -(item[1] - item[0])))

    atoms: list[Atom] = []
    consumed_to = -1
    for start, end, kind, match in candidates:
        if start < consumed_to:
            continue
        resolved = _canonicalise(kind, match)
        if resolved is None:
            continue
        actual_kind, canon = resolved
        sentence = _sentence_for(start, sentence_spans)
        atoms.append(
            Atom(
                text=match.group(0),
                kind=actual_kind,
                canon=canon,
                start=start,
                end=end,
                sentence=sentence,
            )
        )
        consumed_to = end
        # A full timestamp carries a clock time as well as a date. Emit it as
        # its own atom so a wrong report time is caught.
        if actual_kind == "date":
            clock = canonical_time(match.group(0))
            if clock and re.search(r"\d{2}:\d{2}", match.group(0)):
                atoms.append(
                    Atom(
                        text=match.group(0),
                        kind="time",
                        canon=clock,
                        start=start,
                        end=end,
                        sentence=sentence,
                    )
                )
    return atoms


def _sentence_for(offset: int, spans: list[tuple[int, int, str]]) -> str:
    for start, end, sentence in spans:
        if start <= offset < end:
            return sentence
    return spans[-1][2] if spans else ""

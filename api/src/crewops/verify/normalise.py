"""Canonical forms for every kind of atom the grounding check compares.

This module is the single source of truth for "are these two renderings the
same fact". It is deliberately free of any dependency on the rest of the
system so that other workstreams can import it directly:

    from crewops.verify.normalise import (
        canonical_number,
        canonical_duration_minutes,
        canonical_currency,
        canonical_date,
        canonical_time,
        render_duration,
    )

The hard case is duration. The shipped answer keys render 1.33 hours as
`1h20m` and 8.25 hours as `8h15m`, so the equivalence a verifier needs is:

    61.33  ==  61.33h  ==  61h20m  ==  "61 hours 20 minutes"

The rule that makes all four agree is: a duration canonicalises to whole
minutes, rounded half up. 61.33 h is 3679.8 minutes, which rounds to 3680.
61h20m is 3680 minutes exactly. They match. A genuinely different figure does
not: 61.3 h is 3678 minutes, which is two minutes away and therefore a
different fact. That two-minute gap is the entire tolerance budget, and it is
deliberate. Anything wider would let a wrong number through.

Numbers that are not durations canonicalise to a decimal string quantised to
two places, again half up, because two places is what the dataset carries and
what `Fact.rendered()` produces. `61.33` and `61.330` agree; `61.3` does not.
"""

from __future__ import annotations

import re
from datetime import date as date_cls
from datetime import datetime as datetime_cls
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
from typing import Final

__all__ = [
    "MONTH_ABBREVIATIONS",
    "canonical_currency",
    "canonical_date",
    "canonical_datetime",
    "canonical_duration_minutes",
    "canonical_identifier",
    "canonical_number",
    "canonical_time",
    "hours_to_minutes",
    "render_duration",
    "spelled_number",
]

#: Two decimal places: what the dataset carries and what `Fact.rendered()`
#: emits. Quantising further would make 61.333 and 61.334 different facts.
_QUANTUM: Final = Decimal("0.01")

_NUMERIC_RE: Final = re.compile(r"^[+-]?\d+(?:\.\d+)?$")

#: Leading currency markers that may sit in front of an amount.
_CURRENCY_PREFIX_RE: Final = re.compile(r"^(?:INR|inr|Rs\.?|rs\.?|₹)\s*")
_CURRENCY_SUFFIX_RE: Final = re.compile(r"\s*(?:INR|inr|rupees?|Rs\.?|rs\.?)$")

MONTH_ABBREVIATIONS: Final[dict[str, int]] = {
    "jan": 1,
    "january": 1,
    "feb": 2,
    "february": 2,
    "mar": 3,
    "march": 3,
    "apr": 4,
    "april": 4,
    "may": 5,
    "jun": 6,
    "june": 6,
    "jul": 7,
    "july": 7,
    "aug": 8,
    "august": 8,
    "sep": 9,
    "sept": 9,
    "september": 9,
    "oct": 10,
    "october": 10,
    "nov": 11,
    "november": 11,
    "dec": 12,
    "december": 12,
}

#: Cardinals a controller-facing answer might spell out. Kept to zero..twelve
#: because beyond twelve the dataset always uses digits, and a longer list
#: starts colliding with ordinary prose ("a score of crew").
_SPELLED: Final[dict[str, int]] = {
    "zero": 0,
    "one": 1,
    "two": 2,
    "three": 3,
    "four": 4,
    "five": 5,
    "six": 6,
    "seven": 7,
    "eight": 8,
    "nine": 9,
    "ten": 10,
    "eleven": 11,
    "twelve": 12,
}


def spelled_number(word: str) -> int | None:
    """Return the integer a spelled-out cardinal denotes, or None."""
    return _SPELLED.get(word.strip().lower())


def _to_decimal(raw: object) -> Decimal | None:
    """Best effort conversion of a scalar or a numeric string to Decimal."""
    if isinstance(raw, bool):
        # bool is an int subclass. `True` is not the number 1 in a duty report.
        return None
    if isinstance(raw, Decimal):
        return raw
    if isinstance(raw, int | float):
        try:
            return Decimal(str(raw))
        except InvalidOperation:
            return None
    if not isinstance(raw, str):
        return None
    text = raw.strip()
    text = _CURRENCY_PREFIX_RE.sub("", text)
    text = _CURRENCY_SUFFIX_RE.sub("", text)
    text = re.sub(r"[\s\u00a0]+", "", text.replace(",", ""))
    if not _NUMERIC_RE.match(text):
        return None
    try:
        return Decimal(text)
    except InvalidOperation:
        return None


def _format_decimal(value: Decimal) -> str:
    """Quantised, trailing-zero-free decimal string. Never exponential."""
    quantised = value.quantize(_QUANTUM, rounding=ROUND_HALF_UP)
    return format(quantised.normalize(), "f")


def canonical_number(raw: object) -> str | None:
    """Canonical decimal string for a number, or None if it is not numeric.

    >>> canonical_number("18,500")
    '18500'
    >>> canonical_number(61.3333333)
    '61.33'
    >>> canonical_number("61.30")
    '61.3'
    """
    value = _to_decimal(raw)
    if value is None:
        return None
    return _format_decimal(value)


def canonical_currency(raw: object) -> str | None:
    """Canonical form for a money amount. `INR 18,500`, `18500` and `₹18,500`
    all reduce to `18500`. The currency itself is not part of the key because
    the dataset is single currency and a symbol mismatch is not a fact error.
    """
    return canonical_number(raw)


def hours_to_minutes(hours: object) -> int | None:
    """Whole minutes for a value expressed in hours, rounded half up."""
    value = _to_decimal(hours)
    if value is None:
        return None
    return int((value * 60).quantize(Decimal("1"), rounding=ROUND_HALF_UP))


def canonical_duration_minutes(
    *,
    hours: object = None,
    minutes: object = None,
) -> int | None:
    """Whole minutes for a duration given as hours, minutes, or both.

    This is the equivalence that makes `61.33h` and `61h20m` the same fact.

    >>> canonical_duration_minutes(hours=61.33)
    3680
    >>> canonical_duration_minutes(hours=61, minutes=20)
    3680
    >>> canonical_duration_minutes(hours=1.33)
    80
    >>> canonical_duration_minutes(hours=8.25)
    495
    """
    total = Decimal(0)
    seen = False
    if hours is not None:
        as_hours = _to_decimal(hours)
        if as_hours is None:
            return None
        total += as_hours * 60
        seen = True
    if minutes is not None:
        as_minutes = _to_decimal(minutes)
        if as_minutes is None:
            return None
        total += as_minutes
        seen = True
    if not seen:
        return None
    return int(total.quantize(Decimal("1"), rounding=ROUND_HALF_UP))


def render_duration(total_minutes: int) -> str:
    """Render whole minutes the way the shipped answer keys do.

    >>> render_duration(80)
    '1h20m'
    >>> render_duration(495)
    '8h15m'
    >>> render_duration(45)
    '45m'
    """
    sign = "-" if total_minutes < 0 else ""
    magnitude = abs(total_minutes)
    hours, minutes = divmod(magnitude, 60)
    if hours and minutes:
        return f"{sign}{hours}h{minutes:02d}m"
    if hours:
        return f"{sign}{hours}h"
    return f"{sign}{minutes}m"


def canonical_date(raw: object) -> str | None:
    """Canonical `YYYY-MM-DD`, or `--MM-DD` when the year is not stated.

    The partial form matters: an answer that says "15 Sep" is naming the same
    day as `2026-09-15`, and the verifier registers both forms for every
    attested date so the two meet. A date shifted by one day does not match
    under either form, which is the failure this has to catch.
    """
    if isinstance(raw, bool):
        return None
    if isinstance(raw, datetime_cls):
        return raw.date().isoformat()
    if isinstance(raw, date_cls):
        return raw.isoformat()
    if not isinstance(raw, str):
        return None
    text = raw.strip()
    if not text:
        return None

    iso = re.match(r"^(\d{4})-(\d{2})-(\d{2})(?:[T ]|$)", text)
    if iso:
        year, month, day = (int(part) for part in iso.groups())
        if _valid_ymd(year, month, day):
            return f"{year:04d}-{month:02d}-{day:02d}"
        return None

    # "15 Sep", "15 Sep 2026", "15 September 2026", "15th Sep"
    day_first = re.match(
        r"^(\d{1,2})(?:st|nd|rd|th)?\s+([A-Za-z]{3,9})\.?(?:,?\s+(\d{4}))?$", text
    )
    if day_first:
        return _from_parts(day_first.group(2), day_first.group(1), day_first.group(3))

    # "Sep 15", "September 15, 2026"
    month_first = re.match(
        r"^([A-Za-z]{3,9})\.?\s+(\d{1,2})(?:st|nd|rd|th)?(?:,?\s+(\d{4}))?$", text
    )
    if month_first:
        return _from_parts(month_first.group(1), month_first.group(2), month_first.group(3))

    slashed = re.match(r"^(\d{1,2})/(\d{1,2})/(\d{4})$", text)
    if slashed:
        day, month, year = (int(part) for part in slashed.groups())
        if _valid_ymd(year, month, day):
            return f"{year:04d}-{month:02d}-{day:02d}"
    return None


def _from_parts(month_word: str, day_text: str, year_text: str | None) -> str | None:
    month = MONTH_ABBREVIATIONS.get(month_word.lower())
    if month is None:
        return None
    day = int(day_text)
    if not 1 <= day <= 31:
        return None
    if year_text is None:
        return f"--{month:02d}-{day:02d}"
    year = int(year_text)
    if not _valid_ymd(year, month, day):
        return None
    return f"{year:04d}-{month:02d}-{day:02d}"


def _valid_ymd(year: int, month: int, day: int) -> bool:
    try:
        date_cls(year, month, day)
    except ValueError:
        return False
    return True


def canonical_time(raw: object) -> str | None:
    """Canonical `HH:MM` clock time. Seconds and a trailing `Z` are dropped.

    The dataset is single timezone UTC, so a `Z` suffix carries no information
    the verifier can be wrong about.
    """
    if isinstance(raw, bool):
        return None
    if isinstance(raw, datetime_cls):
        return f"{raw.hour:02d}:{raw.minute:02d}"
    if not isinstance(raw, str):
        return None
    match = re.search(r"(\d{1,2}):(\d{2})(?::\d{2})?\s*Z?$", raw.strip())
    if not match:
        return None
    hour, minute = int(match.group(1)), int(match.group(2))
    if hour > 23 or minute > 59:
        return None
    return f"{hour:02d}:{minute:02d}"


def canonical_datetime(raw: object) -> tuple[str, str] | None:
    """Split a timestamp into its canonical date and canonical time."""
    if isinstance(raw, datetime_cls):
        return raw.date().isoformat(), f"{raw.hour:02d}:{raw.minute:02d}"
    if not isinstance(raw, str):
        return None
    text = raw.strip()
    match = re.match(r"^(\d{4}-\d{2}-\d{2})[T ](\d{2}:\d{2})(?::\d{2})?\s*Z?$", text)
    if not match:
        return None
    day = canonical_date(match.group(1))
    clock = canonical_time(match.group(2))
    if day is None or clock is None:
        return None
    return day, clock


def canonical_identifier(raw: object) -> str | None:
    """Canonical form for a crew id, pairing id, flight number, tail or rule id.

    Case and internal whitespace are normalised. Nothing else is: `C-3310` and
    `C-3301` must stay different, which is the whole point.
    """
    if not isinstance(raw, str):
        return None
    text = re.sub(r"\s+", "", raw.strip()).upper()
    return text or None

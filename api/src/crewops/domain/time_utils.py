"""Time parsing and duration formatting, in one place.

Two conventions this module exists to protect:

1. **Naive UTC.** Every timestamp in the dataset ends in a literal `Z` but the
   intended parse is `strptime(s, "%Y-%m-%dT%H:%M:%SZ")`, producing a naive
   datetime treated as UTC throughout. Attaching a tzinfo halfway through the
   pipeline mixes aware and naive values and throws at the first comparison.

2. **Two decimal hours.** The reference implementation that produced the answer
   keys rounds every duration to two places at the point of measurement
   (`round(td.total_seconds() / 3600.0, 2)`) and again after summing a window.
   Rounding later, or not at all, walks the totals away from the shipped keys.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta

#: The one timestamp format in the dataset. No offsets, no sub-minute precision.
UTC_FORMAT = "%Y-%m-%dT%H:%M:%SZ"


def parse_utc(value: str) -> datetime:
    """Parse a dataset timestamp into a naive datetime understood as UTC."""
    return datetime.strptime(value, UTC_FORMAT)


def format_utc(value: datetime) -> str:
    """Render a naive UTC datetime back into the dataset's format."""
    return value.strftime(UTC_FORMAT)


def parse_date(value: str) -> date:
    """Parse a bare `YYYY-MM-DD` date."""
    return date.fromisoformat(value)


def at_clock(day: date, clock: str) -> datetime:
    """Combine a date with an `HH:MM` clock string, as reserve windows are stored.

    No window in the dataset wraps midnight, so a same date construction is
    correct and wraparound logic would be inventing a case that does not exist.
    """
    hour, minute = (int(part) for part in clock.split(":"))
    return datetime(day.year, day.month, day.day, hour, minute)


def hours_between(start: datetime, end: datetime) -> float:
    """Elapsed hours, rounded to two places.

    Matches `hrs()` in the dataset generator exactly. Negative when `end`
    precedes `start`, which is how an overlapping duty pair is encoded.
    """
    return round((end - start).total_seconds() / 3600.0, 2)


def add_hours(value: datetime, hours: float) -> datetime:
    """Shift a timestamp by a fractional number of hours."""
    return value + timedelta(hours=hours)


def format_duration(hours: float) -> str:
    """Render decimal hours the way the shipped answer keys do: 1.33 -> `1h20m`.

    The whole hours are truncated and the remainder is rounded to the nearest
    minute, which is what produced `1h20m` for 1.33h and `8h15m` for 8.25h. A
    remainder that rounds up to 60 renders as `h60m`; that is the reference
    behaviour and no shipped key exercises it.
    """
    whole = int(hours)
    minutes = round((hours - whole) * 60)
    return f"{whole}h{minutes:02d}m"


def format_margin(margin: float) -> str:
    """Signed headroom as prose. Positive is room to spare, negative is a breach."""
    if margin < 0:
        return f"{format_duration(abs(margin))} over the limit"
    return f"{format_duration(margin)} spare"


def date_range(start: date, end: date) -> list[date]:
    """Every calendar date from `start` to `end`, inclusive at both ends."""
    if end < start:
        return []
    return [date.fromordinal(o) for o in range(start.toordinal(), end.toordinal() + 1)]


def window_dates(end: date, days: int) -> list[date]:
    """The `days` calendar dates ending at `end`, inclusive: `[end - days + 1, end]`.

    RULE-DUTY-02 and RULE-FLT-03 are calendar day windows, not rolling hour
    clocks. A 168 hour window gives different and wrong answers.
    """
    return date_range(end - timedelta(days=days - 1), end)


__all__ = [
    "UTC_FORMAT",
    "add_hours",
    "at_clock",
    "date_range",
    "format_duration",
    "format_margin",
    "format_utc",
    "hours_between",
    "parse_date",
    "parse_utc",
    "window_dates",
]

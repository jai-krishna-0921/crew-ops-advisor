"""Every timestamp that leaves this system says which zone it is in.

`_utcnow()` did `datetime.now(UTC).replace(tzinfo=None)`, which produces a
naive datetime that serialises as `2026-09-04T10:25:57.080412`. That string is
correct and unreadable: ECMAScript parses a date-time with no offset as LOCAL
time, so a browser in IST read every thread timestamp 5.5 hours early and the
conversation list said "5h ago" about a conversation that had just been
created. Nothing was wrong with the stored value. The wire format threw the
zone away and the reader guessed.

This matters more here than in most products. CLAUDE.md and the dataset are
emphatic that all times are UTC, because a crew controller reading a report
time in the wrong zone puts a crew at the airport an hour late. A timestamp
this system emits without a zone on it is a defect of the same family.
"""

from __future__ import annotations

from datetime import UTC

from crewops.agent.advisor import _utcnow as advisor_utcnow
from crewops.agent.runner import _utcnow as runner_utcnow


def test_the_advisor_stamps_an_aware_utc_time() -> None:
    stamped = advisor_utcnow()
    assert stamped.tzinfo is not None
    assert stamped.utcoffset() == UTC.utcoffset(None)


def test_the_runner_stamps_an_aware_utc_time() -> None:
    stamped = runner_utcnow()
    assert stamped.tzinfo is not None
    assert stamped.utcoffset() == UTC.utcoffset(None)


def test_the_serialised_form_carries_an_offset() -> None:
    """The string on the wire, which is the thing a browser actually parses."""
    for stamp in (advisor_utcnow(), runner_utcnow()):
        text = stamp.isoformat()
        assert text.endswith("+00:00") or text.endswith("Z"), text

"""The callout is the deliverable. It was computed and then thrown away.

Q36, a shipped Tier 3 question: "Draft the callout notification to C-3310 for
covering P-2291." `draft_notification` returns a `NotificationDraft` with a
`subject` and a ready-to-send `body`:

    Callout: P-2291, report 06:00Z 2026-09-15

    Captain C-3310, you are called out for P-2291.
    Day 1 (2026-09-15): report 06:00Z at BLR crew room. Flights DX412 / ...

The renderer looked for a str payload, a `text` fact, or `payload.text`, found
none of the three, and fell through to the generic template. What reached the
controller was the checklist of what a callout should contain:

    "Fill the callout template: Every time, station and flight number comes
     from rosters.json and flights.json"

Every figure in that was attested and the message itself never appeared. This
is the readability failure in its purest form: the answer existed, was correct,
and was not shown.
"""

from __future__ import annotations

import datetime as dt

SNAPSHOT = dt.datetime(2026, 9, 14, 18, 0, 0)

QUESTION = "Draft the callout notification to C-3310 for covering P-2291."


def _ask(resolver, question: str = QUESTION):
    return resolver.answer(question, thread_id="t-note", turn_id="u-1", asked_at=SNAPSHOT)


def _text(reply) -> str:
    return f"{reply.headline or ''}\n{reply.text}"


def test_the_message_itself_is_shown(resolver) -> None:
    reply = _ask(resolver)
    assert reply.kind.value == "answer", reply.text
    surface = _text(reply)
    assert "C-3310" in surface, surface
    assert "P-2291" in surface, surface


def test_it_carries_the_report_time_and_the_flights(resolver) -> None:
    surface = _text(_ask(resolver))
    assert "06:00" in surface, surface
    assert "DX412" in surface, surface


def test_it_does_not_lead_with_the_checklist(resolver) -> None:
    """"Fill the callout template" is instructions for writing one."""
    reply = _ask(resolver)
    assert not (reply.headline or "").startswith("Fill the callout template"), reply.headline


def test_the_draft_is_still_grounded(resolver) -> None:
    reply = _ask(resolver)
    assert reply.verification.status.value != "rejected", [
        item.atom for item in reply.verification.unattested
    ]

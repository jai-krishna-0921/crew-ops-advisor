"""What the previous turn established, carried into the next one.

Thread memory already existed for the agent: LangGraph's checkpointer restores
the message history, so the model can resolve "which of them are captains"
against the list it just produced. Offline there is no model to resolve a
reference, and the offline path is the one that must work with no API key.

So the resolver keeps the last ANSWERED turn per thread: the intent it ran and
the entities it ran with. A follow-up merges the two, field by field, with the
new question winning wherever it says anything:

    turn 1   "Who is on reserve at BLR on 2026-09-15?"
             intent=reserves  stations=(BLR,)  dates=(2026-09-15,)
    turn 2   "And what about the next day?"
             intent=reserves  stations=(BLR,)  dates=(2026-09-16,)

WHAT THIS DELIBERATELY DOES NOT DO. It does not infer. A merged entity was
either named in the follow-up or established by an answered turn in the same
thread, and the date can move by exactly one day because "the next day" is the
only span a controller means unambiguously. Nothing here reaches a controller
that the verifier has not attested, because this changes the QUESTION and not
the answer, exactly as `canonical_question` does.

Only answered turns are remembered. A refusal establishes nothing, so a
follow-up to one has nothing to carry and is refused in turn.
"""

from __future__ import annotations

from collections import OrderedDict
from dataclasses import dataclass, replace
from datetime import timedelta

from crewops.resolve.intents import Intent
from crewops.resolve.triage import Entities, day_shift

__all__ = ["PriorTurn", "ThreadContext", "merge_entities"]

#: Threads kept before the oldest is dropped. A desk runs a handful of live
#: conversations; this is generous and bounds the memory a long-lived server
#: holds without needing eviction policy anyone has to think about.
_CAPACITY = 256


@dataclass(frozen=True, slots=True)
class PriorTurn:
    """The last answered turn on a thread."""

    intent: Intent
    entities: Entities
    question: str


def merge_entities(prior: Entities, current: Entities, question: str) -> Entities:
    """The follow-up's entities, filled in from the turn before it.

    Field by field: whatever the follow-up names wins, and anything it leaves
    silent is inherited. `numbers` is never inherited, because a bare figure
    from the previous question means nothing in this one and is the easiest
    way to smuggle a stale value into a plan.
    """
    merged = Entities(
        crew_ids=current.crew_ids or prior.crew_ids,
        pairing_ids=current.pairing_ids or prior.pairing_ids,
        flight_numbers=current.flight_numbers or prior.flight_numbers,
        tails=current.tails or prior.tails,
        rule_ids=current.rule_ids or prior.rule_ids,
        stations=current.stations or prior.stations,
        dates=current.dates or prior.dates,
        times=current.times or prior.times,
        aircraft_types=current.aircraft_types or prior.aircraft_types,
        numbers=current.numbers,
        rank=current.rank or prior.rank,
    )

    shift = day_shift(question)
    if shift and merged.dates:
        moved = tuple(day + timedelta(days=shift) for day in merged.dates)
        merged = replace(merged, dates=moved)
    return merged


class ThreadContext:
    """The last answered turn per thread, bounded and in process.

    Not persisted. The audit trail is the `turns` table in `agent.memory`; this
    is only what the next question needs in order to be understood, and a
    restarted server asking the controller to say what they mean is a far
    smaller cost than a stale reference resolved against the wrong turn.
    """

    def __init__(self, capacity: int = _CAPACITY) -> None:
        self._capacity = capacity
        self._turns: OrderedDict[str, PriorTurn] = OrderedDict()

    def remember(self, thread_id: str, turn: PriorTurn) -> None:
        self._turns[thread_id] = turn
        self._turns.move_to_end(thread_id)
        while len(self._turns) > self._capacity:
            self._turns.popitem(last=False)

    def recall(self, thread_id: str) -> PriorTurn | None:
        turn = self._turns.get(thread_id)
        if turn is not None:
            self._turns.move_to_end(thread_id)
        return turn

    def forget(self, thread_id: str) -> None:
        self._turns.pop(thread_id, None)

"""Did the plan actually encode what the question asked for?

WHY THIS EXISTS. The offline resolver matches a question against a fixed set of
shapes. Matching a shape is not the same as answering the question: a shape has
a fixed argument list, and a constraint the question carries that the shape has
no argument for used to be discarded in silence. The tools then ran over the
unfiltered set and the renderer stated the result as the answer.

Three found by asking Tier 1 questions outside the shipped 38:

    "How many crew are not rated for A320?"   -> "123 crew match the filter."
    "How many flights does VT-DXF operate?"   -> "147 flight(s) match."
    "Which certifications expire before X?"   -> the certificates expiring after X

Every figure in those answers is real, computed by deterministic code, and
attested by a `Fact`. The verifier passes them because the verifier checks that
values are real, not that they answer the question that was asked. The guards in
`agent/guards.py` pass them because a legality-bearing tool did run. Nothing was
looking at whether the plan and the question were about the same thing.

That is the single most dangerous shape of failure this system can produce, and
it is the one the whole submission argues against: a fluent, checkable,
confidently wrong answer. `CLAUDE.md` rule 4 says abstain over guess. A narrow
resolver is intended. A narrow resolver that answers anyway is not.

WHAT THIS IS NOT. It is not a second intent matcher and it must not become one.
It answers one question, conservatively: does the plan mention everything the
question constrained on? When it cannot tell, it says nothing, because a
completeness check that fires on doubt abstains on everything and is the same
bug with better manners.
"""

from __future__ import annotations

import json
import re
from collections.abc import Sequence
from typing import Final

from crewops.resolve.intents import PlannedCall

__all__ = ["unmodelled_constraints"]


#: Negation applied to a filter. No tool in the surface takes a negated filter,
#: so any of these means the question cannot be expressed as a planned call.
#:
#: Deliberately anchored to a filter word rather than matching a bare "not".
#: Q24 ships as "Can reserve C-3305 cover the FULL pairing P-2291 (both days)?
#: Why or why not?" and a bare `\bnot\b` would decline it.
_NEGATED_FILTER: Final = re.compile(
    r"\b(?:not|non|never)[\s-]+"
    r"(?:rated|qualified|based|active|assigned|available|reserve|on\s+reserve|"
    r"scheduled|rostered|certified|current)\b"
    r"|\b(?:excluding|other\s+than|apart\s+from|instead\s+of)\b"
    r"|\bwithout\s+(?:a|an|the)?\s*"
    r"(?:rating|certificate|certification|licence|license|medical)\b"
    # A POOL DECLARED EXHAUSTED IS A FILTER TOO, just in the indicative.
    # "Every reserve at BLR is already used. How do I cover P-2291 now?"
    # answered and opened with a reserve at BLR. The controller had just said
    # that option does not exist. Nothing in the roster records a reserve as
    # spent, so there is no honest way to answer it: say so.
    #
    # An exhaustion quantifier is required on both sides, so "which reserves
    # are assigned to P-2291" stays an ordinary question rather than becoming
    # a refusal.
    r"|(?:\b(?:all|every|no|none)\b[^.?!]{0,60}\breserves?\b"
    r"|\breserves?\b[^.?!]{0,40}\b(?:all|every|none)\b)"
    r"[^.?!]{0,40}\b(?:used|gone|taken|assigned|committed|out|unavailable|"
    r"spent|exhausted|left|remaining)\b",
    re.IGNORECASE,
)

#: Identifier shapes that are always a filter when a question names one. A
#: question that says VT-DXF is asking about VT-DXF, so a plan that never
#: mentions it is answering something else.
#:
#: Station codes are deliberately absent. They appear in prose that is not a
#: filter ("crew based at BLR fly to BOM"), and a false abstention on a
#: supported shape costs more than this check gains.
_IDENTIFIERS: Final = re.compile(
    r"\bVT-[A-Z]{3}\b"  # aircraft tail
    r"|\bC-\d{4}\b"  # crew
    r"|\bP-\d{4}\b"  # pairing
    r"|\bDX\d{3}\b"  # flight number
)

#: "expiring before/by/until X" is a backward-looking window. Every
#: certification tool in the surface looks forward from an anchor, so the plan
#: silently answered the opposite question.
_BACKWARD_WINDOW: Final = re.compile(
    r"\b(?:expired?|expiring|lapsed?|lapsing|ended?|ending)\b[^.?!]{0,30}?"
    r"\b(?:before|prior\s+to|earlier\s+than|up\s+to|by)\b",
    re.IGNORECASE,
)

_FORWARD_ARGS: Final = frozenset({"within_days", "until", "horizon_days"})


def _planned_text(plan: Sequence[PlannedCall]) -> str:
    """Every planned call and its arguments, as one searchable string.

    `default=str` so a date or a datetime argument serialises rather than
    raising: this check must never be the reason a turn fails.
    """
    parts: list[str] = []
    for call in plan:
        parts.append(call.tool)
        try:
            parts.append(json.dumps(call.args, sort_keys=True, default=str))
        except (TypeError, ValueError):  # pragma: no cover - defensive
            parts.append(str(call.args))
    return " ".join(parts)


def _forward_window(plan: Sequence[PlannedCall]) -> bool:
    return any(
        any(key in _FORWARD_ARGS for key in (call.args or {})) for call in plan
    )


def unmodelled_constraints(
    question: str, plan: Sequence[PlannedCall]
) -> list[str]:
    """Constraints the question carries that no planned call encodes.

    Empty means the plan is at least as specific as the question. Each entry is
    written for a controller to read: it names the constraint, not the argument
    that was missing.
    """
    if not plan:
        return []
    planned = _planned_text(plan)
    found: list[str] = []

    negation = _NEGATED_FILTER.search(question)
    if negation is not None:
        found.append(
            f"the negative condition {negation.group(0).strip()!r}. No tool takes "
            "a negated filter, so this would have been answered over the "
            "unfiltered set"
        )

    # AT LEAST ONE named identifier has to reach the plan, not every one.
    #
    # A question routinely names an identifier as context while keying on a
    # different one. S6 says "the captains of both VT-DXA (C-3940) and VT-DXB
    # (C-1938)": the tails describe, the crew ids filter, and requiring every
    # identifier to appear in the args declined the flagship scenario. What is
    # actually diagnostic is a question that names identifiers of which *none*
    # reached the plan, because then the plan is keyed on nothing the question
    # said and is answering over the whole collection.
    named = list(dict.fromkeys(m.group(0) for m in _IDENTIFIERS.finditer(question)))
    if named and not any(ident in planned for ident in named):
        found.append(
            f"{', '.join(named)}, which the question names and no tool call "
            "filters on"
        )

    if _BACKWARD_WINDOW.search(question) and _forward_window(plan):
        found.append(
            "a window that runs backwards from the date given. The tool looks "
            "forward from an anchor, so this would have answered the opposite "
            "question"
        )

    return found


"""Structural guardrails, enforced in code.

The verifier checks whether the *values* in an answer are grounded. These
guards check whether the answer was *entitled to exist*: whether the right
class of computation ran at all.

The distinction matters because every atom in "C-3310 is legal for P-2291" can
be attested while the sentence is false. Attestation is about values; a verdict
is a relation between values, and no amount of token matching catches a wrong
relation. What catches it is refusing to accept a verdict that no rules engine
produced.

Each guard returns a `GuardFailure` naming the tools that would fix it, so the
repair pass can be specific rather than scolding.
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Final

from crewops.contracts import RETRIEVAL_ONLY, AbstentionReason, ToolEnvelope

__all__ = [
    "EM_DASH",
    "EN_DASH",
    "LEGALITY_BEARING_TOOLS",
    "RANKING_BEARING_TOOLS",
    "GuardFailure",
    "run_guards",
    "strip_em_dashes",
]


@dataclass(frozen=True, slots=True)
class GuardFailure:
    """One structural rule the drafted answer broke."""

    guard: str
    reason: str
    required_tools: tuple[str, ...]
    abstention_reason: AbstentionReason


# ---------------------------------------------------------------------------
# Which tools can stand behind a legality verdict.
#
# `check_legality` is the canonical one and the only tool whose entire job is
# to produce a verdict. The other two are accepted because their payloads embed
# `LegalityReport` objects produced by the same rules engine on the same data:
# a cover search rule checks every candidate, and a reassignment simulation
# rule checks the mover and anyone displaced. Reporting the verdict inside one
# of those is reporting the engine's output, not inferring one.
#
# Nothing else qualifies. Retrieval never qualifies: knowing that a crew member
# has 51.83 duty hours does not establish that adding a pairing breaches a
# limit, and the temptation to do that subtraction is exactly the failure mode
# this whole system exists to remove.
# ---------------------------------------------------------------------------
LEGALITY_BEARING_TOOLS: Final[frozenset[str]] = frozenset(
    {"check_legality", "find_cover_options", "simulate_reassignment"}
)

#: Only a cover search ranks options against costs and trade-offs.
RANKING_BEARING_TOOLS: Final[frozenset[str]] = frozenset({"find_cover_options"})

EM_DASH: Final = "\u2014"
#: An en dash between spaces reads as an em dash and is banned for the same
#: reason. Written as an escape so this source file stays plain ASCII.
EN_DASH: Final = "\u2013"

# A verdict claim: an assertion that an assignment is or is not permitted.
_VERDICT_RE: Final = re.compile(
    r"\b(?:"
    r"is (?:not )?legal|are (?:not )?legal|illegal|not legal|legally"
    r"|breach(?:es|ed|ing)?|in breach|violat(?:es|ed|ion|ions)"
    r"|exceeds? the limit|over the limit|within (?:the )?limits?"
    r"|complies with|compliant|non-compliant"
    r"|(?:can|cannot|can't|may|may not|must not) (?:legally )?(?:operate|cover|fly|take)"
    r"|clears? all seven|passes all seven"
    r")\b",
    re.IGNORECASE,
)

# A ranked recommendation: an ordering of courses of action.
_RANKING_RE: Final = re.compile(
    r"\b(?:"
    r"option\s*\d|rank(?:ed|ing)?\s*\d|ranked options?"
    r"|cheapest|best option|preferred option|recommend(?:ed|ation)?"
    r"|first choice|second choice|fall\s?back option"
    r")\b",
    re.IGNORECASE,
)

# Hedged non-answers that should have been an abstention.
_NON_ANSWER_RE: Final = re.compile(
    r"^\s*(?:i (?:do not|don't) (?:know|have)|unable to|sorry)", re.IGNORECASE
)


def _tools_used(envelopes: Sequence[ToolEnvelope]) -> set[str]:
    """Names of tools that actually returned something usable this turn."""
    return {envelope.tool for envelope in envelopes if envelope.ok}


def tier_guard(
    tier: int | None, envelopes: Sequence[ToolEnvelope]
) -> GuardFailure | None:
    """Retrieval alone cannot support a Tier 2 or Tier 3 answer.

    Retrieval establishes what is. It does not establish what follows. This is
    the guard that stops the system degrading into a fluent lookup with a
    confident tone.
    """
    if tier is None or tier < 2:
        return None
    used = _tools_used(envelopes)
    if not used:
        return GuardFailure(
            guard="tier",
            reason=(
                f"This is a tier {tier} question and no tool returned anything. "
                "A consequence or a recommendation cannot be reasoned out; it has "
                "to be computed."
            ),
            required_tools=(
                ("simulate_absence", "check_legality")
                if tier == 2
                else ("find_cover_options",)
            ),
            abstention_reason=AbstentionReason.UNDERSPECIFIED,
        )
    if used <= RETRIEVAL_ONLY:
        return GuardFailure(
            guard="tier",
            reason=(
                f"This is a tier {tier} question but only retrieval tools ran "
                f"({', '.join(sorted(used))}). Retrieval establishes what is; it "
                "does not establish what follows."
            ),
            required_tools=(
                ("simulate_absence", "simulate_reassignment", "check_legality")
                if tier == 2
                else ("find_cover_options",)
            ),
            abstention_reason=AbstentionReason.UNDERSPECIFIED,
        )
    return None


def verdict_guard(draft: str, envelopes: Sequence[ToolEnvelope]) -> GuardFailure | None:
    """A legality claim requires a tool that ran the rules engine."""
    if not _VERDICT_RE.search(draft):
        return None
    if _tools_used(envelopes) & LEGALITY_BEARING_TOOLS:
        return None
    return GuardFailure(
        guard="verdict",
        reason=(
            "The answer states whether an assignment is permitted, but no tool "
            "evaluated the rules this turn. A verdict is computed, never inferred."
        ),
        required_tools=("check_legality",),
        abstention_reason=AbstentionReason.REQUIRES_UNMODELLED_RULE,
    )


def ranking_guard(draft: str, envelopes: Sequence[ToolEnvelope]) -> GuardFailure | None:
    """A ranked recommendation requires a cover search."""
    if not _RANKING_RE.search(draft):
        return None
    if _tools_used(envelopes) & RANKING_BEARING_TOOLS:
        return None
    return GuardFailure(
        guard="ranking",
        reason=(
            "The answer ranks courses of action, but no cover search ran. Ranking "
            "needs every candidate enumerated, rule checked and priced, including "
            "the ones that were rejected."
        ),
        required_tools=("find_cover_options",),
        abstention_reason=AbstentionReason.UNDERSPECIFIED,
    )


def substance_guard(draft: str) -> GuardFailure | None:
    """An empty or hedging answer should be an abstention with a reason."""
    if draft.strip() and not _NON_ANSWER_RE.match(draft):
        return None
    return GuardFailure(
        guard="substance",
        reason=(
            "The answer is empty or is a bare refusal. A refusal has to name what "
            "was missing and what the system can answer instead."
        ),
        required_tools=(),
        abstention_reason=AbstentionReason.UNDERSPECIFIED,
    )


def run_guards(
    *, draft: str, tier: int | None, envelopes: Sequence[ToolEnvelope]
) -> GuardFailure | None:
    """First failing guard, in the order a controller would notice them."""
    for failure in (
        substance_guard(draft),
        verdict_guard(draft, envelopes),
        ranking_guard(draft, envelopes),
        tier_guard(tier, envelopes),
    ):
        if failure is not None:
            return failure
    return None


def strip_em_dashes(text: str) -> str:
    """House style, enforced rather than requested.

    The system prompt asks for no em dash. This makes it true regardless. An em
    dash between spaces becomes a comma; one without spaces becomes a comma and
    a space, which reads correctly in the constructions the model produces.
    """
    if EM_DASH not in text and EN_DASH not in text:
        return text
    cleaned = re.sub(rf"\s*{EM_DASH}\s*", ", ", text)
    cleaned = re.sub(rf"\s*{EN_DASH}\s*", ", ", cleaned)
    return re.sub(r",\s*,", ",", cleaned)

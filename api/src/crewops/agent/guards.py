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
from typing import Any, Final

from crewops.contracts import REQUIRED_FOR, RETRIEVAL_ONLY, AbstentionReason, ToolEnvelope

__all__ = [
    "EM_DASH",
    "EN_DASH",
    "LEGALITY_BEARING_TOOLS",
    "RANKING_BEARING_TOOLS",
    "GuardFailure",
    "breach_agreement_guard",
    "computed_breaches",
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

    #: Whether running out of repair budget on this guard should abstain.
    #:
    #: A SAFETY guard is fatal: leading with a pass over a computed breach, or
    #: a tier 3 verdict built from retrieval alone, is dangerous, and refusing
    #: beats it. A STYLE guard is not: re-listing options that are already
    #: drawn beside the prose is untidy, and trading a correct answer for a
    #: tidy refusal inverts the scoring principle the whole system rests on.
    #: Measured, four runs: three good answers and one abstention that had
    #: nothing to do with the style violation, because the rewrite spent the
    #: single repair budget and the verifier then had none left.
    fatal: bool = True


# ---------------------------------------------------------------------------
# Which tools can stand behind a legality verdict.
#
# `check_legality` is the canonical one and the only tool whose entire job is
# to produce a verdict. The others qualify because their output comes from the
# same rules engine on the same data: a cover search rule checks every
# candidate, a reassignment simulation rule checks the mover and anyone
# displaced, and `earliest_report` evaluates RULE-REST-04 and returns its trace.
# Reporting a verdict from inside one of those is reporting the engine's
# output, not inferring one.
#
# Nothing else qualifies. Retrieval never qualifies: knowing that a crew member
# has 51.83 duty hours does not establish that adding a pairing breaches a
# limit, and the temptation to do that subtraction is exactly the failure mode
# this whole system exists to remove.
#
# Derived from the contract rather than restated. These were two hand
# maintained lists and they had already drifted: this one carried
# `simulate_reassignment` and not `plan_joint_cover`, `REQUIRED_FOR` carried
# the reverse. Adding a tool to one and not the other is silent, and the
# symptom is a guard refusing an answer the rules engine genuinely produced.
# ---------------------------------------------------------------------------
LEGALITY_BEARING_TOOLS: Final[frozenset[str]] = REQUIRED_FOR["legality_claim"]

#: Only a cover search ranks options against costs and trade-offs.
RANKING_BEARING_TOOLS: Final[frozenset[str]] = REQUIRED_FOR["recommendation_claim"]

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


#: Every way an answer says "all clear". Matched against the lead only.
_ALL_CLEAR_RE: Final = re.compile(
    r"\b(?:"
    r"passes\s+(?:all|every|the)\b"
    r"|breaches\s+no\b"
    r"|no\s+(?:rule\s+)?(?:is\s+)?breach(?:ed|es)?\b"
    r"|does\s+not\s+breach\b"
    r"|within\s+(?:all\s+)?(?:the\s+)?limits?\b"
    r"|is\s+legal\s+to\s+(?:operate|fly)\b"
    r"|no\s+limit\s+is\s+breached\b"
    # THE PLAIN VERDICT, which is how a legality question is actually
    # answered. Q24 asks "is C-3305 legal to cover the full pairing" and the
    # inversion reads "Yes, C-3305 is legal to cover the full pairing". None
    # of the shapes above matched a single word of it.
    r"|(?:is|are)\s+legal\b"
    r"|(?:can|may)\s+(?:legally\s+)?(?:cover|operate|fly|take|work)\b"
    r"|(?:is|are)\s+(?:cleared|fine|ok(?:ay)?)\s+to\b"
    # A bare "yes" is deliberately absent. It means whatever the question
    # meant, and "Yes. RULE-FDP-01 is breached" is a correct answer that opens
    # with one. Only phrases that assert legality on their own belong here.
    r"|within\s+limits\b"
    r")",
    re.IGNORECASE,
)

#: Saying a limit *was* broken. Used to decide ordering, not presence.
_BREACH_MENTION_RE: Final = re.compile(
    r"\b(?:breach(?:ed|es|ing)?|exceed(?:s|ed)?|over\s+the\s+limit|illegal|"
    r"not\s+legal|cannot\s+legally)\b",
    re.IGNORECASE,
)

#: How many leading characters count as "the lead". A controller reads the
#: first line and acts on it, so that is where agreement is enforced.
_LEAD_CHARS: Final = 240


def computed_breaches(envelopes: Sequence[ToolEnvelope]) -> list[str]:
    """Every breach the deterministic layer computed this turn.

    Reads the typed `Fact` channel and the payload flag. A failed envelope
    establishes nothing, which is the verifier's invariant 4 applied here: a
    call that errored is exactly the case where nothing was computed at all.
    """
    found: list[str] = []
    for envelope in envelopes:
        if not envelope.ok:
            continue
        for fact in envelope.facts or ():
            if fact.key.rsplit(".", 1)[-1] == "breach" and fact.value is True:
                found.append(fact.derivation or f"{fact.key} is True")
        payload = envelope.payload
        if isinstance(payload, dict) and payload.get("breach") is True:
            detail = payload.get("breach_detail")
            if isinstance(detail, str) and detail and detail not in found:
                found.append(detail)
            continue
        # THE SHAPE THIS GUARD COULD NOT SEE, and the most common one in the
        # system. `simulate_delay` returns a dict with a `breach` flag, which
        # is what the two scans above were written for. `check_legality`
        # returns a typed `LegalityReport` whose `overall` is a Verdict and
        # whose detail lives in `per_day`. It is the tool whose entire job is
        # computing breaches, and `computed_breaches` returned nothing for it,
        # so an answer was free to say "legal" over the top of a BREACH.
        found.extend(_report_breaches(payload, found))
    return found


def _report_breaches(payload: Any, already: Sequence[str]) -> list[str]:
    """Breaches carried by a typed report, from any payload shaped like one.

    Duck typed on purpose. `LegalityReport` and the per-option `legality` on a
    `CoverOption` both expose `overall` and `breaches`, and a guard that
    imported either would tie the agent package to the shape of one tool's
    return value.
    """
    overall = getattr(payload, "overall", None)
    if overall is None or getattr(overall, "value", overall) != "breach":
        return []

    found: list[str] = []
    traces = getattr(payload, "breaches", None) or ()
    for trace in traces:
        detail = getattr(trace, "arithmetic", "") or getattr(trace, "rule_id", "")
        line = f"{getattr(trace, 'rule_id', 'a rule')}: {detail}"
        if line not in already and line not in found:
            found.append(line)
    if not found:
        subject = getattr(payload, "crew_id", "") or "the candidate"
        reference = getattr(payload, "assignment_ref", "") or "this assignment"
        found.append(f"{subject} breaches on {reference}.")
    return found


def breach_agreement_guard(
    draft: str, envelopes: Sequence[ToolEnvelope]
) -> GuardFailure | None:
    """The answer may not lead with a pass when a tool computed a breach.

    This is the one failure worse than an abstention, and neither of the other
    two mechanisms sees it. The verifier attests values, and every value in
    "P-2203 passes all seven rules" is real. `verdict_guard` checks that a
    rules tool ran, and in the case this was written for six of them did, all
    returning pass, because the pairing *as scheduled* does pass. The question
    was about the delay.

    So this checks a relation rather than a value: does the lead agree with
    what the deterministic layer computed? Only the lead, because an answer
    that opens with the breach and later notes what passes is correct, and
    reads better than one that refuses to mention a pass at all.
    """
    breaches = computed_breaches(envelopes)
    if not breaches:
        return None

    lead = draft.strip()[:_LEAD_CHARS]
    all_clear = _ALL_CLEAR_RE.search(lead)
    if all_clear is None:
        return None

    # Ordering, not presence. "RULE-FDP-01 is breached, though as scheduled it
    # passes all seven rules" is a good answer and mentions both. What is
    # dangerous is reaching the all-clear first, because that is the sentence
    # a controller acts on.
    mention = _BREACH_MENTION_RE.search(lead)
    if mention is not None and mention.start() < all_clear.start():
        return None
    return GuardFailure(
        guard="breach_agreement",
        reason=(
            "The answer opens by reporting a pass, but the rules engine computed "
            f"a breach this turn: {breaches[0]} A controller reads the first line "
            "and acts on it, so the breach has to lead. State it first, then say "
            "what passes and under which assumption."
        ),
        required_tools=("check_legality",),
        abstention_reason=AbstentionReason.CONFLICTING_DATA,
    )


#: How many of the ranked options the prose may name. The recommendation, and
#: one alternative for when the first choice is unavailable.
#:
#: Not a number picked to make something pass. The offline renderer arrived at
#: exactly this shape on its own (rank 1, one next option, the closest
#: exclusion, 81 words), so the bar sits where a good answer already sits.
_NAMED_OPTIONS_MAX: Final = 2

#: Below this many options there is nothing to over-enumerate: naming both of
#: two is a comparison, not a recital.
_ENUMERATION_FLOOR: Final = 3


def enumeration_guard(
    draft: str, envelopes: Sequence[ToolEnvelope]
) -> GuardFailure | None:
    """The prose may not re-list the ranked options that are drawn beside it.

    A tier 3 answer renders the options as cards and as a cost comparison. The
    prose above them named five of six with their costs, so a controller read
    the same five covers three times and the callout they were meant to act on
    sat under a screen and a half of it.

    `prompts.py` already forbids this in as many words. Saying it a third time
    is not the fix: this is a structural property of the answer and it is
    deterministically checkable, which is what this module is for.

    Rejects are deliberately not counted. "C-1017 was the closest exclusion" is
    the reasoning a controller wants, and the offline path says it too.
    """
    recommendation = next(
        (
            envelope.payload
            for envelope in envelopes
            if envelope.ok and _is_recommendation(envelope.payload)
        ),
        None,
    )
    if recommendation is None:
        return None

    options = [option for option in recommendation.options if option.crew_id]
    if len(options) < _ENUMERATION_FLOOR:
        return None

    named = [option.crew_id for option in options if option.crew_id in draft]
    if len(named) <= _NAMED_OPTIONS_MAX:
        return None

    surplus = named[_NAMED_OPTIONS_MAX:]
    return GuardFailure(
        guard="enumeration",
        reason=(
            f"The answer names {len(named)} of the ranked options "
            f"({', '.join(named)}) and the interface already draws every one of "
            "them as a card with its cost. Name the option you recommend and at "
            "most one alternative, then cut the rest: "
            + ", ".join(surplus)
            + ". Use the space for what the cards cannot say, which is the "
            "constraint that binds and the single thing that would change the "
            "answer."
        ),
        required_tools=(),
        abstention_reason=AbstentionReason.UNDERSPECIFIED,
        fatal=False,
    )


def _is_recommendation(payload: object) -> bool:
    """Duck typed, so this module does not import the ops contracts."""
    return hasattr(payload, "options") and hasattr(payload, "ranking_basis")


def run_guards(
    *, draft: str, tier: int | None, envelopes: Sequence[ToolEnvelope]
) -> GuardFailure | None:
    """First failing guard, in the order a controller would notice them."""
    for failure in (
        substance_guard(draft),
        breach_agreement_guard(draft, envelopes),
        verdict_guard(draft, envelopes),
        ranking_guard(draft, envelopes),
        enumeration_guard(draft, envelopes),
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

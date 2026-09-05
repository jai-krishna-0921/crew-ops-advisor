"""Grading one answer against one shipped answer key.

Four outcomes, and the distinction between two of them is the whole point:

| Outcome | Meaning |
|---|---|
| `CORRECT` | every primary fact in the key is asserted, and no verdict is inverted |
| `PARTIAL` | some primary facts asserted, none contradicted |
| `ABSTAINED` | the system declined, with a reason |
| `WRONG` | facts missing beyond the threshold, or a verdict inverted |

**An abstention is never a failure.** The problem statement says answering ten
questions correctly and saying "I cannot answer that reliably" on the eleventh
scores higher than answering all eleven with three wrong (page 6). A scorecard
that folded abstentions into the wrong column would push this project in
exactly the wrong direction, so they are counted, reported and tracked
separately, and the summary never adds them to the failures.

A **verdict inversion** is graded worse than a miss and flagged `unsafe`. Saying
a candidate is legal when the key says they breach is an operational error, not
a shortfall in recall, and no amount of correct surrounding detail redeems it.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any

from crewops.contracts.reply import Reply, ReplyKind
from crewops.contracts.rules import Verdict
from crewops.eval import atoms as atom_lib
from crewops.eval.atoms import Atom
from crewops.eval.cases import Case

#: Fraction of primary atoms required for CORRECT and for PARTIAL.
CORRECT_THRESHOLD = 0.999
PARTIAL_THRESHOLD = 0.5

#: Rubric questions are graded generously by design: their keys say in terms
#: that they are not exact-match targets.
RUBRIC_CORRECT_THRESHOLD = 0.45
RUBRIC_PARTIAL_THRESHOLD = 0.2


class Outcome(StrEnum):
    CORRECT = "correct"
    PARTIAL = "partial"
    ABSTAINED = "abstained"
    WRONG = "wrong"
    ERROR = "error"
    SKIPPED = "skipped"

    @property
    def is_failure(self) -> bool:
        """Abstention is deliberately not a failure. Neither is a skip."""
        return self in {Outcome.WRONG, Outcome.ERROR}


@dataclass
class Grade:
    case_id: str
    tier: int
    outcome: Outcome
    primary_recall: float = 0.0
    full_recall: float = 0.0
    missed: list[str] = field(default_factory=list)
    unsafe: bool = False
    graded_as: str = "containment"
    grounded: bool | None = None
    verification_status: str | None = None
    abstention_reason: str | None = None
    latency_ms: int = 0
    note: str = ""

    def as_dict(self) -> dict[str, Any]:
        return {
            "case_id": self.case_id,
            "tier": self.tier,
            "outcome": self.outcome.value,
            "primary_recall": round(self.primary_recall, 4),
            "full_recall": round(self.full_recall, 4),
            "missed": self.missed,
            "unsafe": self.unsafe,
            "graded_as": self.graded_as,
            "grounded": self.grounded,
            "verification_status": self.verification_status,
            "abstention_reason": self.abstention_reason,
            "latency_ms": self.latency_ms,
            "note": self.note,
        }


# ------------------------------------------------------------------ expected

#: Fields that appear identically in every option of every answer key and so
#: measure boilerplate rather than correctness. `rules_checked` lists all seven
#: rule ids on every single option in every scenario; requiring a
#: conversational answer to recite them turns recall into a test of verbosity.
#: They are pruned from the primary view and retained in `full_recall`, so the
#: report still shows whether the answer cited its rule coverage.
BOILERPLATE_FIELDS: frozenset[str] = frozenset({"rules_checked", "note"})


def _prune(value: Any) -> Any:
    if isinstance(value, dict):
        return {k: _prune(v) for k, v in value.items() if k not in BOILERPLATE_FIELDS}
    if isinstance(value, list):
        return [_prune(item) for item in value]
    return value


def reduce_expected(expected: Any) -> Any:
    """The subset of an answer key a good conversational answer must assert.

    Tier 3 keys are exhaustive enumerations: S2 lists six ranked options, each
    repeating all seven rule ids. No usable answer recites all of that, so
    grading Tier 3 on full recall would systematically understate a correct
    system. Where the key has a ranking structure, the primary view is the
    chosen option plus whatever sits alongside it. Everything else is reported
    as `full_recall` and does not decide the outcome.

    Keys with no ranking structure are returned whole: Q01's twelve reserves
    and Q35's thirteen assessed flights are all genuinely required.
    """
    if isinstance(expected, dict):
        if "expected_choice" in expected:
            rest = {k: v for k, v in expected.items() if k not in {"options", "expected_choice"}}
            rest["expected_choice"] = expected["expected_choice"]
            return _prune(rest)
        if isinstance(expected.get("options"), list) and expected["options"]:
            rest = {k: v for k, v in expected.items() if k != "options"}
            rest["options"] = [expected["options"][0]]
            return _prune(rest)
        return _prune(expected)

    if isinstance(expected, list) and expected:
        # `rank` must be an ordinal, not a job title. Q01's reserves carry
        # `"rank": "Captain"`, and reading that as a ranking position collapses
        # twelve required reserves down to whichever name sorts first.
        ranked = [
            row
            for row in expected
            if isinstance(row, dict) and isinstance(row.get("rank"), int | float)
        ]
        if len(ranked) == len(expected) and len(expected) > 1:
            return _prune([min(ranked, key=lambda row: float(row["rank"]))])

    return _prune(expected)


def expected_verdict(expected: Any) -> bool | None:
    """True when the key says the assignment is legal, False when it breaches.

    Only read from an explicit top level `legal` or `breach` field, so that a
    Tier 3 answer carrying both legal options and rejected candidates is never
    mistaken for a verdict question.
    """
    if not isinstance(expected, dict):
        return None
    if isinstance(expected.get("legal"), bool):
        return bool(expected["legal"])
    if isinstance(expected.get("breach"), bool):
        return not bool(expected["breach"])
    return None


# ------------------------------------------------------------------ produced

_NEGATIVE = re.compile(
    r"not legal|illegal|would exceed|exceeds the|over the limit|breach\w*|"
    r"cannot legally|is not permitted|not compliant|must not|ineligible",
    re.IGNORECASE,
)
_POSITIVE = re.compile(
    r"is legal|legally|permitted|no breach|within the limit|passes all|"
    r"compliant|clears all|clean cover",
    re.IGNORECASE,
)


def rendered_surface(reply: Reply) -> str:
    """Everything a controller actually sees, as one block of text.

    Prose, headline, tables, rule arithmetic and ranked options all count: an
    answer that puts the figure in a table rather than a sentence has still
    asserted it, and grading prose alone would punish the better interface.
    """
    parts: list[str] = [reply.headline or "", reply.text]

    for table in reply.tables:
        parts.append(table.title)
        parts.append(" ".join(table.columns))
        for row in table.rows:
            parts.append(" ".join("" if cell is None else str(cell) for cell in row))

    for trace in reply.traces:
        parts.append(f"{trace.label} {trace.detail}")

    for rule_trace in reply.rule_traces:
        parts.append(
            f"{rule_trace.rule_id} {rule_trace.arithmetic} {rule_trace.margin_human or ''}"
        )

    for fact in reply.facts:
        parts.append(f"{fact.label} {fact.rendered()} {fact.derivation or ''}")

    if reply.impact is not None:
        parts.append(reply.impact.explanation)
        parts.extend(leg.flight_no for leg in reply.impact.uncrewed_flights)
        parts.extend(reply.impact.pairings_broken)
        parts.extend(risk.detail for risk in reply.impact.downstream_risks)
        parts.append(f"passengers {reply.impact.passengers_affected}")

    if reply.recommendation is not None:
        rec = reply.recommendation
        parts.append(rec.situation)
        parts.append(rec.ranking_basis)
        for option in [*rec.options, *rec.rejected]:
            parts.append(
                f"{option.action} {option.crew_id} {option.cost.total_inr} "
                f"{option.coverage_summary} {option.reasoning}"
            )
        if rec.notification_draft:
            parts.append(rec.notification_draft)

    if reply.abstention is not None:
        parts.append(reply.abstention.message)
        parts.extend(reply.abstention.did_establish)

    return "\n".join(part for part in parts if part)


def produced_verdict(reply: Reply) -> bool | None:
    """Whether the reply asserts legality, illegality, or neither.

    A COVER SEARCH IS ANSWERED BY ITS OPTIONS, NOT BY ITS REJECTS.
    `collect_rule_traces` walks a payload recursively, so a Tier 3 reply
    carries the breaching trace of every candidate the search excluded. Reading
    those as the reply's verdict marked a correct, complete Q37 answer as an
    inverted verdict: full recall, grounded, and flagged unsafe for showing its
    working. `expected_verdict` above refuses to read a verdict out of a Tier 3
    key for the same reason, and says so; this is the produced side of that.

    So when a recommendation is present the verdict is whether a legal option
    exists, which the recommendation states directly. Rejected candidates are
    evidence about other people, not a verdict about this assignment.
    """
    if reply.recommendation is not None:
        return any(option.legal for option in reply.recommendation.options)

    breaches = [t for t in reply.rule_traces if t.verdict is Verdict.BREACH]
    passes = [t for t in reply.rule_traces if t.verdict is Verdict.PASS]
    if breaches:
        return False
    if passes:
        return True

    text = rendered_surface(reply)
    negative = bool(_NEGATIVE.search(text))
    # Strip the negative phrases before testing for positives, so that
    # "cannot legally operate" is not read as an assertion of legality.
    positive = bool(_POSITIVE.search(_NEGATIVE.sub(" ", text)))
    if negative and not positive:
        return False
    if positive and not negative:
        return True
    return None


# ------------------------------------------------------------------- rubric

_STOPWORDS: frozenset[str] = frozenset(
    {
        "about", "above", "also", "are", "been", "being", "below", "but",
        "could", "did", "does", "doing", "each", "for", "from", "had", "has",
        "have", "here", "into", "its", "just", "more", "most", "not", "only",
        "over", "per", "should", "some", "such", "than", "that", "the", "their",
        "them", "then", "there", "they", "this", "under", "very", "was", "were",
        "what", "when", "which", "while", "will", "with", "would", "your",
    }
)  # fmt: skip


def _content_words(value: Any) -> set[str]:
    text = atom_lib.flatten(value).lower()
    return {word for word in re.findall(r"[a-z][a-z_-]{3,}", text) if word not in _STOPWORDS}


def _rubric_coverage(expected: Any, surface: str) -> float:
    wanted = _content_words(expected)
    if not wanted:
        return 1.0
    have = set(re.findall(r"[a-z][a-z_-]{3,}", surface.lower()))
    return len(wanted & have) / len(wanted)


# -------------------------------------------------------------------- grader


def _salient(items: list[Atom]) -> list[Atom]:
    """Drop atoms too weak to require of an answer. See `atoms.is_trivial`."""
    return [atom for atom in items if not atom_lib.is_trivial(atom)]


def grade(case: Case, reply: Reply | None, *, latency_ms: int = 0, error: str = "") -> Grade:
    """Grade one question. See the module docstring for the outcome semantics."""
    if error:
        return Grade(case.case_id, case.tier, Outcome.ERROR, latency_ms=latency_ms, note=error)
    if reply is None:
        return Grade(case.case_id, case.tier, Outcome.SKIPPED, latency_ms=latency_ms)

    surface = rendered_surface(reply)
    produced = atom_lib.extract(surface)

    primary = _salient(atom_lib.dedupe(atom_lib.extract_from(reduce_expected(case.expected))))
    everything = _salient(atom_lib.dedupe(atom_lib.extract_from(case.expected)))

    _, primary_missed = atom_lib.containment(primary, produced)
    full_hit, _ = atom_lib.containment(everything, produced)

    primary_recall = 1.0 if not primary else 1 - len(primary_missed) / len(primary)
    full_recall = 1.0 if not everything else len(full_hit) / len(everything)

    grounded = reply.verification.status.value in {"verified", "repaired"}

    if reply.kind is ReplyKind.ABSTAIN:
        return Grade(
            case.case_id,
            case.tier,
            Outcome.ABSTAINED,
            primary_recall=primary_recall,
            full_recall=full_recall,
            grounded=grounded,
            verification_status=reply.verification.status.value,
            abstention_reason=(
                reply.abstention.reason.value if reply.abstention else "unspecified"
            ),
            latency_ms=latency_ms,
            note=reply.abstention.message if reply.abstention else "",
        )

    if case.is_rubric:
        score = max(primary_recall, _rubric_coverage(case.expected, surface))
        if score >= RUBRIC_CORRECT_THRESHOLD:
            outcome = Outcome.CORRECT
        elif score >= RUBRIC_PARTIAL_THRESHOLD:
            outcome = Outcome.PARTIAL
        else:
            outcome = Outcome.WRONG
        return Grade(
            case.case_id,
            case.tier,
            outcome,
            primary_recall=score,
            full_recall=full_recall,
            missed=[str(atom) for atom in primary_missed],
            graded_as="rubric",
            grounded=grounded,
            verification_status=reply.verification.status.value,
            latency_ms=latency_ms,
            note="key is explicitly not an exact-match target",
        )

    wanted = expected_verdict(case.expected)
    if wanted is not None:
        got = produced_verdict(reply)
        if got is not None and got is not wanted:
            return Grade(
                case.case_id,
                case.tier,
                Outcome.WRONG,
                primary_recall=primary_recall,
                full_recall=full_recall,
                missed=[str(atom) for atom in primary_missed],
                unsafe=True,
                grounded=grounded,
                verification_status=reply.verification.status.value,
                latency_ms=latency_ms,
                note=(
                    f"verdict inverted: key says legal={wanted}, answer asserts legal={got}. "
                    "This is an operational error, not a recall shortfall."
                ),
            )

    if primary_recall >= CORRECT_THRESHOLD:
        outcome = Outcome.CORRECT
    elif primary_recall >= PARTIAL_THRESHOLD:
        outcome = Outcome.PARTIAL
    else:
        outcome = Outcome.WRONG

    return Grade(
        case.case_id,
        case.tier,
        outcome,
        primary_recall=primary_recall,
        full_recall=full_recall,
        missed=[str(atom) for atom in primary_missed],
        grounded=grounded,
        verification_status=reply.verification.status.value,
        latency_ms=latency_ms,
    )


__all__ = [
    "CORRECT_THRESHOLD",
    "PARTIAL_THRESHOLD",
    "Grade",
    "Outcome",
    "expected_verdict",
    "grade",
    "produced_verdict",
    "reduce_expected",
    "rendered_surface",
]

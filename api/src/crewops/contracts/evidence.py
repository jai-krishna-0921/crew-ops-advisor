"""Evidence primitives.

Everything the system asserts to a controller flows through these types. A
`Fact` is the smallest citable unit: one value, one unit, one provenance
string. The verifier in `crewops.verify` accepts a sentence only when every
number, identifier and date in it can be matched to a `Fact` produced by a
tool during the same turn.

No module in this package may import a model client. These are plain data
types shared by the deterministic core, the agent and the HTTP layer.
"""

from __future__ import annotations

from datetime import date, datetime
from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, Field

FactUnit = Literal[
    "hours",
    "minutes",
    "days",
    "inr",
    "count",
    "date",
    "datetime",
    "crew_id",
    "flight_no",
    "pairing_id",
    "rule_id",
    "station",
    "aircraft_type",
    "rank",
    "text",
    "boolean",
    "percent",
]

FactValue = str | int | float | bool | None


class Provenance(str, Enum):
    """Where a fact came from.

    `DATASET` values are read straight off a provided JSON file and are true by
    definition. `COMPUTED` values are the output of deterministic arithmetic in
    `rules/` or `ops/` and must carry a `derivation`. `ASSUMED` marks a stated
    modelling assumption, which the UI renders differently so a controller can
    see the system is not claiming it as observed fact.
    """

    DATASET = "dataset"
    COMPUTED = "computed"
    ASSUMED = "assumed"


class Fact(BaseModel):
    """One citable atom.

    `key` is stable and machine readable so the UI can link prose to evidence.
    `derivation` is mandatory for computed facts: it is the arithmetic a
    controller reads when they want to challenge the number.
    """

    key: str = Field(description="Stable id, for example 'C-2087.duty_7d.projected'")
    label: str = Field(description="Human phrase, for example 'Projected 7 day duty'")
    value: FactValue
    unit: FactUnit
    provenance: Provenance
    source: str = Field(
        description=(
            "For dataset facts, 'file.json#pointer'. For computed facts, the "
            "fully qualified function that produced it."
        )
    )
    derivation: str | None = Field(
        default=None,
        description=(
            "The arithmetic, written out. Required when provenance is COMPUTED. "
            "Example: '48.50h prior + 12.83h added = 61.33h against a 60.00h limit'."
        ),
    )

    def rendered(self) -> str:
        """The value as it should appear in prose, so the verifier can match it."""
        if isinstance(self.value, float):
            return f"{self.value:.2f}".rstrip("0").rstrip(".")
        return str(self.value)


class TraceStep(BaseModel):
    """One readable step in a chain of reasoning.

    Steps are produced by deterministic code, never by the model. The agent may
    choose which steps to surface, but may not author them.
    """

    label: str
    detail: str
    fact_keys: list[str] = Field(default_factory=list)


class Citation(BaseModel):
    """A pointer back into the provided dataset."""

    file: str
    pointer: str = Field(description="Record id or JSON pointer within the file")
    note: str | None = None


class ToolEnvelope(BaseModel):
    """The uniform return type of every tool the agent can call.

    The agent sees `payload` and `trace`. The verifier sees `facts`. Both come
    from the same call, so an answer can never cite a number the tools did not
    compute during this turn.
    """

    tool: str
    args: dict[str, Any] = Field(default_factory=dict)
    ok: bool = True
    payload: Any = None
    facts: list[Fact] = Field(default_factory=list)
    trace: list[TraceStep] = Field(default_factory=list)
    citations: list[Citation] = Field(default_factory=list)
    latency_ms: int = 0
    error: str | None = None
    truncated: bool = Field(
        default=False,
        description="True when the payload was capped for prompt budget. The "
        "full result is still available to the HTTP layer.",
    )

    def fact_index(self) -> dict[str, Fact]:
        return {f.key: f for f in self.facts}


class Table(BaseModel):
    """A result set the UI renders as a real table rather than as prose."""

    title: str
    columns: list[str]
    rows: list[list[FactValue]]
    row_ids: list[str] = Field(
        default_factory=list,
        description="Optional stable id per row so the UI can link to detail views",
    )
    caption: str | None = None


class Confidence(str, Enum):
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class AbstentionReason(str, Enum):
    """Why the system declined. Every value is a specific, actionable gap."""

    OUT_OF_SCOPE = "out_of_scope"
    NOT_IN_DATASET = "not_in_dataset"
    AMBIGUOUS_REFERENT = "ambiguous_referent"
    UNDERSPECIFIED = "underspecified"
    REQUIRES_UNMODELLED_RULE = "requires_unmodelled_rule"
    CONFLICTING_DATA = "conflicting_data"
    VERIFICATION_FAILED = "verification_failed"
    TOOL_ERROR = "tool_error"


class Abstention(BaseModel):
    """A refusal a controller can act on.

    Never a bare 'I do not know'. It names what was missing and what the system
    can answer instead.
    """

    reason: AbstentionReason
    message: str
    missing: list[str] = Field(default_factory=list)
    did_establish: list[str] = Field(
        default_factory=list,
        description="What the system did determine before it ran out of ground",
    )
    suggestions: list[str] = Field(default_factory=list)


class UnattestedAtom(BaseModel):
    """A token in the drafted answer that no tool result supports."""

    atom: str
    kind: Literal["number", "identifier", "date", "currency", "rule_id", "station"]
    context: str = Field(description="Surrounding sentence, for the audit log")


class VerificationStatus(str, Enum):
    VERIFIED = "verified"
    REPAIRED = "repaired"
    REJECTED = "rejected"
    SKIPPED = "skipped"


class VerificationReport(BaseModel):
    """The verifier's own record. Rendered in the UI, not hidden."""

    status: VerificationStatus
    checked_atoms: int = 0
    attested_atoms: int = 0
    unattested: list[UnattestedAtom] = Field(default_factory=list)
    repair_attempts: int = 0
    note: str | None = None


class Timings(BaseModel):
    total_ms: int = 0
    plan_ms: int = 0
    tools_ms: int = 0
    verify_ms: int = 0
    model_calls: int = 0
    tool_calls: int = 0


__all__ = [
    "Abstention",
    "AbstentionReason",
    "Citation",
    "Confidence",
    "Fact",
    "FactUnit",
    "FactValue",
    "Provenance",
    "Table",
    "Timings",
    "ToolEnvelope",
    "TraceStep",
    "UnattestedAtom",
    "VerificationReport",
    "VerificationStatus",
    "date",
    "datetime",
]

"""The one answer type every interface renders.

The CLI, the HTTP layer and the web UI all consume `Reply`. Nothing downstream
of this type is allowed to compute a fact, so a `Reply` is self contained: if a
figure is not in here, it does not get shown.
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Literal

from pydantic import BaseModel, Field

from crewops.contracts.evidence import (
    Abstention,
    Citation,
    Confidence,
    Fact,
    Table,
    Timings,
    ToolEnvelope,
    TraceStep,
    VerificationReport,
)
from crewops.contracts.ops import ImpactReport, Recommendation
from crewops.contracts.rules import RuleTrace

Tier = Literal[1, 2, 3]


class ReplyKind(str, Enum):
    ANSWER = "answer"
    ABSTAIN = "abstain"
    ERROR = "error"


class AnswerMode(str, Enum):
    """Which path produced this reply.

    `AGENT` means the LangGraph planner chose the tools. `DETERMINISTIC` means
    no API key was configured and the offline resolver ran instead. Both paths
    use the same tools and the same verifier, so both are grounded. The UI
    shows the mode, because hiding it would overstate the system.
    """

    AGENT = "agent"
    DETERMINISTIC = "deterministic"


class Reply(BaseModel):
    thread_id: str
    turn_id: str
    question: str
    asked_at: datetime

    kind: ReplyKind
    mode: AnswerMode
    tier: Tier | None = None

    headline: str | None = Field(
        default=None, description="One line a controller reads first, under pressure"
    )
    text: str = Field(default="", description="The prose answer, already verified")

    facts: list[Fact] = Field(default_factory=list)
    traces: list[TraceStep] = Field(default_factory=list)
    rule_traces: list[RuleTrace] = Field(default_factory=list)
    tables: list[Table] = Field(default_factory=list)

    impact: ImpactReport | None = None
    recommendation: Recommendation | None = None

    citations: list[Citation] = Field(default_factory=list)
    tool_calls: list[ToolEnvelope] = Field(default_factory=list)

    abstention: Abstention | None = None
    confidence: Confidence = Confidence.HIGH
    verification: VerificationReport
    timings: Timings = Field(default_factory=Timings)

    caveats: list[str] = Field(
        default_factory=list,
        description="Limits of this specific answer, stated up front rather than "
        "discovered by the controller later",
    )
    follow_ups: list[str] = Field(default_factory=list)


__all__ = ["AnswerMode", "Reply", "ReplyKind", "Tier"]

"""Server sent event contract between the FastAPI layer and the web UI.

Every event is a JSON object with a `type` discriminator, streamed as an SSE
`data:` line. The UI switches on `type` and never parses prose to work out what
happened. `web/src/lib/contracts.ts` mirrors these shapes and must be updated
in the same change as this file.
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, Field

from crewops.contracts.evidence import (
    Abstention,
    Fact,
    ToolEnvelope,
    TraceStep,
    VerificationReport,
)
from crewops.contracts.reply import Reply


class EventType(str, Enum):
    RUN_STARTED = "run_started"
    PLAN = "plan"
    TOOL_CALL = "tool_call"
    TOOL_RESULT = "tool_result"
    TRACE = "trace"
    TOKEN = "token"
    VERIFYING = "verifying"
    VERIFICATION = "verification"
    ABSTAIN = "abstain"
    REPLY = "reply"
    ERROR = "error"
    DONE = "done"


class BaseEvent(BaseModel):
    type: EventType
    turn_id: str
    seq: int = Field(description="Monotonic within a turn, so the UI can order and dedupe")
    at: datetime


class RunStartedEvent(BaseEvent):
    type: Literal[EventType.RUN_STARTED] = EventType.RUN_STARTED
    thread_id: str
    question: str
    mode: Literal["agent", "deterministic"]


class PlanEvent(BaseEvent):
    """What the model intends to do, surfaced before it does it.

    This is the single most trust building event in the stream: the controller
    watches the system decide, rather than waiting on a black box.
    """

    type: Literal[EventType.PLAN] = EventType.PLAN
    intent: str
    tier: int | None = None
    steps: list[str] = Field(default_factory=list)


class ToolCallEvent(BaseEvent):
    type: Literal[EventType.TOOL_CALL] = EventType.TOOL_CALL
    tool: str
    args: dict[str, Any] = Field(default_factory=dict)
    label: str = Field(description="Human phrasing, for example 'Checking duty clocks for C-2087'")


class ToolResultEvent(BaseEvent):
    type: Literal[EventType.TOOL_RESULT] = EventType.TOOL_RESULT
    tool: str
    ok: bool
    latency_ms: int
    summary: str = Field(description="One line, for example '3 legs, 486 passengers'")
    envelope: ToolEnvelope | None = Field(
        default=None, description="Full result. The UI may render it in the evidence drawer."
    )


class TraceEvent(BaseEvent):
    type: Literal[EventType.TRACE] = EventType.TRACE
    step: TraceStep


class TokenEvent(BaseEvent):
    """A fragment of the drafted answer.

    Tokens are provisional. Nothing streamed here is final until a
    `VerificationEvent` reports `verified` or `repaired`. The UI must render
    streaming text in a visibly provisional state and settle it on `REPLY`.
    """

    type: Literal[EventType.TOKEN] = EventType.TOKEN
    text: str


class VerifyingEvent(BaseEvent):
    type: Literal[EventType.VERIFYING] = EventType.VERIFYING
    atom_count: int


class VerificationEvent(BaseEvent):
    type: Literal[EventType.VERIFICATION] = EventType.VERIFICATION
    report: VerificationReport


class AbstainEvent(BaseEvent):
    type: Literal[EventType.ABSTAIN] = EventType.ABSTAIN
    abstention: Abstention


class ReplyEvent(BaseEvent):
    """The settled answer. Everything before this was provisional."""

    type: Literal[EventType.REPLY] = EventType.REPLY
    reply: Reply


class ErrorEvent(BaseEvent):
    type: Literal[EventType.ERROR] = EventType.ERROR
    message: str
    recoverable: bool = False


class DoneEvent(BaseEvent):
    type: Literal[EventType.DONE] = EventType.DONE
    total_ms: int


StreamEvent = (
    RunStartedEvent
    | PlanEvent
    | ToolCallEvent
    | ToolResultEvent
    | TraceEvent
    | TokenEvent
    | VerifyingEvent
    | VerificationEvent
    | AbstainEvent
    | ReplyEvent
    | ErrorEvent
    | DoneEvent
)


class ChatRequest(BaseModel):
    question: str
    thread_id: str | None = Field(
        default=None, description="Omit to start a new thread. Memory is per thread."
    )
    as_of: datetime | None = Field(
        default=None, description="Override the snapshot time. Defaults to the dataset snapshot."
    )
    force_mode: Literal["agent", "deterministic"] | None = None


__all__ = [
    "AbstainEvent",
    "BaseEvent",
    "ChatRequest",
    "DoneEvent",
    "ErrorEvent",
    "EventType",
    "Fact",
    "PlanEvent",
    "ReplyEvent",
    "RunStartedEvent",
    "StreamEvent",
    "TokenEvent",
    "ToolCallEvent",
    "ToolResultEvent",
    "TraceEvent",
    "VerificationEvent",
    "VerifyingEvent",
]

"""The graph's typed state.

One turn, one state object. Everything the verifier, the guards and the reply
builder need has to be in here, because a node cannot reach outside it.
"""

from __future__ import annotations

import operator
from datetime import datetime
from typing import Annotated, Any, TypedDict

from langchain_core.messages import AnyMessage
from langgraph.graph.message import add_messages

from crewops.contracts import (
    Abstention,
    ToolEnvelope,
    VerificationReport,
)

__all__ = ["TurnState", "new_turn_state"]


class TurnState(TypedDict, total=False):
    """State for a single question.

    `messages` and `envelopes` accumulate; everything else is replaced by the
    node that owns it.
    """

    # ------------------------------------------------------------- the ask
    question: str
    thread_id: str
    turn_id: str
    asked_at: datetime
    as_of: datetime | None

    # ------------------------------------------------------------ triage
    in_scope: bool
    tier: int | None
    triage_reason: str

    # -------------------------------------------------------------- plan
    plan_intent: str
    plan_steps: list[str]

    # ------------------------------------------------ the tool calling loop
    messages: Annotated[list[AnyMessage], add_messages]
    envelopes: Annotated[list[ToolEnvelope], operator.add]
    tool_iterations: int

    # --------------------------------------------------------- the answer
    draft: str
    verification: VerificationReport | None
    repairs: int
    abstention: Abstention | None

    #: Set by `verify` when a structural guard rejects the answer, cleared when
    #: it passes. Kept as a plain dict so the checkpointer can serialise it
    #: without knowing about the agent package.
    pending_guard: dict[str, Any] | None

    # ---------------------------------------------------------- bookkeeping
    started_at: float
    timings: dict[str, int]
    model_calls: int


def new_turn_state(
    *,
    question: str,
    thread_id: str,
    turn_id: str,
    asked_at: datetime,
    as_of: datetime | None,
    started_at: float,
) -> dict[str, Any]:
    """The initial state for a turn, as the graph's input dict."""
    return {
        "question": question,
        "thread_id": thread_id,
        "turn_id": turn_id,
        "asked_at": asked_at,
        "as_of": as_of,
        "in_scope": True,
        "tier": None,
        "triage_reason": "",
        "plan_intent": "",
        "plan_steps": [],
        "messages": [],
        "envelopes": [],
        "tool_iterations": 0,
        "draft": "",
        "verification": None,
        "repairs": 0,
        "abstention": None,
        "pending_guard": None,
        "started_at": started_at,
        "timings": {},
        "model_calls": 0,
    }

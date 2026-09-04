"""Drives one turn and turns it into events and a `Reply`.

The runner owns the monotonic `seq` counter and the turn id, so the ordering
guarantee in `docs/CONTRACTS.md` is a property of one small piece of code
rather than a convention spread across eight nodes:

- `verification` always arrives before `reply`
- `reply` always arrives before `done`
- tokens are provisional until `reply` lands

`verification` is emitted here, not in the verify node, precisely so it is
emitted exactly once and always immediately before the reply, including on the
paths where the graph abstained and never verified anything.
"""

from __future__ import annotations

import time
import uuid
from collections.abc import AsyncIterator
from datetime import UTC, datetime
from typing import Any, Final, cast

from langchain_core.language_models import BaseChatModel
from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.graph.state import CompiledStateGraph

from crewops.agent.config import AgentConfig
from crewops.agent.events import unpack
from crewops.agent.graph import build_graph
from crewops.agent.reply import build_reply
from crewops.contracts import (
    AbstainEvent,
    Abstention,
    AbstentionReason,
    DoneEvent,
    ErrorEvent,
    PlanEvent,
    Reply,
    ReplyEvent,
    RunStartedEvent,
    StreamEvent,
    TokenEvent,
    ToolCallEvent,
    ToolEnvelope,
    ToolResultEvent,
    TraceEvent,
    TraceStep,
    VerificationEvent,
    VerifyingEvent,
)

__all__ = ["AgentRunner", "new_thread_id", "new_turn_id"]

_AGENT_NODE: Final = "agent"


def new_turn_id() -> str:
    return f"turn_{uuid.uuid4().hex[:12]}"


def new_thread_id() -> str:
    return f"thr_{uuid.uuid4().hex[:12]}"


def _utcnow() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


class AgentRunner:
    """One compiled graph, many turns."""

    def __init__(
        self,
        *,
        tools: object,
        model: BaseChatModel | None,
        plan_model: BaseChatModel | None = None,
        config: AgentConfig | None = None,
        checkpointer: BaseCheckpointSaver[Any] | None = None,
        snapshot: datetime | None = None,
    ) -> None:
        self.config = config or AgentConfig()
        self.tools = tools
        self.snapshot = snapshot
        self.graph: CompiledStateGraph[Any, Any, Any, Any] = build_graph(
            tools=tools,
            model=model,
            plan_model=plan_model,
            config=self.config,
            checkpointer=checkpointer,
        )

    # ------------------------------------------------------------- streaming

    async def stream(
        self,
        question: str,
        *,
        thread_id: str | None = None,
        turn_id: str | None = None,
        as_of: datetime | None = None,
    ) -> AsyncIterator[StreamEvent]:
        """Yield the full event sequence for one turn."""
        thread = thread_id or new_thread_id()
        turn = turn_id or new_turn_id()
        asked_at = _utcnow()
        started = time.monotonic()
        seq = _Counter(turn)

        yield seq.run_started(thread_id=thread, question=question)

        state: dict[str, Any] = {}
        error: str | None = None
        try:
            async for event, snapshot in self._drive(
                question=question,
                thread=thread,
                turn=turn,
                asked_at=asked_at,
                as_of=as_of,
                started=started,
                seq=seq,
            ):
                if snapshot is not None:
                    state = snapshot
                if event is not None:
                    yield event
        except Exception as exc:
            error = f"{type(exc).__name__}: {exc}"
            yield seq.error(error)

        reply = self._assemble(
            state,
            question=question,
            thread=thread,
            turn=turn,
            asked_at=asked_at,
            started=started,
            error=error,
        )

        # Ordering guarantee, enforced here and nowhere else.
        yield seq.verification(reply)
        if reply.abstention is not None:
            yield seq.abstain(reply.abstention)
        yield seq.reply(reply)
        yield seq.done(int((time.monotonic() - started) * 1000))

    async def _drive(
        self,
        *,
        question: str,
        thread: str,
        turn: str,
        asked_at: datetime,
        as_of: datetime | None,
        started: float,
        seq: _Counter,
    ) -> AsyncIterator[tuple[StreamEvent | None, dict[str, Any] | None]]:
        from crewops.agent.state import new_turn_state

        inputs = new_turn_state(
            question=question,
            thread_id=thread,
            turn_id=turn,
            asked_at=asked_at,
            as_of=as_of or self.snapshot,
            started_at=started,
        )
        run_config: dict[str, Any] = {
            "configurable": {"thread_id": thread},
            "recursion_limit": 4 * self.config.max_tool_iterations + 12,
        }

        stream = self.graph.astream(
            inputs,
            config=cast(Any, run_config),
            stream_mode=["custom", "messages", "values"],
            version="v2",
        )
        try:
            async for part in stream:
                kind = part.get("type")
                data = part.get("data")
                if kind == "custom":
                    event = self._from_custom(data, seq)
                    if event is not None:
                        yield event, None
                elif kind == "messages":
                    event = self._from_token(data, seq)
                    if event is not None:
                        yield event, None
                elif kind == "values" and isinstance(data, dict):
                    yield None, cast(dict[str, Any], data)
        finally:
            # `astream` returns an async generator at runtime; the declared
            # return type does not say so. Closing it is what cancels the run
            # when the consumer walks away mid turn.
            await cast(Any, stream).aclose()

    def _from_custom(self, data: Any, seq: _Counter) -> StreamEvent | None:
        unpacked = unpack(data)
        if unpacked is None:
            return None
        kind, payload = unpacked
        if kind == "plan":
            return seq.plan(payload)
        if kind == "tool_call":
            return seq.tool_call(payload)
        if kind == "tool_result":
            return seq.tool_result(payload)
        if kind == "trace":
            return seq.trace(payload)
        if kind == "verifying":
            return seq.verifying(int(payload.get("atom_count", 0)))
        return None

    def _from_token(self, data: Any, seq: _Counter) -> StreamEvent | None:
        """Only the answering node's text streams. Plan tokens are not the answer."""
        if not isinstance(data, tuple | list) or len(data) != 2:
            return None
        chunk, metadata = data
        if not isinstance(metadata, dict):
            return None
        if metadata.get("langgraph_node") != _AGENT_NODE:
            return None
        text = getattr(chunk, "text", None)
        if not isinstance(text, str):
            content = getattr(chunk, "content", "")
            text = content if isinstance(content, str) else ""
        return seq.token(text) if text else None

    # --------------------------------------------------------------- one shot

    async def run(
        self,
        question: str,
        *,
        thread_id: str | None = None,
        turn_id: str | None = None,
        as_of: datetime | None = None,
    ) -> Reply:
        """Run a turn and return only the settled reply."""
        settled: Reply | None = None
        async for event in self.stream(
            question, thread_id=thread_id, turn_id=turn_id, as_of=as_of
        ):
            if isinstance(event, ReplyEvent):
                settled = event.reply
        if settled is None:  # pragma: no cover - stream always emits a reply
            raise RuntimeError("The turn produced no reply")
        return settled

    # --------------------------------------------------------------- assembly

    def _assemble(
        self,
        state: dict[str, Any],
        *,
        question: str,
        thread: str,
        turn: str,
        asked_at: datetime,
        started: float,
        error: str | None,
    ) -> Reply:
        if error is not None and not state.get("abstention"):
            state = {
                **state,
                "abstention": Abstention(
                    reason=AbstentionReason.TOOL_ERROR,
                    message=(
                        "I cannot answer that reliably. The turn failed before it "
                        f"could be checked: {error}"
                    ),
                    missing=["A completed turn"],
                    suggestions=["Try again, or run the same question with --offline"],
                ),
            }
        return build_reply(
            state,
            question=question,
            thread_id=thread,
            turn_id=turn,
            asked_at=asked_at,
            total_ms=int((time.monotonic() - started) * 1000),
        )


class _Counter:
    """Monotonic `seq` per turn. The only place events are numbered."""

    __slots__ = ("_seq", "turn_id")

    def __init__(self, turn_id: str) -> None:
        self.turn_id = turn_id
        self._seq = 0

    def _next(self) -> int:
        self._seq += 1
        return self._seq

    def _base(self) -> dict[str, Any]:
        return {"turn_id": self.turn_id, "seq": self._next(), "at": _utcnow()}

    def run_started(self, *, thread_id: str, question: str) -> RunStartedEvent:
        return RunStartedEvent(
            **self._base(), thread_id=thread_id, question=question, mode="agent"
        )

    def plan(self, payload: dict[str, Any]) -> PlanEvent:
        return PlanEvent(
            **self._base(),
            intent=str(payload.get("intent", "")),
            tier=payload.get("tier"),
            steps=[str(step) for step in payload.get("steps", [])],
        )

    def tool_call(self, payload: dict[str, Any]) -> ToolCallEvent:
        return ToolCallEvent(
            **self._base(),
            tool=str(payload.get("tool", "")),
            args=dict(payload.get("args") or {}),
            label=str(payload.get("label", "")),
        )

    def tool_result(self, payload: dict[str, Any]) -> ToolResultEvent:
        raw = payload.get("envelope")
        envelope = ToolEnvelope.model_validate(raw) if isinstance(raw, dict) else None
        return ToolResultEvent(
            **self._base(),
            tool=str(payload.get("tool", "")),
            ok=bool(payload.get("ok", False)),
            latency_ms=int(payload.get("latency_ms", 0)),
            summary=str(payload.get("summary", "")),
            envelope=envelope,
        )

    def trace(self, payload: dict[str, Any]) -> TraceEvent:
        raw = payload.get("step") or {}
        return TraceEvent(**self._base(), step=TraceStep.model_validate(raw))

    def token(self, text: str) -> TokenEvent:
        return TokenEvent(**self._base(), text=text)

    def verifying(self, atom_count: int) -> VerifyingEvent:
        return VerifyingEvent(**self._base(), atom_count=atom_count)

    def verification(self, reply: Reply) -> VerificationEvent:
        return VerificationEvent(**self._base(), report=reply.verification)

    def abstain(self, abstention: Abstention) -> AbstainEvent:
        return AbstainEvent(**self._base(), abstention=abstention)

    def reply(self, reply: Reply) -> ReplyEvent:
        return ReplyEvent(**self._base(), reply=reply)

    def error(self, message: str) -> ErrorEvent:
        return ErrorEvent(**self._base(), message=message, recoverable=False)

    def done(self, total_ms: int) -> DoneEvent:
        return DoneEvent(**self._base(), total_ms=total_ms)

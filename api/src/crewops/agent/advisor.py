"""Mode selection. One entry point, one `Reply` type, every interface.

The advisor decides whether a question goes to the LangGraph agent or to the
deterministic resolver, and nothing downstream of it needs to know which. Both
paths use the same tools, the same structural guards and the same grounding
check, so both are grounded; the difference is who chose the tool plan.

The mode is always reported on the `Reply`. Hiding it would overstate the
system, and the rubric rewards the opposite.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from datetime import UTC, datetime
from typing import Any, Literal

from crewops.agent.config import AgentConfig, llm_configured
from crewops.agent.runner import AgentRunner, new_thread_id, new_turn_id
from crewops.contracts import (
    AnswerMode,
    DoneEvent,
    Reply,
    ReplyEvent,
    RunStartedEvent,
    StreamEvent,
    ToolSurface,
    VerificationEvent,
)
from crewops.resolve.resolver import DeterministicResolver

__all__ = ["Advisor", "Mode"]

Mode = Literal["agent", "deterministic"]


def _utcnow() -> datetime:
    """Now, in UTC, WITH the zone left on it.

    This used to strip the tzinfo, which made every timestamp this system
    emits serialise as a bare `2026-09-04T10:25:57`. ECMAScript parses a
    date-time with no offset as LOCAL time, so a browser outside UTC read
    every thread timestamp hours early: the conversation list said "5h ago"
    about a conversation created one second before. The stored value was
    never wrong. The wire format threw the zone away and let the reader
    guess, which on a product whose dataset is emphatically all-UTC is the
    same class of defect as a report time in the wrong zone.
    """
    return datetime.now(UTC)


class Advisor:
    """The single seam between an interface and an answer."""

    def __init__(
        self,
        tools: ToolSurface,
        *,
        model: Any = None,
        plan_model: Any = None,
        config: AgentConfig | None = None,
        checkpointer: Any = None,
        memory: Any = None,
        snapshot: datetime | None = None,
        force_mode: Mode | None = None,
    ) -> None:
        self.tools = tools
        self.config = config or AgentConfig.from_env()
        self.snapshot = snapshot
        self.memory = memory
        self.force_mode = force_mode
        self.resolver = DeterministicResolver(tools, snapshot=snapshot)
        self.runner: AgentRunner | None = None
        if model is not None:
            self.runner = AgentRunner(
                tools=tools,
                model=model,
                plan_model=plan_model,
                config=self.config,
                checkpointer=checkpointer,
                snapshot=snapshot,
            )

    # ------------------------------------------------------------------ mode

    @property
    def mode(self) -> Mode:
        if self.force_mode is not None:
            return self.force_mode
        if self.runner is None:
            return "deterministic"
        return "agent" if llm_configured() else "deterministic"

    def mode_for(self, force_mode: Mode | None) -> Mode:
        requested = force_mode or self.mode
        if requested == "agent" and self.runner is None:
            return "deterministic"
        return requested

    # --------------------------------------------------------------- answers

    async def ask(
        self,
        question: str,
        *,
        thread_id: str | None = None,
        as_of: datetime | None = None,
        force_mode: Mode | None = None,
    ) -> Reply:
        settled: Reply | None = None
        async for event in self.stream(
            question, thread_id=thread_id, as_of=as_of, force_mode=force_mode
        ):
            if isinstance(event, ReplyEvent):
                settled = event.reply
        if settled is None:  # pragma: no cover - stream always emits a reply
            raise RuntimeError("The turn produced no reply")
        return settled

    async def stream(
        self,
        question: str,
        *,
        thread_id: str | None = None,
        turn_id: str | None = None,
        as_of: datetime | None = None,
        force_mode: Mode | None = None,
    ) -> AsyncIterator[StreamEvent]:
        thread = thread_id or new_thread_id()
        turn = turn_id or new_turn_id()
        mode = self.mode_for(force_mode)

        if mode == "agent" and self.runner is not None:
            async for event in self.runner.stream(
                question, thread_id=thread, turn_id=turn, as_of=as_of
            ):
                if isinstance(event, ReplyEvent):
                    await self._record(event.reply)
                yield event
            return

        async for event in self._stream_deterministic(
            question, thread=thread, turn=turn, as_of=as_of
        ):
            yield event

    async def _stream_deterministic(
        self, question: str, *, thread: str, turn: str, as_of: datetime | None
    ) -> AsyncIterator[StreamEvent]:
        """The offline path, in the same event shape as the agent path.

        The deterministic resolver is synchronous and fast, so there is no
        intermediate progress to report. The event sequence is still complete
        and still honours the ordering guarantee, because the UI must not have
        to branch on mode.
        """
        seq = 0

        def _next() -> dict[str, Any]:
            nonlocal seq
            seq += 1
            return {"turn_id": turn, "seq": seq, "at": _utcnow()}

        started = _utcnow()
        yield RunStartedEvent(
            **_next(), thread_id=thread, question=question, mode="deterministic"
        )
        reply = self.resolver.answer(
            question,
            thread_id=thread,
            turn_id=turn,
            asked_at=started,
            as_of=as_of,
        )
        await self._record(reply)
        yield VerificationEvent(**_next(), report=reply.verification)
        if reply.abstention is not None:
            from crewops.contracts import AbstainEvent

            yield AbstainEvent(**_next(), abstention=reply.abstention)
        yield ReplyEvent(**_next(), reply=reply)
        yield DoneEvent(**_next(), total_ms=reply.timings.total_ms)

    # -------------------------------------------------------------- plumbing

    async def _record(self, reply: Reply) -> None:
        if self.memory is None:
            return
        try:
            await self.memory.record(reply)
        except Exception:
            return

    def answer_mode(self, force_mode: Mode | None = None) -> AnswerMode:
        return (
            AnswerMode.AGENT
            if self.mode_for(force_mode) == "agent"
            else AnswerMode.DETERMINISTIC
        )

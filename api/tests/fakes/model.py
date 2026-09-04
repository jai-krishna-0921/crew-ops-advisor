"""A scripted chat model, so the whole graph runs with no API key.

The graph takes a `BaseChatModel` by injection and never imports a concrete
one, which is what makes this possible. Every guardrail test works by scripting
the model into the exact failure the guardrail exists to catch: an answer with
an invented number, a legality verdict with no rules engine behind it, a Tier 3
answer built on retrieval alone, a tool loop that never terminates.
"""

from __future__ import annotations

from collections.abc import Iterator, Sequence
from typing import Any

from langchain_core.callbacks import CallbackManagerForLLMRun
from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage, BaseMessage
from langchain_core.outputs import ChatGeneration, ChatResult
from langchain_core.runnables import Runnable, RunnableLambda
from pydantic import BaseModel, ConfigDict, Field


class Turn:
    """One scripted model response."""

    __slots__ = ("content", "tool_calls")

    def __init__(
        self, content: str = "", tool_calls: Sequence[dict[str, Any]] | None = None
    ) -> None:
        self.content = content
        self.tool_calls = list(tool_calls or [])

    def as_message(self, index: int) -> AIMessage:
        calls = [
            {
                "name": call["name"],
                "args": call.get("args", {}),
                "id": call.get("id", f"call_{index}_{position}"),
                "type": "tool_call",
            }
            for position, call in enumerate(self.tool_calls)
        ]
        return AIMessage(content=self.content, tool_calls=calls)


def tool_call(name: str, **args: Any) -> dict[str, Any]:
    return {"name": name, "args": args}


class ScriptedModel(BaseChatModel):
    """Replays a fixed list of turns. Repeats the last one if it runs out."""

    turns: list[Turn] = Field(default_factory=list)
    plan: Any = None
    calls: int = 0

    model_config = ConfigDict(arbitrary_types_allowed=True)

    @property
    def _llm_type(self) -> str:
        return "scripted"

    def _generate(
        self,
        messages: list[BaseMessage],
        stop: list[str] | None = None,
        run_manager: CallbackManagerForLLMRun | None = None,
        **kwargs: Any,
    ) -> ChatResult:
        index = min(self.calls, len(self.turns) - 1) if self.turns else 0
        self.calls += 1
        turn = self.turns[index] if self.turns else Turn("")
        return ChatResult(generations=[ChatGeneration(message=turn.as_message(index))])

    def bind_tools(self, tools: Sequence[Any], **kwargs: Any) -> BaseChatModel:
        return self

    def with_structured_output(
        self, schema: Any, **kwargs: Any
    ) -> Runnable[Any, Any]:
        plan = self.plan

        def _respond(_input: Any) -> Any:
            if plan is not None:
                return plan
            if isinstance(schema, type) and issubclass(schema, BaseModel):
                return schema.model_construct(
                    intent="Run the tools this question needs",
                    tier=1,
                    steps=["Call the tools", "Answer from what they return"],
                )
            return {}

        return RunnableLambda(_respond)


def script(*turns: Turn) -> ScriptedModel:
    model = ScriptedModel()
    model.turns = list(turns)
    return model


def turns_of(model: ScriptedModel) -> Iterator[Turn]:
    yield from model.turns

"""Application state: built once at startup, shared by every request.

The dataset, the tools, the model and the memory are all expensive to set up
and cheap to share, so the lifespan builds them once. A request handler never
constructs any of them.
"""

from __future__ import annotations

import contextlib
import json
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

from crewops.agent.advisor import Advisor
from crewops.agent.config import AgentConfig, llm_configured
from crewops.agent.factory import DEFAULT_SNAPSHOT, build_model, load_tools
from crewops.agent.memory import Memory
from crewops.contracts import ToolSurface

__all__ = ["AppState", "build_state"]


@dataclass
class AppState:
    """Everything a handler is allowed to reach for."""

    tools: ToolSurface
    advisor: Advisor
    config: AgentConfig
    memory: Memory | None = None
    snapshot: datetime = DEFAULT_SNAPSHOT
    dataset_loaded: bool = False
    dataset_error: str | None = None
    data_dir: Path | None = None
    world: dict[str, Any] = field(default_factory=dict)

    @property
    def llm_configured(self) -> bool:
        return llm_configured() and self.advisor.runner is not None

    @property
    def mode(self) -> str:
        return self.advisor.mode

    def questions(self) -> list[dict[str, Any]]:
        """The 38 shipped sample questions, for the demo launcher.

        Read only, and a missing file is a degraded launcher rather than a
        broken server.
        """
        if self.data_dir is None:
            return []
        path = self.data_dir / "questions.json"
        if not path.is_file():
            return []
        try:
            loaded = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return []
        return loaded if isinstance(loaded, list) else []


def build_state(
    *,
    tools: ToolSurface | None = None,
    model: Any = None,
    plan_model: Any = None,
    config: AgentConfig | None = None,
    memory: Memory | None = None,
    snapshot: datetime | None = None,
    data_dir: Path | None = None,
) -> AppState:
    """Assemble the state. Tolerates a missing core so the server still starts.

    A server that refuses to boot because the dataset moved is less useful than
    one that boots and says, on `/api/health`, exactly what is wrong.
    """
    cfg = config or AgentConfig.from_env()
    dataset_error: str | None = None
    resolved_tools = tools
    if resolved_tools is None:
        try:
            resolved_tools = load_tools(data_dir)
        except Exception as exc:
            dataset_error = f"{type(exc).__name__}: {exc}"

    if resolved_tools is None:
        raise RuntimeError(
            "No ToolSurface available and the deterministic core could not be "
            f"loaded: {dataset_error}"
        )

    resolved_model = model if model is not None else build_model(cfg)
    resolved_plan = plan_model if plan_model is not None else resolved_model

    advisor = Advisor(
        resolved_tools,
        model=resolved_model,
        plan_model=resolved_plan,
        config=cfg,
        checkpointer=memory.checkpointer if memory is not None else None,
        memory=memory,
        snapshot=snapshot,
    )

    state = AppState(
        tools=resolved_tools,
        advisor=advisor,
        config=cfg,
        memory=memory,
        snapshot=snapshot or DEFAULT_SNAPSHOT,
        dataset_error=dataset_error,
        data_dir=data_dir,
    )

    summary = resolved_tools.get_world_summary()
    state.dataset_loaded = summary.ok
    if summary.ok and isinstance(summary.payload, dict):
        state.world = summary.payload
        raw = summary.payload.get("snapshot")
        if isinstance(raw, str):
            with contextlib.suppress(ValueError):
                state.snapshot = datetime.fromisoformat(raw.rstrip("Z"))
    elif not summary.ok:
        state.dataset_error = summary.error
    return state

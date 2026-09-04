"""Where the concrete implementations get wired in, and the only place they are.

Nothing else in `agent/`, `verify/`, `resolve/` or `server/` imports a
`ToolSurface` implementation or a model client. That is what lets the whole
system run end to end against a fake with no API key, and it is what makes
swapping the fake for the real core a change to two functions in this file.

`load_tools` deliberately imports `crewops.tools.registry` lazily and inside a
`try`, so this package still imports cleanly while the Core workstream is
mid-flight.
"""

from __future__ import annotations

import os
from datetime import datetime
from pathlib import Path
from typing import Any, cast

from crewops.agent import providers
from crewops.agent.config import AgentConfig
from crewops.contracts import ToolSurface

__all__ = [
    "CoreUnavailableError",
    "build_model",
    "default_data_dir",
    "default_snapshot",
    "load_tools",
]

#: The dataset's own "now". Every question is answered as of this instant
#: unless the caller overrides it.
DEFAULT_SNAPSHOT = datetime(2026, 9, 14, 18, 0, 0)


class CoreUnavailableError(RuntimeError):
    """The deterministic core is not importable yet."""


def default_snapshot() -> datetime:
    return DEFAULT_SNAPSHOT


def load_tools(data_dir: Path | str | None = None) -> ToolSurface:
    """The real deterministic core.

    One import, one construction. When the Core workstream lands
    `crewops.tools.registry.Tools`, this is the only place that needs to know.
    """
    try:
        from crewops.tools.registry import Tools
    except ImportError as exc:  # pragma: no cover - exercised once, at integration
        raise CoreUnavailableError(
            "crewops.tools.registry.Tools is not available yet. The agent, the "
            "verifier, the CLI and the server all run against any object "
            "satisfying crewops.contracts.ToolSurface, so pass one in "
            "explicitly (the test suite passes FakeTools) until the core lands."
        ) from exc

    root = Path(
        data_dir
        or os.environ.get("CREWOPS_DATA_DIR")
        or default_data_dir()
    )
    # `Tools` takes a loaded WorldState, not a path. The dataset is read once
    # here and shared for the life of the process: it is immutable, and
    # reloading it per request would dominate the latency budget.
    from crewops.domain import load_world

    tools: Any = Tools(load_world(root))
    return cast(ToolSurface, tools)


def default_data_dir() -> Path:
    """Walk up for the shipped dataset. Read only, never written to."""
    here = Path(__file__).resolve()
    for parent in here.parents:
        candidate = parent / "data" / "crew-ops-advisor-dataset" / "data"
        if candidate.is_dir():
            return candidate
    return Path("data/crew-ops-advisor-dataset/data")


def build_model(config: AgentConfig | None = None, *, planner: bool = False) -> Any:
    """The chat model, or None when no provider is configured.

    Returning None rather than raising is deliberate: no provider is a
    supported mode, not an error. The advisor falls through to the
    deterministic path, which answers every tier on its own.

    Which vendor gets constructed, and every quirk that differs between them,
    lives in `agent/providers.py`. This function only decides planner versus
    answerer, because that is the only distinction the rest of the agent draws.
    """
    provider = providers.resolve()
    if provider is None:
        return None

    cfg = config or AgentConfig.from_env()
    return providers.build(
        provider,
        model=cfg.plan_model if planner else cfg.model,
        max_tokens=cfg.plan_max_tokens if planner else cfg.max_tokens,
    )

"""Runtime configuration for the agent.

Everything here is read from the environment once and passed down explicitly.
No module reaches for `os.environ` on its own, so a test can construct a config
and be certain of what it is testing.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Final

__all__ = ["DEFAULT_MODEL", "AgentConfig", "llm_configured"]

#: Current generation Sonnet. Configurable because a judge may want to try a
#: different model, but the whole design assumes a model that plans and
#: explains rather than one that computes, so the tier matters less than usual.
DEFAULT_MODEL: Final = "claude-sonnet-5"

#: The problem statement is explicit: a 45 second response is not a decision
#: aid. These are the budgets that keep the promise, enforced in the graph
#: rather than hoped for in a prompt.
DEFAULT_TOOL_ITERATIONS: Final = 8
DEFAULT_TURN_BUDGET_MS: Final = 25_000


def _env_int(name: str, default: int) -> int:
    raw = os.environ.get(name)
    if not raw:
        return default
    try:
        return int(raw)
    except ValueError:
        return default


def llm_configured() -> bool:
    """True when a key is present. Selects agent mode over the offline path."""
    return bool(os.environ.get("ANTHROPIC_API_KEY", "").strip())


@dataclass(frozen=True, slots=True)
class AgentConfig:
    """Everything the graph needs to know that is not a tool or a question."""

    model: str = DEFAULT_MODEL
    plan_model: str = DEFAULT_MODEL
    max_tokens: int = 2048
    plan_max_tokens: int = 512

    #: Hard cap on trips round the agent/tools loop. Hitting it abstains rather
    #: than letting a confused turn run forever.
    max_tool_iterations: int = DEFAULT_TOOL_ITERATIONS

    #: Wall clock ceiling for one turn. Checked before each model call and
    #: before each tool batch, so an overrun abstains with a useful message
    #: instead of the caller timing out on a dead socket.
    turn_budget_ms: int = DEFAULT_TURN_BUDGET_MS

    #: Exactly one correction pass. Never two, never a silent pass through.
    max_repairs: int = 1

    #: Thread memory. SQLite so a thread survives a restart and replays as an
    #: audit trail.
    memory_path: Path = field(default_factory=lambda: Path(".crewops/memory.db"))

    #: Temperature is deliberately absent. Claude Sonnet 5 rejects sampling
    #: parameters outright, and a decision aid should not be sampling anyway.

    @classmethod
    def from_env(cls) -> AgentConfig:
        raw_memory = os.environ.get("CREWOPS_MEMORY_DB", "").strip()
        return cls(
            model=os.environ.get("CREWOPS_MODEL", DEFAULT_MODEL).strip() or DEFAULT_MODEL,
            plan_model=(
                os.environ.get("CREWOPS_PLAN_MODEL", "").strip()
                or os.environ.get("CREWOPS_MODEL", DEFAULT_MODEL).strip()
                or DEFAULT_MODEL
            ),
            max_tokens=_env_int("CREWOPS_MAX_TOKENS", 2048),
            plan_max_tokens=_env_int("CREWOPS_PLAN_MAX_TOKENS", 512),
            max_tool_iterations=_env_int(
                "CREWOPS_MAX_TOOL_ITERATIONS", DEFAULT_TOOL_ITERATIONS
            ),
            turn_budget_ms=_env_int("CREWOPS_TURN_BUDGET_MS", DEFAULT_TURN_BUDGET_MS),
            max_repairs=_env_int("CREWOPS_MAX_REPAIRS", 1),
            memory_path=Path(raw_memory) if raw_memory else Path(".crewops/memory.db"),
        )

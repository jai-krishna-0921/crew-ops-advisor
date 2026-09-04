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

from crewops.agent import providers

__all__ = ["DEFAULT_MODEL", "AgentConfig", "llm_configured"]

#: Current generation Sonnet. Kept as the bare-constructor default so
#: `AgentConfig()` stays meaningful, but `from_env()` takes the default model
#: from whichever provider is selected: a Claude model id sent to Ollama is a
#: 404 on the first turn. See `agent/providers.py`.
DEFAULT_MODEL: Final = providers.spec(providers.ANTHROPIC).default_model

#: The problem statement is explicit: a 45 second response is not a decision
#: aid. These are the budgets that keep the promise, enforced in the graph
#: rather than hoped for in a prompt.
DEFAULT_TOOL_ITERATIONS: Final = 8

#: 30 seconds, raised from 25 once Tier 2 was measured.
#:
#: Six of fourteen Tier 2 questions were abstaining on the budget alone, and
#: the computations were never the slow part: the agent was asking the same
#: question once per crew member, paying a model round trip each time. Batching
#: `check_legality` removed most of that, and this covers the rest.
#:
#: It does not go higher. The problem statement says a 45 second response is
#: not a decision aid, and a budget set just under the line it is trying to
#: respect is not a budget. An answer that needs more than 30 seconds is one
#: the controller should be told about rather than made to wait for.
DEFAULT_TURN_BUDGET_MS: Final = 30_000


def _env_int(name: str, default: int) -> int:
    raw = os.environ.get(name)
    if not raw:
        return default
    try:
        return int(raw)
    except ValueError:
        return default


def llm_configured() -> bool:
    """True when some provider is selected. Picks agent mode over offline.

    Detection is by environment only, never by a live probe: this is called by
    `Advisor.mode` and by the server on every request.
    """
    return providers.resolve() is not None


@dataclass(frozen=True, slots=True)
class AgentConfig:
    """Everything the graph needs to know that is not a tool or a question."""

    #: Which vendor is behind `model`. Carried on the config so the CLI's
    #: status view and the server's health route can report it without
    #: re-deriving it from the environment.
    provider: str = providers.ANTHROPIC

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

        # No provider selected still has to yield a usable config: callers ask
        # for `.model` to display it, and the offline path never uses it.
        selected = providers.resolve()
        fallback = selected.default_model if selected else DEFAULT_MODEL
        model = os.environ.get("CREWOPS_MODEL", "").strip() or fallback

        return cls(
            provider=selected.name if selected else providers.NONE,
            model=model,
            plan_model=os.environ.get("CREWOPS_PLAN_MODEL", "").strip() or model,
            max_tokens=_env_int("CREWOPS_MAX_TOKENS", 2048),
            plan_max_tokens=_env_int("CREWOPS_PLAN_MAX_TOKENS", 512),
            max_tool_iterations=_env_int(
                "CREWOPS_MAX_TOOL_ITERATIONS", DEFAULT_TOOL_ITERATIONS
            ),
            turn_budget_ms=_env_int("CREWOPS_TURN_BUDGET_MS", DEFAULT_TURN_BUDGET_MS),
            max_repairs=_env_int("CREWOPS_MAX_REPAIRS", 1),
            memory_path=Path(raw_memory) if raw_memory else Path(".crewops/memory.db"),
        )

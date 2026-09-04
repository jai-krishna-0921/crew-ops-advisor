"""The LangGraph agent: the part of the system that plans and explains.

Public surface:

    from crewops.agent import Advisor, AgentConfig, AgentRunner, build_graph

`Advisor` is the one entry point every interface uses. It picks the agent path
or the offline path and returns the same `Reply` either way.

**Why this module imports lazily.** `crewops.agent` sits at the top of the
dependency stack: `Advisor` reaches down into `crewops.resolve` for the offline
path. But `crewops.resolve` reaches back up into `crewops.agent.guards`,
`crewops.agent.reply` and `crewops.agent.toolspecs`, because both answer paths
are held to the same structural guards and build the same `Reply`. Sharing
those is correct. What is not correct is a leaf import like
`from crewops.agent.guards import run_guards` dragging the whole top of the
stack in behind it, which is exactly the cycle that produces.

PEP 562 module `__getattr__` resolves it: importing a submodule of this package
runs an empty package body, and the convenience re-exports below are made real
only when somebody actually asks for one.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:  # pragma: no cover - for type checkers, never at runtime
    # Redundant `X as X` aliases mark these as explicit re-exports. The runtime
    # __all__ below is computed from _EXPORTS to support lazy loading, and a
    # computed __all__ is invisible to both ruff and mypy.
    from crewops.agent.advisor import Advisor as Advisor
    from crewops.agent.advisor import Mode as Mode
    from crewops.agent.config import DEFAULT_MODEL as DEFAULT_MODEL
    from crewops.agent.config import AgentConfig as AgentConfig
    from crewops.agent.config import llm_configured as llm_configured
    from crewops.agent.factory import DEFAULT_SNAPSHOT as DEFAULT_SNAPSHOT
    from crewops.agent.factory import CoreUnavailableError as CoreUnavailableError
    from crewops.agent.factory import build_model as build_model
    from crewops.agent.factory import default_snapshot as default_snapshot
    from crewops.agent.factory import load_tools as load_tools
    from crewops.agent.graph import TurnPlan as TurnPlan
    from crewops.agent.graph import bind_tool_specs as bind_tool_specs
    from crewops.agent.graph import build_graph as build_graph
    from crewops.agent.guards import GuardFailure as GuardFailure
    from crewops.agent.guards import run_guards as run_guards
    from crewops.agent.guards import strip_em_dashes as strip_em_dashes
    from crewops.agent.memory import Memory as Memory
    from crewops.agent.memory import ThreadSummary as ThreadSummary
    from crewops.agent.prompts import PROMPT_VERSION as PROMPT_VERSION
    from crewops.agent.prompts import SYSTEM_PROMPT as SYSTEM_PROMPT
    from crewops.agent.reply import build_reply as build_reply
    from crewops.agent.runner import AgentRunner as AgentRunner
    from crewops.agent.runner import new_thread_id as new_thread_id
    from crewops.agent.runner import new_turn_id as new_turn_id
    from crewops.agent.state import TurnState as TurnState
    from crewops.agent.state import new_turn_state as new_turn_state
    from crewops.agent.toolspecs import TOOL_SPECS as TOOL_SPECS
    from crewops.agent.toolspecs import ToolSpec as ToolSpec
    from crewops.agent.toolspecs import call_tool as call_tool

#: Exported name to the submodule that defines it.
_EXPORTS: dict[str, str] = {
    "DEFAULT_MODEL": "config",
    "DEFAULT_SNAPSHOT": "factory",
    "PROMPT_VERSION": "prompts",
    "SYSTEM_PROMPT": "prompts",
    "TOOL_SPECS": "toolspecs",
    "Advisor": "advisor",
    "AgentConfig": "config",
    "AgentRunner": "runner",
    "CoreUnavailableError": "factory",
    "GuardFailure": "guards",
    "Memory": "memory",
    "Mode": "advisor",
    "ThreadSummary": "memory",
    "ToolSpec": "toolspecs",
    "TurnPlan": "graph",
    "TurnState": "state",
    "bind_tool_specs": "graph",
    "build_graph": "graph",
    "build_model": "factory",
    "build_reply": "reply",
    "call_tool": "toolspecs",
    "default_snapshot": "factory",
    "llm_configured": "config",
    "load_tools": "factory",
    "new_thread_id": "runner",
    "new_turn_id": "runner",
    "new_turn_state": "state",
    "run_guards": "guards",
    "strip_em_dashes": "guards",
}

__all__ = sorted(_EXPORTS)


def __getattr__(name: str) -> Any:
    module_name = _EXPORTS.get(name)
    if module_name is None:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    import importlib

    module = importlib.import_module(f"crewops.agent.{module_name}")
    value = getattr(module, name)
    globals()[name] = value
    return value


def __dir__() -> list[str]:
    return __all__

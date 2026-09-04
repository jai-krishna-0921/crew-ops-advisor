"""Fakes for the agent workstream: a `ToolSurface` and a scripted chat model."""

from tests.fakes.model import ScriptedModel, Turn, script, tool_call
from tests.fakes.tools import FakeTools

__all__ = ["FakeTools", "ScriptedModel", "Turn", "script", "tool_call"]

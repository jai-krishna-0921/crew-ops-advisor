"""Building and calling the advisor, without depending on it being ready.

The scorecard must be useful before the core lands, so nothing here imports an
implementation at module scope. `probe()` tries to construct an `Advisor`,
reports what it managed, and returns `None` cleanly when the pieces are not
there yet. `make eval` then prints a skip message saying exactly what was
missing, rather than a traceback.

`Advisor.ask` is async and every interface is expected to await it. The eval
harness is synchronous, so it drives one event loop per call. That is slightly
wasteful and completely predictable, which is the right trade for a measuring
instrument: an advisor that leaks state between questions would show up as a
scoring artefact rather than as an error.
"""

from __future__ import annotations

import asyncio
import os
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from crewops.contracts.reply import Reply
from crewops.eval.cases import REPO_ROOT

MODE_DETERMINISTIC = "deterministic"
MODE_AGENT = "agent"


def load_env() -> None:
    """Pick up `.env.local` and `.env` from the repository root if present.

    Agent mode is selected by `ANTHROPIC_API_KEY`. Without it everything still
    runs, on the deterministic path. That is the point of the deterministic
    path.
    """
    try:
        from dotenv import load_dotenv
    except ImportError:  # pragma: no cover - dotenv is a declared dependency
        return
    for name in (".env.local", ".env"):
        path: Path = REPO_ROOT / name
        if path.is_file():
            load_dotenv(path, override=False)


def has_api_key() -> bool:
    return bool(os.environ.get("ANTHROPIC_API_KEY", "").strip())


def available_modes() -> tuple[str, ...]:
    """Deterministic always. Agent only when a key is configured."""
    return (MODE_DETERMINISTIC, MODE_AGENT) if has_api_key() else (MODE_DETERMINISTIC,)


@dataclass
class AdvisorHandle:
    """A constructed advisor plus the label the report shows."""

    label: str
    advisor: Any
    has_model: bool

    def ask(self, question: str, *, mode: str, thread_id: str | None = None) -> tuple[Reply, int]:
        """Ask one question and return the reply with a measured latency.

        Latency is wall clock, because wall clock is what a controller
        experiences. `Reply.timings` is recorded alongside it in the artefact.
        """
        effective = mode
        if mode == MODE_AGENT and not self.has_model:
            effective = MODE_DETERMINISTIC

        started = time.perf_counter()
        reply = asyncio.run(self.advisor.ask(question, thread_id=thread_id, force_mode=effective))
        elapsed_ms = int((time.perf_counter() - started) * 1000)

        if not isinstance(reply, Reply):
            raise TypeError(
                f"{self.label} returned {type(reply).__name__}, not a Reply. "
                "Every interface renders one Reply type; see contracts/reply.py."
            )
        return reply, elapsed_ms


#: Set by `probe()` when it cannot build an advisor, so the caller can say why.
_LAST_FAILURE: str = ""


def probe() -> AdvisorHandle | None:
    """Construct an advisor, or return None with a reason in `missing_message`."""
    global _LAST_FAILURE

    # Imported by name rather than by symbol so that a rename on the agent
    # side degrades to a clear message instead of taking the whole report down.
    # This module is a measuring instrument: it must survive the thing it
    # measures being mid-change.
    try:
        from crewops.agent import Advisor
        from crewops.agent.factory import build_model, load_tools
    except ImportError as exc:
        _LAST_FAILURE = f"crewops.agent is not importable yet: {exc}"
        return None

    try:
        tools = load_tools()
    except Exception as exc:
        _LAST_FAILURE = f"load_tools() raised {type(exc).__name__}: {exc}"
        return None

    model: Any = None
    if has_api_key():
        try:
            model = build_model()
        except Exception as exc:
            _LAST_FAILURE = f"build_model() raised {type(exc).__name__}: {exc}"
            model = None

    try:
        advisor = Advisor(tools, model=model)
    except Exception as exc:
        _LAST_FAILURE = f"Advisor() raised {type(exc).__name__}: {exc}"
        return None

    label = "crewops.agent.Advisor" + (" with model" if model is not None else ", tools only")
    return AdvisorHandle(label=label, advisor=advisor, has_model=model is not None)


def missing_message() -> str:
    detail = _LAST_FAILURE or "no reason recorded"
    return (
        "No advisor available, so there is nothing to score yet.\n\n"
        f"  {detail}\n\n"
        "The harness builds crewops.agent.Advisor over the ToolSurface returned\n"
        "by crewops.agent.factory.load_tools(), and awaits Advisor.ask(question,\n"
        "force_mode=...). Both sides of that are the agent workstream's; nothing\n"
        "here needs changing when the core lands."
    )


__all__ = [
    "MODE_AGENT",
    "MODE_DETERMINISTIC",
    "AdvisorHandle",
    "available_modes",
    "has_api_key",
    "load_env",
    "missing_message",
    "probe",
]

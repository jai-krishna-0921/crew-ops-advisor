"""Progress events emitted from inside graph nodes.

Nodes emit lightweight `(kind, payload)` records through LangGraph's custom
stream writer. The runner is the only place that turns them into typed
`StreamEvent` objects, because the runner is the only place that owns the
monotonic `seq` counter and the turn id. Keeping numbering in one place is what
makes the ordering guarantee in `docs/CONTRACTS.md` provable rather than
hopeful.

Emitting is best effort by design: a node called directly from a test is not
inside a graph run, and losing a progress event must never break the answer.
"""

from __future__ import annotations

from typing import Any, Final, Literal

from langgraph.config import get_stream_writer

__all__ = ["EventKind", "emit"]

EventKind = Literal[
    "plan",
    "tool_call",
    "tool_result",
    "trace",
    "verifying",
    "abstain",
    "note",
]

_ENVELOPE_KEY: Final = "crewops_event"


def emit(kind: EventKind, payload: dict[str, Any]) -> None:
    """Emit one progress event. Silently does nothing outside a graph run."""
    try:
        writer = get_stream_writer()
    except Exception:
        return
    try:
        writer({_ENVELOPE_KEY: True, "kind": kind, "data": payload})
    except Exception:
        return


def unpack(chunk: Any) -> tuple[EventKind, dict[str, Any]] | None:
    """Recover a `(kind, payload)` pair from a custom stream chunk."""
    if not isinstance(chunk, dict) or not chunk.get(_ENVELOPE_KEY):
        return None
    kind = chunk.get("kind")
    data = chunk.get("data")
    if not isinstance(kind, str) or not isinstance(data, dict):
        return None
    return kind, data  # type: ignore[return-value]

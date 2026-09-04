"""Building `ToolEnvelope` values, and the grounding guarantee that goes in one.

This is where the guarantee is either kept or lost. The verifier downstream
only knows what the facts tell it: a number that reaches the UI without a
matching `Fact` is a number nobody checked, and it will be rejected, correctly.

So every builder here makes the fact the easy path, and `numeric_atoms` exists
so a test can walk any payload and prove that every number in it is attested.
"""

from __future__ import annotations

import time
from collections.abc import Iterator, Sequence
from datetime import date as DateType  # noqa: N812
from datetime import datetime as DateTime  # noqa: N812
from typing import Any

from pydantic import BaseModel

from crewops.contracts.evidence import (
    Citation,
    Fact,
    FactUnit,
    Provenance,
    ToolEnvelope,
    TraceStep,
)


def dataset_fact(
    key: str, label: str, value: Any, unit: FactUnit, source: str
) -> Fact:
    """A value read straight off a shipped file. True by definition."""
    return Fact(
        key=key,
        label=label,
        value=_scalar(value),
        unit=unit,
        provenance=Provenance.DATASET,
        source=source,
    )


def computed_fact(
    key: str, label: str, value: Any, unit: FactUnit, derivation: str, source: str
) -> Fact:
    """A value this system calculated. The derivation is mandatory.

    `derivation` is what a controller reads when they want to challenge the
    number, so it states the arithmetic rather than summarising it.
    """
    return Fact(
        key=key,
        label=label,
        value=_scalar(value),
        unit=unit,
        provenance=Provenance.COMPUTED,
        source=source,
        derivation=derivation,
    )


def _scalar(value: Any) -> str | int | float | bool | None:
    if isinstance(value, DateTime):
        return value.strftime("%Y-%m-%dT%H:%M:%SZ")
    if isinstance(value, DateType):
        return value.isoformat()
    if isinstance(value, str | int | float | bool) or value is None:
        return value
    return str(value)


def cite(file: str, pointer: str, note: str | None = None) -> Citation:
    return Citation(file=file, pointer=pointer, note=note)


def step(label: str, detail: str, fact_keys: Sequence[str] = ()) -> TraceStep:
    return TraceStep(label=label, detail=detail, fact_keys=list(fact_keys))


class ToolTimer:
    """Measures a tool call so the UI can show where the time went."""

    def __init__(self) -> None:
        self.started = time.perf_counter()

    @property
    def elapsed_ms(self) -> int:
        return int((time.perf_counter() - self.started) * 1000)


def ok_envelope(
    tool: str,
    args: dict[str, Any],
    payload: Any,
    *,
    facts: Sequence[Fact] = (),
    trace: Sequence[TraceStep] = (),
    citations: Sequence[Citation] = (),
    timer: ToolTimer | None = None,
    truncated: bool = False,
) -> ToolEnvelope:
    return ToolEnvelope(
        tool=tool,
        args=_clean_args(args),
        ok=True,
        payload=payload,
        facts=list(facts),
        trace=list(trace),
        citations=list(citations),
        latency_ms=timer.elapsed_ms if timer else 0,
        truncated=truncated,
    )


def error_envelope(
    tool: str,
    args: dict[str, Any],
    error: str,
    *,
    trace: Sequence[TraceStep] = (),
    timer: ToolTimer | None = None,
) -> ToolEnvelope:
    """A lookup that failed.

    An empty result and a failed lookup are different answers. "No crew match
    that filter" is a finding and comes back with `ok=True` and an empty list.
    "That crew id is not in the dataset" is a failure and comes back here, with
    a specific reason a controller can act on.
    """
    return ToolEnvelope(
        tool=tool,
        args=_clean_args(args),
        ok=False,
        payload=None,
        facts=[],
        trace=list(trace),
        citations=[],
        latency_ms=timer.elapsed_ms if timer else 0,
        error=error,
    )


def _clean_args(args: dict[str, Any]) -> dict[str, Any]:
    """Drop the unset arguments so the audit log shows what was actually asked."""
    return {k: _scalar(v) if not isinstance(v, list | tuple) else list(v)
            for k, v in args.items()
            if v is not None}


#: Payload field names that are structural rather than claims about the world,
#: and so do not need their own `Fact`. Keep this list short and justified: it
#: is the only crack in the grounding guarantee.
STRUCTURAL_FIELDS: frozenset[str] = frozenset(
    {
        "rank",       # an ordinal position in a list, not a measurement
        "seq",
        "index",
    }
)


def numeric_atoms(payload: Any, *, _path: str = "") -> Iterator[tuple[str, float]]:
    """Every number in a payload, with the path that reached it.

    Used by the tool tests to prove the grounding guarantee holds: each of these
    must be matched by a `Fact` in the same envelope. Booleans are excluded
    because `bool` is a subclass of `int` in Python and a flag is not a
    measurement.
    """
    if isinstance(payload, BaseModel):
        for name, value in payload:
            if name in STRUCTURAL_FIELDS:
                continue
            yield from numeric_atoms(value, _path=f"{_path}.{name}" if _path else name)
        return
    if isinstance(payload, dict):
        for name, value in payload.items():
            if name in STRUCTURAL_FIELDS:
                continue
            yield from numeric_atoms(value, _path=f"{_path}.{name}")
        return
    if isinstance(payload, list | tuple):
        for i, value in enumerate(payload):
            yield from numeric_atoms(value, _path=f"{_path}[{i}]")
        return
    if isinstance(payload, bool):
        return
    if isinstance(payload, int | float):
        yield (_path, float(payload))


def attested_values(facts: Sequence[Fact]) -> set[float]:
    """Numeric values the facts vouch for, for the grounding check."""
    out: set[float] = set()
    for fact in facts:
        if isinstance(fact.value, bool):
            continue
        if isinstance(fact.value, int | float):
            out.add(float(fact.value))
    return out


__all__ = [
    "STRUCTURAL_FIELDS",
    "ToolTimer",
    "attested_values",
    "cite",
    "computed_fact",
    "dataset_fact",
    "error_envelope",
    "numeric_atoms",
    "ok_envelope",
    "step",
]

"""The HTTP surface, exactly as `docs/CONTRACTS.md` specifies it.

The web app is being built against that table, so the route paths, the request
bodies and the response shapes are a contract, not a preference.

Two properties are load bearing:

1. **The deterministic routes never touch a model.** `/api/simulate`,
   `/api/legality`, `/api/cover` and `/api/brief` call the tool surface
   directly. A judge can unset the key and watch the rules engine answer.
2. **`/api/chat` honours the ordering guarantee.** `verification` before
   `reply`, `reply` before `done`. The runner enforces it; this module only has
   to not reorder what it is handed.
"""

from __future__ import annotations

import json
from datetime import date, datetime
from typing import Annotated, Any, Literal, cast

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.concurrency import run_in_threadpool
from pydantic import BaseModel, Field
from sse_starlette.sse import EventSourceResponse

from crewops.agent import providers
from crewops.agent.toolspecs import call_tool
from crewops.contracts import ALL_RULE_IDS, ChatRequest, ToolEnvelope
from crewops.server.deps import AppState

__all__ = ["router"]

router = APIRouter(prefix="/api")


def _state(request: Request) -> AppState:
    state: AppState | None = getattr(request.app.state, "crewops", None)
    if state is None:  # pragma: no cover - the lifespan always sets it
        raise HTTPException(status_code=503, detail="The server is still starting")
    return state


# ---------------------------------------------------------------------- chat


@router.post("/chat")
async def chat(request: Request, body: ChatRequest) -> EventSourceResponse:
    """Stream one turn as server sent events.

    The generator is closed on client disconnect, which closes the underlying
    graph stream and cancels the run. Without that a controller closing a tab
    would leave a model call and a tool loop running.
    """
    state = _state(request)

    async def publish() -> Any:
        stream = state.advisor.stream(
            body.question,
            thread_id=body.thread_id,
            as_of=body.as_of,
            force_mode=body.force_mode,
        )
        try:
            async for event in stream:
                if await request.is_disconnected():
                    break
                yield {
                    "event": event.type.value,
                    "data": event.model_dump_json(),
                }
        finally:
            # Closing the generator cancels the graph run, so a controller
            # closing a tab does not leave a model call and a tool loop
            # running. `AsyncIterator` does not declare `aclose`; the
            # object is an async generator.
            await cast(Any, stream).aclose()

    return EventSourceResponse(publish(), ping=15)


# -------------------------------------------------------------------- health


class Health(BaseModel):
    status: Literal["ok", "degraded"]
    dataset_loaded: bool
    snapshot: str
    llm_configured: bool
    mode: str
    detail: str | None = None

    #: WHY the mode is what it is, in words a teammate can act on.
    #:
    #: This endpoint used to answer `llm_configured: false, detail: null`, which
    #: is the truth and none of the explanation. Someone who has put a key in a
    #: file and is watching the console answer offline needs to be told which
    #: files were read and which value was ignored. Never contains a key.
    llm_detail: str = ""
    env_files_searched: list[str] = Field(default_factory=list)
    ignored_placeholders: list[str] = Field(default_factory=list)

    #: Whether the provider actually ANSWERED, as opposed to being configured.
    #:
    #: Tri-state, and the third state is the point. True means a round trip
    #: succeeded, False means one failed, and null means either no provider is
    #: configured (a supported state, never a failure) or nobody asked. This
    #: endpoint reported a green "Provider: ollama, Mode: agent" to two
    #: teammates whose every turn was 404ing, because presence of a variable is
    #: all it ever checked.
    provider_reachable: bool | None = None
    provider_detail: str = ""
    provider_model: str | None = None


@router.get("/health")
async def health(request: Request, probe: bool = False) -> Health:
    """Configuration always; a live round trip only when asked for.

    `probe` is opt in because `mode` is read on every page load, and putting a
    network call in front of that would make the console slow to open in order
    to answer a question nobody asked on that request.
    """
    state = _state(request)
    report = providers.diagnose()
    check = (
        await run_in_threadpool(providers.preflight)
        if probe
        else providers.ProviderCheck(
            ok=None,
            provider=report.provider,
            model=None,
            detail="Not probed. Add ?probe=1 to call the provider.",
        )
    )
    return Health(
        status="ok" if state.dataset_loaded else "degraded",
        dataset_loaded=state.dataset_loaded,
        snapshot=state.snapshot.isoformat() + "Z",
        llm_configured=state.llm_configured,
        mode=state.mode,
        detail=state.dataset_error,
        llm_detail=report.detail,
        env_files_searched=list(report.searched),
        ignored_placeholders=list(report.skipped),
        provider_reachable=check.ok,
        provider_detail=check.detail,
        provider_model=check.model,
    )


@router.get("/world/summary")
async def world_summary(request: Request) -> dict[str, Any]:
    state = _state(request)
    envelope = state.tools.get_world_summary()
    if not envelope.ok:
        raise HTTPException(status_code=503, detail=envelope.error or "unavailable")
    return {
        "summary": envelope.payload,
        "facts": [fact.model_dump(mode="json") for fact in envelope.facts],
        "snapshot": state.snapshot.isoformat() + "Z",
    }


# ------------------------------------------------ deterministic, no model


def _run(state: AppState, tool: str, args: dict[str, Any]) -> ToolEnvelope:
    envelope = call_tool(state.tools, tool, args)
    if not envelope.ok:
        raise HTTPException(status_code=422, detail=envelope.error or "the call failed")
    return envelope


class SimulateRequest(BaseModel):
    """One of the three simulations, discriminated by `kind`."""

    kind: Literal["absence", "reassignment", "station_closure"] = "absence"
    crew_id: str | None = None
    from_date: date | None = None
    to_date: date | None = None
    reason: str = "sick call"
    pairing_id: str | None = None
    flight_numbers: list[str] | None = None
    displacing_crew_id: str | None = None
    station: str | None = None
    from_time: datetime | None = None
    to_time: datetime | None = None


@router.post("/simulate")
async def simulate(request: Request, body: SimulateRequest) -> dict[str, Any]:
    """Consequence modelling. Deterministic: no model call on this path."""
    state = _state(request)
    if body.kind == "absence":
        if not body.crew_id or not body.from_date:
            raise HTTPException(
                status_code=422, detail="absence needs crew_id and from_date"
            )
        args: dict[str, Any] = {
            "crew_id": body.crew_id,
            "from_date": body.from_date,
            "reason": body.reason,
        }
        if body.to_date:
            args["to_date"] = body.to_date
        envelope = _run(state, "simulate_absence", args)
    elif body.kind == "reassignment":
        if not body.crew_id:
            raise HTTPException(status_code=422, detail="reassignment needs crew_id")
        args = {"crew_id": body.crew_id}
        for key, value in (
            ("pairing_id", body.pairing_id),
            ("flight_numbers", body.flight_numbers),
            ("displacing_crew_id", body.displacing_crew_id),
        ):
            if value is not None:
                args[key] = value
        envelope = _run(state, "simulate_reassignment", args)
    else:
        if not body.station or not body.from_time or not body.to_time:
            raise HTTPException(
                status_code=422,
                detail="station_closure needs station, from_time and to_time",
            )
        envelope = _run(
            state,
            "simulate_station_closure",
            {
                "station": body.station,
                "from_time": body.from_time,
                "to_time": body.to_time,
            },
        )
    return _envelope_response(envelope)


class LegalityRequest(BaseModel):
    crew_id: str
    pairing_id: str | None = None
    flight_numbers: list[str] | None = None
    on_date: date | None = None
    as_replacement_for: str | None = None


@router.post("/legality")
async def legality(request: Request, body: LegalityRequest) -> dict[str, Any]:
    """All seven rules, one crew member, one assignment. No model call."""
    state = _state(request)
    args = {
        key: value
        for key, value in body.model_dump(exclude_none=True).items()
        if value is not None
    }
    return _envelope_response(_run(state, "check_legality", args))


class CoverRequest(BaseModel):
    """A cover search.

    `for_crew_id` is how a controller actually phrases it: a person is out,
    not a pairing. It also names the seat, and since candidate enumeration
    filters on an exact rank match and the callout rate differs by role, the
    search returns the wrong people at the wrong price without it.
    """

    pairing_id: str | None = None
    flight_numbers: list[str] | None = None
    for_crew_id: str | None = None
    role: str | None = None
    on_date: date | None = None
    exclude_crew_ids: list[str] | None = None
    max_options: int = Field(default=5, ge=1, le=20)
    include_rejected: bool = True


@router.post("/cover")
async def cover(request: Request, body: CoverRequest) -> dict[str, Any]:
    """Ranked cover options with costs and rejects. No model call."""
    state = _state(request)
    if not body.pairing_id and not body.flight_numbers and not body.for_crew_id:
        raise HTTPException(
            status_code=422,
            detail="cover needs a pairing_id, flight_numbers, or a for_crew_id",
        )
    return _envelope_response(
        _run(state, "find_cover_options", body.model_dump(exclude_none=True))
    )


#: `date` is a builtin, so the parameter is named `date_` and aliased back.
_DATE_QUERY = Query(alias="date")


@router.get("/brief")
async def brief(
    request: Request,
    date_: Annotated[date, _DATE_QUERY],
) -> dict[str, Any]:
    """The proactive watchlist for a date. No model call."""
    state = _state(request)
    return _envelope_response(_run(state, "get_watchlist", {"for_date": date_}))


@router.get("/rules")
async def rules(request: Request) -> dict[str, Any]:
    """The seven rules as shipped, straight out of the rulebook."""
    state = _state(request)
    out: list[dict[str, Any]] = []
    for rule_id in ALL_RULE_IDS:
        envelope = call_tool(state.tools, "explain_rule", {"rule_id": rule_id})
        out.append(
            {
                "rule_id": rule_id,
                "ok": envelope.ok,
                "payload": _jsonable(envelope.payload),
                "facts": [fact.model_dump(mode="json") for fact in envelope.facts],
                "error": envelope.error,
            }
        )
    return {"rules": out, "count": len(out)}


@router.get("/questions")
async def questions(request: Request) -> dict[str, Any]:
    """The shipped sample questions, for the demo launcher."""
    state = _state(request)
    rows = state.questions()
    return {"questions": rows, "count": len(rows)}


# ------------------------------------------------------------------- threads


@router.get("/threads")
async def threads(
    request: Request, limit: Annotated[int, Query(ge=1, le=200)] = 50
) -> dict[str, Any]:
    state = _state(request)
    if state.memory is None:
        return {"threads": [], "count": 0, "note": "Thread memory is not enabled."}
    rows = await state.memory.threads(limit=limit)
    return {
        "threads": [
            {
                "thread_id": row.thread_id,
                "first_question": row.first_question,
                "last_question": row.last_question,
                "turns": row.turns,
                "started_at": row.started_at,
                "updated_at": row.updated_at,
                "title": row.title,
                "titled_by": row.titled_by,
            }
            for row in rows
        ],
        "count": len(rows),
    }


@router.get("/threads/{thread_id}")
async def thread(request: Request, thread_id: str) -> dict[str, Any]:
    """Every settled reply on a thread. This is the audit trail."""
    state = _state(request)
    if state.memory is None:
        raise HTTPException(status_code=404, detail="Thread memory is not enabled")
    turns = await state.memory.turns(thread_id)
    if not turns:
        raise HTTPException(status_code=404, detail=f"No thread {thread_id}")
    return {"thread_id": thread_id, "turns": turns, "count": len(turns)}


class RenameThread(BaseModel):
    """A name a person typed. Language, so there is nothing here to attest."""

    title: str = Field(min_length=1, max_length=200)


@router.patch("/threads/{thread_id}")
async def rename_thread(
    request: Request, thread_id: str, body: RenameThread
) -> dict[str, Any]:
    state = _state(request)
    if state.memory is None:
        raise HTTPException(status_code=404, detail="Thread memory is not enabled")
    if not await state.memory.rename(thread_id, body.title):
        raise HTTPException(
            status_code=404, detail=f"No thread {thread_id}, or the title was empty"
        )
    return {"thread_id": thread_id, "title": body.title.strip(), "titled_by": "user"}


@router.delete("/threads")
async def delete_all_threads(request: Request) -> dict[str, Any]:
    """Remove every conversation.

    The most destructive route on this API. It exists because a demo machine
    accumulates dozens of throwaway runs and clearing them one at a time is
    worse than clearing them at once, but it reports the count rather than a
    bare success so the caller can say what actually went.
    """
    state = _state(request)
    if state.memory is None:
        raise HTTPException(status_code=404, detail="Thread memory is not enabled")
    removed = await state.memory.delete_all()
    return {"deleted": removed}


@router.delete("/threads/{thread_id}")
async def delete_thread(request: Request, thread_id: str) -> dict[str, Any]:
    """Remove a conversation and everything recorded on it.

    This deletes an audit trail, which is the one destructive route on this
    API, so it removes exactly one thread and reports whether there was one to
    remove rather than succeeding quietly on a wrong id.
    """
    state = _state(request)
    if state.memory is None:
        raise HTTPException(status_code=404, detail="Thread memory is not enabled")
    if not await state.memory.delete(thread_id):
        raise HTTPException(status_code=404, detail=f"No thread {thread_id}")
    return {"thread_id": thread_id, "deleted": True}


# ------------------------------------------------------------------ plumbing


def _envelope_response(envelope: ToolEnvelope) -> dict[str, Any]:
    """One shape for every deterministic route, so the UI has one parser."""
    return {
        "tool": envelope.tool,
        "ok": envelope.ok,
        "payload": _jsonable(envelope.payload),
        "facts": [fact.model_dump(mode="json") for fact in envelope.facts],
        "trace": [step.model_dump(mode="json") for step in envelope.trace],
        "citations": [c.model_dump(mode="json") for c in envelope.citations],
        "latency_ms": envelope.latency_ms,
    }


def _jsonable(value: Any) -> Any:
    if hasattr(value, "model_dump"):
        return value.model_dump(mode="json")
    try:
        json.dumps(value)
    except (TypeError, ValueError):
        return json.loads(json.dumps(value, default=str))
    return value

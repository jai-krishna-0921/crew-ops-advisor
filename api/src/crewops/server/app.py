"""The FastAPI application.

`WorldState`, the tools, the model and the memory are built once in the
lifespan, not per request. CORS allows the dev web app and nothing else. There
is no authentication: the problem statement puts it explicitly out of scope.
"""

from __future__ import annotations

import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import datetime
from pathlib import Path
from typing import Any

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from crewops.agent.config import AgentConfig
from crewops.agent.memory import Memory
from crewops.agent.voice.config import VoiceConfig
from crewops.contracts import ToolSurface
from crewops.env import REPO_ROOT, load_env
from crewops.server.deps import AppState, build_state
from crewops.server.routes import router
from crewops.server.voice import voice_router

__all__ = ["ALLOWED_METHODS", "ALLOWED_ORIGINS", "create_app"]

#: Every verb this API serves.
#:
#: It read `GET, POST, OPTIONS`, which was true when it was written and stopped
#: being true the moment a conversation could be renamed or deleted. The
#: browser's preflight then answered "Disallowed CORS method" and both features
#: failed from the web app while working perfectly under curl, because the
#: request never reached the route, the store or the UI at all. A test asserts
#: this list covers what the router actually serves, so the next verb cannot be
#: forgotten here.
ALLOWED_METHODS = ("GET", "POST", "PATCH", "DELETE", "OPTIONS")

#: The dev web app. Widen this deliberately, never with a wildcard plus
#: credentials.
ALLOWED_ORIGINS: tuple[str, ...] = (
    "http://localhost:3000",
    "http://127.0.0.1:3000",
)


def create_app(
    *,
    tools: ToolSurface | None = None,
    model: Any = None,
    plan_model: Any = None,
    config: AgentConfig | None = None,
    snapshot: datetime | None = None,
    data_dir: Path | None = None,
    enable_memory: bool = True,
) -> FastAPI:
    """Build the app. Every dependency can be injected, which is how it is tested."""
    # BEFORE the config is read, because the config is what decides whether
    # this process runs the agent or the deterministic resolver. Loading the
    # file afterwards would set the key and change nothing, which is the
    # subtler version of the bug this fixes.
    load_env(REPO_ROOT)
    cfg = config or AgentConfig.from_env()

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        memory: Memory | None = None
        if enable_memory:
            memory = await Memory(cfg.memory_path).open()
        state: AppState = build_state(
            tools=tools,
            model=model,
            plan_model=plan_model,
            config=cfg,
            memory=memory,
            snapshot=snapshot,
            data_dir=data_dir or _env_data_dir(),
        )
        app.state.crewops = state
        try:
            yield
        finally:
            if memory is not None:
                await memory.close()

    app = FastAPI(
        title="Crew Ops Advisor",
        version="0.1.0",
        summary=(
            "A conversational decision aid for an airline Crew Control desk. The "
            "language model plans and explains; deterministic code computes; a "
            "grounding check rejects anything unattested."
        ),
        lifespan=lifespan,
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=list(ALLOWED_ORIGINS),
        allow_credentials=False,
        allow_methods=list(ALLOWED_METHODS),
        allow_headers=["*"],
    )
    app.include_router(router)
    app.state.voice_config = VoiceConfig.from_env()
    app.include_router(voice_router)
    return app


def _env_data_dir() -> Path | None:
    """Where the shipped dataset lives. Read only, always.

    An explicit CREWOPS_DATA_DIR wins. Otherwise fall back to the same walk-up
    discovery the tool factory uses, so the demo launcher and the sample
    questions work from a plain `make dev` with nothing exported. Returning
    None here used to leave /api/questions empty, which silently emptied the
    launcher the whole demo starts from.
    """
    raw = os.environ.get("CREWOPS_DATA_DIR", "").strip()
    if raw:
        return Path(raw)
    from crewops.agent.factory import default_data_dir

    found = default_data_dir()
    return found if found.is_dir() else None

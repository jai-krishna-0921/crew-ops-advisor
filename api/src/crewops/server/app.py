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
from crewops.contracts import ToolSurface
from crewops.server.deps import AppState, build_state
from crewops.server.routes import router

__all__ = ["ALLOWED_ORIGINS", "create_app"]

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
        allow_methods=["GET", "POST", "OPTIONS"],
        allow_headers=["*"],
    )
    app.include_router(router)
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

"""Thread memory: LangGraph checkpointing plus a readable turn log.

Two stores, on purpose, in the same SQLite file.

The **checkpointer** is LangGraph's. It holds the message state so a follow up
question ("and what about the first officer?") resolves against what came
before, and so a thread survives a process restart.

The **turn log** is ours. It holds the settled `Reply` for every turn as JSON.
The checkpointer could not serve `/api/threads` without reaching into its
internals, and more importantly a controller reviewing a decision wants the
answer that was given, with its verification report, not the message history
that produced it. That is the audit trail the problem statement asks for.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from types import TracebackType
from typing import Any, Self

import aiosqlite
from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver

from crewops.contracts import Reply

__all__ = ["Memory", "ThreadSummary"]

_SCHEMA = """
CREATE TABLE IF NOT EXISTS turns (
    turn_id      TEXT PRIMARY KEY,
    thread_id    TEXT NOT NULL,
    asked_at     TEXT NOT NULL,
    question     TEXT NOT NULL,
    mode         TEXT NOT NULL,
    kind         TEXT NOT NULL,
    tier         INTEGER,
    verification TEXT NOT NULL,
    reply_json   TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS turns_thread_idx ON turns (thread_id, asked_at);
"""


@dataclass(frozen=True, slots=True)
class ThreadSummary:
    thread_id: str
    first_question: str
    last_question: str
    turns: int
    started_at: str
    updated_at: str


class Memory:
    """Owns both stores and their connections.

    Use it as an async context manager, or call `open()` and `close()` from a
    server lifespan. Opening is idempotent.
    """

    def __init__(self, path: Path | str) -> None:
        self.path = Path(path)
        self._checkpoint_conn: aiosqlite.Connection | None = None
        self._log_conn: aiosqlite.Connection | None = None
        self._saver: AsyncSqliteSaver | None = None

    # ---------------------------------------------------------- lifecycle

    async def open(self) -> Self:
        if self._saver is not None:
            return self
        if self.path.parent and str(self.path.parent) not in ("", "."):
            self.path.parent.mkdir(parents=True, exist_ok=True)
        self._checkpoint_conn = await aiosqlite.connect(str(self.path))
        saver = AsyncSqliteSaver(self._checkpoint_conn)
        await saver.setup()
        self._saver = saver

        self._log_conn = await aiosqlite.connect(str(self.path))
        await self._log_conn.executescript(_SCHEMA)
        await self._log_conn.commit()
        return self

    async def close(self) -> None:
        for conn in (self._log_conn, self._checkpoint_conn):
            if conn is not None:
                await conn.close()
        self._log_conn = None
        self._checkpoint_conn = None
        self._saver = None

    async def __aenter__(self) -> Self:
        return await self.open()

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        await self.close()

    @property
    def checkpointer(self) -> AsyncSqliteSaver:
        if self._saver is None:
            raise RuntimeError("Memory.open() must be awaited before use")
        return self._saver

    # ----------------------------------------------------------- turn log

    async def record(self, reply: Reply) -> None:
        """Append one settled turn. Never raises into the caller's turn."""
        if self._log_conn is None:
            return
        await self._log_conn.execute(
            "INSERT OR REPLACE INTO turns "
            "(turn_id, thread_id, asked_at, question, mode, kind, tier, "
            " verification, reply_json) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                reply.turn_id,
                reply.thread_id,
                reply.asked_at.isoformat(),
                reply.question,
                reply.mode.value,
                reply.kind.value,
                reply.tier,
                reply.verification.status.value,
                reply.model_dump_json(),
            ),
        )
        await self._log_conn.commit()

    async def threads(self, limit: int = 50) -> list[ThreadSummary]:
        if self._log_conn is None:
            return []
        cursor = await self._log_conn.execute(
            "SELECT thread_id, COUNT(*) AS n, MIN(asked_at), MAX(asked_at) "
            "FROM turns GROUP BY thread_id ORDER BY MAX(asked_at) DESC LIMIT ?",
            (limit,),
        )
        rows = await cursor.fetchall()
        await cursor.close()

        summaries: list[ThreadSummary] = []
        for thread_id, count, started, updated in rows:
            first = await self._question_at(str(thread_id), ascending=True)
            last = await self._question_at(str(thread_id), ascending=False)
            summaries.append(
                ThreadSummary(
                    thread_id=str(thread_id),
                    first_question=first,
                    last_question=last,
                    turns=int(count),
                    started_at=str(started),
                    updated_at=str(updated),
                )
            )
        return summaries

    async def _question_at(self, thread_id: str, *, ascending: bool) -> str:
        if self._log_conn is None:
            return ""
        order = "ASC" if ascending else "DESC"
        cursor = await self._log_conn.execute(
            f"SELECT question FROM turns WHERE thread_id = ? "
            f"ORDER BY asked_at {order} LIMIT 1",
            (thread_id,),
        )
        row = await cursor.fetchone()
        await cursor.close()
        return str(row[0]) if row else ""

    async def turns(self, thread_id: str) -> list[dict[str, Any]]:
        """Every settled reply on a thread, oldest first. The audit trail."""
        if self._log_conn is None:
            return []
        cursor = await self._log_conn.execute(
            "SELECT reply_json FROM turns WHERE thread_id = ? ORDER BY asked_at ASC",
            (thread_id,),
        )
        rows = await cursor.fetchall()
        await cursor.close()
        out: list[dict[str, Any]] = []
        for (raw,) in rows:
            try:
                out.append(json.loads(raw))
            except json.JSONDecodeError:
                continue
        return out

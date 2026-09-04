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

from crewops.agent.titles import title_for
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

-- A conversation's name, kept apart from its turns so renaming one does not
-- touch the audit trail. `titled_by` is the whole point of the table: a name
-- somebody typed must never be overwritten by the next answer's headline.
CREATE TABLE IF NOT EXISTS thread_meta (
    thread_id TEXT PRIMARY KEY,
    title     TEXT NOT NULL,
    titled_by TEXT NOT NULL CHECK (titled_by IN ('auto', 'user'))
);
"""


#: A title longer than this is not a title, it is the question again.
_TITLE_MAX = 72


@dataclass(frozen=True, slots=True)
class ThreadSummary:
    thread_id: str
    first_question: str
    last_question: str
    turns: int
    started_at: str
    updated_at: str
    title: str
    titled_by: str


def _as_title(text: str) -> str:
    """A single tidy line, capped.

    Cuts on a word boundary when there is one to cut on, because a name
    truncated mid-word reads as a bug rather than as a name.
    """
    tidy = " ".join(text.split())
    if len(tidy) <= _TITLE_MAX:
        return tidy
    cut = tidy[:_TITLE_MAX].rsplit(" ", 1)[0]
    return f"{cut or tidy[:_TITLE_MAX]}\u2026"


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
        await self._name_thread(reply)
        await self._log_conn.commit()

    async def _name_thread(self, reply: Reply) -> None:
        """Name a conversation from the question that opened it, once.

        This used to name it from `Reply.headline`, on the reasoning that the
        answer's own opening line is already the sentence somebody would use to
        describe the exchange. It is, at the length an answer needs. In a rail
        the reader has dragged down to 208 pixels it is not: typing "hey"
        produced a conversation called "This is a crew operations desk
        assistant", which describes the product rather than the exchange, and a
        duty hours answer produced ninety characters truncated to "C-1042 (A.
        Nair, Captain, BLR, A3…".

        `title_for` is the replacement and lives next door. Five words,
        identifier first, no model. See `agent/titles.py` for why each of those
        three is the way it is.

        `INSERT OR IGNORE` is what keeps naming to the first turn, and what
        stops it from ever overwriting a name somebody typed, since a user
        rename holds the same primary key.
        """
        if self._log_conn is None:
            return
        title = _as_title(
            title_for(
                reply.question,
                abstention_reason=(
                    reply.abstention.reason if reply.abstention is not None else None
                ),
            )
        )
        if not title:
            return
        await self._log_conn.execute(
            "INSERT OR IGNORE INTO thread_meta (thread_id, title, titled_by) "
            "VALUES (?, ?, 'auto')",
            (reply.thread_id, title),
        )

    async def rename(self, thread_id: str, title: str) -> bool:
        """Give a conversation a name a person chose. Returns whether it stuck."""
        if self._log_conn is None:
            return False
        tidy = _as_title(title)
        if not tidy:
            return False
        cursor = await self._log_conn.execute(
            "SELECT 1 FROM turns WHERE thread_id = ? LIMIT 1", (thread_id,)
        )
        exists = await cursor.fetchone()
        await cursor.close()
        if exists is None:
            return False
        await self._log_conn.execute(
            "INSERT INTO thread_meta (thread_id, title, titled_by) "
            "VALUES (?, ?, 'user') "
            "ON CONFLICT(thread_id) DO UPDATE SET title = excluded.title, "
            "titled_by = 'user'",
            (thread_id, tidy),
        )
        await self._log_conn.commit()
        return True

    async def delete(self, thread_id: str) -> bool:
        """Remove a conversation and its name. Returns whether there was one.

        The name goes with the turns rather than being left behind, so a
        recycled thread id cannot inherit a name from a conversation that no
        longer exists.
        """
        if self._log_conn is None:
            return False
        cursor = await self._log_conn.execute(
            "DELETE FROM turns WHERE thread_id = ?", (thread_id,)
        )
        removed = cursor.rowcount
        await cursor.close()
        await self._log_conn.execute(
            "DELETE FROM thread_meta WHERE thread_id = ?", (thread_id,)
        )
        await self._log_conn.commit()
        return removed > 0

    async def delete_all(self) -> int:
        """Remove every conversation. Returns how many there were.

        Separate from `delete` rather than a loop over it, because this is one
        statement and a loop is N round trips that can stop halfway. The count
        is returned so the caller can say what it removed rather than claiming
        success over an empty log.
        """
        if self._log_conn is None:
            return 0
        cursor = await self._log_conn.execute(
            "SELECT COUNT(DISTINCT thread_id) FROM turns"
        )
        row = await cursor.fetchone()
        await cursor.close()
        count = int(row[0]) if row else 0

        await self._log_conn.execute("DELETE FROM turns")
        await self._log_conn.execute("DELETE FROM thread_meta")
        await self._log_conn.commit()
        return count

    async def threads(self, limit: int = 50) -> list[ThreadSummary]:
        if self._log_conn is None:
            return []
        cursor = await self._log_conn.execute(
            "SELECT t.thread_id, COUNT(*) AS n, MIN(t.asked_at), MAX(t.asked_at), "
            "       m.title, m.titled_by "
            "FROM turns t LEFT JOIN thread_meta m ON m.thread_id = t.thread_id "
            "GROUP BY t.thread_id ORDER BY MAX(t.asked_at) DESC LIMIT ?",
            (limit,),
        )
        rows = await cursor.fetchall()
        await cursor.close()

        summaries: list[ThreadSummary] = []
        for thread_id, count, started, updated, title, titled_by in rows:
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
                    # A thread recorded before this table existed has no row in
                    # it, so it falls back to what the rail used to show.
                    title=str(title) if title else _as_title(first),
                    titled_by=str(titled_by) if titled_by else "auto",
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

"""Log table repository."""
from __future__ import annotations

from typing import Any

from storage.database import Database
from utils.helpers import now_iso

from storage.repositories._shared import _row

class LogRepository:
    def __init__(self, db: Database) -> None:
        self._db = db

    async def add(self, channel: str, level: str, message: str) -> None:
        await self._db.connection.execute(
            "INSERT INTO logs (channel, level, message, created_at) VALUES (?,?,?,?)",
            (channel, level, message, now_iso()),
        )
        await self._db.connection.commit()

    async def recent(self, channel: str | None = None, limit: int = 30) -> list[dict[str, Any]]:
        if channel:
            cur = await self._db.connection.execute(
                "SELECT * FROM logs WHERE channel = ? ORDER BY id DESC LIMIT ?",
                (channel, limit),
            )
        else:
            cur = await self._db.connection.execute(
                "SELECT * FROM logs ORDER BY id DESC LIMIT ?", (limit,)
            )
        rows = await cur.fetchall()
        return [_row(r) for r in rows]

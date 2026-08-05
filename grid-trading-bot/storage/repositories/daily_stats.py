"""Daily stats table repository."""
from __future__ import annotations

from typing import Any

from storage.database import Database
from utils.helpers import now_iso

from storage.repositories._shared import _row

class DailyStatsRepository:
    def __init__(self, db: Database) -> None:
        self._db = db

    async def add_trade(self, date: str, pnl: float) -> None:
        await self._db.connection.execute(
            """INSERT INTO daily_stats (date, realized_pnl, trades_count, updated_at)
               VALUES (?, ?, 1, ?)
               ON CONFLICT(date) DO UPDATE SET
                   realized_pnl  = realized_pnl + excluded.realized_pnl,
                   trades_count  = trades_count + 1,
                   updated_at    = excluded.updated_at""",
            (date, pnl, now_iso()),
        )
        await self._db.connection.commit()

    async def get(self, date: str) -> dict[str, Any] | None:
        cur = await self._db.connection.execute(
            "SELECT * FROM daily_stats WHERE date = ?", (date,)
        )
        row = await cur.fetchone()
        return _row(row) if row else None

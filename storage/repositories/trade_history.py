"""Trade history table repository."""
from __future__ import annotations

from typing import Any

from storage.database import Database
from storage.models import TradeHistoryRecord

from storage.repositories._shared import _row

class TradeHistoryRepository:
    def __init__(self, db: Database) -> None:
        self._db = db

    async def record(self, trade: TradeHistoryRecord) -> None:
        await self._db.connection.execute(
            """INSERT INTO trade_history
                   (trade_id, grid_id, order_id, symbol, side, price, quantity,
                    investment_inr, fee, pnl, executed_at)
               VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
            (
                trade.trade_id, trade.grid_id, trade.order_id,
                trade.symbol, trade.side, trade.price, trade.quantity,
                trade.investment_inr, trade.fee, trade.pnl, trade.executed_at,
            ),
        )
        await self._db.connection.commit()

    async def get_by_order_id(self, order_id: str) -> dict[str, Any] | None:
        """Return the trade history record for a specific order, if one exists.
        Used as an idempotency guard in handle_order_filled.
        """
        cur = await self._db.connection.execute(
            "SELECT * FROM trade_history WHERE order_id = ? LIMIT 1",
            (order_id,),
        )
        row = await cur.fetchone()
        return _row(row) if row else None

    async def list_for_grid(self, grid_id: str, limit: int = 50) -> list[dict[str, Any]]:
        cur = await self._db.connection.execute(
            "SELECT * FROM trade_history WHERE grid_id = ? ORDER BY executed_at DESC LIMIT ?",
            (grid_id, limit),
        )
        rows = await cur.fetchall()
        return [_row(r) for r in rows]

    async def list_for_symbol(self, symbol: str, limit: int = 30) -> list[dict[str, Any]]:
        cur = await self._db.connection.execute(
            "SELECT * FROM trade_history WHERE symbol = ? ORDER BY executed_at DESC LIMIT ?",
            (symbol, limit),
        )
        rows = await cur.fetchall()
        return [_row(r) for r in rows]

    async def list_all(self, limit: int = 200) -> list[dict[str, Any]]:
        cur = await self._db.connection.execute(
            "SELECT * FROM trade_history ORDER BY executed_at DESC LIMIT ?", (limit,)
        )
        rows = await cur.fetchall()
        return [_row(r) for r in rows]

    async def total_realized_pnl(self) -> float:
        cur = await self._db.connection.execute(
            "SELECT COALESCE(SUM(pnl),0) AS total FROM trade_history"
        )
        row = await cur.fetchone()
        return float(row["total"]) if row else 0.0

    async def realized_pnl_since(self, since_iso: str) -> float:
        cur = await self._db.connection.execute(
            "SELECT COALESCE(SUM(pnl),0) AS total FROM trade_history WHERE executed_at >= ?",
            (since_iso,),
        )
        row = await cur.fetchone()
        return float(row["total"]) if row else 0.0

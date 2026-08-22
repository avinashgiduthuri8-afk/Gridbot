"""DCA grid table repository."""
from __future__ import annotations

from typing import Any, Iterable

from storage.database import Database
from storage.models import DCAGridRecord
from utils.helpers import now_iso

from storage.repositories._shared import _row

class DCAGridRepository:
    def __init__(self, db: Database) -> None:
        self._db = db

    async def create(self, grid: DCAGridRecord) -> None:
        await self._db.connection.execute(
            """INSERT INTO dca_grids
                   (grid_id, symbol, status, mode,
                    entry_price, base_investment, dip_buy_amount, dip_percentage,
                    profit_sell_amount, profit_percentage, max_levels, stop_loss_percentage,
                    trailing_enabled, trailing_percentage, trailing_peak_price,
                    current_level, total_quantity, total_investment, average_entry_price,
                    last_buy_price, next_buy_price, next_sell_price,
                    realized_profit, completed_cycles,
                    created_at, updated_at)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                grid.grid_id, grid.symbol, grid.status, grid.mode,
                grid.entry_price, grid.base_investment, grid.dip_buy_amount,
                grid.dip_percentage, grid.profit_sell_amount, grid.profit_percentage,
                grid.max_levels, grid.stop_loss_percentage,
                int(grid.trailing_enabled), grid.trailing_percentage, grid.trailing_peak_price,
                grid.current_level, grid.total_quantity, grid.total_investment,
                grid.average_entry_price, grid.last_buy_price,
                grid.next_buy_price, grid.next_sell_price,
                grid.realized_profit, grid.completed_cycles,
                grid.created_at, grid.updated_at,
            ),
        )
        await self._db.connection.commit()

    async def get(self, grid_id: str) -> dict[str, Any] | None:
        cur = await self._db.connection.execute(
            "SELECT * FROM dca_grids WHERE grid_id = ?", (grid_id,)
        )
        row = await cur.fetchone()
        return _row(row) if row else None

    async def list_all(self) -> list[dict[str, Any]]:
        cur = await self._db.connection.execute(
            "SELECT * FROM dca_grids ORDER BY created_at DESC"
        )
        rows = await cur.fetchall()
        return [_row(r) for r in rows]

    async def list_by_status(self, statuses: Iterable[str]) -> list[dict[str, Any]]:
        status_list = list(statuses)
        placeholders = ",".join("?" for _ in status_list)
        cur = await self._db.connection.execute(
            f"SELECT * FROM dca_grids WHERE status IN ({placeholders}) ORDER BY created_at",
            tuple(status_list),
        )
        rows = await cur.fetchall()
        return [_row(r) for r in rows]

    async def get_active_by_symbol(self, symbol: str) -> dict[str, Any] | None:
        cur = await self._db.connection.execute(
            """SELECT * FROM dca_grids
               WHERE symbol = ? AND status IN ('active','paused')
               ORDER BY created_at DESC LIMIT 1""",
            (symbol,),
        )
        row = await cur.fetchone()
        return _row(row) if row else None

    async def update_status(self, grid_id: str, status: str) -> None:
        await self._db.connection.execute(
            "UPDATE dca_grids SET status = ?, updated_at = ? WHERE grid_id = ?",
            (status, now_iso(), grid_id),
        )
        await self._db.connection.commit()

    async def update_state(self, grid_id: str, **fields: Any) -> None:
        """Update one or more dynamic state columns atomically.

        SECURITY NOTE: column names come from **fields' keys and are
        interpolated directly into the SQL string (values are still safely
        parameterized via `?`). This is only safe because every call site in
        this codebase passes literal keyword arguments written in source
        code (e.g. `update_state(grid_id, current_level=5)`) — never a dict
        built from Telegram input, an API response, or any other external
        source. Do not call this with `**untrusted_dict`.
        """
        if not fields:
            return
        fields["updated_at"] = now_iso()
        set_clause = ", ".join(f"{k} = ?" for k in fields)
        params = list(fields.values()) + [grid_id]
        await self._db.connection.execute(
            f"UPDATE dca_grids SET {set_clause} WHERE grid_id = ?", params
        )
        await self._db.connection.commit()

    async def delete(self, grid_id: str) -> None:
        await self._db.connection.execute(
            "DELETE FROM dca_grids WHERE grid_id = ?", (grid_id,)
        )
        await self._db.connection.commit()

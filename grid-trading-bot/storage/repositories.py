"""Repository classes providing typed CRUD access per table.

Each repository owns queries for exactly one table and returns plain
dataclasses (see models.py) rather than raw rows, so callers never touch
SQL directly.
"""

from __future__ import annotations

from dataclasses import asdict
from typing import Any, Iterable

import aiosqlite

from storage.database import Database
from storage.models import (
    GridLevelRecord,
    GridRecord,
    OrderRecord,
    PositionRecord,
    TradeHistoryRecord,
)
from utils.helpers import now_iso
from utils.logger import get_logger

log = get_logger("database")


def _row_to_dict(row: aiosqlite.Row) -> dict[str, Any]:
    return {key: row[key] for key in row.keys()}


class SettingsRepository:
    def __init__(self, db: Database) -> None:
        self._db = db

    async def get(self, key: str, default: str | None = None) -> str | None:
        cur = await self._db.connection.execute(
            "SELECT value FROM settings WHERE key = ?", (key,)
        )
        row = await cur.fetchone()
        return row["value"] if row else default

    async def set(self, key: str, value: str) -> None:
        await self._db.connection.execute(
            """INSERT INTO settings (key, value, updated_at) VALUES (?, ?, ?)
               ON CONFLICT(key) DO UPDATE SET value = excluded.value,
                   updated_at = excluded.updated_at""",
            (key, value, now_iso()),
        )
        await self._db.connection.commit()


class CoinConfigRepository:
    def __init__(self, db: Database) -> None:
        self._db = db

    async def upsert(
        self,
        symbol: str,
        grid_levels: int,
        investment_per_grid: float,
        upper_price: float | None,
        lower_price: float | None,
        grid_type: str,
    ) -> None:
        await self._db.connection.execute(
            """INSERT INTO coin_configs
                   (symbol, grid_levels, investment_per_grid, upper_price,
                    lower_price, grid_type, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?)
               ON CONFLICT(symbol) DO UPDATE SET
                   grid_levels = excluded.grid_levels,
                   investment_per_grid = excluded.investment_per_grid,
                   upper_price = excluded.upper_price,
                   lower_price = excluded.lower_price,
                   grid_type = excluded.grid_type,
                   updated_at = excluded.updated_at""",
            (symbol, grid_levels, investment_per_grid, upper_price, lower_price, grid_type, now_iso()),
        )
        await self._db.connection.commit()

    async def get(self, symbol: str) -> dict[str, Any] | None:
        cur = await self._db.connection.execute(
            "SELECT * FROM coin_configs WHERE symbol = ?", (symbol,)
        )
        row = await cur.fetchone()
        return _row_to_dict(row) if row else None

    async def all(self) -> list[dict[str, Any]]:
        cur = await self._db.connection.execute("SELECT * FROM coin_configs")
        rows = await cur.fetchall()
        return [_row_to_dict(r) for r in rows]


class GridRepository:
    def __init__(self, db: Database) -> None:
        self._db = db

    async def create(self, grid: GridRecord) -> None:
        await self._db.connection.execute(
            """INSERT INTO grids
                   (grid_id, symbol, grid_type, status, upper_price, lower_price,
                    grid_levels, investment_per_grid, total_invested,
                    realized_profit, completed_cycles, stopped_reason,
                    created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                grid.grid_id, grid.symbol, grid.grid_type, grid.status,
                grid.upper_price, grid.lower_price, grid.grid_levels,
                grid.investment_per_grid, grid.total_invested,
                grid.realized_profit, grid.completed_cycles,
                grid.stopped_reason, grid.created_at, grid.updated_at,
            ),
        )
        await self._db.connection.commit()

    async def update_status(self, grid_id: str, status: str, reason: str | None = None) -> None:
        await self._db.connection.execute(
            "UPDATE grids SET status = ?, stopped_reason = ?, updated_at = ? WHERE grid_id = ?",
            (status, reason, now_iso(), grid_id),
        )
        await self._db.connection.commit()

    async def update_financials(
        self, grid_id: str, total_invested: float, realized_profit: float, completed_cycles: int
    ) -> None:
        await self._db.connection.execute(
            """UPDATE grids SET total_invested = ?, realized_profit = ?,
                   completed_cycles = ?, updated_at = ? WHERE grid_id = ?""",
            (total_invested, realized_profit, completed_cycles, now_iso(), grid_id),
        )
        await self._db.connection.commit()

    async def get(self, grid_id: str) -> dict[str, Any] | None:
        cur = await self._db.connection.execute(
            "SELECT * FROM grids WHERE grid_id = ?", (grid_id,)
        )
        row = await cur.fetchone()
        return _row_to_dict(row) if row else None

    async def get_active_by_symbol(self, symbol: str) -> dict[str, Any] | None:
        cur = await self._db.connection.execute(
            """SELECT * FROM grids WHERE symbol = ? AND status IN ('active', 'paused')
               ORDER BY created_at DESC LIMIT 1""",
            (symbol,),
        )
        row = await cur.fetchone()
        return _row_to_dict(row) if row else None

    async def list_by_status(self, statuses: Iterable[str]) -> list[dict[str, Any]]:
        placeholders = ",".join("?" for _ in statuses)
        cur = await self._db.connection.execute(
            f"SELECT * FROM grids WHERE status IN ({placeholders}) ORDER BY created_at",
            tuple(statuses),
        )
        rows = await cur.fetchall()
        return [_row_to_dict(r) for r in rows]

    async def list_all(self) -> list[dict[str, Any]]:
        cur = await self._db.connection.execute("SELECT * FROM grids ORDER BY created_at DESC")
        rows = await cur.fetchall()
        return [_row_to_dict(r) for r in rows]


class GridLevelRepository:
    def __init__(self, db: Database) -> None:
        self._db = db

    async def bulk_create(self, levels: list[GridLevelRecord]) -> None:
        await self._db.connection.executemany(
            """INSERT INTO grid_levels (grid_id, level_index, price, side, is_filled, order_id)
               VALUES (?, ?, ?, ?, ?, ?)""",
            [
                (lv.grid_id, lv.level_index, lv.price, lv.side, int(lv.is_filled), lv.order_id)
                for lv in levels
            ],
        )
        await self._db.connection.commit()

    async def mark_filled(self, grid_id: str, level_index: int, side: str, order_id: str) -> None:
        await self._db.connection.execute(
            """UPDATE grid_levels SET is_filled = 1, order_id = ?
               WHERE grid_id = ? AND level_index = ? AND side = ?""",
            (order_id, grid_id, level_index, side),
        )
        await self._db.connection.commit()

    async def reset_level(self, grid_id: str, level_index: int, side: str) -> None:
        await self._db.connection.execute(
            """UPDATE grid_levels SET is_filled = 0, order_id = NULL
               WHERE grid_id = ? AND level_index = ? AND side = ?""",
            (grid_id, level_index, side),
        )
        await self._db.connection.commit()

    async def list_for_grid(self, grid_id: str) -> list[dict[str, Any]]:
        cur = await self._db.connection.execute(
            "SELECT * FROM grid_levels WHERE grid_id = ? ORDER BY level_index", (grid_id,)
        )
        rows = await cur.fetchall()
        return [_row_to_dict(r) for r in rows]


class OrderRepository:
    def __init__(self, db: Database) -> None:
        self._db = db

    async def create(self, order: OrderRecord) -> None:
        await self._db.connection.execute(
            """INSERT INTO orders
                   (order_id, grid_id, exchange_order_id, symbol, side, price,
                    quantity, filled_quantity, filled_price, status,
                    level_index, error_message, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                order.order_id, order.grid_id, order.exchange_order_id,
                order.symbol, order.side, order.price, order.quantity,
                order.filled_quantity, order.filled_price, order.status,
                order.level_index, order.error_message, order.created_at,
                order.updated_at,
            ),
        )
        await self._db.connection.commit()

    async def update_status(
        self,
        order_id: str,
        status: str,
        exchange_order_id: str | None = None,
        filled_quantity: float | None = None,
        filled_price: float | None = None,
        error_message: str | None = None,
    ) -> None:
        fields = ["status = ?", "updated_at = ?"]
        params: list[Any] = [status, now_iso()]
        if exchange_order_id is not None:
            fields.append("exchange_order_id = ?")
            params.append(exchange_order_id)
        if filled_quantity is not None:
            fields.append("filled_quantity = ?")
            params.append(filled_quantity)
        if filled_price is not None:
            fields.append("filled_price = ?")
            params.append(filled_price)
        if error_message is not None:
            fields.append("error_message = ?")
            params.append(error_message)
        params.append(order_id)
        await self._db.connection.execute(
            f"UPDATE orders SET {', '.join(fields)} WHERE order_id = ?", params
        )
        await self._db.connection.commit()

    async def get(self, order_id: str) -> dict[str, Any] | None:
        cur = await self._db.connection.execute(
            "SELECT * FROM orders WHERE order_id = ?", (order_id,)
        )
        row = await cur.fetchone()
        return _row_to_dict(row) if row else None

    async def list_open(self) -> list[dict[str, Any]]:
        cur = await self._db.connection.execute(
            "SELECT * FROM orders WHERE status IN ('pending', 'open', 'partially_filled')"
        )
        rows = await cur.fetchall()
        return [_row_to_dict(r) for r in rows]

    async def list_for_grid(self, grid_id: str) -> list[dict[str, Any]]:
        cur = await self._db.connection.execute(
            "SELECT * FROM orders WHERE grid_id = ? ORDER BY created_at DESC", (grid_id,)
        )
        rows = await cur.fetchall()
        return [_row_to_dict(r) for r in rows]


class PositionRepository:
    def __init__(self, db: Database) -> None:
        self._db = db

    async def create(self, position: PositionRecord) -> None:
        await self._db.connection.execute(
            """INSERT INTO positions
                   (position_id, grid_id, symbol, entry_order_id, entry_price,
                    quantity, status, exit_order_id, exit_price, realized_pnl,
                    created_at, closed_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                position.position_id, position.grid_id, position.symbol,
                position.entry_order_id, position.entry_price, position.quantity,
                position.status, position.exit_order_id, position.exit_price,
                position.realized_pnl, position.created_at, position.closed_at,
            ),
        )
        await self._db.connection.commit()

    async def close(
        self, position_id: str, exit_order_id: str, exit_price: float, realized_pnl: float
    ) -> None:
        await self._db.connection.execute(
            """UPDATE positions SET status = 'closed', exit_order_id = ?,
                   exit_price = ?, realized_pnl = ?, closed_at = ? WHERE position_id = ?""",
            (exit_order_id, exit_price, realized_pnl, now_iso(), position_id),
        )
        await self._db.connection.commit()

    async def list_open_for_grid(self, grid_id: str) -> list[dict[str, Any]]:
        cur = await self._db.connection.execute(
            "SELECT * FROM positions WHERE grid_id = ? AND status = 'open' ORDER BY created_at",
            (grid_id,),
        )
        rows = await cur.fetchall()
        return [_row_to_dict(r) for r in rows]

    async def list_all_open(self) -> list[dict[str, Any]]:
        cur = await self._db.connection.execute(
            "SELECT * FROM positions WHERE status = 'open' ORDER BY created_at"
        )
        rows = await cur.fetchall()
        return [_row_to_dict(r) for r in rows]


class TradeHistoryRepository:
    def __init__(self, db: Database) -> None:
        self._db = db

    async def record(self, trade: TradeHistoryRecord) -> None:
        await self._db.connection.execute(
            """INSERT INTO trade_history
                   (trade_id, grid_id, order_id, symbol, side, price, quantity,
                    fee, pnl, executed_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                trade.trade_id, trade.grid_id, trade.order_id, trade.symbol,
                trade.side, trade.price, trade.quantity, trade.fee, trade.pnl,
                trade.executed_at,
            ),
        )
        await self._db.connection.commit()

    async def list_for_grid(self, grid_id: str, limit: int = 50) -> list[dict[str, Any]]:
        cur = await self._db.connection.execute(
            "SELECT * FROM trade_history WHERE grid_id = ? ORDER BY executed_at DESC LIMIT ?",
            (grid_id, limit),
        )
        rows = await cur.fetchall()
        return [_row_to_dict(r) for r in rows]

    async def list_for_symbol(self, symbol: str, limit: int = 20) -> list[dict[str, Any]]:
        cur = await self._db.connection.execute(
            "SELECT * FROM trade_history WHERE symbol = ? ORDER BY executed_at DESC LIMIT ?",
            (symbol, limit),
        )
        rows = await cur.fetchall()
        return [_row_to_dict(r) for r in rows]

    async def total_realized_pnl(self) -> float:
        cur = await self._db.connection.execute("SELECT COALESCE(SUM(pnl), 0) AS total FROM trade_history")
        row = await cur.fetchone()
        return float(row["total"]) if row else 0.0

    async def realized_pnl_since(self, since_iso: str) -> float:
        cur = await self._db.connection.execute(
            "SELECT COALESCE(SUM(pnl), 0) AS total FROM trade_history WHERE executed_at >= ?",
            (since_iso,),
        )
        row = await cur.fetchone()
        return float(row["total"]) if row else 0.0


class DailyStatsRepository:
    def __init__(self, db: Database) -> None:
        self._db = db

    async def add_trade(self, date: str, pnl: float) -> None:
        await self._db.connection.execute(
            """INSERT INTO daily_stats (date, realized_pnl, trades_count, updated_at)
               VALUES (?, ?, 1, ?)
               ON CONFLICT(date) DO UPDATE SET
                   realized_pnl = realized_pnl + excluded.realized_pnl,
                   trades_count = trades_count + 1,
                   updated_at = excluded.updated_at""",
            (date, pnl, now_iso()),
        )
        await self._db.connection.commit()

    async def get(self, date: str) -> dict[str, Any] | None:
        cur = await self._db.connection.execute(
            "SELECT * FROM daily_stats WHERE date = ?", (date,)
        )
        row = await cur.fetchone()
        return _row_to_dict(row) if row else None


class LogRepository:
    def __init__(self, db: Database) -> None:
        self._db = db

    async def add(self, channel: str, level: str, message: str) -> None:
        await self._db.connection.execute(
            "INSERT INTO logs (channel, level, message, created_at) VALUES (?, ?, ?, ?)",
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
        return [_row_to_dict(r) for r in rows]


class Repositories:
    """Container bundling all repositories behind a single object."""

    def __init__(self, db: Database) -> None:
        self.db = db
        self.settings = SettingsRepository(db)
        self.coin_configs = CoinConfigRepository(db)
        self.grids = GridRepository(db)
        self.grid_levels = GridLevelRepository(db)
        self.orders = OrderRepository(db)
        self.positions = PositionRepository(db)
        self.trade_history = TradeHistoryRepository(db)
        self.daily_stats = DailyStatsRepository(db)
        self.logs = LogRepository(db)

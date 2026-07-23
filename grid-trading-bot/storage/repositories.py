"""Repository classes providing typed CRUD access per table.

Each repository owns queries for exactly one table. Callers never
touch SQL directly — they work through these typed, async methods.
"""

from __future__ import annotations

import json
from typing import Any, Iterable

import aiosqlite

from storage.database import Database
from storage.models import DCAGridRecord, OrderRecord, TradeHistoryRecord
from utils.helpers import now_iso
from utils.logger import get_logger

VALID_MONITOR_INTERVALS = (2, 5, 10, 15, 30)
DEFAULT_MONITOR_INTERVAL = 5

log = get_logger("database")


def _row(row: aiosqlite.Row) -> dict[str, Any]:
    return {key: row[key] for key in row.keys()}


# ---------------------------------------------------------------------------
# DCA grid table
# ---------------------------------------------------------------------------


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


# ---------------------------------------------------------------------------
# Orders table
# ---------------------------------------------------------------------------


class OrderRepository:
    def __init__(self, db: Database) -> None:
        self._db = db

    async def create(self, order: OrderRecord) -> None:
        await self._db.connection.execute(
            """INSERT INTO orders
                   (order_id, grid_id, exchange_order_id, client_order_id, symbol, side,
                    order_type, price, quantity, filled_quantity, filled_price,
                    fee, status, reconciliation_status, reconciliation_retry_count, created_at, updated_at)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                order.order_id, order.grid_id, order.exchange_order_id,
                order.client_order_id,
                order.symbol, order.side, order.order_type,
                order.price, order.quantity,
                order.filled_quantity, order.filled_price,
                order.fee,
                order.status, order.reconciliation_status, order.reconciliation_retry_count,
                order.created_at, order.updated_at,
            ),
        )
        await self._db.connection.commit()

    async def get(self, order_id: str) -> dict[str, Any] | None:
        cur = await self._db.connection.execute(
            "SELECT * FROM orders WHERE order_id = ?", (order_id,)
        )
        row = await cur.fetchone()
        return _row(row) if row else None

    async def list_open(self) -> list[dict[str, Any]]:
        """All non-terminal orders, including uncertain submissions."""
        cur = await self._db.connection.execute(
            "SELECT * FROM orders WHERE status IN "
            "('pending','submitted','unknown','open','partially_filled')"
        )
        rows = await cur.fetchall()
        return [_row(r) for r in rows]

    async def get_by_exchange_order_id(
        self, exchange_order_id: str
    ) -> dict[str, Any] | None:
        """Look up a local order by its exchange-assigned ID."""
        cur = await self._db.connection.execute(
            "SELECT * FROM orders WHERE exchange_order_id = ?",
            (exchange_order_id,),
        )
        row = await cur.fetchone()
        return _row(row) if row else None

    async def get_by_client_order_id(self, client_order_id: str) -> dict[str, Any] | None:
        cur = await self._db.connection.execute(
            "SELECT * FROM orders WHERE client_order_id = ?", (client_order_id,)
        )
        row = await cur.fetchone()
        return _row(row) if row else None

    async def list_for_grid(self, grid_id: str) -> list[dict[str, Any]]:
        cur = await self._db.connection.execute(
            "SELECT * FROM orders WHERE grid_id = ? ORDER BY created_at DESC",
            (grid_id,),
        )
        rows = await cur.fetchall()
        return [_row(r) for r in rows]

    async def list_pending_for_grid(self, grid_id: str) -> list[dict[str, Any]]:
        cur = await self._db.connection.execute(
            """SELECT * FROM orders WHERE grid_id = ?
               AND status IN ('pending','submitted','unknown','open','partially_filled')""",
            (grid_id,),
        )
        rows = await cur.fetchall()
        return [_row(r) for r in rows]

    async def list_needing_reconciliation(self) -> list[dict[str, Any]]:
        """Uncertain creates. These are never re-submitted by this process."""
        cur = await self._db.connection.execute(
            """SELECT * FROM orders
               WHERE status IN ('submitted', 'unknown') AND exchange_order_id IS NULL"""
        )
        rows = await cur.fetchall()
        return [_row(r) for r in rows]

    async def list_submitted_no_exchange_id(self) -> list[dict[str, Any]]:
        """Backward-compatible alias for callers upgraded with migration 003."""
        return await self.list_needing_reconciliation()

    async def count_pending_side(self, grid_id: str, side: str) -> int:
        """Count non-terminal orders for a given grid and side.
        Includes SUBMITTED so in-flight calls prevent duplicate placement.
        """
        cur = await self._db.connection.execute(
            """SELECT COUNT(*) AS cnt FROM orders
               WHERE grid_id = ? AND side = ?
                AND status IN ('pending','submitted','unknown','open','partially_filled')""",
            (grid_id, side),
        )
        row = await cur.fetchone()
        return int(row["cnt"]) if row else 0

    async def delete_for_grid(self, grid_id: str) -> None:
        """Delete all order rows that belong to a given grid.

        Must be called before deleting the grid row itself to satisfy
        the orders → dca_grids foreign-key constraint.
        """
        await self._db.connection.execute(
            "DELETE FROM orders WHERE grid_id = ?", (grid_id,)
        )
        await self._db.connection.commit()

    async def update_status(
        self,
        order_id: str,
        status: str,
        exchange_order_id: str | None = None,
        filled_quantity: float | None = None,
        filled_price: float | None = None,
        fee: float | None = None,
        reconciliation_status: str | None = None,
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
        if fee is not None:
            fields.append("fee = ?")
            params.append(fee)
        if reconciliation_status is not None:
            fields.append("reconciliation_status = ?")
            params.append(reconciliation_status)
        params.append(order_id)
        await self._db.connection.execute(
            f"UPDATE orders SET {', '.join(fields)} WHERE order_id = ?", params
        )
        await self._db.connection.commit()

    async def mark_unknown(self, order_id: str, reason: str) -> None:
        """Record an ambiguous create attempt without ever creating another order."""
        await self._db.connection.execute(
            """UPDATE orders
               SET status = 'unknown', reconciliation_status = ?,
                   reconciliation_retry_count = reconciliation_retry_count + 1,
                   updated_at = ?
               WHERE order_id = ?""",
            (reason, now_iso(), order_id),
        )
        await self._db.connection.commit()


# ---------------------------------------------------------------------------
# Trade history table
# ---------------------------------------------------------------------------


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


# ---------------------------------------------------------------------------
# Daily stats table
# ---------------------------------------------------------------------------


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


# ---------------------------------------------------------------------------
# Logs table
# ---------------------------------------------------------------------------


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


# ---------------------------------------------------------------------------
# Monitor settings table
# ---------------------------------------------------------------------------


class MonitorSettingsRepository:
    """Persists key-value pairs for the price monitor (interval, etc.)."""

    _KEY_INTERVAL = "price_monitor_interval"
    _KEY_EMERGENCY_STOP = "emergency_stop"
    _KEY_BACKUP_STATUS = "drive_backup_status"

    def __init__(self, db: Database) -> None:
        self._db = db

    async def get_backup_status(self) -> dict[str, Any] | None:
        """Return the last-known Drive backup outcome, or None if a backup
        has never run this database's lifetime. Shape:
        {last_success_at, last_success_file_id, last_error_at, last_error_message}
        (any of these may be None/absent individually).
        """
        cur = await self._db.connection.execute(
            "SELECT value FROM monitor_settings WHERE key = ?",
            (self._KEY_BACKUP_STATUS,),
        )
        row = await cur.fetchone()
        if row is None:
            return None
        return json.loads(row["value"])

    async def record_backup_success(self, file_id: str) -> None:
        """Record a successful backup, clearing any previously-recorded
        error (a fresh success supersedes it for status-reporting purposes)."""
        status = await self.get_backup_status() or {}
        status["last_success_at"] = now_iso()
        status["last_success_file_id"] = file_id
        status["last_error_at"] = None
        status["last_error_message"] = None
        await self._save_backup_status(status)

    async def record_backup_failure(self, error_message: str) -> None:
        """Record a failed backup attempt. Deliberately does NOT clear the
        last recorded success — /backupstatus should still be able to show
        "last good backup was N hours ago" even while also showing the most
        recent failure.
        """
        status = await self.get_backup_status() or {}
        status["last_error_at"] = now_iso()
        status["last_error_message"] = error_message
        await self._save_backup_status(status)

    async def _save_backup_status(self, status: dict[str, Any]) -> None:
        await self._db.connection.execute(
            """INSERT INTO monitor_settings (key, value, updated_at)
               VALUES (?, ?, ?)
               ON CONFLICT(key) DO UPDATE SET value = excluded.value,
                                              updated_at = excluded.updated_at""",
            (self._KEY_BACKUP_STATUS, json.dumps(status), now_iso()),
        )
        await self._db.connection.commit()

    async def get_emergency_stop(self) -> bool:
        """Return the persisted emergency-stop state (defaults to False)."""
        cur = await self._db.connection.execute(
            "SELECT value FROM monitor_settings WHERE key = ?",
            (self._KEY_EMERGENCY_STOP,),
        )
        row = await cur.fetchone()
        if row is None:
            return False
        return row["value"] == "1"

    async def set_emergency_stop(self, active: bool) -> None:
        """Persist the emergency-stop flag so it survives a restart."""
        await self._db.connection.execute(
            """INSERT INTO monitor_settings (key, value, updated_at)
               VALUES (?, ?, ?)
               ON CONFLICT(key) DO UPDATE SET value = excluded.value,
                                              updated_at = excluded.updated_at""",
            (self._KEY_EMERGENCY_STOP, "1" if active else "0", now_iso()),
        )
        await self._db.connection.commit()

    async def get_interval(self) -> int | None:
        """Return the stored interval, or None if never explicitly set.

        Callers should fall back to their own default when None is returned
        so that environment-variable configuration is honoured on first start.
        """
        cur = await self._db.connection.execute(
            "SELECT value FROM monitor_settings WHERE key = ?",
            (self._KEY_INTERVAL,),
        )
        row = await cur.fetchone()
        if row is None:
            return None
        try:
            value = int(row["value"])
        except (ValueError, KeyError):
            return None
        if value not in VALID_MONITOR_INTERVALS:
            return None
        return value

    async def set_interval(self, seconds: int) -> None:
        """Persist the monitor interval (must be one of VALID_MONITOR_INTERVALS)."""
        if seconds not in VALID_MONITOR_INTERVALS:
            raise ValueError(
                f"Invalid monitor interval {seconds}s. "
                f"Allowed: {', '.join(str(v) for v in VALID_MONITOR_INTERVALS)}s"
            )
        await self._db.connection.execute(
            """INSERT INTO monitor_settings (key, value, updated_at)
               VALUES (?, ?, ?)
               ON CONFLICT(key) DO UPDATE SET value = excluded.value,
                                              updated_at = excluded.updated_at""",
            (self._KEY_INTERVAL, str(seconds), now_iso()),
        )
        await self._db.connection.commit()


# ---------------------------------------------------------------------------
# Price alerts table
# ---------------------------------------------------------------------------


class PriceAlertRepository:
    """Persists one-shot price alerts across restarts."""

    def __init__(self, db: Database) -> None:
        self._db = db

    async def create(
        self,
        alert_id: str,
        symbol: str,
        target_price: float,
        direction: str,
        set_at: str,
    ) -> None:
        """Insert a new alert, replacing any existing alert with the same id."""
        await self._db.connection.execute(
            """INSERT INTO price_alerts (alert_id, symbol, target_price, direction, set_at)
               VALUES (?, ?, ?, ?, ?)
               ON CONFLICT(alert_id) DO UPDATE
                   SET symbol = excluded.symbol,
                       target_price = excluded.target_price,
                       direction = excluded.direction,
                       set_at = excluded.set_at""",
            (alert_id, symbol, target_price, direction, set_at),
        )
        await self._db.connection.commit()

    async def delete_by_symbol(self, symbol: str) -> int:
        """Delete all alerts for a symbol.  Returns the number of rows removed."""
        cur = await self._db.connection.execute(
            "DELETE FROM price_alerts WHERE symbol = ?", (symbol,)
        )
        await self._db.connection.commit()
        return cur.rowcount or 0

    async def delete_by_id(self, alert_id: str) -> None:
        """Delete a single alert by its ID (used when an alert fires)."""
        await self._db.connection.execute(
            "DELETE FROM price_alerts WHERE alert_id = ?", (alert_id,)
        )
        await self._db.connection.commit()

    async def list_all(self) -> list[dict]:
        cur = await self._db.connection.execute(
            "SELECT * FROM price_alerts ORDER BY set_at"
        )
        rows = await cur.fetchall()
        return [_row(r) for r in rows]


# ---------------------------------------------------------------------------
# Grid defaults (Quick Default Grid Mode)
# ---------------------------------------------------------------------------


class GridDefaultsRepository:
    """Persists the single-row set of default grid parameters used by the
    Quick Default Grid workflow. Table is constrained to exactly one row
    (id=1) via a CHECK constraint — this is a settings singleton, not a
    per-user or per-coin table.
    """

    _ROW_ID = 1

    def __init__(self, db: Database) -> None:
        self._db = db

    async def get(self) -> dict | None:
        cur = await self._db.connection.execute(
            "SELECT * FROM grid_defaults WHERE id = ?", (self._ROW_ID,)
        )
        row = await cur.fetchone()
        return _row(row) if row else None

    async def get_or_seed(self, seed: dict) -> dict:
        """Return the saved defaults, creating them from *seed* on first use.

        This is what makes the feature "persist after restart" from the very
        first run — the seed values are only ever written once; every
        subsequent call returns whatever the user has since edited via
        /defaults.
        """
        existing = await self.get()
        if existing is not None:
            return existing
        await self._db.connection.execute(
            """INSERT INTO grid_defaults
               (id, base_investment, dip_buy_amount, dip_percentage,
                profit_sell_amount, profit_percentage, max_levels,
                stop_loss_percentage, last_mode, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                self._ROW_ID,
                seed["base_investment"], seed["dip_buy_amount"], seed["dip_percentage"],
                seed["profit_sell_amount"], seed["profit_percentage"], seed["max_levels"],
                seed["stop_loss_percentage"], seed.get("last_mode"), now_iso(),
            ),
        )
        await self._db.connection.commit()
        return await self.get()

    async def update(self, **fields) -> dict:
        """Update one or more default fields (upserting the row if it
        somehow doesn't exist yet — defensive, since get_or_seed should
        normally have created it first)."""
        allowed = {
            "base_investment", "dip_buy_amount", "dip_percentage",
            "profit_sell_amount", "profit_percentage", "max_levels",
            "stop_loss_percentage", "last_mode",
        }
        unknown = set(fields) - allowed
        if unknown:
            raise ValueError(f"Unknown grid default field(s): {sorted(unknown)}")

        existing = await self.get()
        if existing is None:
            # Nothing to merge with — caller must supply a complete seed
            # via get_or_seed() first in normal operation. Defensive only.
            raise RuntimeError("grid_defaults row does not exist — call get_or_seed() first")

        merged = {**existing, **fields}
        await self._db.connection.execute(
            """UPDATE grid_defaults SET
                   base_investment = ?, dip_buy_amount = ?, dip_percentage = ?,
                   profit_sell_amount = ?, profit_percentage = ?, max_levels = ?,
                   stop_loss_percentage = ?, last_mode = ?, updated_at = ?
               WHERE id = ?""",
            (
                merged["base_investment"], merged["dip_buy_amount"], merged["dip_percentage"],
                merged["profit_sell_amount"], merged["profit_percentage"], merged["max_levels"],
                merged["stop_loss_percentage"], merged.get("last_mode"), now_iso(),
                self._ROW_ID,
            ),
        )
        await self._db.connection.commit()
        return await self.get()


# ---------------------------------------------------------------------------
# Container
# ---------------------------------------------------------------------------


class Repositories:
    """Bundles every repository behind a single object."""

    def __init__(self, db: Database) -> None:
        self.db = db
        self.grids = DCAGridRepository(db)
        self.orders = OrderRepository(db)
        self.trade_history = TradeHistoryRepository(db)
        self.daily_stats = DailyStatsRepository(db)
        self.logs = LogRepository(db)
        self.monitor_settings = MonitorSettingsRepository(db)
        self.price_alerts = PriceAlertRepository(db)
        self.grid_defaults = GridDefaultsRepository(db)

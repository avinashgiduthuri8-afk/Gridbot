"""Orders table repository."""
from __future__ import annotations

from typing import Any

from storage.database import Database
from storage.models import OrderRecord
from utils.helpers import now_iso

from storage.repositories._shared import _row

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

    async def list_all(self, limit: int = 200) -> list[dict[str, Any]]:
        """Every order across every grid, most recent first — used by the
        dashboard's Orders page. Mirrors TradeHistoryRepository.list_all."""
        cur = await self._db.connection.execute(
            "SELECT * FROM orders ORDER BY created_at DESC LIMIT ?", (limit,)
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

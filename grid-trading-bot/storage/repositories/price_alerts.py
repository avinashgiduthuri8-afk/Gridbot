"""Price alert table repository."""
from __future__ import annotations

from storage.database import Database

from storage.repositories._shared import _row

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

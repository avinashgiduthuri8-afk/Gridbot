"""Grid defaults table repository."""
from __future__ import annotations

from storage.database import Database
from utils.helpers import now_iso

from storage.repositories._shared import _row

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

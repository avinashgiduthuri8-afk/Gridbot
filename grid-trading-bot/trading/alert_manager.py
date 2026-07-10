"""Price alert manager — in-memory with optional DB persistence.

Each alert is one-shot: it fires exactly once when the target price is crossed
in the expected direction, then is removed automatically.

Direction is determined at alert creation time by comparing the target to the
current live price:
- target > current_price  →  "above"  (fire when price >= target)
- target < current_price  →  "below"  (fire when price <= target)
- target == current_price →  rejected (already at target)

When a ``PriceAlertRepository`` is supplied the manager persists every add/delete
to SQLite and survives bot restarts.  Pass ``repos=None`` to keep the original
pure-in-memory behaviour (useful in tests).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Literal

from utils.helpers import new_id
from utils.logger import get_logger

if TYPE_CHECKING:
    from storage.repositories import PriceAlertRepository

log = get_logger("trading")


@dataclass
class PriceAlert:
    alert_id: str
    symbol: str
    target_price: float
    direction: Literal["above", "below"]
    set_at: str


class AlertManager:
    def __init__(self, repo: "PriceAlertRepository | None" = None) -> None:
        self._alerts: list[PriceAlert] = []
        self._repo = repo

    # ------------------------------------------------------------------
    # Startup
    # ------------------------------------------------------------------

    def load(self, rows: list[dict]) -> None:
        """Populate in-memory state from DB rows (call once at startup)."""
        self._alerts = [
            PriceAlert(
                alert_id=r["alert_id"],
                symbol=r["symbol"],
                target_price=float(r["target_price"]),
                direction=r["direction"],
                set_at=r["set_at"],
            )
            for r in rows
        ]
        log.info("Loaded %d price alert(s) from database", len(self._alerts))

    # ------------------------------------------------------------------
    # Mutations
    # ------------------------------------------------------------------

    def add(self, symbol: str, target_price: float, current_price: float, set_at: str) -> str:
        """Memory-only add — for tests and callers that handle their own persistence.

        Production Telegram handlers should use ``add_and_persist()`` instead.
        Returns the direction ("above"/"below") or raises ValueError.
        """
        direction = self._resolve_direction(symbol, target_price, current_price)
        self._alerts = [
            a for a in self._alerts
            if not (a.symbol == symbol and a.target_price == target_price)
        ]
        alert_id = new_id("alr")
        self._alerts.append(PriceAlert(
            alert_id=alert_id, symbol=symbol,
            target_price=target_price, direction=direction, set_at=set_at,
        ))
        log.info("Alert set: %s @ ₹%s (%s)", symbol, target_price, direction)
        return direction

    async def add_and_persist(
        self, symbol: str, target_price: float, current_price: float, set_at: str
    ) -> str:
        """Persist the new alert to DB first, then add to memory.

        DB-first ordering ensures that if the app crashes after a successful
        DB write, the alert is still present after restart (loaded from DB).
        Returns the direction string; raises ValueError if target == current.
        """
        direction = self._resolve_direction(symbol, target_price, current_price)
        # Remove duplicate from memory before writing to DB
        self._alerts = [
            a for a in self._alerts
            if not (a.symbol == symbol and a.target_price == target_price)
        ]
        alert_id = new_id("alr")
        if self._repo:
            await self._repo.create(alert_id, symbol, target_price, direction, set_at)
        self._alerts.append(PriceAlert(
            alert_id=alert_id, symbol=symbol,
            target_price=target_price, direction=direction, set_at=set_at,
        ))
        log.info("Alert set (persisted): %s @ ₹%s (%s)", symbol, target_price, direction)
        return direction

    def _resolve_direction(
        self, symbol: str, target_price: float, current_price: float
    ) -> "Literal['above', 'below']":
        if target_price > current_price:
            return "above"
        if target_price < current_price:
            return "below"
        raise ValueError(
            f"Target ₹{target_price:,.2f} equals current price — alert would fire instantly."
        )

    def delete(self, symbol: str) -> int:
        """Memory-only delete — for tests.  Production code should use ``delete_and_persist()``."""
        before = len(self._alerts)
        self._alerts = [a for a in self._alerts if a.symbol != symbol]
        removed = before - len(self._alerts)
        if removed:
            log.info("Deleted %d alert(s) for %s", removed, symbol)
        return removed

    async def delete_and_persist(self, symbol: str) -> int:
        """Delete from DB first, then from memory.

        DB-first ordering ensures that if the app crashes mid-operation the
        alert is gone from both DB and memory after the next restart.
        """
        if self._repo:
            await self._repo.delete_by_symbol(symbol)
        removed = self.delete(symbol)
        return removed

    # ------------------------------------------------------------------
    # Reads
    # ------------------------------------------------------------------

    def list_all(self) -> list[PriceAlert]:
        return list(self._alerts)

    def symbols_with_alerts(self) -> list[str]:
        return list({a.symbol for a in self._alerts})

    # ------------------------------------------------------------------
    # Check
    # ------------------------------------------------------------------

    def check_and_fire(self, symbol: str, current_price: float) -> list[PriceAlert]:
        """Return all alerts for *symbol* whose condition is now met, removing
        them from the store (one-shot semantics)."""
        fired: list[PriceAlert] = []
        remaining: list[PriceAlert] = []
        for alert in self._alerts:
            if alert.symbol != symbol:
                remaining.append(alert)
                continue
            triggered = (
                alert.direction == "above" and current_price >= alert.target_price
            ) or (
                alert.direction == "below" and current_price <= alert.target_price
            )
            if triggered:
                log.info("Alert fired: %s @ ₹%s (current ₹%s)", symbol, alert.target_price, current_price)
                fired.append(alert)
            else:
                remaining.append(alert)
        self._alerts = remaining
        return fired

    async def fire_and_persist(self, symbol: str, current_price: float) -> list[PriceAlert]:
        """Identify fired alerts, persist their deletion first, then remove from memory.

        DB-first ordering: if the app crashes after persisting but before updating
        memory, the next restart won't reload the fired alert (already gone from DB).
        """
        would_fire = [
            a for a in self._alerts
            if a.symbol == symbol and (
                (a.direction == "above" and current_price >= a.target_price)
                or (a.direction == "below" and current_price <= a.target_price)
            )
        ]
        if would_fire and self._repo:
            for alert in would_fire:
                await self._repo.delete_by_id(alert.alert_id)
                log.info(
                    "Alert fired (persisted): %s @ ₹%s (current ₹%s)",
                    symbol, alert.target_price, current_price,
                )
        fired_ids = {a.alert_id for a in would_fire}
        self._alerts = [a for a in self._alerts if a.alert_id not in fired_ids]
        return would_fire

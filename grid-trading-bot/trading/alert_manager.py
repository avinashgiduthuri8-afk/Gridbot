"""In-memory price alert manager.

Each alert is one-shot: it fires exactly once when the target price is crossed
in the expected direction, then is removed automatically.  Alerts are not
persisted across restarts — this is by design for simplicity.

Direction is determined at alert creation time by comparing the target to the
current live price:
- target > current_price  →  "above"  (fire when price >= target)
- target < current_price  →  "below"  (fire when price <= target)
- target == current_price →  rejected (already at target)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

from utils.logger import get_logger

log = get_logger("trading")


@dataclass
class PriceAlert:
    symbol: str
    target_price: float
    direction: Literal["above", "below"]
    set_at: str


class AlertManager:
    def __init__(self) -> None:
        self._alerts: list[PriceAlert] = []

    # ------------------------------------------------------------------
    # Mutations
    # ------------------------------------------------------------------

    def add(self, symbol: str, target_price: float, current_price: float, set_at: str) -> str:
        """Add a price alert.  Returns the direction string ("above"/"below")
        or raises ValueError if the target is already met."""
        if target_price > current_price:
            direction: Literal["above", "below"] = "above"
        elif target_price < current_price:
            direction = "below"
        else:
            raise ValueError(f"Target ₹{target_price:,.2f} equals current price — alert would fire instantly.")

        # Deduplicate: replace any existing alert for the same symbol + target
        self._alerts = [
            a for a in self._alerts
            if not (a.symbol == symbol and a.target_price == target_price)
        ]
        self._alerts.append(PriceAlert(symbol=symbol, target_price=target_price,
                                       direction=direction, set_at=set_at))
        log.info("Alert set: %s @ ₹%s (%s)", symbol, target_price, direction)
        return direction

    def delete(self, symbol: str) -> int:
        """Remove all alerts for a symbol.  Returns the number removed."""
        before = len(self._alerts)
        self._alerts = [a for a in self._alerts if a.symbol != symbol]
        removed = before - len(self._alerts)
        if removed:
            log.info("Deleted %d alert(s) for %s", removed, symbol)
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

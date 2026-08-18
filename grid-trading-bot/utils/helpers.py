"""Small shared utilities: decimal-safe math, ID generation, retry helpers."""

from __future__ import annotations

import math
import time
import uuid
from typing import Any


def new_id(prefix: str) -> str:
    """Generate a short, sortable unique ID for grids/orders."""
    return f"{prefix}_{int(time.time() * 1000)}_{uuid.uuid4().hex[:6]}"


def is_valid_price(price: float) -> bool:
    """True only for a usable market price: a finite, positive number.

    Rejects 0, negative values, NaN, and +/-Infinity — all real failure
    modes an exchange ticker can return during an outage or a data bug.
    Used as a guard before ANY price is allowed to drive a trading
    decision (dip-buy, profit-sell, stop-loss); a garbage reading here
    must never reach that logic, since e.g. a price of 0 would otherwise
    satisfy a stop-loss condition for any grid and trigger an unwanted
    full-position sell.
    """
    return isinstance(price, (int, float)) and math.isfinite(price) and price > 0


def now_ms() -> int:
    return int(time.time() * 1000)


def now_iso() -> str:
    from datetime import datetime, timezone

    return datetime.now(timezone.utc).isoformat()


def fmt_price(value: float, precision: int | None = None) -> str:
    """Format a price in ₹ with the right number of decimal places.

    If *precision* is provided (from MarketInfo.base_currency_precision) it is
    used directly.  Otherwise a magnitude heuristic is applied so that cheap
    coins (SHIB: ₹0.002) show meaningful decimals and expensive coins (BTC:
    ₹6,500,000) don't show trailing zeros:

      price >= 100    →  2 dp  (BTC, ETH)
      price >= 1      →  4 dp  (XRP, MATIC, SOL)
      price >= 0.01   →  6 dp  (small alts)
      price < 0.01    →  8 dp  (SHIB, etc.)
    """
    if precision is not None:
        dp = max(0, precision)
    elif value >= 100:
        dp = 2
    elif value >= 1:
        dp = 4
    elif value >= 0.01:
        dp = 6
    else:
        dp = 8
    return f"₹{value:,.{dp}f}"


def safe_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default

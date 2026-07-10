"""Small shared utilities: decimal-safe math, ID generation, retry helpers."""

from __future__ import annotations

import time
import uuid
from decimal import ROUND_DOWN, Decimal
from typing import Any


def new_id(prefix: str) -> str:
    """Generate a short, sortable unique ID for grids/orders."""
    return f"{prefix}_{int(time.time() * 1000)}_{uuid.uuid4().hex[:6]}"


def to_decimal(value: Any) -> Decimal:
    """Convert a value to Decimal safely (via str to avoid float artifacts)."""
    if isinstance(value, Decimal):
        return value
    return Decimal(str(value))


def round_step(value: Decimal, step: Decimal) -> Decimal:
    """Round `value` down to the nearest multiple of `step` (exchange lot size)."""
    if step <= 0:
        return value
    return (value / step).to_integral_value(rounding=ROUND_DOWN) * step


def quantize(value: Decimal, decimals: int) -> Decimal:
    """Quantize a Decimal to a fixed number of decimal places, rounding down."""
    if decimals < 0:
        decimals = 0
    exp = Decimal(1).scaleb(-decimals)
    return value.quantize(exp, rounding=ROUND_DOWN)


def now_ms() -> int:
    return int(time.time() * 1000)


def now_iso() -> str:
    from datetime import datetime, timezone

    return datetime.now(timezone.utc).isoformat()


def format_inr(value: Decimal) -> str:
    return f"₹{value:,.2f}"


def format_pct(value: Decimal) -> str:
    return f"{value:+.2f}%"


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

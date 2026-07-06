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


def safe_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default

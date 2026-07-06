"""Static constants shared across the bot."""

from __future__ import annotations

from enum import Enum


class GridType(str, Enum):
    ARITHMETIC = "arithmetic"
    GEOMETRIC = "geometric"


class GridStatus(str, Enum):
    ACTIVE = "active"
    PAUSED = "paused"
    STOPPED = "stopped"
    COMPLETED = "completed"


class OrderSide(str, Enum):
    BUY = "buy"
    SELL = "sell"


class OrderStatus(str, Enum):
    PENDING = "pending"
    OPEN = "open"
    FILLED = "filled"
    PARTIALLY_FILLED = "partially_filled"
    CANCELLED = "cancelled"
    REJECTED = "rejected"
    FAILED = "failed"


class PositionStatus(str, Enum):
    OPEN = "open"
    CLOSED = "closed"


DEFAULT_GRID_LEVELS = 10
DEFAULT_INVESTMENT_PER_GRID = 100.0

MIN_GRID_LEVELS = 3
MAX_GRID_LEVELS = 50

# CoinDCX market suffix used for INR pairs, e.g. BTCINR -> B-BTC_INR internally
# on some endpoints, but the public ticker + order API use the plain symbol
# (e.g. "BTCINR") directly, which is what this bot standardizes on.
QUOTE_CURRENCY = "INR"

TELEGRAM_MAX_MESSAGE_LENGTH = 4000

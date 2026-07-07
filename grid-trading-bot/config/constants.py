"""Static constants and enums shared across the DCA grid bot."""

from __future__ import annotations

from enum import Enum


class GridStatus(str, Enum):
    ACTIVE = "active"
    PAUSED = "paused"
    STOPPED = "stopped"
    COMPLETED = "completed"


class TradingMode(str, Enum):
    PAPER = "paper"
    REAL = "real"


class OrderSide(str, Enum):
    BUY = "buy"
    SELL = "sell"


class OrderStatus(str, Enum):
    PENDING = "pending"            # local record created, exchange call not yet attempted
    SUBMITTED = "submitted"        # exchange call in-flight (crash here → uncertain if landed)
    OPEN = "open"                  # acknowledged by exchange, waiting to fill
    PARTIALLY_FILLED = "partially_filled"
    FILLED = "filled"
    CANCELLED = "cancelled"
    REJECTED = "rejected"          # exchange rejected immediately (permanent)
    EXPIRED = "expired"            # time-in-force expired before full fill
    FAILED = "failed"              # could not be placed (local or permanent exchange error)


QUOTE_CURRENCY = "INR"
TELEGRAM_MAX_MESSAGE_LENGTH = 4000

DEFAULT_DIP_PERCENTAGE = 5.0
DEFAULT_PROFIT_PERCENTAGE = 7.0
DEFAULT_STOP_LOSS_PERCENTAGE = 50.0
DEFAULT_MAX_LEVELS = 10
DEFAULT_BASE_INVESTMENT = 500.0
DEFAULT_DIP_BUY_AMOUNT = 100.0
DEFAULT_PROFIT_SELL_AMOUNT = 150.0

"""Static constants and enums shared across the DCA grid bot."""

from __future__ import annotations

import re
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

# Strict alphanumeric-only trading symbol pattern. Used everywhere a
# user-typed symbol is validated *before* being echoed back into a
# parse_mode="HTML" Telegram message — a bare `.endswith("INR")` check
# would let characters like < > & through, which can break Telegram's
# HTML entity parsing (the bot's own "Checking <b>{symbol}</b>…" message
# would fail to send) well before exchange-side pair validation ever runs.
SYMBOL_PATTERN = re.compile(r"^[A-Z0-9]+INR$")

# Matches new_id()'s output format exactly: "<prefix>_<13-digit-ms>_<6hex>".
# Used the same way as SYMBOL_PATTERN — reject a malformed grid_id before
# it's ever echoed into a parse_mode="HTML" "not found" reply.
GRID_ID_PATTERN = re.compile(r"^grd_[0-9]{10,16}_[0-9a-f]{6}$")
TELEGRAM_MAX_MESSAGE_LENGTH = 4000

DEFAULT_DIP_PERCENTAGE = 5.0
DEFAULT_PROFIT_PERCENTAGE = 7.0
DEFAULT_STOP_LOSS_PERCENTAGE = 50.0
DEFAULT_MAX_LEVELS = 10
DEFAULT_BASE_INVESTMENT = 500.0
DEFAULT_DIP_BUY_AMOUNT = 100.0
DEFAULT_PROFIT_SELL_AMOUNT = 150.0

# Seed values for the Quick Default Grid workflow's grid_defaults table,
# used only the very first time /defaults or the "Default Grid" option is
# used. Deliberately a separate set of numbers from the DEFAULT_* constants
# above (which are just placeholder/example text shown in the Custom Grid
# flow's prompts) — editing one must never silently affect the other.
QUICK_GRID_DEFAULTS_SEED = {
    "base_investment": 500.0,
    "dip_buy_amount": 100.0,
    "dip_percentage": 5.0,
    "profit_sell_amount": 120.0,
    "profit_percentage": 7.0,
    "max_levels": 5,
    "stop_loss_percentage": 50.0,
    "last_mode": None,
}

"""Static constants and enums shared across the DCA grid bot."""

from __future__ import annotations

import re
from enum import Enum


class GridStatus(str, Enum):
    ACTIVE = "active"
    PAUSED = "paused"
    STOPPING = "stopping"
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
    UNKNOWN = "unknown"            # delivery/result uncertain; reconcile only, never resubmit
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


# ==============================================================================
# INDIAN STOCK MARKET CONSTANTS & ENUMS (PROJECT-BETA)
# ==============================================================================


class MarketRegime(str, Enum):
    STRONG_BULLISH = "STRONG_BULLISH"
    BULLISH = "BULLISH"
    NEUTRAL = "NEUTRAL"
    BEARISH = "BEARISH"
    STRONG_BEARISH = "STRONG_BEARISH"
    HIGH_VOLATILITY = "HIGH_VOLATILITY"


class SignalType(str, Enum):
    BREAKOUT = "BREAKOUT"
    PULLBACK = "PULLBACK"
    MOMENTUM_CONTINUATION = "MOMENTUM_CONTINUATION"
    REVERSAL = "REVERSAL"
    VCP_BREAKOUT = "VCP_BREAKOUT"
    POCKET_PIVOT = "POCKET_PIVOT"
    NR7_COMPRESSION = "NR7_COMPRESSION"
    HIGH_DELIVERY_BREAKOUT = "HIGH_DELIVERY_BREAKOUT"


class SignalStrength(str, Enum):
    VERY_STRONG = "VERY_STRONG"  # 90 - 100
    STRONG = "STRONG"            # 80 - 89
    VALID = "VALID"              # 70 - 79
    WATCHLIST = "WATCHLIST"      # 60 - 69
    REJECT = "REJECT"            # < 60


class SessionState(str, Enum):
    PRE_MARKET = "PRE_MARKET"                  # 09:00 - 09:15 IST
    MARKET_OPEN = "MARKET_OPEN"                # 09:15 - 09:30 IST
    INTRADAY_REGULAR = "INTRADAY_REGULAR"      # 09:30 - 15:15 IST
    MARKET_CLOSE = "MARKET_CLOSE"              # 15:15 - 15:30 IST
    POST_MARKET = "POST_MARKET"                # 15:30 - 16:00 IST
    CLOSED = "CLOSED"                          # 16:00 - 09:00 IST & Weekends/Holidays


class Timeframe(str, Enum):
    M5 = "5m"
    M15 = "15m"
    M30 = "30m"
    H1 = "1h"
    H4 = "4h"
    D1 = "1d"
    W1 = "1w"


class StockUniverseType(str, Enum):
    NIFTY_50 = "NIFTY_50"
    NIFTY_100 = "NIFTY_100"
    NIFTY_200 = "NIFTY_200"
    NIFTY_500 = "NIFTY_500"
    CUSTOM = "CUSTOM"


# Default Indian stock scanner scoring weights (Sum to 100)
DEFAULT_SCANNER_WEIGHTS = {
    "technical_trend": 20,
    "momentum": 15,
    "volume": 15,
    "price_action": 15,
    "multi_timeframe": 15,
    "market_regime": 10,
    "sector_strength": 5,
    "news_sentiment": 5,
}

# Score tier thresholds
SCORE_THRESHOLDS = {
    "VERY_STRONG": 90.0,
    "STRONG": 80.0,
    "VALID": 70.0,
    "WATCHLIST": 60.0,
}

MIN_REQUIRED_RR = 2.0
DEFAULT_MAX_FINAL_SIGNALS = 3


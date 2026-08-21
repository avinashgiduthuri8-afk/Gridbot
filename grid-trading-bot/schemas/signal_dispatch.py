"""Standardized Payload Models for Master Signal Dispatcher & Execution Bots.

Defines the exact institutional payload contract sent to downstream execution bots
(Zerodha Kite, Dhan, Fyers, Custom Python/Node workers) over Webhooks and WebSocket streams.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from utils.helpers import now_iso


@dataclass
class SignalOrderPayload:
    """Institutional machine-readable trade instruction broadcast to downstream bots."""
    signal_id: str
    timestamp_ist: str
    symbol: str
    exchange: str = "NSE"
    instrument_type: str = "EQUITY_CASH"      # EQUITY_CASH, EQUITY_FUT
    action: str = "BUY"                       # BUY, SELL
    order_type: str = "LIMIT"                 # LIMIT, STOP_LIMIT, MARKET
    entry_price: float = 0.0
    stop_loss: float = 0.0
    target_1: float = 0.0                     # 2.0R Default
    target_2: float = 0.0                     # 3.5R Runner
    risk_per_share: float = 0.0               # entry_price - stop_loss
    recommended_rr_ratio: float = 2.0
    trailing_strategy: str = "TRAIL_20_EMA_DAILY" # TRAIL_20_EMA_DAILY, ATR_CHANDELIER, STEP_1R
    setup_type: str = "BREAKOUT"
    confidence_score: float = 85.0
    confluence_factors: dict[str, Any] = field(default_factory=dict)
    validity_expiry_ist: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "signal_id": self.signal_id,
            "timestamp_ist": self.timestamp_ist,
            "symbol": self.symbol,
            "exchange": self.exchange,
            "instrument_type": self.instrument_type,
            "action": self.action,
            "order_type": self.order_type,
            "entry_price": round(self.entry_price, 2),
            "stop_loss": round(self.stop_loss, 2),
            "target_1": round(self.target_1, 2),
            "target_2": round(self.target_2, 2),
            "risk_per_share": round(self.risk_per_share, 2),
            "recommended_rr_ratio": round(self.recommended_rr_ratio, 2),
            "trailing_strategy": self.trailing_strategy,
            "setup_type": self.setup_type,
            "confidence_score": round(self.confidence_score, 1),
            "confluence_factors": self.confluence_factors,
            "validity_expiry_ist": self.validity_expiry_ist,
        }


@dataclass
class BotRegistration:
    """Downstream execution bot configured to receive automated signals."""
    bot_id: str
    name: str
    target_broker: str                        # Zerodha, Dhan, Fyers, Finvasia, AngelOne, Custom
    webhook_url: str
    secret_key: str                           # HMAC-SHA256 Secret
    subscribed_setups: list[str] = field(default_factory=lambda: ["ALL"])
    min_confidence_score: float = 75.0
    is_active: bool = True
    created_at: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "bot_id": self.bot_id,
            "name": self.name,
            "target_broker": self.target_broker,
            "webhook_url": self.webhook_url,
            "secret_key": self.secret_key,
            "subscribed_setups": self.subscribed_setups,
            "min_confidence_score": round(self.min_confidence_score, 1),
            "is_active": self.is_active,
            "created_at": self.created_at or now_iso(),
        }


@dataclass
class DispatchReceipt:
    """Audit log of an automated signal delivery to a downstream execution bot."""
    dispatch_id: str
    signal_id: str
    bot_id: str
    timestamp: str
    status: str                               # SUCCESS, FAILED, RETRYING
    response_code: int = 0
    latency_ms: float = 0.0
    error_message: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "dispatch_id": self.dispatch_id,
            "signal_id": self.signal_id,
            "bot_id": self.bot_id,
            "timestamp": self.timestamp,
            "status": self.status,
            "response_code": self.response_code,
            "latency_ms": round(self.latency_ms, 2),
            "error_message": self.error_message,
        }

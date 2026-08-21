"""Signal Lifecycle & Deduplication Manager for Indian Equities.

Manages signal progression states:
WATCH -> SETUP -> CONFIRMED -> SIGNAL -> REJECTED / EXPIRED / INVALIDATED
and deduplicates repeated scan cycles.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any

from utils.helpers import now_iso
from utils.logger import get_logger

log = get_logger("scanner")


class SignalLifecycleState(str, Enum):
    WATCH = "WATCH"                    # Initial candidate on daily/1H chart
    SETUP = "SETUP"                    # Technical setup identified, awaiting 15M trigger
    CONFIRMED = "CONFIRMED"            # Multi-timeframe and volume confirmation met
    SIGNAL = "SIGNAL"                  # Published high-conviction signal
    REJECTED = "REJECTED"              # Blocked by hard risk/extension gate
    EXPIRED = "EXPIRED"                # Exceeded TTL window without execution
    INVALIDATED = "INVALIDATED"        # Key technical invalidation level breached


@dataclass
class ActiveSignalRecord:
    symbol: str
    signal_id: str
    lifecycle_state: SignalLifecycleState
    entry_price: float
    stop_loss: float
    target_1: float
    score: float
    created_at: datetime
    updated_at: datetime
    ttl_seconds: int = 14400          # 4-hour default validity for intraday setups

    @property
    def is_expired(self) -> bool:
        age = (datetime.now(timezone.utc) - self.created_at).total_seconds()
        return age > self.ttl_seconds


class SignalLifecycleManager:
    """Tracks active stock signals across scan iterations to eliminate duplicates."""

    def __init__(self, default_ttl_seconds: int = 14400) -> None:
        self._active_signals: dict[str, ActiveSignalRecord] = {}
        self._default_ttl = default_ttl_seconds

    def check_deduplication(
        self,
        symbol: str,
        new_entry: float,
        new_score: float,
    ) -> tuple[bool, str]:
        """Checks if a fresh signal is a duplicate of an existing active signal.

        Returns (is_duplicate, reason).
        """
        record = self._active_signals.get(symbol)
        if not record:
            return False, "New signal"

        # Check expiration
        if record.is_expired:
            del self._active_signals[symbol]
            return False, "Previous signal expired"

        # Check price delta (< 0.8% change and score within 3 pts is duplicate)
        price_diff_pct = abs(new_entry - record.entry_price) / record.entry_price * 100.0
        score_diff = abs(new_score - record.score)

        if price_diff_pct < 0.8 and score_diff < 4.0:
            return True, f"Duplicate of active signal created at {record.created_at.strftime('%H:%M:%S')}"

        return False, "Material level or setup update"

    def register_signal(
        self,
        symbol: str,
        signal_id: str,
        entry_price: float,
        stop_loss: float,
        target_1: float,
        score: float,
        state: SignalLifecycleState = SignalLifecycleState.CONFIRMED,
    ) -> ActiveSignalRecord:
        """Registers or updates an active signal record."""
        now = datetime.now(timezone.utc)
        record = ActiveSignalRecord(
            symbol=symbol,
            signal_id=signal_id,
            lifecycle_state=state,
            entry_price=entry_price,
            stop_loss=stop_loss,
            target_1=target_1,
            score=score,
            created_at=now,
            updated_at=now,
            ttl_seconds=self._default_ttl,
        )
        self._active_signals[symbol] = record
        return record

    def invalidate_if_breached(self, symbol: str, current_price: float) -> bool:
        """Invalidates an active signal if current price breaches its stop loss."""
        record = self._active_signals.get(symbol)
        if not record:
            return False

        if current_price <= record.stop_loss:
            record.lifecycle_state = SignalLifecycleState.INVALIDATED
            log.info("Signal %s invalidated: price ₹%.2f breached SL ₹%.2f", symbol, current_price, record.stop_loss)
            del self._active_signals[symbol]
            return True

        return False

    def prune_expired(self) -> int:
        """Removes expired signals from memory."""
        expired_syms = [s for s, r in self._active_signals.items() if r.is_expired]
        for sym in expired_syms:
            del self._active_signals[sym]
        return len(expired_syms)

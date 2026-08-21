"""Price Extension & Chasing Filter for Indian Equities.

Evaluates whether a stock is too far extended from its baseline (EMA 20, VWAP, Breakout Pivot)
in ATR units to prevent chasing at cyclical swing highs.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from engine.indicators.technical import IndicatorSnapshot


@dataclass
class ExtensionMetrics:
    symbol: str
    last_price: float
    dist_to_ema20_atr: float = 0.0     # Distance from 20 EMA in multiples of ATR
    dist_to_ema50_pct: float = 0.0     # % distance from 50 EMA
    dist_to_vwap_pct: float = 0.0      # % distance from VWAP
    dist_to_pivot_pct: float = 0.0     # % distance above breakout resistance level
    is_overextended: bool = False
    entry_quality_score: float = 10.0  # 0 to 10 scale
    extension_status: str = "OPTIMAL"  # OPTIMAL, ACCEPTABLE, EXTENDED, OVEREXTENDED
    warning_message: str = ""


class ExtensionFilter:
    """Detects overextended price action and scores entry timing quality."""

    def __init__(
        self,
        max_ema20_atr_dist: float = 2.2,
        max_breakout_chase_pct: float = 4.0,
    ) -> None:
        self.max_ema20_atr_dist = max_ema20_atr_dist
        self.max_breakout_chase_pct = max_breakout_chase_pct

    def evaluate_extension(
        self,
        symbol: str,
        snap_1d: IndicatorSnapshot,
        pivot_level: float | None = None,
    ) -> ExtensionMetrics:
        """Evaluates entry proximity to structural baselines."""
        price = snap_1d.last_price
        atr = snap_1d.atr if snap_1d.atr and snap_1d.atr > 0 else (price * 0.015)
        ema_20 = snap_1d.ema_20 or price
        ema_50 = snap_1d.ema_50 or price
        vwap = snap_1d.vwap or price
        pivot = pivot_level or snap_1d.resistance_20 or ema_20

        # 1. ATR Distance from 20 EMA
        dist_ema20_atr = (price - ema_20) / atr if atr > 0 else 0.0
        # 2. Percentage distance from 50 EMA & VWAP
        dist_ema50_pct = ((price - ema_50) / ema_50 * 100.0) if ema_50 > 0 else 0.0
        dist_vwap_pct = ((price - vwap) / vwap * 100.0) if vwap > 0 else 0.0
        # 3. Distance above breakout pivot
        dist_pivot_pct = ((price - pivot) / pivot * 100.0) if pivot > 0 else 0.0

        is_overextended = False
        warning = ""
        entry_score = 10.0
        status = "OPTIMAL"

        if dist_ema20_atr > self.max_ema20_atr_dist:
            is_overextended = True
            status = "OVEREXTENDED"
            entry_score = 0.0
            warning = f"Overextended: {dist_ema20_atr:.1f}x ATR above 20 EMA (limit: {self.max_ema20_atr_dist:.1f}x)"
        elif dist_pivot_pct > self.max_breakout_chase_pct:
            is_overextended = True
            status = "OVEREXTENDED"
            entry_score = 1.0
            warning = f"Chasing Breakout: +{dist_pivot_pct:.1f}% above pivot ₹{pivot:.2f} (limit: {self.max_breakout_chase_pct:.1f}%)"
        elif dist_ema20_atr > 1.6:
            status = "EXTENDED"
            entry_score = 4.0
            warning = f"Moderately stretched: {dist_ema20_atr:.1f}x ATR from 20 EMA"
        elif dist_ema20_atr > 0.9:
            status = "ACCEPTABLE"
            entry_score = 7.5
        else:
            status = "OPTIMAL"
            entry_score = 10.0

        return ExtensionMetrics(
            symbol=symbol,
            last_price=round(price, 2),
            dist_to_ema20_atr=round(dist_ema20_atr, 2),
            dist_to_ema50_pct=round(dist_ema50_pct, 2),
            dist_to_vwap_pct=round(dist_vwap_pct, 2),
            dist_to_pivot_pct=round(dist_pivot_pct, 2),
            is_overextended=is_overextended,
            entry_quality_score=entry_score,
            extension_status=status,
            warning_message=warning,
        )

"""Relative Strength (RS) & Alpha Calculator for Indian Equities.

Calculates stock performance alpha vs NIFTY 50 benchmark and relevant sector indices
over multiple lookback windows (5-day, 20-day, 50-day).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from engine.data.base import OHLCVCandle


@dataclass
class RelativeStrengthMetrics:
    symbol: str
    alpha_5d: float = 0.0          # Stock 5d % change minus NIFTY 5d % change
    alpha_20d: float = 0.0         # Stock 20d % change minus NIFTY 20d % change
    alpha_50d: float = 0.0         # Stock 50d % change minus NIFTY 50d % change
    normalized_rs_score: float = 50.0  # 0 to 100 scale
    is_outperforming: bool = False
    rs_score: float = 0.0          # Component score (0 - 5 pts)
    tier: str = "NEUTRAL"          # WEAK (0-30), NEUTRAL (30-50), STRONG (50-70), EXCEPTIONAL (70-100)


class RelativeStrengthCalculator:
    """Calculates relative performance of a stock against NIFTY benchmark."""

    @staticmethod
    def calculate_alpha(
        stock_candles: list[OHLCVCandle],
        nifty_candles: list[OHLCVCandle],
        symbol_override: str = "",
    ) -> RelativeStrengthMetrics:
        """Calculates outperformance alpha against NIFTY 50."""
        if not stock_candles or not nifty_candles:
            return RelativeStrengthMetrics(symbol=symbol_override)

        symbol = symbol_override or getattr(stock_candles[-1], "symbol", "") or "STOCK"

        if len(stock_candles) < 5 or len(nifty_candles) < 5:
            return RelativeStrengthMetrics(symbol=symbol)

        s_now = stock_candles[-1].close
        n_now = nifty_candles[-1].close

        # 5-day return
        s_5d = stock_candles[-5].close if len(stock_candles) >= 5 else stock_candles[0].close
        s_ret_5d = ((s_now - s_5d) / s_5d * 100.0) if s_5d > 0 else 0.0

        n_5d = nifty_candles[-5].close if len(nifty_candles) >= 5 else nifty_candles[0].close
        n_ret_5d = ((n_now - n_5d) / n_5d * 100.0) if n_5d > 0 else 0.0

        alpha_5d = round(s_ret_5d - n_ret_5d, 2)

        # 20-day return
        alpha_20d = alpha_5d
        if len(stock_candles) >= 20 and len(nifty_candles) >= 20:
            s_20d = stock_candles[-20].close
            s_ret_20d = ((s_now - s_20d) / s_20d * 100.0) if s_20d > 0 else 0.0

            n_20d = nifty_candles[-20].close
            n_ret_20d = ((n_now - n_20d) / n_20d * 100.0) if n_20d > 0 else 0.0

            alpha_20d = round(s_ret_20d - n_ret_20d, 2)

        # 50-day return (if available)
        alpha_50d = alpha_20d
        if len(stock_candles) >= 50 and len(nifty_candles) >= 50:
            s_50d = stock_candles[-50].close
            s_ret_50d = ((s_now - s_50d) / s_50d * 100.0) if s_50d > 0 else 0.0

            n_50d = nifty_candles[-50].close
            n_ret_50d = ((n_now - n_50d) / n_50d * 100.0) if n_50d > 0 else 0.0

            alpha_50d = round(s_ret_50d - n_ret_50d, 2)

        # Multi-factor normalized RS score (0 - 100)
        # Weighted: 50% from 20d, 30% from 5d, 20% from 50d
        composite_alpha = (alpha_20d * 0.50) + (alpha_5d * 0.30) + (alpha_50d * 0.20)
        # Map composite alpha (-10% to +10%) into 0 - 100 score
        normalized_rs = max(0.0, min(100.0, round(50.0 + (composite_alpha * 5.0), 1)))

        if normalized_rs >= 70.0:
            tier = "EXCEPTIONAL"
            score_5pt = 5.0
        elif normalized_rs >= 50.0:
            tier = "STRONG"
            score_5pt = 4.0
        elif normalized_rs >= 30.0:
            tier = "NEUTRAL"
            score_5pt = 2.5
        else:
            tier = "WEAK"
            score_5pt = 1.0

        is_outperforming = alpha_20d > 0.0 and alpha_5d > 0.0

        return RelativeStrengthMetrics(
            symbol=symbol,
            alpha_5d=alpha_5d,
            alpha_20d=alpha_20d,
            alpha_50d=alpha_50d,
            normalized_rs_score=normalized_rs,
            is_outperforming=is_outperforming,
            rs_score=score_5pt,
            tier=tier,
        )

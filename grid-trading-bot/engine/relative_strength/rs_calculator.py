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
    alpha_20d: float = 0.0        # Stock 20d % change minus NIFTY 20d % change
    mansfield_rs: float = 0.0     # Normalized Mansfield RS score
    is_outperforming: bool = False
    rs_score: float = 0.0         # Component score (0-5 pts)


class RelativeStrengthCalculator:
    """Calculates relative performance of a stock against NIFTY benchmark."""

    @staticmethod
    def calculate_alpha(
        stock_candles: list[OHLCVCandle],
        nifty_candles: list[OHLCVCandle],
    ) -> RelativeStrengthMetrics:
        """Calculates outperformance alpha against NIFTY 50."""
        if len(stock_candles) < 20 or len(nifty_candles) < 20:
            return RelativeStrengthMetrics(symbol=stock_candles[-1].symbol if stock_candles else "")

        symbol = stock_candles[-1].timeframe  # Fallback

        # 5-day return
        s_5d = stock_candles[-5].close if len(stock_candles) >= 5 else stock_candles[0].close
        s_now = stock_candles[-1].close
        s_ret_5d = ((s_now - s_5d) / s_5d * 100.0) if s_5d > 0 else 0.0

        n_5d = nifty_candles[-5].close if len(nifty_candles) >= 5 else nifty_candles[0].close
        n_now = nifty_candles[-1].close
        n_ret_5d = ((n_now - n_5d) / n_5d * 100.0) if n_5d > 0 else 0.0

        alpha_5d = s_ret_5d - n_5d

        # 20-day return
        s_20d = stock_candles[-20].close if len(stock_candles) >= 20 else stock_candles[0].close
        s_ret_20d = ((s_now - s_20d) / s_20d * 100.0) if s_20d > 0 else 0.0

        n_20d = nifty_candles[-20].close if len(nifty_candles) >= 20 else nifty_candles[0].close
        n_ret_20d = ((n_now - n_20d) / n_20d * 100.0) if n_20d > 0 else 0.0

        alpha_20d = s_ret_20d - n_20d

        # Score computation (0 - 5 pts)
        score = 2.5
        if alpha_20d > 3.0:
            score = 5.0
        elif alpha_20d > 1.0:
            score = 4.0
        elif alpha_20d > -1.0:
            score = 3.0
        elif alpha_20d > -3.0:
            score = 1.5
        else:
            score = 0.5

        return RelativeStrengthMetrics(
            symbol=stock_candles[-1].timeframe,
            alpha_5d=alpha_5d,
            alpha_20d=alpha_20d,
            mansfield_rs=alpha_20d,
            is_outperforming=alpha_20d > 0.5,
            rs_score=score,
        )

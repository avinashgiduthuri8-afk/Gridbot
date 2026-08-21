"""Multi-Timeframe (MTF) Confluence Engine for Indian Equities.

Evaluates 1D (Structure/Trend), 1H (Setup Formation), and 15M (Execution Trigger)
to ensure signals only fire with multi-timeframe confirmation.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Any

from engine.data.base import MarketDataProvider, OHLCVCandle
from engine.indicators.technical import IndicatorSnapshot, TechnicalIndicatorEngine
from utils.logger import get_logger

log = get_logger("mtf_analyzer")


@dataclass
class MTFAnalysis:
    """Multi-timeframe evaluation across 1D, 1H, and 15M."""
    symbol: str
    snap_1d: IndicatorSnapshot | None = None
    snap_1h: IndicatorSnapshot | None = None
    snap_15m: IndicatorSnapshot | None = None

    trend_1d: str = "NEUTRAL"       # BULLISH, BEARISH, NEUTRAL
    trend_1h: str = "NEUTRAL"
    trend_15m: str = "NEUTRAL"

    is_aligned_bullish: bool = False
    confluence_score: float = 0.0   # 0.0 to 15.0 pts
    details: str = ""


class MultiTimeframeAnalyzer:
    """Orchestrates multi-timeframe data retrieval and alignment checks."""

    def __init__(self, indicator_engine: TechnicalIndicatorEngine | None = None) -> None:
        self.indicator_engine = indicator_engine or TechnicalIndicatorEngine()

    def evaluate_trend_single_tf(self, snap: IndicatorSnapshot) -> str:
        """Determines directional trend for a single timeframe snapshot."""
        bullish_votes = 0
        bearish_votes = 0

        # 1. EMA Alignment
        if snap.ema_20 and snap.ema_50:
            if snap.last_price > snap.ema_20 > snap.ema_50:
                bullish_votes += 2
            elif snap.last_price < snap.ema_20 < snap.ema_50:
                bearish_votes += 2
            elif snap.last_price > snap.ema_20:
                bullish_votes += 1
            else:
                bearish_votes += 1

        if snap.ema_200:
            if snap.last_price > snap.ema_200:
                bullish_votes += 1
            else:
                bearish_votes += 1

        # 2. Momentum (RSI)
        if snap.rsi is not None:
            if snap.rsi >= 55.0:
                bullish_votes += 1
            elif snap.rsi <= 45.0:
                bearish_votes += 1

        # 3. MACD
        if snap.macd_hist is not None:
            if snap.macd_hist > 0:
                bullish_votes += 1
            else:
                bearish_votes += 1

        if bullish_votes >= bearish_votes + 2:
            return "BULLISH"
        elif bearish_votes >= bullish_votes + 2:
            return "BEARISH"
        return "NEUTRAL"

    def analyze_confluence(
        self,
        symbol: str,
        candles_1d: list[OHLCVCandle],
        candles_1h: list[OHLCVCandle],
        candles_15m: list[OHLCVCandle],
    ) -> MTFAnalysis:
        """Computes comprehensive multi-timeframe confluence and score."""
        snap_1d = self.indicator_engine.compute_snapshot(symbol, candles_1d, "1d")
        snap_1h = self.indicator_engine.compute_snapshot(symbol, candles_1h, "1h")
        snap_15m = self.indicator_engine.compute_snapshot(symbol, candles_15m, "15m")

        trend_1d = self.evaluate_trend_single_tf(snap_1d)
        trend_1h = self.evaluate_trend_single_tf(snap_1h)
        trend_15m = self.evaluate_trend_single_tf(snap_15m)

        score = 0.0
        details_list = []

        # 1D Trend Confirmation (Weight: 6 pts)
        if trend_1d == "BULLISH":
            score += 6.0
            details_list.append("1D Trend: Bullish")
        elif trend_1d == "NEUTRAL":
            score += 3.0
            details_list.append("1D Trend: Neutral")
        else:
            details_list.append("1D Trend: Bearish")

        # 1H Setup Confirmation (Weight: 5 pts)
        if trend_1h == "BULLISH":
            score += 5.0
            details_list.append("1H Setup: Bullish")
        elif trend_1h == "NEUTRAL":
            score += 2.5
            details_list.append("1H Setup: Neutral")
        else:
            details_list.append("1H Setup: Bearish")

        # 15M Trigger Confirmation (Weight: 4 pts)
        if trend_15m == "BULLISH":
            score += 4.0
            details_list.append("15M Trigger: Confirmed")
        elif trend_15m == "NEUTRAL":
            score += 2.0
            details_list.append("15M Trigger: Consolidating")
        else:
            details_list.append("15M Trigger: Bearish")

        is_aligned_bullish = (trend_1d == "BULLISH" and trend_1h == "BULLISH" and trend_15m == "BULLISH")
        if is_aligned_bullish:
            details_list.append("🔥 Full MTF Alignment")

        return MTFAnalysis(
            symbol=symbol,
            snap_1d=snap_1d,
            snap_1h=snap_1h,
            snap_15m=snap_15m,
            trend_1d=trend_1d,
            trend_1h=trend_1h,
            trend_15m=trend_15m,
            is_aligned_bullish=is_aligned_bullish,
            confluence_score=score,
            details=" | ".join(details_list),
        )

    async def fetch_and_analyze(
        self,
        provider: MarketDataProvider,
        symbol: str,
    ) -> MTFAnalysis:
        """Helper to fetch 1D, 1H, and 15M candles concurrently and analyze."""
        c_1d, c_1h, c_15m = await asyncio.gather(
            provider.get_historical_ohlcv(symbol, "1d", 100),
            provider.get_historical_ohlcv(symbol, "1h", 60),
            provider.get_historical_ohlcv(symbol, "15m", 50),
        )
        return self.analyze_confluence(symbol, c_1d, c_1h, c_15m)

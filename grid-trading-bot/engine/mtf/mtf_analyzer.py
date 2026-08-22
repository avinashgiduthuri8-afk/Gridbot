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

    def evaluate_1d_structure(self, snap: IndicatorSnapshot) -> str:
        """Evaluates 1D Macro Structure & Stage-2 Trend Baseline."""
        if not snap or snap.last_price <= 0:
            return "NEUTRAL"

        price = snap.last_price
        bullish_score = 0
        bearish_score = 0

        # 1. Moving Average Structure (EMA 20 / 50 / 200)
        if snap.ema_20 and snap.ema_50:
            if price >= snap.ema_20 >= snap.ema_50:
                bullish_score += 3
            elif price < snap.ema_20 < snap.ema_50:
                bearish_score += 3
            elif price >= snap.ema_50:
                bullish_score += 1
            else:
                bearish_score += 1

        if snap.ema_200:
            if price >= snap.ema_200:
                bullish_score += 2
            else:
                bearish_score += 2

        # 2. Macro Momentum & ADX Trend Strength
        if snap.rsi is not None:
            if 50.0 <= snap.rsi <= 75.0:
                bullish_score += 1
            elif snap.rsi < 45.0:
                bearish_score += 1

        if snap.adx is not None and snap.adx >= 20.0 and snap.di_plus and snap.di_minus and snap.di_plus > snap.di_minus:
            bullish_score += 1

        if bullish_score >= bearish_score + 2:
            return "BULLISH"
        elif bearish_score >= bullish_score + 2:
            return "BEARISH"
        return "NEUTRAL"

    def evaluate_1h_setup(self, snap: IndicatorSnapshot) -> str:
        """Evaluates 1H Setup Geometry, Consolidation & Dynamic Support."""
        if not snap or snap.last_price <= 0:
            return "NEUTRAL"

        price = snap.last_price
        ema_20 = snap.ema_20 or price
        bb_width = snap.bb_bandwidth or 10.0

        # Constructive support bounce near 1H 20 EMA (within 2.5%) or tight consolidation (BB <= 10%)
        is_near_support = abs(price - ema_20) / price <= 0.025
        is_compressed = bb_width <= 10.0 or snap.is_nr7
        is_uptrend = snap.is_ema_aligned_bullish or (snap.ema_50 is not None and ema_20 >= snap.ema_50)

        # Rejection of deep breakdown
        if snap.ema_50 and price < (snap.ema_50 * 0.98):
            return "BEARISH"

        if is_uptrend and (is_near_support or is_compressed or snap.is_above_vwap):
            if snap.rsi is not None and snap.rsi >= 48.0:
                return "BULLISH"

        if snap.macd_hist is not None and snap.macd_hist > 0:
            return "BULLISH"

        return "NEUTRAL"

    def evaluate_15m_trigger(self, snap: IndicatorSnapshot) -> str:
        """Evaluates 15M Execution Timing, VWAP Support & Rejection of Overextended Entries."""
        if not snap or snap.last_price <= 0:
            return "NEUTRAL"

        price = snap.last_price
        vwap = snap.vwap
        rsi = snap.rsi or 50.0

        # 1. Overextension / Exhaustion Rejection (RSI > 76 or red rejection candle)
        if rsi > 76.0:
            return "BEARISH"  # Chasing overbought exhaustion

        if snap.open and price < snap.open and snap.resistance_20 and price < (snap.resistance_20 * 0.995):
            return "BEARISH"  # Intraday rejection wick at resistance

        # 2. Trigger Confirmation: Price holding firmly above VWAP + Green trigger candle
        is_above_vwap = (vwap is None or price >= vwap)
        is_green_bar = snap.open is None or price >= snap.open
        has_volume = snap.volume_surge_ratio >= 1.15

        if is_above_vwap and (is_green_bar or has_volume) and (48.0 <= rsi <= 74.0):
            return "BULLISH"

        if not is_above_vwap and price < (vwap * 0.995):
            return "BEARISH"

        return "NEUTRAL"

    def analyze_confluence(
        self,
        symbol: str,
        candles_1d: list[OHLCVCandle],
        candles_1h: list[OHLCVCandle],
        candles_15m: list[OHLCVCandle],
    ) -> MTFAnalysis:
        """Computes specialized multi-timeframe confluence and score."""
        snap_1d = self.indicator_engine.compute_snapshot(symbol, candles_1d, "1d")
        snap_1h = self.indicator_engine.compute_snapshot(symbol, candles_1h, "1h")
        snap_15m = self.indicator_engine.compute_snapshot(symbol, candles_15m, "15m")

        trend_1d = self.evaluate_1d_structure(snap_1d)
        trend_1h = self.evaluate_1h_setup(snap_1h)
        trend_15m = self.evaluate_15m_trigger(snap_15m)

        score = 0.0
        details_list = []

        # 1D Trend Confirmation (Weight: 6 pts)
        if trend_1d == "BULLISH":
            score += 6.0
            details_list.append("1D Structure: Stage-2 Bullish")
        elif trend_1d == "NEUTRAL":
            score += 3.0
            details_list.append("1D Structure: Neutral")
        else:
            details_list.append("1D Structure: Bearish")

        # 1H Setup Confirmation (Weight: 5 pts)
        if trend_1h == "BULLISH":
            score += 5.0
            details_list.append("1H Setup: Consolidated/Support")
        elif trend_1h == "NEUTRAL":
            score += 2.5
            details_list.append("1H Setup: Neutral")
        else:
            details_list.append("1H Setup: Breakdown")

        # 15M Trigger Confirmation (Weight: 4 pts)
        if trend_15m == "BULLISH":
            score += 4.0
            details_list.append("15M Trigger: Confirmed above VWAP")
        elif trend_15m == "NEUTRAL":
            score += 1.5
            details_list.append("15M Trigger: Consolidating")
        else:
            details_list.append("15M Trigger: Exhaustion/Overextended")

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

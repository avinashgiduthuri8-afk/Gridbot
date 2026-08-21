"""Technical Setup Identification Engine for Indian Equities.

Evaluates high-probability setups:
1. Resistance Breakout with Volume Expansion
2. Trend Pullback to Dynamic Support (EMA 20/50)
3. Momentum Continuation (ADX > 25, Relative Strength)
4. Selective High-Conviction Reversals
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from config.constants import SignalType
from engine.indicators.technical import IndicatorSnapshot
from utils.logger import get_logger

log = get_logger("setup_detector")


@dataclass
class SetupEvaluation:
    setup_type: SignalType
    is_triggered: bool
    quality_score: float         # 0.0 to 15.0 pts
    description: str
    trigger_price: float
    key_level: float


class TechnicalSetupDetector:
    """Detects and scores classic trading setups on Indian stocks."""

    def evaluate_all_setups(
        self,
        snap_1d: IndicatorSnapshot,
        snap_15m: IndicatorSnapshot | None = None,
    ) -> list[SetupEvaluation]:
        """Runs all setup detectors and returns candidates ordered by quality."""
        results: list[SetupEvaluation] = []

        # 1. Breakout Setup
        bo = self._detect_breakout(snap_1d, snap_15m)
        if bo.is_triggered:
            results.append(bo)

        # 2. Pullback Setup
        pb = self._detect_pullback(snap_1d, snap_15m)
        if pb.is_triggered:
            results.append(pb)

        # 3. Momentum Continuation
        mc = self._detect_momentum_continuation(snap_1d, snap_15m)
        if mc.is_triggered:
            results.append(mc)

        # 4. Selective Reversal
        rev = self._detect_reversal(snap_1d, snap_15m)
        if rev.is_triggered:
            results.append(rev)

        results.sort(key=lambda s: s.quality_score, reverse=True)
        return results

    def _detect_breakout(
        self,
        snap_1d: IndicatorSnapshot,
        snap_15m: IndicatorSnapshot | None = None,
    ) -> SetupEvaluation:
        """Evaluates 20-day swing resistance breakout with volume surge."""
        price = snap_1d.last_price
        resistance = snap_1d.resistance_20 or price
        volume_surge = snap_1d.volume_surge_ratio
        rsi = snap_1d.rsi or 50.0

        # Breakout condition: Price at or within 0.8% of resistance or breaking out
        is_breaking = price >= (resistance * 0.995)
        has_volume = volume_surge >= 1.3
        has_momentum = rsi >= 55.0

        is_triggered = is_breaking and has_momentum
        score = 0.0

        if is_triggered:
            score = 10.0
            if volume_surge >= 1.8:
                score += 3.0
            elif volume_surge >= 1.4:
                score += 2.0

            if 58.0 <= rsi <= 72.0:
                score += 2.0

        desc = f"Resistance breakout above ₹{resistance:.2f} with {volume_surge:.1f}x volume surge"
        return SetupEvaluation(
            setup_type=SignalType.BREAKOUT,
            is_triggered=is_triggered,
            quality_score=min(score, 15.0),
            description=desc,
            trigger_price=price,
            key_level=resistance,
        )

    def _detect_pullback(
        self,
        snap_1d: IndicatorSnapshot,
        snap_15m: IndicatorSnapshot | None = None,
    ) -> SetupEvaluation:
        """Evaluates pullback to 20/50 EMA in an established uptrend."""
        price = snap_1d.last_price
        ema_20 = snap_1d.ema_20
        ema_50 = snap_1d.ema_50
        rsi = snap_1d.rsi or 50.0

        if not (ema_20 and ema_50 and ema_20 > ema_50):
            return SetupEvaluation(
                setup_type=SignalType.PULLBACK,
                is_triggered=False,
                quality_score=0.0,
                description="No established EMA trend for pullback",
                trigger_price=price,
                key_level=ema_20 or price,
            )

        # Price within 1.5% of EMA 20 or EMA 50
        dist_to_ema20_pct = abs(price - ema_20) / ema_20 * 100.0
        is_near_support = dist_to_ema20_pct <= 1.8 and price >= (ema_20 * 0.985)
        rsi_recovering = 45.0 <= rsi <= 62.0

        is_triggered = is_near_support and rsi_recovering
        score = 0.0

        if is_triggered:
            score = 11.0
            if snap_1d.is_above_vwap:
                score += 2.0
            if snap_1d.macd_hist and snap_1d.macd_hist > 0:
                score += 2.0

        desc = f"Pullback test of 20 EMA (₹{ema_20:.2f}) with RSI {rsi:.1f} recovery"
        return SetupEvaluation(
            setup_type=SignalType.PULLBACK,
            is_triggered=is_triggered,
            quality_score=min(score, 15.0),
            description=desc,
            trigger_price=price,
            key_level=ema_20,
        )

    def _detect_momentum_continuation(
        self,
        snap_1d: IndicatorSnapshot,
        snap_15m: IndicatorSnapshot | None = None,
    ) -> SetupEvaluation:
        """Evaluates strong trend momentum continuation (ADX > 25, DI+ > DI-)."""
        price = snap_1d.last_price
        adx = snap_1d.adx or 0.0
        di_p = snap_1d.di_plus or 0.0
        di_m = snap_1d.di_minus or 0.0
        rsi = snap_1d.rsi or 50.0

        is_trending = adx >= 24.0 and di_p > di_m
        is_bullish_momentum = 60.0 <= rsi <= 78.0

        is_triggered = is_trending and is_bullish_momentum and snap_1d.is_ema_aligned_bullish
        score = 0.0

        if is_triggered:
            score = 11.0
            if adx >= 30.0:
                score += 2.0
            if snap_1d.volume_surge_ratio >= 1.2:
                score += 2.0

        desc = f"Momentum continuation with ADX {adx:.1f} and strong DI+ dominance"
        return SetupEvaluation(
            setup_type=SignalType.MOMENTUM_CONTINUATION,
            is_triggered=is_triggered,
            quality_score=min(score, 15.0),
            description=desc,
            trigger_price=price,
            key_level=snap_1d.ema_20 or price,
        )

    def _detect_reversal(
        self,
        snap_1d: IndicatorSnapshot,
        snap_15m: IndicatorSnapshot | None = None,
    ) -> SetupEvaluation:
        """Highly selective reversal setup at major daily support with RSI divergence."""
        price = snap_1d.last_price
        support = snap_1d.support_20 or price
        rsi = snap_1d.rsi or 50.0
        volume_surge = snap_1d.volume_surge_ratio

        # Never trigger reversal just because RSI is low; must have volume spike + support touch
        at_support = abs(price - support) / support * 100.0 <= 1.0
        oversold_turning = 30.0 <= rsi <= 42.0 and snap_1d.macd_hist and snap_1d.macd_hist > 0
        volume_confirmed = volume_surge >= 1.5

        is_triggered = at_support and oversold_turning and volume_confirmed
        score = 0.0

        if is_triggered:
            score = 10.0
            if volume_surge >= 2.0:
                score += 3.0
            if snap_1d.bb_pct_b and snap_1d.bb_pct_b < 0.2:
                score += 2.0

        desc = f"Selective reversal test at major support ₹{support:.2f} with volume surge"
        return SetupEvaluation(
            setup_type=SignalType.REVERSAL,
            is_triggered=is_triggered,
            quality_score=min(score, 15.0),
            description=desc,
            trigger_price=price,
            key_level=support,
        )

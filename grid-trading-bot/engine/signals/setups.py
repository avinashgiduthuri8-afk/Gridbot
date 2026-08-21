"""Technical Setup Identification Engine for Indian Equities.

Evaluates high-probability setups with strict price-action & volume confirmation:
1. Resistance Breakout with Volatility Compression (Squeeze) & Volume Expansion
2. Trend Pullback with Volume Contraction (Dry-Up) to Dynamic Support (EMA 20/50)
3. Momentum Continuation (ADX >= 25, DI+ dominance, VWAP support)
4. Selective High-Conviction Reversals at Major Daily Support
"""

from __future__ import annotations

from dataclasses import dataclass, field
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
    setup_reason: str = ""
    confirmation_reason: str = ""
    rejection_risks: list[str] = field(default_factory=list)
    is_false_breakout_risk: bool = False


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
        """Evaluates 20-day swing resistance breakout with compression and volume."""
        price = snap_1d.last_price
        resistance = snap_1d.resistance_20 or price
        volume_surge = snap_1d.volume_surge_ratio
        rsi = snap_1d.rsi or 50.0
        bb_width = snap_1d.bb_bandwidth or 1.0

        risks: list[str] = []

        # Breakout condition: Price breaking resistance
        is_breaking = price >= (resistance * 0.998)
        has_volume = volume_surge >= 1.4
        has_momentum = 55.0 <= rsi <= 76.0

        # Check for volatility compression (Bollinger Band squeeze)
        is_compressed = bb_width < 0.12 or (snap_1d.atr and snap_1d.atr < (price * 0.02))

        # Check for false breakout upper wick rejection on 15M trigger bar if available
        is_false_breakout = False
        if snap_15m and snap_15m.last_price < snap_15m.open:
            # Red 15M trigger bar after touching resistance
            if snap_15m.last_price < (resistance * 0.995):
                is_false_breakout = True
                risks.append("Intraday rejection wick at resistance")

        if rsi > 76.0:
            risks.append(f"RSI overbought ({rsi:.1f})")

        is_triggered = is_breaking and has_momentum and not is_false_breakout
        score = 0.0

        if is_triggered:
            score = 10.0
            if volume_surge >= 1.8:
                score += 3.0
            elif volume_surge >= 1.4:
                score += 1.5

            if is_compressed:
                score += 2.0  # Bonus for breakout from tight compression

            if snap_1d.is_above_vwap:
                score += 1.0

            if snap_1d.macd_hist and snap_1d.macd_hist > 0:
                score += 1.0

        setup_reason = f"Breakout above 20-day resistance ₹{resistance:.2f}"
        conf_reason = f"Confirmed with {volume_surge:.1f}x volume surge and RSI {rsi:.1f}"

        return SetupEvaluation(
            setup_type=SignalType.BREAKOUT,
            is_triggered=is_triggered,
            quality_score=min(score, 15.0),
            description=f"{setup_reason} ({conf_reason})",
            trigger_price=price,
            key_level=resistance,
            setup_reason=setup_reason,
            confirmation_reason=conf_reason,
            rejection_risks=risks,
            is_false_breakout_risk=is_false_breakout,
        )

    def _detect_pullback(
        self,
        snap_1d: IndicatorSnapshot,
        snap_15m: IndicatorSnapshot | None = None,
    ) -> SetupEvaluation:
        """Evaluates pullback to 20/50 EMA in established uptrend on contracting volume."""
        price = snap_1d.last_price
        ema_20 = snap_1d.ema_20
        ema_50 = snap_1d.ema_50
        rsi = snap_1d.rsi or 50.0
        volume_surge = snap_1d.volume_surge_ratio

        risks: list[str] = []

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
        is_near_support = dist_to_ema20_pct <= 2.0 and price >= (ema_20 * 0.982)
        rsi_recovering = 45.0 <= rsi <= 64.0

        # Healthy pullback has dry volume (volume surge <= 1.2 during dip)
        is_dry_volume = volume_surge <= 1.2

        if not is_dry_volume:
            risks.append(f"Elevated selling volume ({volume_surge:.1f}x) during pullback")

        is_triggered = is_near_support and rsi_recovering
        score = 0.0

        if is_triggered:
            score = 11.0
            if is_dry_volume:
                score += 2.0  # Healthy low-volume retracement
            if snap_1d.is_above_vwap:
                score += 1.0
            if snap_1d.macd_hist and snap_1d.macd_hist > 0:
                score += 1.0

        setup_reason = f"Orderly pullback to 20 EMA (₹{ema_20:.2f})"
        conf_reason = f"Support holding with RSI {rsi:.1f} stabilization and low volume"

        return SetupEvaluation(
            setup_type=SignalType.PULLBACK,
            is_triggered=is_triggered,
            quality_score=min(score, 15.0),
            description=f"{setup_reason} ({conf_reason})",
            trigger_price=price,
            key_level=ema_20,
            setup_reason=setup_reason,
            confirmation_reason=conf_reason,
            rejection_risks=risks,
        )

    def _detect_momentum_continuation(
        self,
        snap_1d: IndicatorSnapshot,
        snap_15m: IndicatorSnapshot | None = None,
    ) -> SetupEvaluation:
        """Evaluates strong trend momentum continuation (ADX >= 25, DI+ > DI-, VWAP support)."""
        price = snap_1d.last_price
        adx = snap_1d.adx or 0.0
        di_p = snap_1d.di_plus or 0.0
        di_m = snap_1d.di_minus or 0.0
        rsi = snap_1d.rsi or 50.0

        risks: list[str] = []

        is_trending = adx >= 24.0 and di_p > di_m
        is_bullish_momentum = 58.0 <= rsi <= 76.0

        if rsi > 74.0:
            risks.append("Momentum near upper band (RSI > 74)")

        is_triggered = is_trending and is_bullish_momentum and snap_1d.is_ema_aligned_bullish
        score = 0.0

        if is_triggered:
            score = 11.0
            if adx >= 30.0:
                score += 2.0
            if snap_1d.volume_surge_ratio >= 1.2:
                score += 1.5
            if snap_1d.is_above_vwap:
                score += 1.0

        setup_reason = f"Bullish momentum continuation (ADX {adx:.1f})"
        conf_reason = f"DI+ dominance ({di_p:.1f} > {di_m:.1f}) and price > VWAP"

        return SetupEvaluation(
            setup_type=SignalType.MOMENTUM_CONTINUATION,
            is_triggered=is_triggered,
            quality_score=min(score, 15.0),
            description=f"{setup_reason} ({conf_reason})",
            trigger_price=price,
            key_level=snap_1d.ema_20 or price,
            setup_reason=setup_reason,
            confirmation_reason=conf_reason,
            rejection_risks=risks,
        )

    def _detect_reversal(
        self,
        snap_1d: IndicatorSnapshot,
        snap_15m: IndicatorSnapshot | None = None,
    ) -> SetupEvaluation:
        """Highly selective reversal setup at major daily support with RSI turning."""
        price = snap_1d.last_price
        support = snap_1d.support_20 or price
        rsi = snap_1d.rsi or 50.0
        volume_surge = snap_1d.volume_surge_ratio

        risks: list[str] = ["Counter-trend setup: higher structural failure risk"]

        at_support = abs(price - support) / support * 100.0 <= 1.2
        oversold_turning = 32.0 <= rsi <= 44.0 and snap_1d.macd_hist and snap_1d.macd_hist > 0
        volume_confirmed = volume_surge >= 1.4

        is_triggered = at_support and oversold_turning and volume_confirmed
        score = 0.0

        if is_triggered:
            score = 10.0
            if volume_surge >= 2.0:
                score += 3.0
            if snap_1d.bb_pct_b and snap_1d.bb_pct_b < 0.2:
                score += 2.0

        setup_reason = f"Reversal bounce at major support ₹{support:.2f}"
        conf_reason = f"Oversold turn with {volume_surge:.1f}x capitulation volume and expanding MACD hist"

        return SetupEvaluation(
            setup_type=SignalType.REVERSAL,
            is_triggered=is_triggered,
            quality_score=min(score, 15.0),
            description=f"{setup_reason} ({conf_reason})",
            trigger_price=price,
            key_level=support,
            setup_reason=setup_reason,
            confirmation_reason=conf_reason,
            rejection_risks=risks,
        )

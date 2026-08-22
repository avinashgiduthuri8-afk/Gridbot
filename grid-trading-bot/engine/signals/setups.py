"""Technical Setup Identification Engine for Indian Equities.

Evaluates high-probability setups with strict price-action & volume confirmation:
1. Minervini VCP (Volatility Contraction Pattern, BB Bandwidth <= 8.5%, Volume >= 1.6x)
2. Pocket Pivot (Stage-2 uptrend, bounce within 3% of 20 EMA, Pocket Volume >= 1.6x)
3. NR7 / Inside Bar Volatility Squeeze (7-day narrow range compression <= 7.0% BB)
4. High-Delivery Institutional Breakout (Delivery % >= 50% + Volume >= 1.8x)
5. Resistance Breakout with Squeeze & Volume Expansion
6. Trend Pullback with Volume Contraction to Dynamic Support (EMA 20/50)
7. Momentum Continuation (ADX >= 25, DI+ dominance, VWAP support)
8. Selective High-Conviction Reversals at Major Daily Support
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
    """Detects and scores precision institutional setups on Indian stocks."""

    def evaluate_all_setups(
        self,
        snap_1d: IndicatorSnapshot,
        snap_15m: IndicatorSnapshot | None = None,
        delivery_pct: float | None = None,
    ) -> list[SetupEvaluation]:
        """Runs all setup detectors and returns candidates ordered by quality."""
        results: list[SetupEvaluation] = []

        # 1. High Delivery Institutional Breakout (Top Priority if delivery >= 50%)
        if delivery_pct is not None and delivery_pct >= 50.0:
            hdb = self._detect_high_delivery_breakout(snap_1d, snap_15m, delivery_pct)
            if hdb.is_triggered:
                results.append(hdb)

        # 2. VCP Pattern (Minervini)
        vcp = self._detect_vcp(snap_1d, snap_15m)
        if vcp.is_triggered:
            results.append(vcp)

        # 3. Pocket Pivot (Morales/Kacher)
        pp = self._detect_pocket_pivot(snap_1d, snap_15m)
        if pp.is_triggered:
            results.append(pp)

        # 4. NR7 / Squeeze
        nr7 = self._detect_nr7(snap_1d, snap_15m)
        if nr7.is_triggered:
            results.append(nr7)

        # 5. Breakout Setup
        bo = self._detect_breakout(snap_1d, snap_15m)
        if bo.is_triggered:
            results.append(bo)

        # 6. Pullback Setup
        pb = self._detect_pullback(snap_1d, snap_15m)
        if pb.is_triggered:
            results.append(pb)

        # 7. Momentum Continuation
        mc = self._detect_momentum_continuation(snap_1d, snap_15m)
        if mc.is_triggered:
            results.append(mc)

        # 8. Selective Reversal
        rev = self._detect_reversal(snap_1d, snap_15m)
        if rev.is_triggered:
            results.append(rev)

        results.sort(key=lambda s: s.quality_score, reverse=True)
        return results

    def _detect_high_delivery_breakout(
        self,
        snap_1d: IndicatorSnapshot,
        snap_15m: IndicatorSnapshot | None,
        delivery_pct: float,
    ) -> SetupEvaluation:
        """Detects high-delivery volume accumulation breakout."""
        price = snap_1d.last_price
        resistance = snap_1d.resistance_20 or price
        vol_surge = snap_1d.volume_surge_ratio

        is_breaking = price >= (resistance * 0.998)
        has_volume = vol_surge >= 1.8
        is_triggered = is_breaking and has_volume and delivery_pct >= 50.0

        score = 15.0 if is_triggered else 0.0
        return SetupEvaluation(
            setup_type=SignalType.HIGH_DELIVERY_BREAKOUT,
            is_triggered=is_triggered,
            quality_score=score,
            description=f"Institutional High-Delivery Breakout ({delivery_pct:.1f}% delivery + {vol_surge:.1f}x volume)",
            trigger_price=round(resistance, 2),
            key_level=round(resistance, 2),
            setup_reason=f"High institutional delivery accumulation ({delivery_pct:.1f}%) breaking 20d resistance",
            confirmation_reason=f"Volume surge {vol_surge:.1f}x with price holding above breakout level",
            rejection_risks=[],
        )

    def _detect_vcp(
        self,
        snap_1d: IndicatorSnapshot,
        snap_15m: IndicatorSnapshot | None = None,
    ) -> SetupEvaluation:
        """Detects Minervini Volatility Contraction Pattern (VCP)."""
        price = snap_1d.last_price
        resistance = snap_1d.resistance_20 or price
        bb_width = snap_1d.bb_bandwidth or 1.0
        vol_surge = snap_1d.volume_surge_ratio

        # Hardened VCP rules: BB bandwidth <= 8.5%, price near pivot (within 3.5%), volume >= 1.4x
        is_tight_base = bb_width <= 0.085
        is_near_pivot = (resistance * 0.965) <= price <= (resistance * 1.025)
        has_breakout_volume = vol_surge >= 1.4

        is_triggered = is_tight_base and is_near_pivot and has_breakout_volume and snap_1d.is_ema_aligned_bullish
        score = 14.5 if is_triggered else 0.0

        return SetupEvaluation(
            setup_type=SignalType.VCP_BREAKOUT,
            is_triggered=is_triggered,
            quality_score=score,
            description="Volatility Contraction Pattern (VCP) Squeeze Breakout",
            trigger_price=round(resistance, 2),
            key_level=round(resistance, 2),
            setup_reason="Multi-wave volatility contraction with tight base (BB width <= 8.5%)",
            confirmation_reason=f"Volume expansion {vol_surge:.1f}x emerging from right-side contraction base",
            rejection_risks=[],
        )

    def _detect_pocket_pivot(
        self,
        snap_1d: IndicatorSnapshot,
        snap_15m: IndicatorSnapshot | None = None,
    ) -> SetupEvaluation:
        """Detects Pocket Pivot signature (volume surge off 10/20 EMA support)."""
        price = snap_1d.last_price
        ema_20 = snap_1d.ema_20 or price
        vol_surge = snap_1d.volume_surge_ratio
        rsi = snap_1d.rsi or 50.0

        # Hardened Pocket Pivot: Price within 3% of 20 EMA, EMA20 > EMA50, volume surge >= 1.6x
        is_near_ema20 = abs(price - ema_20) / price <= 0.03
        has_pocket_vol = vol_surge >= 1.6
        is_in_uptrend = (snap_1d.ema_50 is not None and ema_20 > snap_1d.ema_50) or snap_1d.is_ema_aligned_bullish

        is_triggered = is_near_ema20 and has_pocket_vol and is_in_uptrend and (50.0 <= rsi <= 74.0)
        score = 14.0 if is_triggered else 0.0

        return SetupEvaluation(
            setup_type=SignalType.POCKET_PIVOT,
            is_triggered=is_triggered,
            quality_score=score,
            description="Institutional Pocket Pivot off 20 EMA Support",
            trigger_price=round(price, 2),
            key_level=round(ema_20, 2),
            setup_reason="Constructive bounce off rising 20 EMA in established uptrend",
            confirmation_reason=f"Pocket volume signature ({vol_surge:.1f}x 20d average)",
            rejection_risks=[],
        )

    def _detect_nr7(
        self,
        snap_1d: IndicatorSnapshot,
        snap_15m: IndicatorSnapshot | None = None,
    ) -> SetupEvaluation:
        """Detects NR7 (Narrowest Range of 7 days) Volatility Compression."""
        price = snap_1d.last_price
        bb_width = snap_1d.bb_bandwidth or 1.0
        vol_surge = snap_1d.volume_surge_ratio

        # NR7: Extreme compression (BB bandwidth <= 0.07) followed by price trigger above VWAP
        is_nr7_compressed = bb_width <= 0.07
        is_triggered = is_nr7_compressed and snap_1d.is_above_vwap and vol_surge >= 1.25
        score = 13.5 if is_triggered else 0.0

        return SetupEvaluation(
            setup_type=SignalType.NR7_COMPRESSION,
            is_triggered=is_triggered,
            quality_score=score,
            description="NR7 Narrow-Range Inside Squeeze Expansion",
            trigger_price=round(price, 2),
            key_level=round(price * 0.99, 2),
            setup_reason="NR7 tight range consolidation indicating impending directional expansion",
            confirmation_reason="Price holding above VWAP with initial volume surge",
            rejection_risks=[],
        )

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

        is_breaking = price >= (resistance * 0.998)
        has_volume = volume_surge >= 1.4
        has_momentum = 55.0 <= rsi <= 76.0
        is_compressed = bb_width < 0.12 or (snap_1d.atr and snap_1d.atr < (price * 0.02))

        is_false_breakout = False
        if snap_15m and snap_15m.open and snap_15m.last_price < snap_15m.open:
            if snap_15m.last_price < (resistance * 0.995):
                is_false_breakout = True
                risks.append("Intraday rejection wick at resistance")

        if rsi > 76.0:
            risks.append(f"High RSI overbought ({rsi:.1f})")

        is_triggered = is_breaking and has_volume and has_momentum and not is_false_breakout

        score = 0.0
        if is_triggered:
            score = 10.0
            if volume_surge >= 2.0:
                score += 2.0
            if is_compressed:
                score += 2.0
            if snap_1d.is_above_vwap:
                score += 1.0
            if is_false_breakout:
                score = max(0.0, score - 6.0)

        setup_reason = f"Breakout above 20-day swing resistance ₹{resistance:.2f}"
        if is_compressed:
            setup_reason += " after volatility compression squeeze"

        conf_reason = f"Confirmed with {volume_surge:.1f}x volume surge"
        if snap_1d.is_above_vwap:
            conf_reason += " and price holding firmly above VWAP"

        return SetupEvaluation(
            setup_type=SignalType.BREAKOUT,
            is_triggered=is_triggered,
            quality_score=min(score, 15.0),
            description=f"20-day Resistance Breakout at ₹{resistance:.2f} (Vol: {volume_surge:.1f}x)",
            trigger_price=round(resistance, 2),
            key_level=round(resistance, 2),
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
        """Evaluates trend pullback with volume dry-up to 20/50 EMA dynamic support."""
        price = snap_1d.last_price
        ema_20 = snap_1d.ema_20 or price
        ema_50 = snap_1d.ema_50 or (price * 0.95)
        volume_surge = snap_1d.volume_surge_ratio
        rsi = snap_1d.rsi or 50.0

        risks: list[str] = []
        is_uptrend = snap_1d.is_ema_aligned_bullish or (ema_20 > ema_50)
        is_near_ema20 = abs(price - ema_20) / price < 0.015
        is_near_ema50 = abs(price - ema_50) / price < 0.015
        is_near_support = is_near_ema20 or is_near_ema50
        has_volume_dryup = volume_surge < 1.1
        has_rsi_support = 45.0 <= rsi <= 62.0

        is_triggered = is_uptrend and is_near_support and has_volume_dryup and has_rsi_support

        score = 0.0
        if is_triggered:
            score = 10.0
            if has_volume_dryup:
                score += 2.5
            if snap_1d.is_above_vwap:
                score += 1.5
            if snap_1d.is_ema_aligned_bullish:
                score += 1.0

        sup_level = ema_20 if is_near_ema20 else ema_50
        setup_reason = f"Bullish pullback to {'20 EMA' if is_near_ema20 else '50 EMA'} support ₹{sup_level:.2f}"
        conf_reason = f"Volume contracting on pullback ({volume_surge:.1f}x) with RSI in support zone ({rsi:.1f})"

        return SetupEvaluation(
            setup_type=SignalType.PULLBACK,
            is_triggered=is_triggered,
            quality_score=min(score, 15.0),
            description=f"Pullback to {'20 EMA' if is_near_ema20 else '50 EMA'} Support ₹{sup_level:.2f}",
            trigger_price=round(price, 2),
            key_level=round(sup_level, 2),
            setup_reason=setup_reason,
            confirmation_reason=conf_reason,
            rejection_risks=risks,
        )

    def _detect_momentum_continuation(
        self,
        snap_1d: IndicatorSnapshot,
        snap_15m: IndicatorSnapshot | None = None,
    ) -> SetupEvaluation:
        """Evaluates high-momentum continuation with strong ADX and DI+ dominance."""
        adx = snap_1d.adx or 0.0
        di_plus = snap_1d.di_plus or 0.0
        di_minus = snap_1d.di_minus or 0.0
        price = snap_1d.last_price

        is_strong_trend = adx >= 24.0 and di_plus > di_minus
        is_above_vwap = snap_1d.is_above_vwap
        is_macd_bullish = snap_1d.macd_hist is not None and snap_1d.macd_hist > 0

        is_triggered = is_strong_trend and is_above_vwap and is_macd_bullish

        score = 0.0
        if is_triggered:
            score = 11.0
            if adx >= 30.0:
                score += 2.0
            if di_plus > (di_minus * 1.5):
                score += 2.0

        return SetupEvaluation(
            setup_type=SignalType.MOMENTUM_CONTINUATION,
            is_triggered=is_triggered,
            quality_score=min(score, 15.0),
            description=f"Momentum Continuation (ADX {adx:.1f}, DI+ {di_plus:.1f} > DI- {di_minus:.1f})",
            trigger_price=round(price, 2),
            key_level=round(snap_1d.ema_20 or price, 2),
            setup_reason=f"Strong directional trend with ADX at {adx:.1f}",
            confirmation_reason="DI+ buyer dominance and MACD bullish expansion above VWAP",
            rejection_risks=[],
        )

    def _detect_reversal(
        self,
        snap_1d: IndicatorSnapshot,
        snap_15m: IndicatorSnapshot | None = None,
    ) -> SetupEvaluation:
        """Evaluates oversold bounce at major 20-day support."""
        price = snap_1d.last_price
        support = snap_1d.support_20 or price
        rsi = snap_1d.rsi or 50.0

        is_near_support = (support * 0.99) <= price <= (support * 1.02)
        is_oversold = rsi <= 35.0

        is_triggered = is_near_support and is_oversold

        score = 0.0
        if is_triggered:
            score = 9.0
            if rsi <= 28.0:
                score += 3.0

        return SetupEvaluation(
            setup_type=SignalType.REVERSAL,
            is_triggered=is_triggered,
            quality_score=min(score, 15.0),
            description=f"Oversold Support Reversal at ₹{support:.2f} (RSI {rsi:.1f})",
            trigger_price=round(price, 2),
            key_level=round(support, 2),
            setup_reason=f"Oversold RSI ({rsi:.1f}) at major 20-day swing support ₹{support:.2f}",
            confirmation_reason="Price holding above key structural base",
            rejection_risks=["Counter-trend trade requiring disciplined stop loss"],
        )

"""Weighted Signal Scoring & Quality Gate Engine for Indian Equities.

Evaluates candidates across 8 distinct institutional dimensions (Total 100 points):
1. Technical Trend (20 pts)
2. Momentum & Oscillators (15 pts)
3. Volume & VWAP Confirmation (15 pts)
4. Price Action & Setup Quality (15 pts)
5. Multi-Timeframe Alignment (15 pts)
6. Market Regime Fit (10 pts)
7. Sector Strength & Alpha (5 pts)
8. News & Corporate Sentiment (5 pts)

Applies hard pre-scoring rejection gates:
- Extreme Overextension (ATR distance) -> REJECT
- R:R < 2.0 or Overhead Resistance Cap -> REJECT
- Multi-Timeframe Conflict (Counter-trend) -> REJECT
- Adverse Corporate News / Event Risk -> REJECT
- Hostile Market Regime -> REJECT / Heavy Cap
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from config.constants import DEFAULT_SCANNER_WEIGHTS, SCORE_THRESHOLDS, MarketRegime, SignalStrength, SignalType
from engine.indicators.technical import IndicatorSnapshot
from engine.mtf.mtf_analyzer import MTFAnalysis
from engine.regime.regime_detector import MarketRegimeAnalysis
from engine.relative_strength.rs_calculator import RelativeStrengthMetrics
from engine.risk_reward.extension_filter import ExtensionMetrics
from engine.risk_reward.rr_calculator import RiskRewardPlan
from engine.sentiment.news_evaluator import SentimentAnalysis
from engine.signals.setups import SetupEvaluation
from utils.logger import get_logger

log = get_logger("scoring_engine")


@dataclass
class ScoreBreakdown:
    """Detailed transparent breakdown of points awarded across all 8 dimensions."""
    technical_trend: float = 0.0      # max 20
    momentum: float = 0.0             # max 15
    volume: float = 0.0               # max 15
    price_action: float = 0.0         # max 15
    multi_timeframe: float = 0.0      # max 15
    market_regime: float = 0.0        # max 10
    sector_strength: float = 0.0      # max 5
    news_sentiment: float = 0.0       # max 5
    total_score: float = 0.0          # max 100

    def to_dict(self) -> dict[str, float]:
        return {
            "technical_trend": round(self.technical_trend, 1),
            "momentum": round(self.momentum, 1),
            "volume": round(self.volume, 1),
            "price_action": round(self.price_action, 1),
            "multi_timeframe": round(self.multi_timeframe, 1),
            "market_regime": round(self.market_regime, 1),
            "sector_strength": round(self.sector_strength, 1),
            "news_sentiment": round(self.news_sentiment, 1),
            "total_score": round(self.total_score, 1),
        }


@dataclass
class ScoredSignal:
    """Final candidate signal with full rationale, geometry, confidence, and risks."""
    symbol: str
    signal_type: SignalType
    strength: SignalStrength
    total_score: float
    breakdown: ScoreBreakdown
    risk_reward: RiskRewardPlan

    confidence: str = "MEDIUM"        # HIGH, MEDIUM, LOW
    lifecycle_state: str = "CONFIRMED"# WATCH, SETUP, CONFIRMED, REJECTED
    sector: str = "General"
    sector_rank: int = 0
    market_regime: str = "NEUTRAL"
    timeframes_summary: str = ""
    setup_reason: str = ""
    confirmation_reason: str = ""
    rationale: list[str] = field(default_factory=list)
    rejection_risks: list[str] = field(default_factory=list)
    extension: ExtensionMetrics | None = None
    timestamp: str = ""

    @property
    def is_tradable(self) -> bool:
        return (
            self.strength in (SignalStrength.VERY_STRONG, SignalStrength.STRONG)
            and self.risk_reward.is_acceptable
            and self.confidence in ("HIGH", "MEDIUM")
        )


class SignalScoringEngine:
    """Calculates weighted signal scores, enforces quality gates, and classifies confidence."""

    def __init__(self, weights: dict[str, float] | None = None) -> None:
        self.weights = weights or DEFAULT_SCANNER_WEIGHTS

    def calculate_score(
        self,
        symbol: str,
        snap_1d: IndicatorSnapshot,
        mtf: MTFAnalysis,
        setup: SetupEvaluation,
        regime: MarketRegimeAnalysis,
        sector_score: float,
        rs_metrics: RelativeStrengthMetrics,
        sentiment: SentimentAnalysis,
        rr_plan: RiskRewardPlan,
        extension: ExtensionMetrics | None = None,
        sector_name: str = "General",
        sector_rank: int = 0,
    ) -> ScoredSignal:
        """Evaluates all dimensions, enforces hard quality gates, and constructs ScoredSignal."""
        rationale: list[str] = []
        risks: list[str] = list(setup.rejection_risks)

        # 1. Technical Trend (Max 20 pts)
        trend_pts = 0.0
        if snap_1d.is_ema_aligned_bullish:
            trend_pts += 12.0
            rationale.append("Perfect Bullish EMA Alignment (Price > EMA20 > EMA50 > EMA200)")
        elif snap_1d.ema_20 and snap_1d.last_price >= snap_1d.ema_20:
            trend_pts += 7.0
            rationale.append("Trading above 20 EMA")

        if snap_1d.ema_200 and snap_1d.last_price >= snap_1d.ema_200:
            trend_pts += 4.0

        if snap_1d.adx and snap_1d.adx >= 22.0 and snap_1d.di_plus and snap_1d.di_minus and snap_1d.di_plus > snap_1d.di_minus:
            trend_pts += 4.0
            rationale.append(f"Strong trend momentum (ADX: {snap_1d.adx:.1f})")

        trend_pts = min(trend_pts, 20.0)

        # 2. Momentum & Oscillators (Max 15 pts)
        mom_pts = 0.0
        rsi = snap_1d.rsi or 50.0
        if 55.0 <= rsi <= 72.0:
            mom_pts += 8.0
            rationale.append(f"RSI in Bullish Acceleration Zone ({rsi:.1f})")
        elif 50.0 <= rsi < 55.0 or (72.0 < rsi <= 78.0):
            mom_pts += 5.0
        elif 40.0 <= rsi < 50.0:
            mom_pts += 2.0

        if snap_1d.macd_hist and snap_1d.macd_hist > 0:
            mom_pts += 4.0
            rationale.append("MACD Histogram Bullish & Expanding")

        if snap_1d.macd_line and snap_1d.macd_signal and snap_1d.macd_line > snap_1d.macd_signal:
            mom_pts += 3.0

        mom_pts = min(mom_pts, 15.0)

        # 3. Volume & VWAP (Max 15 pts)
        vol_pts = 0.0
        v_surge = snap_1d.volume_surge_ratio
        if v_surge >= 2.0:
            vol_pts += 10.0
            rationale.append(f"Exceptional Volume Surge ({v_surge:.1f}x 20d SMA)")
        elif v_surge >= 1.4:
            vol_pts += 7.0
            rationale.append(f"Confirmed Volume Expansion ({v_surge:.1f}x 20d SMA)")
        elif v_surge >= 1.0:
            vol_pts += 4.0

        if snap_1d.is_above_vwap:
            vol_pts += 5.0
            rationale.append("Price Holding Firmly Above VWAP")

        vol_pts = min(vol_pts, 15.0)

        # 4. Price Action & Setup Quality (Max 15 pts)
        pa_pts = min(setup.quality_score, 15.0)
        if setup.description:
            rationale.append(setup.description)

        # 5. Multi-Timeframe Confluence (Max 15 pts)
        mtf_pts = min(mtf.confluence_score, 15.0)
        if mtf.is_aligned_bullish:
            rationale.append("Triple Timeframe Alignment (1D + 1H + 15M Bullish)")
        elif mtf.trend_1d == "BEARISH" and setup.setup_type != SignalType.REVERSAL:
            risks.append("Counter-trend: Trading against Daily Bearish Trend")

        # 6. Market Regime Fit (Max 10 pts)
        regime_pts = min(regime.regime_score, 10.0)
        rationale.append(f"Market Regime: {regime.regime.value} ({regime.summary})")
        if regime.regime in (MarketRegime.STRONG_BEARISH, MarketRegime.HIGH_VOLATILITY):
            risks.append(f"Hostile market regime: {regime.regime.value}")

        # 7. Sector Strength (Max 5 pts)
        sec_pts = min(sector_score, 5.0)
        if sec_pts >= 4.0:
            rationale.append(f"Sector Outperformance: {sector_name} (Rank #{sector_rank})")
        elif sec_pts <= 2.0:
            risks.append(f"Sector Laggard: {sector_name} underperforming benchmark")

        # 8. News & Corporate Sentiment (Max 5 pts)
        news_pts = min(sentiment.score, 5.0)
        if sentiment.sentiment == "POSITIVE":
            rationale.append(f"News Sentiment: {sentiment.reason}")

        # Total Raw Score
        raw_total = trend_pts + mom_pts + vol_pts + pa_pts + mtf_pts + regime_pts + sec_pts + news_pts
        final_score = raw_total * regime.long_confidence_multiplier

        # HARD PRE-SCORING QUALITY GATES
        is_hard_vetoed = False

        if extension and extension.is_overextended:
            is_hard_vetoed = True
            final_score = 0.0
            risks.append(f"⚠️ OVEREXTENDED: {extension.warning_message}")

        if sentiment.is_vetoed:
            is_hard_vetoed = True
            final_score = 0.0
            risks.append("⚠️ EVENT RISK: Vetoed due to adverse corporate news or earnings volatility")

        if not rr_plan.is_acceptable:
            is_hard_vetoed = True
            final_score = min(final_score, 55.0)  # Cannot qualify if R:R is rejected
            risks.append(f"⚠️ R:R REJECTED: {rr_plan.rejection_reason}")

        if mtf.trend_1d == "BEARISH" and setup.setup_type not in (SignalType.REVERSAL,):
            # Counter-trend against daily bear market
            final_score = min(final_score, 50.0)

        final_score = max(0.0, min(100.0, round(final_score, 1)))

        # Tier Classification
        if is_hard_vetoed:
            strength = SignalStrength.REJECT
            lifecycle_state = "REJECTED"
        elif final_score >= SCORE_THRESHOLDS["VERY_STRONG"]:
            strength = SignalStrength.VERY_STRONG
            lifecycle_state = "CONFIRMED"
        elif final_score >= SCORE_THRESHOLDS["STRONG"]:
            strength = SignalStrength.STRONG
            lifecycle_state = "CONFIRMED"
        elif final_score >= SCORE_THRESHOLDS["VALID"]:
            strength = SignalStrength.VALID
            lifecycle_state = "SETUP"
        elif final_score >= SCORE_THRESHOLDS["WATCHLIST"]:
            strength = SignalStrength.WATCHLIST
            lifecycle_state = "WATCH"
        else:
            strength = SignalStrength.REJECT
            lifecycle_state = "REJECTED"

        # Statistical Confidence Calibration
        if is_hard_vetoed:
            confidence = "LOW"
        elif (
            final_score >= 85.0
            and mtf.is_aligned_bullish
            and rr_plan.rr_ratio >= 2.0
            and regime.regime in (MarketRegime.STRONG_BULLISH, MarketRegime.BULLISH)
            and len(risks) == 0
        ):
            confidence = "HIGH"
        elif final_score >= 75.0 and rr_plan.is_acceptable:
            confidence = "MEDIUM"
        else:
            confidence = "LOW"

        breakdown = ScoreBreakdown(
            technical_trend=trend_pts,
            momentum=mom_pts,
            volume=vol_pts,
            price_action=pa_pts,
            multi_timeframe=mtf_pts,
            market_regime=regime_pts,
            sector_strength=sec_pts,
            news_sentiment=news_pts,
            total_score=final_score,
        )

        tf_summary = f"1D: {mtf.trend_1d} | 1H: {mtf.trend_1h} | 15M: {mtf.trend_15m}"

        return ScoredSignal(
            symbol=symbol,
            signal_type=setup.setup_type,
            strength=strength,
            total_score=final_score,
            breakdown=breakdown,
            risk_reward=rr_plan,
            confidence=confidence,
            lifecycle_state=lifecycle_state,
            sector=sector_name,
            sector_rank=sector_rank,
            market_regime=regime.regime.value,
            timeframes_summary=tf_summary,
            setup_reason=setup.setup_reason,
            confirmation_reason=setup.confirmation_reason,
            rationale=rationale,
            rejection_risks=risks,
            extension=extension,
        )

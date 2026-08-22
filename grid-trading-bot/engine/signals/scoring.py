"""Institutional Signal Scoring & Expectancy Engine for Indian Equities.

Evaluates 8 weighted dimensions, enforces binary hard quality gates,
calculates the Institutional Expectancy Index (IEI), and calibrates statistical confidence.
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
    iei_score: float = 0.0            # Institutional Expectancy Index
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
        delivery_pct: float | None = None,
        stock_info: Any | None = None,
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
            mom_pts += 7.0
            rationale.append(f"Optimal Bullish RSI Momentum ({rsi:.1f})")
        elif 45.0 <= rsi < 55.0:
            mom_pts += 4.0
        elif rsi > 76.0:
            mom_pts += 2.0
            risks.append(f"Elevated RSI ({rsi:.1f}) near overbought")

        if snap_1d.macd_hist and snap_1d.macd_hist > 0:
            mom_pts += 5.0
            if snap_1d.macd_line and snap_1d.macd_signal and snap_1d.macd_line > snap_1d.macd_signal:
                mom_pts += 3.0
                rationale.append("MACD Bullish Cross with expanding positive histogram")

        mom_pts = min(mom_pts, 15.0)

        # 3. Volume & Institutional Flow (Max 15 pts)
        vol_pts = 0.0
        vol_surge = snap_1d.volume_surge_ratio
        if vol_surge >= 2.0:
            vol_pts += 10.0
            rationale.append(f"Heavy Institutional Volume Surge ({vol_surge:.1f}x 20DMA)")
        elif vol_surge >= 1.4:
            vol_pts += 7.0
            rationale.append(f"Volume Surge ({vol_surge:.1f}x 20DMA)")
        elif setup.setup_type == SignalType.PULLBACK and vol_surge < 1.0:
            vol_pts += 8.0
            rationale.append(f"Constructive Volume Dry-Up on Pullback ({vol_surge:.1f}x)")

        if snap_1d.is_above_vwap:
            vol_pts += 5.0
            rationale.append("Price trading firmly above VWAP")
        else:
            risks.append("Price trading below VWAP intraday")

        vol_pts = min(vol_pts, 15.0)

        # 4. Price Action Setup Quality (Max 15 pts)
        pa_pts = min(setup.quality_score, 15.0)
        if setup.is_triggered:
            rationale.append(f"Triggered Setup: {setup.description}")

        # 5. Multi-Timeframe Confluence (Max 15 pts)
        mtf_pts = 0.0
        if mtf.is_aligned_bullish:
            mtf_pts += 15.0
            rationale.append("Full Triple-Timeframe Bullish Alignment (1D + 1H + 15M)")
        else:
            if mtf.trend_1d == "BULLISH":
                mtf_pts += 6.0
            if mtf.trend_1h == "BULLISH":
                mtf_pts += 5.0
            if mtf.trend_15m == "BULLISH":
                mtf_pts += 4.0

        mtf_pts = min(mtf_pts, 15.0)

        # 6. Market Regime Compatibility (Max 10 pts)
        regime_pts = min(getattr(regime, "regime_score", getattr(regime, "strength_score", 5.0)), 10.0)

        # 7. Sector Strength & Tailwinds (Max 5 pts)
        sec_pts = min(sector_score * 0.05, 5.0)
        if sec_pts >= 4.0:
            rationale.append(f"Sector Outperformance: {sector_name} (Rank #{sector_rank})")
        elif sec_pts <= 2.0:
            risks.append(f"Sector Laggard: {sector_name} underperforming benchmark")

        # 8. News & Corporate Sentiment (Max 5 pts)
        news_pts = min(sentiment.score, 5.0)
        if sentiment.sentiment == "POSITIVE" and sentiment.score > 0.0:
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
            final_score = min(final_score, 55.0)
            risks.append(f"⚠️ R:R REJECTED: {rr_plan.rejection_reason}")

        # Fundamental Governance & Solvency Floor
        if stock_info is not None:
            pledged = getattr(stock_info, "pledged_pct", 0.0) or 0.0
            if pledged > 40.0:
                is_hard_vetoed = True
                final_score = 0.0
                risks.append(f"⚠️ GOVERNANCE RISK: High promoter pledging ({pledged:.1f}% > 40.0%)")
            elif pledged > 20.0:
                risks.append(f"Elevated promoter pledging ({pledged:.1f}%)")

            roce = getattr(stock_info, "roce_pct", None)
            debt_eq = getattr(stock_info, "debt_to_equity", None)
            if roce is not None and roce < -5.0 and debt_eq is not None and debt_eq > 3.0:
                is_hard_vetoed = True
                final_score = 0.0
                risks.append(f"⚠️ FINANCIAL DISTRESS: Negative ROCE ({roce:.1f}%) with high Debt/Equity ({debt_eq:.1f})")

        # Enforce Multi-Pillar Minimum Floor (prevent indicator stacking)
        # Technical trend >= 8, Setup quality >= 8, Volume/RS >= 6
        if not is_hard_vetoed:
            if trend_pts < 8.0 or pa_pts < 8.0 or vol_pts < 6.0:
                final_score = min(final_score, 74.0)

        final_score = max(0.0, min(100.0, round(final_score, 1)))

        # Institutional Expectancy Index (IEI)
        # IEI = (Setup Quality * 0.40) + (Mansfield RS Alpha * 0.30) + (Sector Rank Score * 0.20) + (Delivery Score * 0.10)
        del_score = (delivery_pct / 10.0) if delivery_pct else 5.0
        rs_alpha = max(0.0, min(15.0, rs_metrics.score if hasattr(rs_metrics, "score") else 10.0))
        sec_rank_score = max(1.0, 10.0 - (sector_rank * 0.8))

        iei = (pa_pts * 0.40 * 6.66) + (rs_alpha * 0.30 * 6.66) + (sec_rank_score * 0.20 * 10.0) + (del_score * 0.10 * 10.0)
        iei_score = round(max(0.0, min(100.0, iei)), 1)

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
            iei_score=iei_score,
        )

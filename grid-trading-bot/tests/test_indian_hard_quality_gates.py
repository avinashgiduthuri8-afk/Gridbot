"""Tests for Pre-Scoring Hard Quality Gates (Overextension, R:R, MTF conflict, Adverse news)."""

from config.constants import MarketRegime, SignalStrength, SignalType
from engine.indicators.technical import IndicatorSnapshot
from engine.mtf.mtf_analyzer import MTFAnalysis
from engine.regime.regime_detector import MarketRegimeAnalysis
from engine.relative_strength.rs_calculator import RelativeStrengthMetrics
from engine.risk_reward.extension_filter import ExtensionMetrics
from engine.risk_reward.rr_calculator import RiskRewardPlan
from engine.sentiment.news_evaluator import SentimentAnalysis
from engine.signals.scoring import SignalScoringEngine
from engine.signals.setups import SetupEvaluation


def test_hard_gate_rejects_overextended_stock():
    engine = SignalScoringEngine()

    snap = IndicatorSnapshot(
        symbol="STOCK",
        timeframe="1d",
        last_price=1000.0,
        ema_20=980.0,
        ema_50=950.0,
        ema_200=900.0,
        vwap=990.0,
    )
    mtf = MTFAnalysis(symbol="STOCK", is_aligned_bullish=True, confluence_score=15.0)
    setup = SetupEvaluation(
        setup_type=SignalType.BREAKOUT,
        is_triggered=True,
        quality_score=15.0,
        description="Breakout",
        trigger_price=1000.0,
        key_level=950.0,
    )
    regime = MarketRegimeAnalysis(regime=MarketRegime.STRONG_BULLISH, regime_score=10.0, long_confidence_multiplier=1.0)
    rs = RelativeStrengthMetrics(symbol="STOCK", alpha_20d=5.0)
    sentiment = SentimentAnalysis(symbol="STOCK", sentiment="NEUTRAL", score=3.0)
    rr = RiskRewardPlan(
        symbol="STOCK",
        entry_price=1000.0,
        stop_loss=980.0,
        target_1=1040.0,
        target_2=1080.0,
        risk_amount=20.0,
        reward_amount=40.0,
        risk_percentage=2.0,
        reward_percentage=4.0,
        rr_ratio=2.0,
        is_acceptable=True,
    )

    # Overextended extension metric
    ext = ExtensionMetrics(
        symbol="STOCK",
        last_price=1000.0,
        dist_to_ema20_atr=3.5,
        is_overextended=True,
        warning_message="Overextended 3.5x ATR",
    )

    sig = engine.calculate_score(
        symbol="STOCK",
        snap_1d=snap,
        mtf=mtf,
        setup=setup,
        regime=regime,
        sector_score=5.0,
        rs_metrics=rs,
        sentiment=sentiment,
        rr_plan=rr,
        extension=ext,
    )

    # Must be hard rejected!
    assert sig.total_score == 0.0
    assert sig.strength == SignalStrength.REJECT
    assert sig.is_tradable is False
    assert any("OVEREXTENDED" in r for r in sig.rejection_risks)


def test_hard_gate_rejects_poor_rr():
    engine = SignalScoringEngine()

    snap = IndicatorSnapshot(
        symbol="STOCK",
        timeframe="1d",
        last_price=1000.0,
        ema_20=980.0,
        ema_50=950.0,
        ema_200=900.0,
        vwap=990.0,
    )
    mtf = MTFAnalysis(symbol="STOCK", is_aligned_bullish=True, confluence_score=15.0)
    setup = SetupEvaluation(
        setup_type=SignalType.BREAKOUT,
        is_triggered=True,
        quality_score=15.0,
        description="Breakout",
        trigger_price=1000.0,
        key_level=950.0,
    )
    regime = MarketRegimeAnalysis(regime=MarketRegime.STRONG_BULLISH, regime_score=10.0, long_confidence_multiplier=1.0)
    rs = RelativeStrengthMetrics(symbol="STOCK", alpha_20d=5.0)
    sentiment = SentimentAnalysis(symbol="STOCK", sentiment="NEUTRAL", score=3.0)

    # Unacceptable R:R (1.4x)
    rr = RiskRewardPlan(
        symbol="STOCK",
        entry_price=1000.0,
        stop_loss=980.0,
        target_1=1028.0,
        target_2=1050.0,
        risk_amount=20.0,
        reward_amount=28.0,
        risk_percentage=2.0,
        reward_percentage=2.8,
        rr_ratio=1.4,
        is_acceptable=False,
        rejection_reason="R:R 1.4 < 2.0",
    )

    sig = engine.calculate_score(
        symbol="STOCK",
        snap_1d=snap,
        mtf=mtf,
        setup=setup,
        regime=regime,
        sector_score=5.0,
        rs_metrics=rs,
        sentiment=sentiment,
        rr_plan=rr,
    )

    # Must not be tradable and capped < 60
    assert sig.total_score <= 55.0
    assert sig.is_tradable is False
    assert sig.strength == SignalStrength.REJECT

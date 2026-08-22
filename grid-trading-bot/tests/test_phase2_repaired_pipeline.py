"""Comprehensive End-to-End Verification Tests for Repaired Phase 2 Signal Quality Engine."""

import pytest
from config.constants import MarketRegime, SignalStrength, SignalType
from engine.data.base import OHLCVCandle
from engine.data.stock_info_provider import StockInfo
from engine.indicators.technical import TechnicalIndicatorEngine
from engine.mtf.mtf_analyzer import MultiTimeframeAnalyzer
from engine.regime.regime_detector import MarketRegimeAnalysis
from engine.relative_strength.rs_calculator import RelativeStrengthCalculator
from engine.risk_reward.extension_filter import ExtensionFilter
from engine.risk_reward.nse_safety_filter import NSESafetyFilter
from engine.risk_reward.rr_calculator import RiskRewardCalculator
from engine.sentiment.news_evaluator import NewsSentimentEvaluator
from engine.signals.scoring import SignalScoringEngine
from engine.signals.setups import TechnicalSetupDetector


def create_bullish_candles(count: int = 250, base_price: float = 1000.0) -> list[OHLCVCandle]:
    """Generates 250 realistic daily candles in a steady Stage-2 uptrend."""
    candles = []
    for i in range(count):
        price = base_price + (i * 1.5)
        # Tight consolidation at the end (VCP right side)
        if i >= count - 10:
            high = price + 2.0
            low = price - 2.0
            close = price + 0.5
            vol = 250000 if i == count - 1 else 100000
        else:
            high = price + 8.0
            low = price - 6.0
            close = price
            vol = 120000

        candles.append(
            OHLCVCandle(
                timestamp=f"2024-01-{(i%28)+1:02d}T09:15:00Z",
                open=close - 1.0,
                high=high,
                low=low,
                close=close,
                volume=vol,
            )
        )
    return candles


def test_stage3_200_ema_presence():
    engine = TechnicalIndicatorEngine()
    
    # 100 bars lookback produces None for ema_200
    candles_100 = create_bullish_candles(count=100)
    snap_100 = engine.compute_snapshot("INFY", candles_100, "1d")
    assert snap_100.ema_200 is None

    # 250 bars lookback produces genuine populated ema_200
    candles_250 = create_bullish_candles(count=250)
    snap_250 = engine.compute_snapshot("INFY", candles_250, "1d")
    assert snap_250.ema_200 is not None
    assert snap_250.ema_200 > 0
    assert snap_250.is_ema_aligned_bullish is True


def test_stage6_empty_news_flow_zero_score():
    evaluator = NewsSentimentEvaluator()
    analysis = evaluator.evaluate_news("TCS", [])
    assert analysis.score == 0.0
    assert analysis.sentiment == "NEUTRAL"


def test_stage9_fundamental_pledge_hard_gate_rejection():
    filter_engine = NSESafetyFilter()
    distressed_info = StockInfo(
        symbol="GTLINFRA.NS",
        company_name="GTL Infrastructure",
        pledged_pct=58.5,  # > 40.0% safety floor
    )

    hard_gate = filter_engine.validate_binary_hard_gates(
        symbol="GTLINFRA.NS",
        current_price=15.0,
        stock_info=distressed_info,
    )
    assert hard_gate.passed is False
    assert hard_gate.rejection_category == "FUNDAMENTALS"
    assert "promoter pledged" in hard_gate.rejection_reason.lower()


def test_repaired_vcp_end_to_end_scoring_attribution():
    candles = create_bullish_candles(count=250, base_price=1000.0)
    indicator_engine = TechnicalIndicatorEngine()
    mtf_analyzer = MultiTimeframeAnalyzer(indicator_engine)
    setup_detector = TechnicalSetupDetector()
    rs_calculator = RelativeStrengthCalculator()
    sentiment_evaluator = NewsSentimentEvaluator()
    extension_filter = ExtensionFilter()
    rr_calculator = RiskRewardCalculator(min_rr=2.0)
    scoring_engine = SignalScoringEngine()

    snap_1d = indicator_engine.compute_snapshot("TRENT", candles, "1d")
    # Verify BB bandwidth percentage scale
    assert snap_1d.bb_bandwidth is not None
    assert snap_1d.bb_bandwidth <= 8.5

    # Confluence
    mtf = mtf_analyzer.analyze_confluence("TRENT", candles, candles[-60:], candles[-50:])
    assert mtf.trend_1d == "BULLISH"

    # Setup identification with authentic delivery (62%)
    setups = setup_detector.evaluate_all_setups(snap_1d, delivery_pct=62.0)
    assert len(setups) > 0
    best_setup = setups[0]

    # R:R geometry with resistance providing > 2.0R headroom
    snap_1d.resistance_20 = snap_1d.last_price + (snap_1d.atr * 2.8 if snap_1d.atr else 60.0)
    rr_plan = rr_calculator.calculate_plan("TRENT", snap_1d.last_price, snap_1d, setup_type=best_setup.setup_type.value)
    assert rr_plan.is_acceptable is True
    assert rr_plan.rr_ratio >= 2.0

    # Bullish regime
    regime = MarketRegimeAnalysis(
        regime=MarketRegime.STRONG_BULLISH,
        regime_score=9.0,
        nifty_trend="BULLISH",
        bank_trend="BULLISH",
        vix_status="LOW",
        vix_value=13.2,
        long_confidence_multiplier=1.1,
    )

    rs_metrics = rs_calculator.calculate_alpha(candles, candles, "TRENT")
    sentiment = sentiment_evaluator.evaluate_news("TRENT", [])

    stock_info = StockInfo(
        symbol="TRENT.NS",
        company_name="Trent Ltd",
        delivery_pct=62.0,
        pledged_pct=0.0,
        roce_pct=24.5,
        debt_to_equity=0.4,
    )

    scored = scoring_engine.calculate_score(
        symbol="TRENT",
        snap_1d=snap_1d,
        mtf=mtf,
        setup=best_setup,
        regime=regime,
        sector_score=5.0,
        rs_metrics=rs_metrics,
        sentiment=sentiment,
        rr_plan=rr_plan,
        sector_name="Retail",
        sector_rank=1,
        delivery_pct=62.0,
        stock_info=stock_info,
    )

    assert scored.total_score >= 80.0
    assert scored.iei_score >= 80.0
    assert scored.strength in (SignalStrength.STRONG, SignalStrength.VERY_STRONG)
    assert not scored.rejection_risks or not any("VETOED" in r for r in scored.rejection_risks)

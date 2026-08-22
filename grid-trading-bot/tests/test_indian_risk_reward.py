"""Tests for Risk/Reward Geometry and Minimum R:R Gating."""

from engine.indicators.technical import IndicatorSnapshot
from engine.risk_reward.rr_calculator import RiskRewardCalculator


def test_risk_reward_acceptable_plan():
    calc = RiskRewardCalculator(min_rr=2.0)
    snap_1d = IndicatorSnapshot(
        symbol="RELIANCE",
        timeframe="1d",
        last_price=1250.0,
        atr=20.0,
        support_20=1220.0,
        resistance_20=1335.0,  # Clear structural room (85.0 reward vs 36.0 risk = 2.36R)
        ema_20=1240.0,
    )
    plan = calc.calculate_plan("RELIANCE", 1250.0, snap_1d, setup_type="BREAKOUT")

    assert plan.entry_price == 1250.0
    assert plan.stop_loss < 1250.0
    assert plan.target_1 > 1250.0
    assert plan.rr_ratio >= 2.0
    assert plan.is_acceptable is True


def test_risk_reward_rejection_low_rr():
    # If overhead resistance limits upside to 1.0R when min_rr=2.5 required -> Rejected
    calc = RiskRewardCalculator(min_rr=2.5)
    snap_1d = IndicatorSnapshot(
        symbol="TCS",
        timeframe="1d",
        last_price=3500.0,
        atr=50.0,
        support_20=3400.0,
        resistance_20=3580.0,  # Only 80 pts reward vs 100 pts risk (0.8R)
    )
    plan = calc.calculate_plan("TCS", 3500.0, snap_1d, setup_type="PULLBACK")
    assert plan.rr_ratio < 2.5
    assert plan.is_acceptable is False
    assert len(plan.rejection_reason) > 0

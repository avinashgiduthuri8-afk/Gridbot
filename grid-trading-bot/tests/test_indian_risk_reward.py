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
        resistance_20=1320.0,
        ema_20=1240.0,
    )
    plan = calc.calculate_plan("RELIANCE", 1250.0, snap_1d, setup_type="BREAKOUT")

    assert plan.entry_price == 1250.0
    assert plan.stop_loss < 1250.0
    assert plan.target_1 > 1250.0
    assert plan.rr_ratio >= 2.0
    assert plan.is_acceptable is True


def test_risk_reward_rejection_low_rr():
    # If calculator configured with min_rr=3.5, standard 2.0x target gets rejected
    calc = RiskRewardCalculator(min_rr=3.5)
    snap_1d = IndicatorSnapshot(
        symbol="TCS",
        timeframe="1d",
        last_price=3500.0,
        atr=50.0,
        support_20=3400.0,
    )
    plan = calc.calculate_plan("TCS", 3500.0, snap_1d, setup_type="PULLBACK")
    assert plan.rr_ratio < 3.5
    assert plan.is_acceptable is False
    assert "Risk/Reward" in plan.rejection_reason

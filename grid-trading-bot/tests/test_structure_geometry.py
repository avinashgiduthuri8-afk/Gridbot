"""Tests for Market-Structure Stop Loss and Target Geometry."""

from engine.indicators.technical import IndicatorSnapshot
from engine.risk_reward.rr_calculator import RiskRewardCalculator


def test_vcp_market_structure_stop_and_targets():
    calc = RiskRewardCalculator(min_rr=2.0)

    snap = IndicatorSnapshot(
        symbol="TATAMOTORS.NS",
        timeframe="1d",
        last_price=1000.0,
        support_20=970.0,
        resistance_20=1080.0,
        ema_20=980.0,
        atr=20.0,
    )

    plan = calc.calculate_plan("TATAMOTORS.NS", 1000.0, snap, setup_type="VCP_BREAKOUT")

    assert plan.is_acceptable is True
    # Stop Loss should be structural (Base low ~974.0 - 0.3*20 = ~968.0)
    assert plan.stop_loss <= 975.0
    # Target 1 should enforce at least 2.0R
    assert plan.target_1 >= 1000.0 + (plan.risk_amount * 2.0)
    assert plan.rr_ratio >= 2.0
    assert "VCP" in plan.stop_loss_basis


def test_overhead_resistance_clearance_rejection():
    calc = RiskRewardCalculator(min_rr=2.0)

    # Stock at 1000 with strong resistance at 1015, but SL at 980 (Risk = 20, Reward = 15 -> RR = 0.75)
    snap = IndicatorSnapshot(
        symbol="SBIN.NS",
        timeframe="1d",
        last_price=1000.0,
        support_20=980.0,
        resistance_20=1015.0,  # Caps upside
        atr=20.0,
    )

    plan = calc.calculate_plan("SBIN.NS", 1000.0, snap, setup_type="BREAKOUT")
    assert plan.is_acceptable is False
    assert "resistance" in plan.rejection_reason.lower()

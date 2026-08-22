"""Tests for Binary Hard Gates and Instant Disqualification."""

from engine.risk_reward.nse_safety_filter import NSESafetyFilter, NSESafetyMetrics


def test_extension_hard_gate_rejection():
    filter_engine = NSESafetyFilter(max_ema20_extension_pct=4.5)

    # 1. Normal stock: 2% above 20 EMA -> Passes
    res_pass = filter_engine.validate_binary_hard_gates(
        symbol="TCS.NS",
        current_price=3570.0,
        ema_20=3500.0,  # +2.0%
        ema_50=3400.0,
    )
    assert res_pass.passed is True

    # 2. Overextended stock: 6% above 20 EMA -> Rejected
    res_fail = filter_engine.validate_binary_hard_gates(
        symbol="RELIANCE.NS",
        current_price=3180.0,
        ema_20=3000.0,  # +6.0%
        ema_50=2900.0,
    )
    assert res_fail.passed is False
    assert res_fail.rejection_category == "EXTENSION"
    assert "Overextended" in res_fail.rejection_reason


def test_market_regime_and_vix_hard_gate():
    filter_engine = NSESafetyFilter(max_vix_threshold=22.0)

    # 1. Hostile Bear Market Regime -> Rejected for long breakouts
    res_bear = filter_engine.validate_binary_hard_gates(
        symbol="INFY.NS",
        current_price=1600.0,
        ema_20=1580.0,
        market_regime="BEARISH",
        india_vix=15.0,
    )
    assert res_bear.passed is False
    assert res_bear.rejection_category == "REGIME"

    # 2. India VIX spike > 22.0 -> Rejected
    res_vix = filter_engine.validate_binary_hard_gates(
        symbol="INFY.NS",
        current_price=1600.0,
        ema_20=1580.0,
        market_regime="BULLISH",
        india_vix=24.5,
    )
    assert res_vix.passed is False
    assert res_vix.rejection_category == "REGIME"
    assert "India VIX" in res_vix.rejection_reason


def test_liquidity_and_turnover_hard_gate():
    filter_engine = NSESafetyFilter(min_daily_turnover_cr=10.0)

    # Low turnover stock -> Rejected
    res_liq = filter_engine.validate_binary_hard_gates(
        symbol="PENNYSTOCK.NS",
        current_price=50.0,
        ema_20=49.0,
        daily_turnover_cr=4.5,  # ₹4.5 Cr < ₹10 Cr
    )
    assert res_liq.passed is False
    assert res_liq.rejection_category == "LIQUIDITY"

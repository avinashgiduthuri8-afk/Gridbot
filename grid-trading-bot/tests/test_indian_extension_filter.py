"""Tests for Price Extension & Chasing Filter."""

from engine.indicators.technical import IndicatorSnapshot
from engine.risk_reward.extension_filter import ExtensionFilter


def test_extension_filter_optimal_entry():
    filter_engine = ExtensionFilter(max_ema20_atr_dist=2.2, max_breakout_chase_pct=4.0)

    # Stock at 1010, EMA 20 at 1000, ATR is 15 -> dist is 10/15 = 0.67x ATR
    snap = IndicatorSnapshot(
        symbol="TCS",
        timeframe="1d",
        last_price=1010.0,
        ema_20=1000.0,
        ema_50=970.0,
        vwap=1005.0,
        atr=15.0,
        resistance_20=1005.0,
    )
    metrics = filter_engine.evaluate_extension("TCS", snap, pivot_level=1005.0)

    assert metrics.is_overextended is False
    assert metrics.extension_status == "OPTIMAL"
    assert metrics.entry_quality_score == 10.0
    assert metrics.dist_to_ema20_atr < 1.0


def test_extension_filter_overextended_rejection():
    filter_engine = ExtensionFilter(max_ema20_atr_dist=2.2, max_breakout_chase_pct=4.0)

    # Stock at 1100, EMA 20 at 1000, ATR is 15 -> dist is 100/15 = 6.67x ATR (massively extended!)
    snap = IndicatorSnapshot(
        symbol="EXTENDED_STOCK",
        timeframe="1d",
        last_price=1100.0,
        ema_20=1000.0,
        ema_50=950.0,
        vwap=1020.0,
        atr=15.0,
        resistance_20=1000.0,
    )
    metrics = filter_engine.evaluate_extension("EXTENDED_STOCK", snap, pivot_level=1000.0)

    assert metrics.is_overextended is True
    assert metrics.extension_status == "OVEREXTENDED"
    assert metrics.entry_quality_score <= 1.0
    assert "Overextended" in metrics.warning_message or "Chasing" in metrics.warning_message

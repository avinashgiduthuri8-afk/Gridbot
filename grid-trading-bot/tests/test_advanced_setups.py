"""Tests for Advanced Institutional Technical Setups (VCP, Pocket Pivot, NR7, High Delivery)."""

import pytest
from config.constants import SignalType
from engine.indicators.technical import IndicatorSnapshot
from engine.signals.setups import TechnicalSetupDetector


def test_vcp_breakout_detection():
    detector = TechnicalSetupDetector()

    # VCP: Tight BB bandwidth (< 0.10), price near 20d resistance, volume surge, bullish EMA alignment
    snap_1d = IndicatorSnapshot(
        symbol="TRENT",
        timeframe="1d",
        last_price=5000.0,
        open=4920.0,
        ema_20=4800.0,
        ema_50=4600.0,
        ema_200=4200.0,
        resistance_20=4980.0,
        support_20=4650.0,
        volume_surge_ratio=1.65,
        bb_bandwidth=0.08,  # Tight base
        rsi=64.0,
        vwap=4950.0,
    )

    setups = detector.evaluate_all_setups(snap_1d)
    vcp = next((s for s in setups if s.setup_type == SignalType.VCP_BREAKOUT), None)
    assert vcp is not None
    assert vcp.is_triggered
    assert vcp.quality_score >= 14.0
    assert "Volatility Contraction" in vcp.description


def test_pocket_pivot_detection():
    detector = TechnicalSetupDetector()

    # Pocket Pivot: Price near 20 EMA, EMA20 > EMA50, volume surge >= 1.6x, RSI >= 52
    snap_1d = IndicatorSnapshot(
        symbol="DIXON",
        timeframe="1d",
        last_price=12000.0,
        open=11800.0,
        ema_20=11950.0,
        ema_50=11200.0,
        volume_surge_ratio=1.9,
        rsi=58.0,
        vwap=11900.0,
    )

    setups = detector.evaluate_all_setups(snap_1d)
    pp = next((s for s in setups if s.setup_type == SignalType.POCKET_PIVOT), None)
    assert pp is not None
    assert pp.is_triggered
    assert pp.quality_score >= 13.5
    assert "Pocket Pivot" in pp.description


def test_nr7_squeeze_detection():
    detector = TechnicalSetupDetector()

    # NR7: Extreme squeeze (BB bandwidth < 0.08), above VWAP, volume surge >= 1.2
    snap_1d = IndicatorSnapshot(
        symbol="BEL",
        timeframe="1d",
        last_price=310.0,
        open=308.0,
        bb_bandwidth=0.06,  # NR7 compression
        vwap=308.5,
        volume_surge_ratio=1.35,
        rsi=56.0,
    )

    setups = detector.evaluate_all_setups(snap_1d)
    nr7 = next((s for s in setups if s.setup_type == SignalType.NR7_COMPRESSION), None)
    assert nr7 is not None
    assert nr7.is_triggered
    assert "NR7" in nr7.description


def test_high_delivery_breakout_detection():
    detector = TechnicalSetupDetector()

    snap_1d = IndicatorSnapshot(
        symbol="HAL",
        timeframe="1d",
        last_price=4500.0,
        open=4420.0,
        resistance_20=4480.0,
        volume_surge_ratio=2.2,
        vwap=4450.0,
    )

    setups = detector.evaluate_all_setups(snap_1d, delivery_pct=62.5)
    hdb = next((s for s in setups if s.setup_type == SignalType.HIGH_DELIVERY_BREAKOUT), None)
    assert hdb is not None
    assert hdb.is_triggered
    assert hdb.quality_score == 15.0
    assert "62.5% delivery" in hdb.description

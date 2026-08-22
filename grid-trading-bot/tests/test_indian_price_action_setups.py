"""Tests for Price Action Setups (Breakout with compression, Pullback volume dry-up, False Breakout rejection)."""

from config.constants import SignalType
from engine.indicators.technical import IndicatorSnapshot
from engine.signals.setups import TechnicalSetupDetector


def test_breakout_with_compression_and_volume():
    detector = TechnicalSetupDetector()

    # Price at 1005 breaking resistance 1000 with 1.8x volume and tight BB bandwidth
    snap_1d = IndicatorSnapshot(
        symbol="RELIANCE",
        timeframe="1d",
        last_price=1005.0,
        resistance_20=1000.0,
        volume_surge_ratio=1.8,
        rsi=62.0,
        bb_bandwidth=7.5,  # Tight consolidation squeeze in percentage (7.5%)
        vwap=1000.0,
    )
    setups = detector.evaluate_all_setups(snap_1d)

    assert len(setups) > 0
    bo = next((s for s in setups if s.setup_type == SignalType.BREAKOUT), None)
    assert bo is not None
    assert bo.is_triggered is True
    assert bo.quality_score >= 12.0
    assert "Breakout" in bo.setup_reason


def test_pullback_with_volume_dryup():
    detector = TechnicalSetupDetector()

    # Pullback near 20 EMA with dry volume (0.8x SMA)
    snap_1d = IndicatorSnapshot(
        symbol="HDFCBANK",
        timeframe="1d",
        last_price=1502.0,
        ema_20=1500.0,
        ema_50=1460.0,
        volume_surge_ratio=0.8,  # Contracting volume during pullback
        rsi=52.0,
        vwap=1498.0,
    )
    setups = detector.evaluate_all_setups(snap_1d)

    assert len(setups) > 0
    pb = next((s for s in setups if s.setup_type == SignalType.PULLBACK), None)
    assert pb is not None
    assert pb.is_triggered is True
    assert pb.quality_score >= 12.0
    assert "pullback" in pb.setup_reason.lower()


def test_false_breakout_rejection_wick():
    detector = TechnicalSetupDetector()

    # Daily breakout attempt at 1005 with resistance at 1000
    snap_1d = IndicatorSnapshot(
        symbol="INFY",
        timeframe="1d",
        last_price=1005.0,
        resistance_20=1000.0,
        volume_surge_ratio=1.5,
        rsi=65.0,
    )
    # 15M trigger bar is red and dropped below 995 (rejection wick!)
    snap_15m = IndicatorSnapshot(
        symbol="INFY",
        timeframe="15m",
        open=1006.0,
        last_price=992.0,
    )
    setups = detector.evaluate_all_setups(snap_1d, snap_15m)

    bo = next((s for s in setups if s.setup_type == SignalType.BREAKOUT), None)
    # False breakout with rejection wick should not trigger
    assert bo is None or bo.is_triggered is False

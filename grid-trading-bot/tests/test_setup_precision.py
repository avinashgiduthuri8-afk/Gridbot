"""Tests for Precision Setup Detectors (VCP, Pocket Pivot, NR7, High Delivery)."""

from config.constants import SignalType
from engine.indicators.technical import IndicatorSnapshot
from engine.signals.setups import TechnicalSetupDetector


def test_vcp_tightness_and_breakout_rules():
    detector = TechnicalSetupDetector()

    # Valid tight VCP with BB bandwidth 7.5% and 1.8x volume
    snap_valid = IndicatorSnapshot(
        symbol="TATAMOTORS.NS",
        timeframe="1d",
        last_price=1000.0,
        resistance_20=1005.0,
        support_20=960.0,
        ema_20=980.0,
        ema_50=940.0,
        ema_200=900.0,
        volume_surge_ratio=1.8,
        bb_bandwidth=0.075,
    )
    vcp_eval = detector._detect_vcp(snap_valid)
    assert vcp_eval.is_triggered is True
    assert vcp_eval.setup_type == SignalType.VCP_BREAKOUT
    assert vcp_eval.quality_score >= 14.0

    # Loose VCP with BB bandwidth 14% -> Fails
    snap_loose = IndicatorSnapshot(
        symbol="TATAMOTORS.NS",
        timeframe="1d",
        last_price=1000.0,
        resistance_20=1005.0,
        volume_surge_ratio=1.8,
        bb_bandwidth=0.14,
        ema_20=980.0,
        ema_50=940.0,
    )
    vcp_loose = detector._detect_vcp(snap_loose)
    assert vcp_loose.is_triggered is False


def test_pocket_pivot_bounce_rules():
    detector = TechnicalSetupDetector()

    # Valid Pocket Pivot: price within 2% of 20 EMA with 2.2x volume surge in Stage 2 uptrend
    snap_pp = IndicatorSnapshot(
        symbol="TITAN.NS",
        timeframe="1d",
        last_price=3520.0,
        ema_20=3500.0,
        ema_50=3400.0,
        ema_200=3200.0,
        rsi=62.0,
        volume_surge_ratio=2.2,
    )
    pp_eval = detector._detect_pocket_pivot(snap_pp)
    assert pp_eval.is_triggered is True
    assert pp_eval.setup_type == SignalType.POCKET_PIVOT

    # Overextended from 20 EMA (> 5%) -> Fails
    snap_ext = IndicatorSnapshot(
        symbol="TITAN.NS",
        timeframe="1d",
        last_price=3750.0,
        ema_20=3500.0,  # +7.1%
        ema_50=3400.0,
        volume_surge_ratio=2.2,
    )
    pp_ext = detector._detect_pocket_pivot(snap_ext)
    assert pp_ext.is_triggered is False


def test_high_delivery_breakout_rules():
    detector = TechnicalSetupDetector()

    snap_hdb = IndicatorSnapshot(
        symbol="RELIANCE.NS",
        timeframe="1d",
        last_price=3010.0,
        resistance_20=3000.0,
        volume_surge_ratio=2.4,
    )

    # 1. High delivery (62%) -> Triggers
    hdb_pass = detector._detect_high_delivery_breakout(snap_hdb, None, delivery_pct=62.0)
    assert hdb_pass.is_triggered is True
    assert hdb_pass.quality_score == 15.0

    # 2. Low delivery (32%) -> Fails
    hdb_fail = detector._detect_high_delivery_breakout(snap_hdb, None, delivery_pct=32.0)
    assert hdb_fail.is_triggered is False

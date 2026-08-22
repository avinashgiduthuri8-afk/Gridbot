"""Regression Tests for Bollinger Bandwidth Percentage Scale and Genuine NR7 Detection."""

from config.constants import SignalType
from engine.data.base import OHLCVCandle
from engine.indicators.technical import IndicatorSnapshot, TechnicalIndicatorEngine
from engine.signals.setups import TechnicalSetupDetector


def test_vcp_realistic_percentage_scale():
    detector = TechnicalSetupDetector()

    # Real-world VCP with 6.2% bandwidth (returned as 6.2 from TechnicalIndicatorEngine)
    snap = IndicatorSnapshot(
        symbol="TRENT",
        timeframe="1d",
        last_price=5000.0,
        resistance_20=5020.0,
        ema_20=4850.0,
        ema_50=4600.0,
        ema_200=4100.0,
        volume_surge_ratio=1.55,
        bb_bandwidth=6.2,  # 6.2% width on real percentage scale
        rsi=64.0,
    )
    res = detector._detect_vcp(snap)
    assert res.is_triggered is True
    assert res.setup_type == SignalType.VCP_BREAKOUT
    assert res.quality_score >= 14.0


def test_vcp_rejection_on_loose_base():
    detector = TechnicalSetupDetector()

    # Wide base (12.5% bandwidth) must fail VCP tight base check (limit: <= 8.5%)
    snap = IndicatorSnapshot(
        symbol="TRENT",
        timeframe="1d",
        last_price=5000.0,
        resistance_20=5020.0,
        ema_20=4850.0,
        ema_50=4600.0,
        volume_surge_ratio=1.55,
        bb_bandwidth=12.5,
        rsi=64.0,
    )
    res = detector._detect_vcp(snap)
    assert res.is_triggered is False


def test_genuine_nr7_calculation_from_candles():
    engine = TechnicalIndicatorEngine()
    detector = TechnicalSetupDetector()

    # Create 10 candles consolidating around 1000 where candle 9 (today) has the narrowest high-low range (2.0 vs 8.0 prior)
    candles = []
    for i in range(10):
        if i == 9:
            # Today: NR7 narrow range bar, close above VWAP
            high = 1002.0
            low = 1000.0  # Range = 2.0
            close = 1001.5
            vol = 160000
        else:
            high = 1004.0
            low = 996.0  # Range = 8.0
            close = 1000.0
            vol = 100000

        candles.append(
            OHLCVCandle(
                timestamp=f"2024-01-{i+1:02d}T09:15:00Z",
                open=close - 1.0,
                high=high,
                low=low,
                close=close,
                volume=vol,
            )
        )

    snap = engine.compute_snapshot("INFY", candles, "1d")
    assert snap.is_nr7 is True

    # Setup detector evaluates NR7 with price above VWAP and volume
    nr7_eval = detector._detect_nr7(snap)
    assert nr7_eval.is_triggered is True
    assert nr7_eval.setup_type == SignalType.NR7_COMPRESSION


def test_nr7_rejection_when_not_narrowest_range():
    engine = TechnicalIndicatorEngine()
    detector = TechnicalSetupDetector()

    # Create 10 candles where today has a WIDE range (25.0 vs 8.0 prior)
    candles = []
    for i in range(10):
        if i == 9:
            # Today: Wide range bar (not NR7)
            high = 1030.0
            low = 1005.0  # Range = 25.0
            close = 1025.0
            vol = 150000
        else:
            high = 1000.0 + 4.0
            low = 1000.0 - 4.0  # Range = 8.0
            close = 1000.0
            vol = 100000

        candles.append(
            OHLCVCandle(
                timestamp=f"2024-01-{i+1:02d}T09:15:00Z",
                open=close,
                high=high,
                low=low,
                close=close,
                volume=vol,
            )
        )

    snap = engine.compute_snapshot("INFY", candles, "1d")
    assert snap.is_nr7 is False

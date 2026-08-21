"""Tests for Technical Indicator Engine (EMA, RSI, MACD, ATR, ADX, VWAP, Bollinger Bands)."""

from datetime import datetime, timezone

from engine.data.base import OHLCVCandle
from engine.indicators.technical import TechnicalIndicatorEngine


def _make_candles(prices: list[float], volumes: list[float] | None = None) -> list[OHLCVCandle]:
    vols = volumes or [100000.0] * len(prices)
    candles = []
    for i, p in enumerate(prices):
        candles.append(
            OHLCVCandle(
                timestamp=datetime.now(timezone.utc),
                open=p * 0.998,
                high=p * 1.005,
                low=p * 0.995,
                close=p,
                volume=vols[i],
                timeframe="1d",
            )
        )
    return candles


def test_calculate_ema():
    prices = [100.0 + i for i in range(30)]
    ema_20 = TechnicalIndicatorEngine.calculate_ema(prices, 20)
    assert len(ema_20) == 30
    assert not math_isnan(ema_20[-1])
    assert ema_20[-1] > ema_20[20]


def test_calculate_rsi():
    # Steadily rising prices -> high RSI
    rising = [100.0 + (i * 2) for i in range(30)]
    rsi_rising = TechnicalIndicatorEngine.calculate_rsi(rising, 14)
    assert rsi_rising[-1] > 80.0

    # Steadily falling prices -> low RSI
    falling = [200.0 - (i * 2) for i in range(30)]
    rsi_falling = TechnicalIndicatorEngine.calculate_rsi(falling, 14)
    assert rsi_falling[-1] < 20.0


def test_calculate_macd():
    # Accelerating price series
    prices = [100.0 + (i ** 1.3) for i in range(40)]
    m_line, s_line, hist = TechnicalIndicatorEngine.calculate_macd(prices, 12, 26, 9)
    assert len(m_line) == 40
    assert not math_isnan(m_line[-1])
    assert not math_isnan(s_line[-1])
    assert not math_isnan(hist[-1])
    assert hist[-1] > 0  # Accelerating uptrend histogram positive


def test_calculate_atr():
    candles = _make_candles([100.0 + i for i in range(30)])
    atr = TechnicalIndicatorEngine.calculate_atr(candles, 14)
    assert len(atr) == 30
    assert not math_isnan(atr[-1])
    assert atr[-1] > 0


def test_calculate_adx():
    candles = _make_candles([100.0 + (i * 2.0) for i in range(50)])
    adx, di_p, di_m = TechnicalIndicatorEngine.calculate_adx(candles, 14)
    assert len(adx) == 50
    assert not math_isnan(adx[-1])
    assert di_p[-1] > di_m[-1]  # Strong bull trend has DI+ > DI-


def test_calculate_vwap():
    candles = _make_candles([100.0, 110.0, 120.0], volumes=[1000.0, 2000.0, 3000.0])
    vwap = TechnicalIndicatorEngine.calculate_vwap(candles)
    assert vwap is not None
    assert 100.0 < vwap < 120.0


def test_compute_snapshot_bullish_alignment():
    # Upward trending series
    prices = [1000.0 + (i * 10.0) for i in range(210)]
    candles = _make_candles(prices)
    snap = TechnicalIndicatorEngine.compute_snapshot("RELIANCE", candles, "1d")

    assert snap.symbol == "RELIANCE"
    assert snap.last_price == prices[-1]
    assert snap.is_ema_aligned_bullish is True
    assert snap.is_above_vwap is True
    assert snap.rsi is not None and snap.rsi > 60.0


def math_isnan(val: float) -> bool:
    import math
    return math.isnan(val)

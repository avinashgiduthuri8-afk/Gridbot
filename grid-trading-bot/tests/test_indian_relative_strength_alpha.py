"""Tests for Relative Strength & Mansfield Alpha Engine."""

from datetime import datetime, timezone

from engine.data.base import OHLCVCandle
from engine.relative_strength.rs_calculator import RelativeStrengthCalculator


def _make_candles(prices: list[float]) -> list[OHLCVCandle]:
    return [
        OHLCVCandle(
            timestamp=datetime.now(timezone.utc),
            open=p * 0.998,
            high=p * 1.005,
            low=p * 0.995,
            close=p,
            volume=100000.0,
            timeframe="1d",
        )
        for p in prices
    ]


def test_relative_strength_true_percentage_alpha():
    # Stock prices: starts at 100, goes to 110 (+10% gain)
    stock_prices = [100.0 + (i * 0.5) for i in range(21)]
    # NIFTY prices: starts at 24000, goes to 24480 (+2% gain)
    nifty_prices = [24000.0 + (i * 24.0) for i in range(21)]

    stock_candles = _make_candles(stock_prices)
    nifty_candles = _make_candles(nifty_prices)

    metrics = RelativeStrengthCalculator.calculate_alpha(stock_candles, nifty_candles, "RELIANCE")

    # Alpha should be around +8% (10% - 2%)
    assert metrics.alpha_20d > 7.0
    assert metrics.is_outperforming is True
    assert metrics.normalized_rs_score >= 70.0
    assert metrics.tier == "EXCEPTIONAL"
    assert metrics.rs_score == 5.0


def test_relative_strength_underperformer():
    # Stock drops -5% while NIFTY rises +2%
    stock_prices = [100.0 - (i * 0.25) for i in range(21)]
    nifty_prices = [24000.0 + (i * 24.0) for i in range(21)]

    stock_candles = _make_candles(stock_prices)
    nifty_candles = _make_candles(nifty_prices)

    metrics = RelativeStrengthCalculator.calculate_alpha(stock_candles, nifty_candles, "LAGGARD")

    assert metrics.alpha_20d < 0.0
    assert metrics.is_outperforming is False
    assert metrics.normalized_rs_score < 40.0
    assert metrics.tier in ("WEAK", "NEUTRAL")

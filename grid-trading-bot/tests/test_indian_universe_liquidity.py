"""Tests for Indian Stock Universe and Liquidity Screening."""

from config.indian_universe import get_all_sectors, get_stock_sector, get_universe_stocks
from engine.data.base import OHLCVCandle, Quote
from engine.universe.universe_filter import LiquidityFilterConfig, StockUniverseFilter
from datetime import datetime, timezone


def test_universe_stock_definitions():
    nifty50 = get_universe_stocks("NIFTY_50")
    assert len(nifty50) >= 50
    assert "RELIANCE" in nifty50
    assert "TCS" in nifty50
    assert "HDFCBANK" in nifty50

    nifty100 = get_universe_stocks("NIFTY_100")
    assert len(nifty100) >= 90
    assert "ZOMATO" in nifty100


def test_stock_sector_mapping():
    assert get_stock_sector("TCS") == "IT"
    assert get_stock_sector("HDFCBANK") == "Banking"
    assert get_stock_sector("MARUTI") == "Auto"
    assert get_stock_sector("SUNPHARMA") == "Pharma"
    assert "IT" in get_all_sectors()
    assert "Banking" in get_all_sectors()


def test_liquidity_filter_pass():
    filter_engine = StockUniverseFilter(LiquidityFilterConfig(min_price=50.0, min_avg_volume_20d=100_000.0))
    candles = [
        OHLCVCandle(
            timestamp=datetime.now(timezone.utc),
            open=1000.0,
            high=1010.0,
            low=995.0,
            close=1005.0,
            volume=500_000.0,
        )
        for _ in range(35)
    ]
    is_liquid, reason, _ = filter_engine.evaluate_liquidity("RELIANCE", candles)
    assert is_liquid is True
    assert "passed" in reason.lower()


def test_liquidity_filter_rejection_low_price():
    filter_engine = StockUniverseFilter(LiquidityFilterConfig(min_price=50.0))
    candles = [
        OHLCVCandle(
            timestamp=datetime.now(timezone.utc),
            open=20.0,
            high=21.0,
            low=19.0,
            close=20.5,
            volume=500_000.0,
        )
        for _ in range(35)
    ]
    is_liquid, reason, _ = filter_engine.evaluate_liquidity("PENNYSTOCK", candles)
    assert is_liquid is False
    assert "below minimum threshold" in reason


def test_liquidity_filter_rejection_low_volume():
    filter_engine = StockUniverseFilter(LiquidityFilterConfig(min_avg_volume_20d=200_000.0))
    candles = [
        OHLCVCandle(
            timestamp=datetime.now(timezone.utc),
            open=500.0,
            high=510.0,
            low=495.0,
            close=505.0,
            volume=10_000.0,  # Only 10k shares / day
        )
        for _ in range(35)
    ]
    is_liquid, reason, _ = filter_engine.evaluate_liquidity("ILLIQUID_STOCK", candles)
    assert is_liquid is False
    assert "volume" in reason.lower()

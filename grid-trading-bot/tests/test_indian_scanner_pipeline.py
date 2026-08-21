"""Tests for full 12-stage Indian Stock Scanner Pipeline."""

import pytest
from datetime import datetime, timezone

from config.constants import MarketRegime, SignalStrength, SignalType
from engine.data.base import OHLCVCandle
from engine.data.csv_provider import CsvReplayProvider
from engine.signals.scanner import IndianStockScanner


@pytest.mark.asyncio
async def test_scanner_full_12_stage_pipeline():
    provider = CsvReplayProvider()

    # Generate synthetic bullish candles for test symbols
    provider.load_synthetic_bullish_candles("RELIANCE", start_price=1200.0, num_bars=100, timeframe="1d")
    provider.load_synthetic_bullish_candles("RELIANCE", start_price=1240.0, num_bars=60, timeframe="1h")
    provider.load_synthetic_bullish_candles("RELIANCE", start_price=1248.0, num_bars=50, timeframe="15m")

    provider.load_synthetic_bullish_candles("TCS", start_price=3000.0, num_bars=100, timeframe="1d")
    provider.load_synthetic_bullish_candles("TCS", start_price=3100.0, num_bars=60, timeframe="1h")
    provider.load_synthetic_bullish_candles("TCS", start_price=3140.0, num_bars=50, timeframe="15m")

    scanner = IndianStockScanner(provider=provider)
    res = await scanner.scan(universe_name="NIFTY_50", max_signals=3, allow_out_of_session=True)

    assert res.total_scanned > 0
    assert res.total_passed_liquidity >= 2
    assert len(res.top_signals) <= 3

    if res.top_signals:
        top_sig = res.top_signals[0]
        assert top_sig.total_score >= 70.0
        assert top_sig.risk_reward.rr_ratio >= 2.0
        assert top_sig.breakdown.total_score == top_sig.total_score
        assert len(top_sig.rationale) > 0

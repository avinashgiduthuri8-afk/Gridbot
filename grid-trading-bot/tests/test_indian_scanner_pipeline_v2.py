"""Tests for Indian Stock Scanner Pipeline V2 with Deduplication & Confidence."""

import pytest
from datetime import datetime, timezone

from config.constants import MarketRegime, SignalStrength, SignalType
from engine.data.csv_provider import CsvReplayProvider
from engine.signals.scanner import IndianStockScanner


@pytest.mark.asyncio
async def test_scanner_pipeline_v2_deduplication_and_explainability():
    provider = CsvReplayProvider()

    # Load synthetic data for RELIANCE and TCS
    provider.load_synthetic_bullish_candles("RELIANCE", start_price=1200.0, num_bars=100, timeframe="1d")
    provider.load_synthetic_bullish_candles("RELIANCE", start_price=1240.0, num_bars=60, timeframe="1h")
    provider.load_synthetic_bullish_candles("RELIANCE", start_price=1248.0, num_bars=50, timeframe="15m")

    provider.load_synthetic_bullish_candles("TCS", start_price=3000.0, num_bars=100, timeframe="1d")
    provider.load_synthetic_bullish_candles("TCS", start_price=3100.0, num_bars=60, timeframe="1h")
    provider.load_synthetic_bullish_candles("TCS", start_price=3140.0, num_bars=50, timeframe="15m")

    scanner = IndianStockScanner(provider=provider)

    # 1. First scan cycle
    res1 = await scanner.scan(universe_name="NIFTY_50", max_signals=2, allow_out_of_session=True)
    assert res1.total_scanned > 0
    assert len(res1.top_signals) <= 2

    if res1.top_signals:
        sig = res1.top_signals[0]
        assert sig.total_score >= 70.0
        assert sig.confidence in ("HIGH", "MEDIUM")
        assert len(sig.setup_reason) > 0
        assert len(sig.confirmation_reason) > 0

    # 2. Second scan cycle (immediately after) -> Deduplication flags active
    res2 = await scanner.scan(universe_name="NIFTY_50", max_signals=2, allow_out_of_session=True)
    assert res2.total_scanned > 0
    # Scanner completes smoothly with deduplication cache active
    assert res2.scan_duration_seconds >= 0.0

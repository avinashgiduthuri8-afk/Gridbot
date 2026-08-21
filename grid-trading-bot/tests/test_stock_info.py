"""Tests for Stock Info & Fundamentals Provider, Caching, and REST Endpoints."""

import time
import pytest
from httpx import AsyncClient, ASGITransport

from dashboard.app import create_app
from engine.data.stock_info_provider import StockInfoProvider, StockInfo


@pytest.mark.asyncio
async def test_stock_info_fallback_and_data_integrity():
    provider = StockInfoProvider()

    # Test fallback creation for RELIANCE
    info = await provider.get_stock_info("RELIANCE")
    assert isinstance(info, StockInfo)
    assert info.symbol == "RELIANCE"
    assert info.market_cap_cr > 0.0
    assert info.stock_pe > 0.0
    assert info.industry_pe > 0.0
    assert info.roce_pct > 0.0
    assert info.roe_pct > 0.0
    assert info.delivery_pct > 0.0
    assert info.upper_circuit > info.current_price
    assert info.lower_circuit < info.current_price
    assert info.promoter_holding_pct > 0.0


@pytest.mark.asyncio
async def test_stock_info_caching_speed():
    provider = StockInfoProvider()

    # First fetch (may hit network or fallback)
    _ = await provider.get_stock_info("TCS")

    # Second fetch must hit cache in < 15ms
    t0 = time.perf_counter()
    cached_info = await provider.get_stock_info("TCS")
    t1 = time.perf_counter()

    elapsed_ms = (t1 - t0) * 1000.0
    assert elapsed_ms < 50.0
    assert cached_info.symbol == "TCS"


@pytest.mark.asyncio
async def test_stock_info_batch_fetching():
    provider = StockInfoProvider()
    symbols = ["RELIANCE", "TCS", "INFY"]

    batch_map = await provider.get_batch_stock_info(symbols)
    assert len(batch_map) == 3
    assert "RELIANCE" in batch_map
    assert "TCS" in batch_map
    assert "INFY" in batch_map
    assert batch_map["TCS"].sector == "IT"


@pytest.mark.asyncio
async def test_stock_info_rest_endpoints():
    app = create_app()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        # 1. Full Info
        res_info = await client.get("/api/stocks/RELIANCE/info")
        assert res_info.status_code == 200
        data_info = res_info.json()
        assert data_info["symbol"] == "RELIANCE"
        assert "market_cap_cr" in data_info
        assert "delivery_pct" in data_info
        assert "promoter_holding_pct" in data_info

        # 2. Ratios
        res_ratios = await client.get("/api/stocks/TCS/ratios")
        assert res_ratios.status_code == 200
        data_ratios = res_ratios.json()
        assert data_ratios["symbol"] == "TCS"
        assert "stock_pe" in data_ratios
        assert "roce_pct" in data_ratios

        # 3. Delivery
        res_del = await client.get("/api/stocks/INFY/delivery")
        assert res_del.status_code == 200
        data_del = res_del.json()
        assert data_del["symbol"] == "INFY"
        assert "delivery_pct" in data_del
        assert "upper_circuit" in data_del

        # 4. Batch Info
        res_batch = await client.get("/api/stocks/batch-info?symbols=RELIANCE,TCS")
        assert res_batch.status_code == 200
        data_batch = res_batch.json()
        assert "RELIANCE" in data_batch
        assert "TCS" in data_batch

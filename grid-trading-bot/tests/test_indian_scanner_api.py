"""Integration tests for Indian Stock Scanner FastAPI REST endpoints."""

import pytest
from httpx import ASGITransport, AsyncClient

from dashboard.app import create_app
from engine.data.csv_provider import CsvReplayProvider
from engine.signals.scanner import IndianStockScanner
from services.scanner_service import ScannerService
from storage.database import Database
from storage.repositories import Repositories


@pytest.fixture
async def test_app(tmp_path):
    db_path = str(tmp_path / "test_scanner_api.db")
    db = Database(db_path)
    await db.connect()
    await db.migrate()
    repos = Repositories(db)

    provider = CsvReplayProvider()
    provider.load_synthetic_bullish_candles("RELIANCE", start_price=1200.0, num_bars=100, timeframe="1d")
    provider.load_synthetic_bullish_candles("RELIANCE", start_price=1240.0, num_bars=60, timeframe="1h")
    provider.load_synthetic_bullish_candles("RELIANCE", start_price=1248.0, num_bars=50, timeframe="15m")

    scanner = IndianStockScanner(provider=provider)
    svc = ScannerService(provider=provider, scanner=scanner)

    app = create_app()
    app.state.db = db
    app.state.repos = repos
    app.state.scanner_service = svc

    yield app

    await db.close()


@pytest.mark.asyncio
async def test_api_session_status(test_app):
    async with AsyncClient(transport=ASGITransport(app=test_app), base_url="http://test") as client:
        resp = await client.get("/api/scanner/session")
        assert resp.status_code == 200
        data = resp.json()
        assert "session_state" in data
        assert "current_time_ist" in data


@pytest.mark.asyncio
async def test_api_market_regime(test_app):
    async with AsyncClient(transport=ASGITransport(app=test_app), base_url="http://test") as client:
        resp = await client.get("/api/regime")
        assert resp.status_code == 200
        data = resp.json()
        assert "regime" in data
        assert "vix_value" in data


@pytest.mark.asyncio
async def test_api_sector_matrix(test_app):
    async with AsyncClient(transport=ASGITransport(app=test_app), base_url="http://test") as client:
        resp = await client.get("/api/sectors")
        assert resp.status_code == 200
        data = resp.json()
        assert "sectors" in data


@pytest.mark.asyncio
async def test_api_run_scan_and_get_latest(test_app):
    async with AsyncClient(transport=ASGITransport(app=test_app), base_url="http://test") as client:
        scan_resp = await client.post("/api/scanner/scan", json={"universe": "NIFTY_50", "max_signals": 2})
        assert scan_resp.status_code == 200
        scan_data = scan_resp.json()
        assert "top_signals" in scan_data
        assert "total_scanned" in scan_data

        latest_resp = await client.get("/api/scanner/latest")
        assert latest_resp.status_code == 200
        latest_data = latest_resp.json()
        assert latest_data["total_scanned"] == scan_data["total_scanned"]


@pytest.mark.asyncio
async def test_api_backtest_run(test_app):
    async with AsyncClient(transport=ASGITransport(app=test_app), base_url="http://test") as client:
        bt_resp = await client.post("/api/backtest/run", json={"universe": "NIFTY_50", "lookback_bars": 60})
        assert bt_resp.status_code == 200
        bt_data = bt_resp.json()
        assert "total_signals" in bt_data
        assert "win_rate_pct" in bt_data

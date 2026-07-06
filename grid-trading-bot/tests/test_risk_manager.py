"""Tests for RiskManager checks, using the real SQLite-backed repositories
against a temporary on-disk database (aiosqlite has no true in-memory
mode across connections, so each test gets its own temp file)."""

from __future__ import annotations

import pytest

from config.settings import RiskSettings
from risk.risk_manager import RiskManager
from storage.database import Database
from storage.models import GridRecord
from storage.repositories import Repositories
from utils.helpers import now_iso


@pytest.fixture
async def repos(tmp_path):
    db_path = tmp_path / "test.db"
    db = Database(str(db_path))
    await db.connect()
    await db.migrate()
    yield Repositories(db)
    await db.close()


@pytest.fixture
def risk_settings():
    return RiskSettings(
        max_total_capital=10000,
        max_capital_per_coin=5000,
        max_simultaneous_grids=2,
        min_wallet_balance=500,
        daily_loss_limit=1000,
    )


async def test_allows_grid_within_limits(repos, risk_settings):
    manager = RiskManager(risk_settings, repos)
    result = await manager.check_can_start_grid("BTCINR", 1000, wallet_inr_balance=5000)
    assert result.allowed


async def test_rejects_grid_exceeding_per_coin_cap(repos, risk_settings):
    manager = RiskManager(risk_settings, repos)
    result = await manager.check_can_start_grid("BTCINR", 6000, wallet_inr_balance=10000)
    assert not result.allowed
    assert "per-coin" in result.reason


async def test_rejects_grid_when_wallet_balance_too_low(repos, risk_settings):
    manager = RiskManager(risk_settings, repos)
    result = await manager.check_can_start_grid("BTCINR", 1000, wallet_inr_balance=1200)
    assert not result.allowed
    assert "minimum" in result.reason


async def test_rejects_duplicate_symbol_grid(repos, risk_settings):
    await repos.grids.create(
        GridRecord(
            grid_id="grid_1", symbol="BTCINR", grid_type="arithmetic", status="active",
            upper_price=100, lower_price=50, grid_levels=5, investment_per_grid=100,
            created_at=now_iso(), updated_at=now_iso(),
        )
    )
    manager = RiskManager(risk_settings, repos)
    result = await manager.check_can_start_grid("BTCINR", 500, wallet_inr_balance=5000)
    assert not result.allowed
    assert "already running" in result.reason


async def test_rejects_when_max_simultaneous_grids_reached(repos, risk_settings):
    for i in range(2):
        await repos.grids.create(
            GridRecord(
                grid_id=f"grid_{i}", symbol=f"COIN{i}INR", grid_type="arithmetic", status="active",
                upper_price=100, lower_price=50, grid_levels=5, investment_per_grid=100,
                created_at=now_iso(), updated_at=now_iso(),
            )
        )
    manager = RiskManager(risk_settings, repos)
    result = await manager.check_can_start_grid("ETHINR", 100, wallet_inr_balance=5000)
    assert not result.allowed
    assert "Maximum simultaneous grids" in result.reason


async def test_emergency_stop_blocks_new_grids(repos, risk_settings):
    manager = RiskManager(risk_settings, repos)
    manager.trigger_emergency_stop()
    result = await manager.check_can_start_grid("BTCINR", 100, wallet_inr_balance=5000)
    assert not result.allowed
    assert manager.emergency_stopped

    manager.clear_emergency_stop()
    assert not manager.emergency_stopped

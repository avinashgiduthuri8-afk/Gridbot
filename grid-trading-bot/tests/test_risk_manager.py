"""Tests for RiskManager checks against the DCA grid schema."""

from __future__ import annotations

import pytest

from config.settings import RiskSettings
from risk.risk_manager import RiskManager
from utils.helpers import now_iso
from storage.models import DCAGridRecord
from utils.helpers import new_id


def _make_grid(symbol: str, total_investment: float = 0.0) -> DCAGridRecord:
    now = now_iso()
    return DCAGridRecord(
        grid_id=new_id("grd"),
        symbol=symbol,
        status="active",
        entry_price=54000.0,
        base_investment=500.0,
        dip_buy_amount=100.0,
        dip_percentage=5.0,
        profit_sell_amount=150.0,
        profit_percentage=7.0,
        max_levels=10,
        stop_loss_percentage=50.0,
        current_level=1,
        total_quantity=0.01,
        total_investment=total_investment,
        average_entry_price=54000.0,
        last_buy_price=54000.0,
        next_buy_price=51300.0,
        next_sell_price=57780.0,
        realized_profit=0.0,
        completed_cycles=0,
        created_at=now,
        updated_at=now,
    )


@pytest.fixture
def risk_settings():
    return RiskSettings(
        max_total_capital=10000,
        max_capital_per_coin=5000,
        max_simultaneous_grids=2,
        min_wallet_balance=500,
        daily_loss_limit=1000,
    )


@pytest.mark.anyio
async def test_allows_grid_within_limits(repos, risk_settings):
    manager = RiskManager(risk_settings, repos)
    result = await manager.check_can_start_grid("BTCINR", 1000, wallet_inr_balance=5000)
    assert result.allowed


@pytest.mark.anyio
async def test_rejects_grid_exceeding_per_coin_cap(repos, risk_settings):
    manager = RiskManager(risk_settings, repos)
    result = await manager.check_can_start_grid("BTCINR", 6000, wallet_inr_balance=10000)
    assert not result.allowed
    assert "per-coin" in result.reason


@pytest.mark.anyio
async def test_rejects_when_wallet_balance_too_low(repos, risk_settings):
    manager = RiskManager(risk_settings, repos)
    # wallet=1200, investment=1000 → remaining=200 < min_wallet_balance=500
    result = await manager.check_can_start_grid("BTCINR", 1000, wallet_inr_balance=1200)
    assert not result.allowed
    assert "minimum" in result.reason


@pytest.mark.anyio
async def test_rejects_duplicate_symbol(repos, risk_settings):
    grid = _make_grid("BTCINR")
    await repos.grids.create(grid)
    manager = RiskManager(risk_settings, repos)
    result = await manager.check_can_start_grid("BTCINR", 500, wallet_inr_balance=5000)
    assert not result.allowed
    assert "already running" in result.reason


@pytest.mark.anyio
async def test_rejects_when_max_simultaneous_grids_reached(repos, risk_settings):
    for sym in ["BTCINR", "ETHINR"]:
        await repos.grids.create(_make_grid(sym))
    manager = RiskManager(risk_settings, repos)
    result = await manager.check_can_start_grid("SOLINR", 100, wallet_inr_balance=5000)
    assert not result.allowed
    assert "Maximum simultaneous grids" in result.reason


@pytest.mark.anyio
async def test_rejects_when_total_capital_exceeded(repos):
    # Use a settings that allows up to 5 grids so the capital check fires
    # before the simultaneous-grid-count check.
    generous_settings = RiskSettings(
        max_total_capital=10000,
        max_capital_per_coin=5000,
        max_simultaneous_grids=5,
        min_wallet_balance=500,
        daily_loss_limit=1000,
    )
    # Two grids already consuming 9000 INR total
    grid1 = _make_grid("BTCINR", total_investment=4500.0)
    grid2 = _make_grid("ETHINR", total_investment=4500.0)
    await repos.grids.create(grid1)
    await repos.grids.create(grid2)
    # New grid (2000 INR) would push 9000+2000=11000 > 10000 limit
    manager = RiskManager(generous_settings, repos)
    result = await manager.check_can_start_grid("SOLINR", 2000, wallet_inr_balance=5000)
    assert not result.allowed
    assert "Total capital limit" in result.reason


@pytest.mark.anyio
async def test_emergency_stop_blocks_new_grids(repos, risk_settings):
    manager = RiskManager(risk_settings, repos)
    await manager.trigger_emergency_stop()
    result = await manager.check_can_start_grid("BTCINR", 100, wallet_inr_balance=5000)
    assert not result.allowed
    assert manager.emergency_stopped


@pytest.mark.anyio
async def test_clear_emergency_stop(repos, risk_settings):
    manager = RiskManager(risk_settings, repos)
    await manager.trigger_emergency_stop()
    await manager.clear_emergency_stop()
    assert not manager.emergency_stopped


@pytest.mark.anyio
async def test_emergency_stop_survives_restart(repos, risk_settings):
    """A restart must not silently re-enable trading after an emergency stop.

    Regression test for the bug where RiskManager._emergency_stop was
    in-memory only: a fresh RiskManager instance sharing the same repos
    (simulating a process restart against the same DB) must come back up
    still stopped until load_emergency_stop() is called, and must reflect
    False if it was never triggered.
    """
    manager = RiskManager(risk_settings, repos)
    await manager.trigger_emergency_stop()

    # Simulate a restart: a brand-new RiskManager instance, same repos/DB.
    restarted_manager = RiskManager(risk_settings, repos)
    assert not restarted_manager.emergency_stopped, "fresh instance defaults to False before loading"
    await restarted_manager.load_emergency_stop()
    assert restarted_manager.emergency_stopped, "emergency stop must be restored from persisted state"

    # And clearing it persists too.
    await restarted_manager.clear_emergency_stop()
    another_restart = RiskManager(risk_settings, repos)
    await another_restart.load_emergency_stop()
    assert not another_restart.emergency_stopped
    # Use the instance that actually reloaded the cleared state — `manager`
    # itself never had clear_emergency_stop() called on it, so its own
    # in-memory flag is still stale (this mirrors real usage: each process
    # holds one long-lived RiskManager, so there's no cross-instance sync).
    result = await another_restart.check_can_start_grid("BTCINR", 100, wallet_inr_balance=5000)
    assert result.allowed

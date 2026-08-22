"""Comprehensive regression tests for Group 9.3: Risk Management & Capital Safety.

Validates all 16 required invariants:
 1. daily loss limit blocks new grids
 2. daily loss limit blocks dip buys
 3. daily loss limit persists across restart
 4. daily loss resets on new date
 5. multi-grid losses accumulate toward global daily limit
 6. max total capital limit enforced across full DCA ladders
 7. max capital per coin enforced
 8. min wallet balance enforced
 9. max simultaneous grids limit enforced
10. emergency stop persists across restart
11. stop-loss priority and position exit
12. sell clamping prevents negative position
13. real vs paper balance isolation
14. insufficient wallet balance blocks order
15. order rejection preserves risk consistency
16. concurrent risk checks remain safe
"""

from __future__ import annotations

import asyncio
import pytest
from datetime import datetime, timezone

from config.constants import GridStatus, OrderStatus
from config.settings import RiskSettings
from exchange.exceptions import OrderRejectedError
from risk.risk_manager import RiskManager
from storage.models import DCAGridRecord, OrderRecord
from trading.dca_manager import DCAManager
from trading.order_manager import OrderManager
from utils.helpers import new_id, now_iso

pytestmark = pytest.mark.anyio


def _make_grid(
    symbol: str = "BTCINR",
    status: str = GridStatus.ACTIVE.value,
    mode: str = "real",
    base_investment: float = 500.0,
    dip_buy_amount: float = 100.0,
    max_levels: int = 5,
    current_level: int = 1,
    total_quantity: float = 0.00925,
    total_investment: float = 499.5,
    average_entry_price: float = 54000.0,
) -> DCAGridRecord:
    now = now_iso()
    return DCAGridRecord(
        grid_id=new_id("grd"),
        symbol=symbol,
        status=status,
        mode=mode,
        entry_price=54000.0,
        base_investment=base_investment,
        dip_buy_amount=dip_buy_amount,
        dip_percentage=5.0,
        profit_sell_amount=150.0,
        profit_percentage=7.0,
        max_levels=max_levels,
        stop_loss_percentage=50.0,
        current_level=current_level,
        total_quantity=total_quantity,
        total_investment=total_investment,
        average_entry_price=average_entry_price,
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
        max_simultaneous_grids=5,
        min_wallet_balance=500,
        daily_loss_limit=1000,
    )


@pytest.fixture
def risk_manager(risk_settings, repos):
    return RiskManager(risk_settings, repos)


@pytest.fixture
def order_manager(mock_exchange, repos):
    return OrderManager(mock_exchange, repos)


@pytest.fixture
def dca_manager(mock_exchange, repos, order_manager, mock_notifier, risk_manager):
    return DCAManager(
        exchange=mock_exchange,
        repos=repos,
        order_manager=order_manager,
        notifier=mock_notifier,
        risk=risk_manager,
    )


# 1. Daily loss limit blocks new grids
async def test_daily_loss_limit_blocks_new_grids(repos, risk_manager):
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    # Simulate reaching the 1000 INR loss limit
    await repos.daily_stats.add_trade(today, -1000.0)

    result = await risk_manager.check_can_start_grid("BTCINR", 500.0, wallet_inr_balance=5000.0)
    assert not result.allowed
    assert "Daily loss limit" in result.reason


# 2. Daily loss limit blocks dip buys
async def test_daily_loss_limit_blocks_dip_buys(repos, dca_manager, mock_exchange):
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    await repos.daily_stats.add_trade(today, -1050.0)

    grid = _make_grid()
    await repos.grids.create(grid)

    await dca_manager.check_grid_triggers(grid.grid_id, 50000.0)
    assert len(mock_exchange.orders_placed) == 0


# 3. Daily loss limit persists across restart
async def test_daily_loss_limit_persists_across_restart(repos, risk_settings):
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    await repos.daily_stats.add_trade(today, -1000.0)

    # Fresh instance of RiskManager simulating a process restart
    restarted_risk = RiskManager(risk_settings, repos)
    result = await restarted_risk.check_can_start_grid("BTCINR", 500.0, wallet_inr_balance=5000.0)
    assert not result.allowed
    assert "Daily loss limit" in result.reason


# 4. Daily loss resets on new date
async def test_daily_loss_resets_on_new_date(repos, risk_manager):
    # Yesterday's loss
    await repos.daily_stats.add_trade("2026-01-01", -1500.0)

    # Today has no loss recorded yet
    result = await risk_manager.check_can_start_grid("BTCINR", 500.0, wallet_inr_balance=5000.0)
    assert result.allowed


# 5. Multi-grid losses accumulate toward global daily limit
async def test_multi_grid_losses_accumulate(repos, risk_manager):
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    # Grid A loses 600
    await repos.daily_stats.add_trade(today, -600.0)
    # Check is still ok
    res1 = await risk_manager.check_can_start_grid("SOLINR", 500.0, wallet_inr_balance=5000.0)
    assert res1.allowed

    # Grid B loses 450 (total loss = 1050 > 1000 limit)
    await repos.daily_stats.add_trade(today, -450.0)
    res2 = await risk_manager.check_can_start_grid("SOLINR", 500.0, wallet_inr_balance=5000.0)
    assert not res2.allowed
    assert "Daily loss limit" in res2.reason


# 6. Max total capital limit enforced across full DCA ladders
async def test_max_total_capital_limit_enforced_across_ladder(repos, risk_manager):
    # Grid 1: spent 2000, 4 dips left * 1000 = 6000 total commitment
    grid1 = _make_grid("BTCINR", base_investment=2000.0, dip_buy_amount=1000.0, max_levels=5, current_level=1, total_investment=2000.0)
    # Grid 2: spent 1000, 2 dips left * 1000 = 3000 total commitment
    grid2 = _make_grid("ETHINR", base_investment=1000.0, dip_buy_amount=1000.0, max_levels=3, current_level=1, total_investment=1000.0)
    await repos.grids.create(grid1)
    await repos.grids.create(grid2)
    # Total committed = 6000 + 3000 = 9000. Max total capital = 10000.
    # New grid with 2000 commitment (exceeds 10000)
    result = await risk_manager.check_can_start_grid("SOLINR", 2000.0, wallet_inr_balance=10000.0)
    assert not result.allowed
    assert "Total capital limit" in result.reason


# 7. Max capital per coin enforced
async def test_max_capital_per_coin_enforced(risk_manager):
    # Limit is 5000
    result = await risk_manager.check_can_start_grid("BTCINR", 5500.0, wallet_inr_balance=10000.0)
    assert not result.allowed
    assert "Per-coin" in result.reason or "per-coin" in result.reason


# 8. Min wallet balance enforced
async def test_min_wallet_balance_enforced(risk_manager):
    # Wallet balance 800, planned 500 -> remaining 300 < min_wallet_balance (500)
    result = await risk_manager.check_can_start_grid("BTCINR", 500.0, wallet_inr_balance=800.0)
    assert not result.allowed
    assert "minimum" in result.reason or "wallet balance" in result.reason.lower()


# 9. Max simultaneous grids limit enforced
async def test_max_simultaneous_grids_enforced(repos, risk_manager):
    for i in range(5):
        await repos.grids.create(_make_grid(symbol=f"COIN{i}INR"))

    result = await risk_manager.check_can_start_grid("NEWCOININR", 100.0, wallet_inr_balance=10000.0)
    assert not result.allowed
    assert "Maximum simultaneous grids" in result.reason


# 10. Emergency stop persists across restart
async def test_emergency_stop_persists_across_restart(repos, risk_settings):
    manager = RiskManager(risk_settings, repos)
    await manager.trigger_emergency_stop()
    assert manager.emergency_stopped

    restarted = RiskManager(risk_settings, repos)
    await restarted.load_emergency_stop()
    assert restarted.emergency_stopped

    result = await restarted.check_can_start_grid("BTCINR", 100.0, wallet_inr_balance=5000.0)
    assert not result.allowed
    assert "Emergency stop" in result.reason


# 11. Stop-loss priority and position exit
async def test_stop_loss_priority_and_full_exit(dca_manager, repos, mock_exchange):
    grid = _make_grid(average_entry_price=54000.0, total_quantity=0.01)
    await repos.grids.create(grid)

    # Price crashes to 25000 (below 50% stop loss)
    await dca_manager.check_grid_triggers(grid.grid_id, 25000.0)

    # Must place full position exit sell order
    assert len(mock_exchange.orders_placed) == 1
    assert mock_exchange.orders_placed[0].side == "sell"
    assert mock_exchange.orders_placed[0].quantity == 0.01

    updated = await repos.grids.get(grid.grid_id)
    assert updated["status"] == GridStatus.STOPPED.value


# 12. Sell clamping prevents negative position
async def test_sell_clamping_prevents_negative_position(dca_manager, repos):
    grid = _make_grid(total_quantity=0.005)
    await repos.grids.create(grid)

    # Manual sell requesting 100000 INR (far more than 0.005 BTC)
    await dca_manager.manual_sell(grid.grid_id, inr_amount=100000.0)

    orders = await repos.orders.list_for_grid(grid.grid_id)
    assert len(orders) == 1
    assert orders[0]["quantity"] == 0.005  # clamped to available


# 13. Real vs paper balance isolation
async def test_real_vs_paper_balance_isolation(dca_manager):
    real_bal = await dca_manager._get_wallet_balance("real")
    paper_bal = await dca_manager._get_wallet_balance("paper")

    # Paper balance is virtual and isolated from real balance
    assert paper_bal == 1_000_000.0
    assert real_bal == 50000.0  # mock exchange default


# 14. Insufficient wallet balance blocks order
async def test_insufficient_wallet_balance_blocks_order(risk_manager):
    result = await risk_manager.check_can_place_order(order_value_inr=5000.0, wallet_inr_balance=1000.0)
    assert not result.allowed
    assert "Insufficient" in result.reason


# 15. Order rejection preserves risk consistency
async def test_order_rejection_preserves_risk_consistency(dca_manager, repos, mock_exchange):
    grid = _make_grid(current_level=1, total_investment=500.0, total_quantity=0.01)
    await repos.grids.create(grid)

    mock_exchange.place_exception = OrderRejectedError("CoinDCX error")
    await dca_manager.check_grid_triggers(grid.grid_id, 50000.0)

    # Grid values must not have changed
    g = await repos.grids.get(grid.grid_id)
    assert g["current_level"] == 1
    assert g["total_investment"] == 500.0
    assert g["total_quantity"] == 0.01


# 16. Concurrent risk checks remain safe
async def test_concurrent_risk_checks_remain_safe(repos, risk_manager):
    # Concurrently check risk for 10 prospective orders
    tasks = [
        risk_manager.check_can_place_order(order_value_inr=500.0, wallet_inr_balance=5000.0)
        for _ in range(10)
    ]
    results = await asyncio.gather(*tasks)
    assert all(r.allowed for r in results)

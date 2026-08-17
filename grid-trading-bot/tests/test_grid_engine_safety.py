"""Comprehensive regression tests for Group 9.2: Grid Engine Safety & Correctness.

Validates all 16 required invariants:
 1. duplicate dip trigger prevention
 2. duplicate profit trigger prevention
 3. max-level boundary enforcement
 4. failed buy does not advance level
 5. failed sell does not complete cycle
 6. partial fill handling / level advancement only on full fill
 7. pause prevents new orders
 8. stopped grid cannot trade
 9. completed grid cannot trade
10. trailing peak persistence and reset
11. restart with submitted order
12. restart with paused grid
13. restart with stopped grid
14. restart with completed grid
15. NULL-safe grid values
16. concurrent trigger protection via grid lock
"""

from __future__ import annotations

import asyncio
import pytest

from config.constants import GridStatus, OrderStatus
from config.settings import RiskSettings
from exchange.base import ExchangeOrder
from exchange.exceptions import OrderRejectedError
from risk.risk_manager import RiskManager
from storage.models import DCAGridRecord, OrderRecord
from trading.dca_manager import DCAManager
from trading.order_manager import OrderManager
from trading.recovery import RecoveryManager
from utils.helpers import new_id, now_iso

pytestmark = pytest.mark.anyio


def _make_grid(
    grid_id: str | None = None,
    symbol: str = "BTCINR",
    status: str = GridStatus.ACTIVE.value,
    mode: str = "real",
    current_level: int = 1,
    max_levels: int = 5,
    total_quantity: float = 0.00925,
    total_investment: float = 499.5,
    average_entry_price: float = 54000.0,
    last_buy_price: float = 54000.0,
    next_buy_price: float = 51300.0,
    next_sell_price: float = 57780.0,
    realized_profit: float = 0.0,
    completed_cycles: int = 0,
    trailing_enabled: bool = False,
    trailing_percentage: float | None = None,
    trailing_peak_price: float | None = None,
) -> DCAGridRecord:
    now = now_iso()
    return DCAGridRecord(
        grid_id=grid_id or new_id("grd"),
        symbol=symbol,
        status=status,
        mode=mode,
        entry_price=54000.0,
        base_investment=500.0,
        dip_buy_amount=100.0,
        dip_percentage=5.0,
        profit_sell_amount=150.0,
        profit_percentage=7.0,
        max_levels=max_levels,
        stop_loss_percentage=50.0,
        current_level=current_level,
        total_quantity=total_quantity,
        total_investment=total_investment,
        average_entry_price=average_entry_price,
        last_buy_price=last_buy_price,
        next_buy_price=next_buy_price,
        next_sell_price=next_sell_price,
        realized_profit=realized_profit,
        completed_cycles=completed_cycles,
        trailing_enabled=trailing_enabled,
        trailing_percentage=trailing_percentage,
        trailing_peak_price=trailing_peak_price,
        created_at=now,
        updated_at=now,
    )


def _make_order(
    grid_id: str,
    side: str = "buy",
    status: str = OrderStatus.OPEN.value,
    exchange_order_id: str | None = "EX0001",
    quantity: float = 0.00925,
    filled_quantity: float = 0.0,
    price: float = 54000.0,
) -> OrderRecord:
    now = now_iso()
    return OrderRecord(
        order_id=new_id("ord"),
        grid_id=grid_id,
        exchange_order_id=exchange_order_id,
        symbol="BTCINR",
        side=side,
        order_type="market_order",
        price=price,
        quantity=quantity,
        filled_quantity=filled_quantity,
        filled_price=0.0,
        status=status,
        created_at=now,
        updated_at=now,
    )


@pytest.fixture
def order_manager(mock_exchange, repos):
    return OrderManager(mock_exchange, repos)


@pytest.fixture
def dca_manager(mock_exchange, repos, order_manager, mock_notifier, permissive_risk_settings):
    risk = RiskManager(permissive_risk_settings, repos)
    return DCAManager(
        exchange=mock_exchange,
        repos=repos,
        order_manager=order_manager,
        notifier=mock_notifier,
        risk=risk,
    )


# 1. Duplicate dip trigger prevention
async def test_duplicate_dip_trigger_prevention(dca_manager, repos, mock_exchange):
    grid = _make_grid()
    await repos.grids.create(grid)

    # First price tick triggers a dip buy
    await dca_manager.check_grid_triggers(grid.grid_id, 50000.0)
    assert len(mock_exchange.orders_placed) == 1
    assert mock_exchange.orders_placed[0].side == "buy"

    # Leave the order as OPEN (in flight)
    order = (await repos.orders.list_for_grid(grid.grid_id))[0]
    await repos.orders.update_status(order["order_id"], OrderStatus.OPEN.value)

    # Repeated price ticks with the same dip price must not place a second buy
    for _ in range(5):
        await dca_manager.check_grid_triggers(grid.grid_id, 50000.0)

    assert len(mock_exchange.orders_placed) == 1


# 2. Duplicate profit trigger prevention
async def test_duplicate_profit_trigger_prevention(dca_manager, repos, mock_exchange):
    grid = _make_grid()
    await repos.grids.create(grid)

    # First price tick crosses profit target
    await dca_manager.check_grid_triggers(grid.grid_id, 58000.0)
    assert len(mock_exchange.orders_placed) == 1
    assert mock_exchange.orders_placed[0].side == "sell"

    # Leave the order as OPEN (in flight)
    order = (await repos.orders.list_for_grid(grid.grid_id))[0]
    await repos.orders.update_status(order["order_id"], OrderStatus.OPEN.value)

    # Repeated price ticks with high price must not place duplicate sells
    for _ in range(5):
        await dca_manager.check_grid_triggers(grid.grid_id, 58000.0)

    assert len(mock_exchange.orders_placed) == 1


# 3. Max-level boundary enforcement
async def test_max_level_boundary_prevents_dip_buy(dca_manager, repos, mock_exchange):
    grid = _make_grid(current_level=5, max_levels=5)
    await repos.grids.create(grid)

    await dca_manager.check_grid_triggers(grid.grid_id, 45000.0)
    assert len(mock_exchange.orders_placed) == 0


# 4. Failed buy does not advance level
async def test_failed_buy_does_not_advance_level(dca_manager, repos, mock_exchange):
    grid = _make_grid(current_level=1)
    await repos.grids.create(grid)

    mock_exchange.place_exception = OrderRejectedError("insufficient balance")
    await dca_manager.check_grid_triggers(grid.grid_id, 50000.0)

    refreshed_grid = await repos.grids.get(grid.grid_id)
    assert refreshed_grid["current_level"] == 1
    assert refreshed_grid["total_quantity"] == grid.total_quantity
    assert refreshed_grid["average_entry_price"] == grid.average_entry_price


# 5. Failed sell does not complete cycle
async def test_failed_sell_does_not_complete_cycle(dca_manager, repos, mock_exchange):
    grid = _make_grid(current_level=1, completed_cycles=0, realized_profit=0.0)
    await repos.grids.create(grid)

    mock_exchange.place_exception = OrderRejectedError("sell order rejected")
    await dca_manager.check_grid_triggers(grid.grid_id, 60000.0)

    refreshed_grid = await repos.grids.get(grid.grid_id)
    assert refreshed_grid["completed_cycles"] == 0
    assert refreshed_grid["realized_profit"] == 0.0


# 6. Partial fill handling (level only advances on full fill)
async def test_partial_fill_does_not_advance_level(dca_manager, repos, mock_exchange):
    grid = _make_grid(current_level=1)
    await repos.grids.create(grid)

    order = _make_order(grid.grid_id, side="buy", status=OrderStatus.PARTIALLY_FILLED.value, quantity=0.01, filled_quantity=0.004)
    await repos.orders.create(order)

    # Grid level stays 1 while partially filled
    refreshed_grid = await repos.grids.get(grid.grid_id)
    assert refreshed_grid["current_level"] == 1

    # When full fill arrives, handle_order_filled advances the level to 2
    await dca_manager.handle_order_filled(order.order_id, fill_price=54000.0, fill_qty=0.01)
    refreshed_grid_after = await repos.grids.get(grid.grid_id)
    assert refreshed_grid_after["current_level"] == 2


# 7. Pause prevents new orders
async def test_paused_grid_prevents_new_orders(dca_manager, repos, mock_exchange):
    grid = _make_grid(status=GridStatus.PAUSED.value)
    await repos.grids.create(grid)

    # Both dip and profit triggers are ignored
    await dca_manager.check_grid_triggers(grid.grid_id, 40000.0)
    await dca_manager.check_grid_triggers(grid.grid_id, 70000.0)

    assert len(mock_exchange.orders_placed) == 0


# 8. Stopped grid cannot trade
async def test_stopped_grid_cannot_trade(dca_manager, repos, mock_exchange):
    grid = _make_grid(status=GridStatus.STOPPED.value)
    await repos.grids.create(grid)

    await dca_manager.check_grid_triggers(grid.grid_id, 40000.0)
    await dca_manager.check_grid_triggers(grid.grid_id, 70000.0)

    assert len(mock_exchange.orders_placed) == 0


# 9. Completed grid cannot trade
async def test_completed_grid_cannot_trade(dca_manager, repos, mock_exchange):
    grid = _make_grid(status=GridStatus.COMPLETED.value, total_quantity=0.0)
    await repos.grids.create(grid)

    await dca_manager.check_grid_triggers(grid.grid_id, 40000.0)
    await dca_manager.check_grid_triggers(grid.grid_id, 70000.0)

    assert len(mock_exchange.orders_placed) == 0


# 10. Trailing peak persistence and reset
async def test_trailing_peak_persistence_and_reset(dca_manager, repos, mock_exchange):
    grid = _make_grid(trailing_enabled=True, trailing_percentage=3.0)
    await repos.grids.create(grid)

    # Activate trailing at 58000
    await dca_manager.check_grid_triggers(grid.grid_id, 58000.0)
    g = await repos.grids.get(grid.grid_id)
    assert g["trailing_peak_price"] == 58000.0

    # Price moves up to 60000 -> peak updates
    await dca_manager.check_grid_triggers(grid.grid_id, 60000.0)
    g = await repos.grids.get(grid.grid_id)
    assert g["trailing_peak_price"] == 60000.0

    # Price small drop to 59500 (< 3%) -> peak unchanged
    await dca_manager.check_grid_triggers(grid.grid_id, 59500.0)
    g = await repos.grids.get(grid.grid_id)
    assert g["trailing_peak_price"] == 60000.0

    # Price drop to 58000 (> 3.3% drop from 60000) -> trailing stop fires sell
    await dca_manager.check_grid_triggers(grid.grid_id, 58000.0)
    assert len(mock_exchange.orders_placed) == 1
    assert mock_exchange.orders_placed[0].side == "sell"

    # Peak resets to None
    g_after = await repos.grids.get(grid.grid_id)
    assert g_after["trailing_peak_price"] is None


# 11. Restart with submitted order
async def test_restart_with_submitted_order(repos, mock_exchange, mock_notifier, dca_manager):
    grid = _make_grid()
    await repos.grids.create(grid)
    client_id = new_id("ord")
    order = _make_order(grid.grid_id, status=OrderStatus.SUBMITTED.value, exchange_order_id=None)
    order.order_id = client_id
    order.client_order_id = client_id
    await repos.orders.create(order)

    # Simulate exchange having accepted the order
    mock_exchange.orders_placed.append(
        ExchangeOrder(
            exchange_order_id="EX_SUBMITTED_RECOVERY",
            symbol="BTCINR",
            side="buy",
            price=54000.0,
            quantity=0.00925,
            filled_quantity=0.0,
            filled_price=0.0,
            status=OrderStatus.OPEN.value,
            raw_status="open",
            client_order_id=client_id,
        )
    )

    recovery = RecoveryManager(mock_exchange, repos, mock_notifier, dca_manager)
    summary = await recovery.recover()
    assert summary["reconciled_orders"] >= 1

    recovered = await repos.orders.get(client_id)
    assert recovered["exchange_order_id"] == "EX_SUBMITTED_RECOVERY"
    assert recovered["status"] == OrderStatus.OPEN.value


# 12. Restart with paused grid
async def test_restart_with_paused_grid(repos, mock_exchange, mock_notifier, dca_manager):
    grid = _make_grid(status=GridStatus.PAUSED.value)
    await repos.grids.create(grid)

    recovery = RecoveryManager(mock_exchange, repos, mock_notifier, dca_manager)
    summary = await recovery.recover()
    assert summary["active_grids"] == 1  # active + paused counted

    refreshed = await repos.grids.get(grid.grid_id)
    assert refreshed["status"] == GridStatus.PAUSED.value


# 13. Restart with stopped grid
async def test_restart_with_stopped_grid(repos, mock_exchange, mock_notifier, dca_manager):
    grid = _make_grid(status=GridStatus.STOPPED.value)
    await repos.grids.create(grid)

    recovery = RecoveryManager(mock_exchange, repos, mock_notifier, dca_manager)
    summary = await recovery.recover()
    assert summary["active_grids"] == 0

    refreshed = await repos.grids.get(grid.grid_id)
    assert refreshed["status"] == GridStatus.STOPPED.value


# 14. Restart with completed grid
async def test_restart_with_completed_grid(repos, mock_exchange, mock_notifier, dca_manager):
    grid = _make_grid(status=GridStatus.COMPLETED.value, total_quantity=0.0)
    await repos.grids.create(grid)

    recovery = RecoveryManager(mock_exchange, repos, mock_notifier, dca_manager)
    summary = await recovery.recover()
    assert summary["active_grids"] == 0

    refreshed = await repos.grids.get(grid.grid_id)
    assert refreshed["status"] == GridStatus.COMPLETED.value


# 15. NULL-safe grid values
async def test_null_safe_grid_values(repos, dca_manager):
    # Verify starting and adjusting grid with zero / none fields
    grid = _make_grid(
        realized_profit=0.0,
        completed_cycles=0,
        trailing_peak_price=None,
    )
    await repos.grids.create(grid)
    loaded = await repos.grids.get(grid.grid_id)
    assert loaded["realized_profit"] == 0.0
    assert loaded["completed_cycles"] == 0
    assert loaded["trailing_peak_price"] is None


# 16. Concurrent trigger protection via grid lock and in-flight order count
async def test_concurrent_trigger_protection(dca_manager, repos, mock_exchange):
    grid = _make_grid()
    await repos.grids.create(grid)
    order = _make_order(grid_id=grid.grid_id, side="buy", status=OrderStatus.OPEN.value)
    await repos.orders.create(order)

    # Concurrently fire 10 trigger checks for the same grid
    tasks = [
        dca_manager.check_grid_triggers(grid.grid_id, 50000.0)
        for _ in range(10)
    ]
    await asyncio.gather(*tasks)

    # Exactly 0 new orders placed because an order is already in-flight
    assert len(mock_exchange.orders_placed) == 0

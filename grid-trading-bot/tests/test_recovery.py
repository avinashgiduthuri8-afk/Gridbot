"""Tests for RecoveryManager: startup reconciliation of open orders."""

from __future__ import annotations

import pytest

from config.constants import GridStatus, OrderStatus
from config.settings import RiskSettings
from exchange.base import ExchangeOrder
from exchange.exceptions import ExchangeError
from risk.risk_manager import RiskManager
from storage.models import DCAGridRecord, OrderRecord
from trading.dca_manager import DCAManager
from trading.order_manager import OrderManager
from trading.recovery import RecoveryManager
from utils.helpers import new_id, now_iso


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_grid(grid_id: str, symbol: str = "BTCINR", status: str = GridStatus.ACTIVE.value) -> DCAGridRecord:
    now = now_iso()
    return DCAGridRecord(
        grid_id=grid_id,
        symbol=symbol,
        status=status,
        entry_price=54000.0,
        base_investment=500.0,
        dip_buy_amount=100.0,
        dip_percentage=5.0,
        profit_sell_amount=150.0,
        profit_percentage=7.0,
        max_levels=10,
        stop_loss_percentage=50.0,
        current_level=1,
        total_quantity=0.00925,
        total_investment=499.5,
        average_entry_price=54000.0,
        last_buy_price=54000.0,
        next_buy_price=51300.0,
        next_sell_price=57780.0,
        realized_profit=0.0,
        completed_cycles=0,
        created_at=now,
        updated_at=now,
    )


def _make_order(
    grid_id: str,
    side: str = "buy",
    status: str = OrderStatus.OPEN.value,
    exchange_order_id: str | None = "EX0001",
) -> OrderRecord:
    now = now_iso()
    return OrderRecord(
        order_id=new_id("ord"),
        grid_id=grid_id,
        exchange_order_id=exchange_order_id,
        symbol="BTCINR",
        side=side,
        order_type="market_order",
        price=54000.0,
        quantity=0.00925,
        filled_quantity=0.0,
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


@pytest.fixture
def recovery(mock_exchange, repos, mock_notifier, dca_manager):
    return RecoveryManager(
        exchange=mock_exchange,
        repos=repos,
        notifier=mock_notifier,
        dca_manager=dca_manager,
    )


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_recover_no_open_orders_returns_zero(recovery, repos):
    grid = _make_grid(new_id("grd"))
    await repos.grids.create(grid)
    summary = await recovery.recover()
    assert summary["reconciled_orders"] == 0
    assert summary["active_grids"] == 1


@pytest.mark.anyio
async def test_recover_sends_notification(recovery, mock_notifier, repos):
    grid = _make_grid(new_id("grd"))
    await repos.grids.create(grid)
    await recovery.recover()
    assert mock_notifier.was_called("recovery_complete")


@pytest.mark.anyio
async def test_recover_marks_order_failed_when_no_exchange_id(recovery, repos, mock_exchange):
    grid = _make_grid(new_id("grd"))
    await repos.grids.create(grid)
    order = _make_order(grid.grid_id, exchange_order_id=None, status=OrderStatus.PENDING.value)
    await repos.orders.create(order)

    summary = await recovery.recover()
    assert summary["reconciled_orders"] == 1

    refreshed = await repos.orders.get(order.order_id)
    assert refreshed["status"] == OrderStatus.FAILED.value


@pytest.mark.anyio
async def test_recover_processes_fill_that_happened_while_bot_was_down(
    recovery, repos, mock_exchange
):
    grid = _make_grid(new_id("grd"))
    await repos.grids.create(grid)

    eid = "EX_OFFLINE"
    order = _make_order(grid.grid_id, status=OrderStatus.OPEN.value, exchange_order_id=eid)
    await repos.orders.create(order)

    filled_ex_order = ExchangeOrder(
        exchange_order_id=eid,
        symbol="BTCINR",
        side="buy",
        price=54000.0,
        quantity=0.00185,
        filled_quantity=0.00185,
        filled_price=54000.0,
        status=OrderStatus.FILLED.value,
        raw_status="filled",
    )
    mock_exchange.orders_placed.append(filled_ex_order)

    summary = await recovery.recover()
    assert summary["reconciled_orders"] == 1

    refreshed_order = await repos.orders.get(order.order_id)
    assert refreshed_order["status"] == OrderStatus.FILLED.value

    refreshed_grid = await repos.grids.get(grid.grid_id)
    assert refreshed_grid["current_level"] == 2


@pytest.mark.anyio
async def test_recover_skips_order_when_exchange_raises(recovery, repos, mock_exchange):
    grid = _make_grid(new_id("grd"))
    await repos.grids.create(grid)

    order = _make_order(grid.grid_id, status=OrderStatus.OPEN.value, exchange_order_id="EX_MISSING")
    await repos.orders.create(order)

    summary = await recovery.recover()
    assert summary["reconciled_orders"] == 0

    refreshed = await repos.orders.get(order.order_id)
    assert refreshed["status"] == OrderStatus.OPEN.value


@pytest.mark.anyio
async def test_recover_already_terminal_order_not_counted(recovery, repos):
    grid = _make_grid(new_id("grd"))
    await repos.grids.create(grid)
    order = _make_order(grid.grid_id, status=OrderStatus.FILLED.value, exchange_order_id="EX_DONE")
    await repos.orders.create(order)

    summary = await recovery.recover()
    assert summary["reconciled_orders"] == 0


@pytest.mark.anyio
async def test_recover_counts_paused_grids(recovery, repos):
    active = _make_grid(new_id("grd"), status=GridStatus.ACTIVE.value)
    paused = _make_grid(new_id("grd"), symbol="ETHINR", status=GridStatus.PAUSED.value)
    stopped = _make_grid(new_id("grd"), symbol="SOLINR", status=GridStatus.STOPPED.value)
    for g in [active, paused, stopped]:
        await repos.grids.create(g)

    summary = await recovery.recover()
    assert summary["active_grids"] == 2

"""Tests for OrderMonitor: background poll loop detects fills and routes them."""

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
from trading.order_monitor import OrderMonitor
from utils.helpers import new_id, now_iso


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_grid(grid_id: str, symbol: str = "BTCINR") -> DCAGridRecord:
    now = now_iso()
    return DCAGridRecord(
        grid_id=grid_id,
        symbol=symbol,
        status=GridStatus.ACTIVE.value,
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


def _make_open_order(
    grid_id: str,
    side: str = "buy",
    exchange_order_id: str = "EX0001",
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
        quantity=0.00185,
        filled_quantity=0.0,
        filled_price=0.0,
        status=OrderStatus.OPEN.value,
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
def monitor(repos, order_manager, dca_manager):
    return OrderMonitor(
        repos=repos,
        order_manager=order_manager,
        dca_manager=dca_manager,
        poll_interval=1,
    )


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_poll_once_no_open_orders_does_nothing(monitor, repos, mock_exchange):
    before = len(mock_exchange.orders_placed)
    await monitor._poll_once()
    assert len(mock_exchange.orders_placed) == before


@pytest.mark.anyio
async def test_poll_once_skips_order_without_exchange_id(monitor, repos):
    grid = _make_grid(new_id("grd"))
    await repos.grids.create(grid)
    now = now_iso()
    order = OrderRecord(
        order_id=new_id("ord"),
        grid_id=grid.grid_id,
        exchange_order_id=None,
        symbol="BTCINR",
        side="buy",
        order_type="market_order",
        price=54000.0,
        quantity=0.001,
        filled_quantity=0.0,
        filled_price=0.0,
        status=OrderStatus.PENDING.value,
        created_at=now,
        updated_at=now,
    )
    await repos.orders.create(order)
    await monitor._poll_once()
    refreshed = await repos.orders.get(order.order_id)
    assert refreshed["status"] == OrderStatus.PENDING.value


@pytest.mark.anyio
async def test_poll_once_detects_filled_order_and_updates_grid(
    monitor, repos, mock_exchange, dca_manager
):
    grid = _make_grid(new_id("grd"))
    await repos.grids.create(grid)

    eid = "EX_FILL_01"
    order = _make_open_order(grid.grid_id, "buy", eid)
    await repos.orders.create(order)

    filled = ExchangeOrder(
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
    mock_exchange.orders_placed.append(filled)

    await monitor._poll_once()

    refreshed_order = await repos.orders.get(order.order_id)
    assert refreshed_order["status"] == OrderStatus.FILLED.value

    refreshed_grid = await repos.grids.get(grid.grid_id)
    assert refreshed_grid["current_level"] == 2


@pytest.mark.anyio
async def test_poll_once_order_still_open_does_not_trigger_fill(
    monitor, repos, mock_exchange
):
    grid = _make_grid(new_id("grd"))
    await repos.grids.create(grid)

    eid = "EX_OPEN_01"
    order = _make_open_order(grid.grid_id, "buy", eid)
    await repos.orders.create(order)

    still_open = ExchangeOrder(
        exchange_order_id=eid,
        symbol="BTCINR",
        side="buy",
        price=54000.0,
        quantity=0.00185,
        filled_quantity=0.0,
        filled_price=0.0,
        status=OrderStatus.OPEN.value,
        raw_status="open",
    )
    mock_exchange.orders_placed.append(still_open)

    initial_level = (await repos.grids.get(grid.grid_id))["current_level"]
    await monitor._poll_once()
    assert (await repos.grids.get(grid.grid_id))["current_level"] == initial_level


@pytest.mark.anyio
async def test_poll_once_exchange_error_is_swallowed(monitor, repos, mock_exchange):
    grid = _make_grid(new_id("grd"))
    await repos.grids.create(grid)

    eid = "EX_BAD_01"
    order = _make_open_order(grid.grid_id, "buy", eid)
    await repos.orders.create(order)

    await monitor._poll_once()

    refreshed = await repos.orders.get(order.order_id)
    assert refreshed["status"] == OrderStatus.OPEN.value


@pytest.mark.anyio
async def test_monitor_start_and_stop():
    import asyncio
    from unittest.mock import AsyncMock, MagicMock

    repos_mock = MagicMock()
    repos_mock.orders.list_open = AsyncMock(return_value=[])
    om_mock = MagicMock()
    dm_mock = MagicMock()

    mon = OrderMonitor(repos=repos_mock, order_manager=om_mock,
                       dca_manager=dm_mock, poll_interval=100)
    mon.start()
    assert mon._task is not None
    assert not mon._task.done()
    await mon.stop()
    assert mon._task is None

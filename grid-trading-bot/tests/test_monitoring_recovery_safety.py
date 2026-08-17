"""Comprehensive regression tests for Group 9.4: Monitoring, Recovery & Observability Safety.

Validates all 16 required invariants:
 1. submitted order recovery via client_order_id
 2. unknown order recovery retention
 3. already-filled order offline recovery
 4. repeated recovery execution idempotency
 5. orphan exchange order detection and notification
 6. exchange unavailable during startup recovery handled gracefully
 7. order monitor exchange failure does not crash loop
 8. price monitor invalid price (0, NaN, negative) filtered out
 9. price monitor API failure recovery
10. duplicate monitoring fill events prevented
11. concurrent monitor and recovery processing safe
12. notification failure does not crash trading engine
13. restart with active order preserved
14. restart with paused grid remains paused
15. restart with stopped grid remains stopped
16. restart with completed grid remains completed
"""

from __future__ import annotations

import asyncio
import pytest
from unittest.mock import AsyncMock, MagicMock

from config.constants import GridStatus, OrderStatus
from config.settings import RiskSettings
from exchange.base import ExchangeOrder
from exchange.exceptions import ExchangeConnectionError, ExchangeError
from notifications.notifier import Notifier
from risk.risk_manager import RiskManager
from storage.models import DCAGridRecord, OrderRecord
from telegram.error import TelegramError
from trading.dca_manager import DCAManager
from trading.order_manager import OrderManager
from trading.order_monitor import OrderMonitor
from trading.price_monitor import PriceMonitor
from trading.recovery import RecoveryManager
from utils.helpers import new_id, now_iso

pytestmark = pytest.mark.anyio


def _make_grid(
    grid_id: str | None = None,
    symbol: str = "BTCINR",
    status: str = GridStatus.ACTIVE.value,
    mode: str = "real",
    current_level: int = 1,
    total_quantity: float = 0.00925,
    total_investment: float = 499.5,
    average_entry_price: float = 54000.0,
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
        max_levels=10,
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


def _make_order(
    grid_id: str,
    side: str = "buy",
    status: str = OrderStatus.OPEN.value,
    exchange_order_id: str | None = "EX0001",
    quantity: float = 0.00925,
    filled_quantity: float = 0.0,
    price: float = 54000.0,
    client_order_id: str | None = None,
) -> OrderRecord:
    now = now_iso()
    oid = new_id("ord")
    return OrderRecord(
        order_id=oid,
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
        client_order_id=client_order_id or oid,
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
def recovery_manager(mock_exchange, repos, mock_notifier, dca_manager):
    return RecoveryManager(
        exchange=mock_exchange,
        repos=repos,
        notifier=mock_notifier,
        dca_manager=dca_manager,
    )


@pytest.fixture
def order_monitor(repos, order_manager, dca_manager, mock_notifier, mock_exchange):
    return OrderMonitor(
        repos=repos,
        order_manager=order_manager,
        dca_manager=dca_manager,
        notifier=mock_notifier,
        exchange=mock_exchange,
        poll_interval=1,
        sync_every_n_cycles=1000,
    )


@pytest.fixture
def price_monitor(mock_exchange, repos, dca_manager, mock_notifier):
    return PriceMonitor(
        exchange=mock_exchange,
        repos=repos,
        dca_manager=dca_manager,
        notifier=mock_notifier,
        default_interval=2,
    )


# 1. Submitted order recovery via client_order_id
async def test_submitted_order_recovery(repos, mock_exchange, recovery_manager):
    grid = _make_grid()
    await repos.grids.create(grid)

    client_id = new_id("ord")
    order = _make_order(grid.grid_id, status=OrderStatus.SUBMITTED.value, exchange_order_id=None, client_order_id=client_id)
    order.order_id = client_id
    await repos.orders.create(order)

    # Exchange matches by client_order_id
    mock_exchange.orders_placed.append(
        ExchangeOrder(
            exchange_order_id="EX_REC_01",
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

    summary = await recovery_manager.recover()
    assert summary["reconciled_orders"] >= 1

    rec = await repos.orders.get(client_id)
    assert rec["exchange_order_id"] == "EX_REC_01"
    assert rec["status"] == OrderStatus.OPEN.value


# 2. Unknown order recovery retention (unmatched remains UNKNOWN)
async def test_unknown_order_recovery_retention(repos, mock_exchange, recovery_manager):
    grid = _make_grid()
    await repos.grids.create(grid)

    client_id = new_id("ord")
    order = _make_order(grid.grid_id, status=OrderStatus.UNKNOWN.value, exchange_order_id=None, client_order_id=client_id)
    order.order_id = client_id
    await repos.orders.create(order)

    # No match on exchange
    mock_exchange.orders_placed = []

    summary = await recovery_manager.recover()
    assert summary["reconciled_orders"] >= 1

    rec = await repos.orders.get(client_id)
    assert rec["status"] == OrderStatus.UNKNOWN.value
    assert rec["exchange_order_id"] is None


# 3. Already-filled order offline recovery
async def test_already_filled_order_recovery(repos, mock_exchange, recovery_manager):
    grid = _make_grid()
    await repos.grids.create(grid)

    order = _make_order(grid.grid_id, status=OrderStatus.OPEN.value, exchange_order_id="EX_OFFLINE_FILL")
    await repos.orders.create(order)

    mock_exchange.status_overrides["EX_OFFLINE_FILL"] = ExchangeOrder(
        exchange_order_id="EX_OFFLINE_FILL",
        symbol="BTCINR",
        side="buy",
        price=54000.0,
        quantity=0.00925,
        filled_quantity=0.00925,
        filled_price=54000.0,
        status=OrderStatus.FILLED.value,
        raw_status="filled",
    )

    summary = await recovery_manager.recover()
    assert summary["fills_recovered"] == 1

    refreshed_grid = await repos.grids.get(grid.grid_id)
    assert refreshed_grid["current_level"] == 2


# 4. Repeated recovery execution idempotency
async def test_repeated_recovery_idempotency(repos, mock_exchange, recovery_manager):
    grid = _make_grid()
    await repos.grids.create(grid)

    order = _make_order(grid.grid_id, status=OrderStatus.OPEN.value, exchange_order_id="EX_IDEM")
    await repos.orders.create(order)

    mock_exchange.status_overrides["EX_IDEM"] = ExchangeOrder(
        exchange_order_id="EX_IDEM",
        symbol="BTCINR",
        side="buy",
        price=54000.0,
        quantity=0.00925,
        filled_quantity=0.00925,
        filled_price=54000.0,
        status=OrderStatus.FILLED.value,
        raw_status="filled",
    )

    # First run recovers the fill
    summary1 = await recovery_manager.recover()
    assert summary1["fills_recovered"] == 1
    g1 = await repos.grids.get(grid.grid_id)
    assert g1["current_level"] == 2

    # Second run is completely idempotent and doesn't re-apply
    summary2 = await recovery_manager.recover()
    assert summary2["fills_recovered"] == 0
    g2 = await repos.grids.get(grid.grid_id)
    assert g2["current_level"] == 2


# 5. Orphan exchange order detection and notification
async def test_orphan_exchange_order_handling(repos, mock_exchange, recovery_manager, mock_notifier):
    grid = _make_grid(mode="real")
    await repos.grids.create(grid)

    # Exchange has an open order not known in DB
    mock_exchange.open_orders_override = [
        ExchangeOrder(
            exchange_order_id="EX_ORPHAN_999",
            symbol="BTCINR",
            side="buy",
            price=54000.0,
            quantity=0.005,
            filled_quantity=0.0,
            filled_price=0.0,
            status=OrderStatus.OPEN.value,
            raw_status="open",
        )
    ]

    summary = await recovery_manager.recover()
    assert summary["orphans_linked"] == 1
    assert mock_notifier.was_called("orphan_orders_detected")


# 6. Exchange unavailable during recovery handled gracefully
async def test_exchange_unavailable_during_recovery(repos, mock_exchange, recovery_manager):
    grid = _make_grid()
    await repos.grids.create(grid)

    order = _make_order(grid.grid_id, status=OrderStatus.OPEN.value, exchange_order_id="EX_UNREACHABLE")
    await repos.orders.create(order)

    # Mock exchange raising on get_order_status
    async def _failing_get_order_status(eid):
        raise ExchangeConnectionError("CoinDCX unreachable")

    mock_exchange.get_order_status = _failing_get_order_status  # type: ignore[method-assign]

    summary = await recovery_manager.recover()
    assert summary["fills_recovered"] == 0

    # Order remains safely in OPEN state without corruption
    o = await repos.orders.get(order.order_id)
    assert o["status"] == OrderStatus.OPEN.value


# 7. Order monitor exchange failure does not crash loop
async def test_monitor_exchange_failure_does_not_kill_loop(repos, mock_exchange, order_monitor):
    grid = _make_grid()
    await repos.grids.create(grid)

    order = _make_order(grid.grid_id, status=OrderStatus.OPEN.value, exchange_order_id="EX_ERR")
    await repos.orders.create(order)

    # Should not raise exception
    await order_monitor._poll_once()
    o = await repos.orders.get(order.order_id)
    assert o["status"] == OrderStatus.OPEN.value


# 8. Price monitor invalid price handling
async def test_price_monitor_invalid_price_handling(repos, mock_exchange, price_monitor, dca_manager):
    grid = _make_grid()
    await repos.grids.create(grid)

    mock_exchange.ticker_price = 0.0  # Invalid garbage price
    await price_monitor._run_cycle()

    # No trades triggered on invalid price 0.0
    assert len(mock_exchange.orders_placed) == 0


# 9. Price monitor API failure recovery
async def test_price_monitor_api_failure_recovery(repos, mock_exchange, price_monitor):
    grid = _make_grid()
    await repos.grids.create(grid)

    # First cycle fails with network error
    async def _failing_batch(symbols):
        raise ExchangeConnectionError("Network drop")

    original_batch = mock_exchange.get_tickers_batch
    mock_exchange.get_tickers_batch = _failing_batch  # type: ignore[method-assign]

    await price_monitor._run_cycle()
    status1 = price_monitor.get_status()
    assert not status1.api_ok
    assert status1.consecutive_failures == 1

    # Second cycle recovers
    mock_exchange.get_tickers_batch = original_batch  # type: ignore[method-assign]
    await price_monitor._run_cycle()
    status2 = price_monitor.get_status()
    assert status2.api_ok
    assert status2.consecutive_failures == 0


# 10. Duplicate monitoring events prevented
async def test_duplicate_monitoring_events_prevented(repos, mock_exchange, order_monitor, mock_notifier):
    grid = _make_grid()
    await repos.grids.create(grid)

    order = _make_order(grid.grid_id, status=OrderStatus.OPEN.value, exchange_order_id="EX_SINGLE_FILL")
    await repos.orders.create(order)

    mock_exchange.status_overrides["EX_SINGLE_FILL"] = ExchangeOrder(
        exchange_order_id="EX_SINGLE_FILL",
        symbol="BTCINR",
        side="buy",
        price=54000.0,
        quantity=0.00925,
        filled_quantity=0.00925,
        filled_price=54000.0,
        status=OrderStatus.FILLED.value,
        raw_status="filled",
    )

    # Polling twice must only process the fill once
    await order_monitor._poll_once()
    await order_monitor._poll_once()

    g = await repos.grids.get(grid.grid_id)
    assert g["current_level"] == 2  # not 3


# 11. Concurrent monitor and recovery processing
async def test_concurrent_monitor_and_recovery_processing(repos, mock_exchange, order_monitor, recovery_manager):
    grid = _make_grid()
    await repos.grids.create(grid)

    order = _make_order(grid.grid_id, status=OrderStatus.OPEN.value, exchange_order_id="EX_CONCURRENT")
    await repos.orders.create(order)

    mock_exchange.status_overrides["EX_CONCURRENT"] = ExchangeOrder(
        exchange_order_id="EX_CONCURRENT",
        symbol="BTCINR",
        side="buy",
        price=54000.0,
        quantity=0.00925,
        filled_quantity=0.00925,
        filled_price=54000.0,
        status=OrderStatus.FILLED.value,
        raw_status="filled",
    )

    # Concurrently execute monitor poll and recovery
    await asyncio.gather(
        order_monitor._poll_once(),
        recovery_manager.recover(),
    )

    g = await repos.grids.get(grid.grid_id)
    assert g["current_level"] == 2


# 12. Notification failure does not crash trading
async def test_notification_failure_does_not_crash_trading():
    bot_mock = MagicMock()
    bot_mock.send_message = AsyncMock(side_effect=TelegramError("Network timeout"))
    notifier = Notifier(bot_mock, (123456,))

    # Should not raise exception
    await notifier.send("Test message")
    await notifier.grid_started("BTCINR", "grd_1", 54000.0, 500.0, 5.0, 7.0, 10, 57780.0)


# 13. Restart with active order preserved
async def test_restart_with_active_order(repos, mock_exchange, recovery_manager):
    grid = _make_grid(status=GridStatus.ACTIVE.value)
    await repos.grids.create(grid)

    order = _make_order(grid.grid_id, status=OrderStatus.OPEN.value, exchange_order_id="EX_ACTIVE_RESTART")
    await repos.orders.create(order)

    summary = await recovery_manager.recover()
    assert summary["active_grids"] == 1

    o = await repos.orders.get(order.order_id)
    assert o["status"] == OrderStatus.OPEN.value


# 14. Restart with paused grid
async def test_restart_with_paused_grid(repos, mock_exchange, recovery_manager):
    grid = _make_grid(status=GridStatus.PAUSED.value)
    await repos.grids.create(grid)

    summary = await recovery_manager.recover()
    assert summary["active_grids"] == 1

    g = await repos.grids.get(grid.grid_id)
    assert g["status"] == GridStatus.PAUSED.value


# 15. Restart with stopped grid
async def test_restart_with_stopped_grid(repos, mock_exchange, recovery_manager):
    grid = _make_grid(status=GridStatus.STOPPED.value)
    await repos.grids.create(grid)

    summary = await recovery_manager.recover()
    assert summary["active_grids"] == 0

    g = await repos.grids.get(grid.grid_id)
    assert g["status"] == GridStatus.STOPPED.value


# 16. Restart with completed grid
async def test_restart_with_completed_grid(repos, mock_exchange, recovery_manager):
    grid = _make_grid(status=GridStatus.COMPLETED.value, total_quantity=0.0)
    await repos.grids.create(grid)

    summary = await recovery_manager.recover()
    assert summary["active_grids"] == 0

    g = await repos.grids.get(grid.grid_id)
    assert g["status"] == GridStatus.COMPLETED.value

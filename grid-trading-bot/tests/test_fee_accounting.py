"""Fee-accounting regressions for live trading fills."""

from __future__ import annotations

import pytest

from config.constants import GridStatus, OrderStatus
from exchange.base import ExchangeOrder, Trade
from storage.models import DCAGridRecord, OrderRecord
from utils.helpers import new_id, now_iso

pytestmark = pytest.mark.anyio


def _make_grid(
    *,
    total_investment: float = 0.0,
    total_quantity: float = 0.0,
    average_entry_price: float = 0.0,
    realized_profit: float = 0.0,
    completed_cycles: int = 0,
    status: str = GridStatus.ACTIVE.value,
) -> DCAGridRecord:
    now = now_iso()
    return DCAGridRecord(
        grid_id=new_id("grd"),
        symbol="BTCINR",
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
        total_quantity=total_quantity,
        total_investment=total_investment,
        average_entry_price=average_entry_price,
        last_buy_price=54000.0,
        next_buy_price=51300.0,
        next_sell_price=57780.0,
        realized_profit=realized_profit,
        completed_cycles=completed_cycles,
        created_at=now,
        updated_at=now,
    )


def _make_order(grid_id: str, side: str, exchange_order_id: str) -> OrderRecord:
    now = now_iso()
    return OrderRecord(
        order_id=new_id("ord"),
        grid_id=grid_id,
        exchange_order_id=exchange_order_id,
        symbol="BTCINR",
        side=side,
        order_type="market_order",
        price=54000.0,
        quantity=0.01,
        filled_quantity=0.0,
        filled_price=0.0,
        status=OrderStatus.OPEN.value,
        created_at=now,
        updated_at=now,
    )


async def _sync_filled_order(
    dca_manager,
    order_id: str,
    exchange_order_id: str,
    fee: float,
    side: str,
) -> None:
    dca_manager._order_manager._exchange.status_overrides[exchange_order_id] = ExchangeOrder(
        exchange_order_id=exchange_order_id,
        symbol="BTCINR",
        side=side,
        price=54000.0,
        quantity=0.01,
        filled_quantity=0.01,
        filled_price=54000.0,
        fee=fee,
        status=OrderStatus.FILLED.value,
        raw_status="filled",
    )
    await dca_manager._order_manager.sync_order_status(order_id)


async def test_buy_fee_only_updates_investment_and_trade_history(dca_manager, repos):
    grid = _make_grid()
    await repos.grids.create(grid)
    order = _make_order(grid.grid_id, "buy", "EXBUY1")
    await repos.orders.create(order)

    await _sync_filled_order(dca_manager, order.order_id, "EXBUY1", 0.75, "buy")
    await dca_manager.handle_order_filled(order.order_id, fill_price=54000.0, fill_qty=0.01)

    updated = await repos.grids.get(grid.grid_id)
    assert updated["total_investment"] == pytest.approx(540.75)

    db_order = await repos.orders.get(order.order_id)
    assert db_order["fee"] == pytest.approx(0.75)

    trades = await repos.trade_history.list_for_grid(grid.grid_id)
    assert trades[0]["fee"] == pytest.approx(0.75)
    assert trades[0]["investment_inr"] == pytest.approx(540.75)


async def test_sell_fee_only_net_pnl_is_lower(dca_manager, repos):
    grid = _make_grid(
        total_investment=500.0,
        total_quantity=0.01,
        average_entry_price=50000.0,
    )
    await repos.grids.create(grid)
    order = _make_order(grid.grid_id, "sell", "EXSELL1")
    await repos.orders.create(order)

    await _sync_filled_order(dca_manager, order.order_id, "EXSELL1", 0.60, "sell")
    await dca_manager.handle_order_filled(order.order_id, fill_price=55000.0, fill_qty=0.01)

    updated = await repos.grids.get(grid.grid_id)
    assert updated["realized_profit"] == pytest.approx(49.4)

    trades = await repos.trade_history.list_for_grid(grid.grid_id)
    assert trades[0]["fee"] == pytest.approx(0.60)
    assert trades[0]["pnl"] == pytest.approx(49.4)
    assert trades[0]["investment_inr"] == pytest.approx(549.4)


async def test_both_fees_are_applied(dca_manager, repos):
    grid = _make_grid(
        total_investment=500.0,
        total_quantity=0.01,
        average_entry_price=50000.0,
    )
    await repos.grids.create(grid)

    buy = _make_order(grid.grid_id, "buy", "EXBUY2")
    await repos.orders.create(buy)
    await _sync_filled_order(dca_manager, buy.order_id, "EXBUY2", 0.50, "buy")
    await dca_manager.handle_order_filled(buy.order_id, fill_price=50000.0, fill_qty=0.01)

    sell = _make_order(grid.grid_id, "sell", "EXSELL2")
    await repos.orders.create(sell)
    await _sync_filled_order(dca_manager, sell.order_id, "EXSELL2", 0.40, "sell")
    await dca_manager.handle_order_filled(sell.order_id, fill_price=55000.0, fill_qty=0.01)

    updated = await repos.grids.get(grid.grid_id)
    assert updated["realized_profit"] == pytest.approx(49.1)


async def test_zero_fees_remain_safe(dca_manager, repos):
    grid = _make_grid()
    await repos.grids.create(grid)
    order = _make_order(grid.grid_id, "buy", "EXBUY0")
    await repos.orders.create(order)

    await _sync_filled_order(dca_manager, order.order_id, "EXBUY0", 0.0, "buy")
    await dca_manager.handle_order_filled(order.order_id, fill_price=54000.0, fill_qty=0.01)

    updated = await repos.grids.get(grid.grid_id)
    assert updated["total_investment"] == pytest.approx(540.0)
    trades = await repos.trade_history.list_for_grid(grid.grid_id)
    assert trades[0]["fee"] == pytest.approx(0.0)


async def test_multiple_partial_fills_aggregate_fees(dca_manager, repos, mock_exchange):
    grid = _make_grid(
        total_investment=500.0,
        total_quantity=0.01,
        average_entry_price=50000.0,
    )
    await repos.grids.create(grid)
    order = _make_order(grid.grid_id, "sell", "EXPARTIAL1")
    await repos.orders.create(order)

    async def _history(symbol: str | None = None, limit: int = 50, order_id: str | None = None):
        return [
            Trade(exchange_order_id="EXPARTIAL1", symbol="BTCINR", side="sell", price=55000.0, quantity=0.004, fee=0.20, executed_at=now_iso()),
            Trade(exchange_order_id="EXPARTIAL1", symbol="BTCINR", side="sell", price=55000.0, quantity=0.006, fee=0.35, executed_at=now_iso()),
        ]

    mock_exchange.get_trade_history = _history  # type: ignore[method-assign]
    await dca_manager.handle_order_filled(order.order_id, fill_price=55000.0, fill_qty=0.01)

    updated = await repos.grids.get(grid.grid_id)
    assert updated["realized_profit"] == pytest.approx(49.45)

    db_order = await repos.orders.get(order.order_id)
    assert db_order["fee"] == pytest.approx(0.55)


async def test_missing_fee_history_falls_back_to_zero(dca_manager, repos, mock_exchange):
    grid = _make_grid()
    await repos.grids.create(grid)
    order = _make_order(grid.grid_id, "buy", "EXLEGACY0")
    await repos.orders.create(order)

    async def _empty_history(symbol: str | None = None, limit: int = 50, order_id: str | None = None):
        return []

    mock_exchange.get_trade_history = _empty_history  # type: ignore[method-assign]
    await dca_manager.handle_order_filled(order.order_id, fill_price=54000.0, fill_qty=0.01)

    updated = await repos.grids.get(grid.grid_id)
    assert updated["total_investment"] == pytest.approx(540.0)
    db_order = await repos.orders.get(order.order_id)
    assert db_order["fee"] == pytest.approx(0.0)

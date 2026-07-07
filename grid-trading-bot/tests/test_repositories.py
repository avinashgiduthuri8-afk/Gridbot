"""Integration tests exercising the DCA SQLite repositories end-to-end."""

from __future__ import annotations

import pytest

from storage.models import DCAGridRecord, OrderRecord, TradeHistoryRecord
from utils.helpers import new_id, now_iso


def _make_grid(symbol: str = "BTCINR", status: str = "active") -> DCAGridRecord:
    now = now_iso()
    return DCAGridRecord(
        grid_id=new_id("grd"),
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
        current_level=0,
        total_quantity=0.0,
        total_investment=0.0,
        average_entry_price=0.0,
        last_buy_price=54000.0,
        next_buy_price=0.0,
        next_sell_price=0.0,
        realized_profit=0.0,
        completed_cycles=0,
        created_at=now,
        updated_at=now,
    )


def _make_order(grid_id: str, side: str = "buy", status: str = "pending") -> OrderRecord:
    now = now_iso()
    return OrderRecord(
        order_id=new_id("ord"),
        grid_id=grid_id,
        exchange_order_id=None,
        symbol="BTCINR",
        side=side,
        order_type="market_order",
        price=54000.0,
        quantity=0.01,
        filled_quantity=0.0,
        filled_price=0.0,
        status=status,
        created_at=now,
        updated_at=now,
    )


# ------------------------------------------------------------------
# DCAGridRepository
# ------------------------------------------------------------------


@pytest.mark.anyio
async def test_grid_create_and_fetch(repos):
    grid = _make_grid()
    await repos.grids.create(grid)
    fetched = await repos.grids.get(grid.grid_id)
    assert fetched is not None
    assert fetched["symbol"] == "BTCINR"
    assert fetched["status"] == "active"


@pytest.mark.anyio
async def test_list_by_status_filters_correctly(repos):
    g1 = _make_grid("BTCINR", "active")
    g2 = _make_grid("ETHINR", "paused")
    g3 = _make_grid("SOLINR", "stopped")
    for g in [g1, g2, g3]:
        await repos.grids.create(g)

    active = await repos.grids.list_by_status(["active"])
    assert len(active) == 1
    assert active[0]["symbol"] == "BTCINR"

    active_paused = await repos.grids.list_by_status(["active", "paused"])
    assert len(active_paused) == 2


@pytest.mark.anyio
async def test_update_status(repos):
    grid = _make_grid()
    await repos.grids.create(grid)
    await repos.grids.update_status(grid.grid_id, "paused")
    fetched = await repos.grids.get(grid.grid_id)
    assert fetched["status"] == "paused"


@pytest.mark.anyio
async def test_update_state_partial(repos):
    grid = _make_grid()
    await repos.grids.create(grid)
    await repos.grids.update_state(
        grid.grid_id,
        current_level=1,
        average_entry_price=54100.0,
        total_quantity=0.00924,
        total_investment=500.0,
        next_buy_price=51395.0,
        next_sell_price=57887.0,
    )
    fetched = await repos.grids.get(grid.grid_id)
    assert fetched["current_level"] == 1
    assert fetched["average_entry_price"] == pytest.approx(54100.0)
    assert fetched["next_buy_price"] == pytest.approx(51395.0)
    assert fetched["entry_price"] == pytest.approx(54000.0)  # unchanged


@pytest.mark.anyio
async def test_get_active_by_symbol(repos):
    grid = _make_grid("SOLINR")
    await repos.grids.create(grid)
    found = await repos.grids.get_active_by_symbol("SOLINR")
    assert found is not None
    assert found["symbol"] == "SOLINR"

    not_found = await repos.grids.get_active_by_symbol("BTCINR")
    assert not_found is None


@pytest.mark.anyio
async def test_list_all_returns_all(repos):
    for symbol in ["BTCINR", "ETHINR", "SOLINR"]:
        await repos.grids.create(_make_grid(symbol))
    all_grids = await repos.grids.list_all()
    assert len(all_grids) == 3


# ------------------------------------------------------------------
# OrderRepository
# ------------------------------------------------------------------


@pytest.mark.anyio
async def test_order_create_and_list_open(repos):
    grid = _make_grid()
    await repos.grids.create(grid)
    order = _make_order(grid.grid_id)
    await repos.orders.create(order)

    open_orders = await repos.orders.list_open()
    assert len(open_orders) == 1
    assert open_orders[0]["order_id"] == order.order_id


@pytest.mark.anyio
async def test_order_not_listed_after_fill(repos):
    grid = _make_grid()
    await repos.grids.create(grid)
    order = _make_order(grid.grid_id)
    await repos.orders.create(order)
    await repos.orders.update_status(order.order_id, "filled", filled_quantity=0.01, filled_price=54100.0)

    open_orders = await repos.orders.list_open()
    assert len(open_orders) == 0


@pytest.mark.anyio
async def test_count_pending_side(repos):
    grid = _make_grid()
    await repos.grids.create(grid)
    buy1 = _make_order(grid.grid_id, "buy", "pending")
    buy2 = _make_order(grid.grid_id, "buy", "open")
    sell1 = _make_order(grid.grid_id, "sell", "pending")
    for o in [buy1, buy2, sell1]:
        await repos.orders.create(o)

    assert await repos.orders.count_pending_side(grid.grid_id, "buy") == 2
    assert await repos.orders.count_pending_side(grid.grid_id, "sell") == 1


@pytest.mark.anyio
async def test_update_order_status_with_fill(repos):
    grid = _make_grid()
    await repos.grids.create(grid)
    order = _make_order(grid.grid_id)
    await repos.orders.create(order)
    await repos.orders.update_status(
        order.order_id, "filled",
        exchange_order_id="EX999",
        filled_quantity=0.01,
        filled_price=54050.0,
    )
    fetched = await repos.orders.get(order.order_id)
    assert fetched["status"] == "filled"
    assert fetched["exchange_order_id"] == "EX999"
    assert fetched["filled_price"] == pytest.approx(54050.0)


# ------------------------------------------------------------------
# TradeHistoryRepository
# ------------------------------------------------------------------


@pytest.mark.anyio
async def test_trade_record_and_fetch(repos):
    grid = _make_grid()
    await repos.grids.create(grid)
    trade = TradeHistoryRecord(
        trade_id=new_id("trd"),
        grid_id=grid.grid_id,
        order_id=new_id("ord"),
        symbol="BTCINR",
        side="buy",
        price=54000.0,
        quantity=0.00924,
        investment_inr=500.0,
        fee=0.0,
        pnl=0.0,
        executed_at=now_iso(),
    )
    await repos.trade_history.record(trade)
    trades = await repos.trade_history.list_for_grid(grid.grid_id)
    assert len(trades) == 1
    assert trades[0]["investment_inr"] == pytest.approx(500.0)


@pytest.mark.anyio
async def test_total_realized_pnl(repos):
    grid = _make_grid()
    await repos.grids.create(grid)
    for pnl in [25.0, -10.0, 50.0]:
        await repos.trade_history.record(
            TradeHistoryRecord(
                trade_id=new_id("trd"),
                grid_id=grid.grid_id,
                order_id=new_id("ord"),
                symbol="BTCINR",
                side="sell",
                price=55000.0,
                quantity=0.001,
                investment_inr=55.0,
                fee=0.0,
                pnl=pnl,
                executed_at=now_iso(),
            )
        )
    total = await repos.trade_history.total_realized_pnl()
    assert total == pytest.approx(65.0)


# ------------------------------------------------------------------
# DailyStatsRepository
# ------------------------------------------------------------------


@pytest.mark.anyio
async def test_daily_stats_accumulate(repos):
    await repos.daily_stats.add_trade("2026-07-07", 100.0)
    await repos.daily_stats.add_trade("2026-07-07", -30.0)
    stats = await repos.daily_stats.get("2026-07-07")
    assert stats["realized_pnl"] == pytest.approx(70.0)
    assert stats["trades_count"] == 2


@pytest.mark.anyio
async def test_daily_stats_separate_dates(repos):
    await repos.daily_stats.add_trade("2026-07-06", 50.0)
    await repos.daily_stats.add_trade("2026-07-07", 20.0)
    stats_6 = await repos.daily_stats.get("2026-07-06")
    stats_7 = await repos.daily_stats.get("2026-07-07")
    assert stats_6["realized_pnl"] == pytest.approx(50.0)
    assert stats_7["realized_pnl"] == pytest.approx(20.0)

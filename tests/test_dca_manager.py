"""Integration tests for DCAManager using in-memory DB and MockExchange."""

from __future__ import annotations

import asyncio

import pytest

from config.constants import GridStatus, OrderStatus
from config.settings import RiskSettings
from risk.risk_manager import RiskManager
from storage.models import DCAGridRecord, OrderRecord
from trading.dca_manager import DCAManager
from trading.order_manager import OrderManager
from utils.helpers import new_id, now_iso


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _default_params(symbol: str = "BTCINR") -> dict:
    return {
        "symbol": symbol,
        "entry_price": 54000.0,
        "base_investment": 500.0,
        "dip_buy_amount": 100.0,
        "dip_percentage": 5.0,
        "profit_sell_amount": 150.0,
        "profit_percentage": 7.0,
        "max_levels": 10,
        "stop_loss_percentage": 50.0,
    }


def _make_active_grid(grid_id: str, symbol: str = "BTCINR") -> DCAGridRecord:
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


def _make_order_record(
    grid_id: str,
    side: str = "buy",
    status: str = OrderStatus.PENDING.value,
    exchange_order_id: str | None = None,
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


# ---------------------------------------------------------------------------
# start_grid
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_start_grid_creates_db_record(dca_manager, repos):
    grid_id = await dca_manager.start_grid(_default_params())
    grid = await repos.grids.get(grid_id)
    assert grid is not None
    assert grid["symbol"] == "BTCINR"
    assert grid["status"] == GridStatus.ACTIVE.value
    assert grid["entry_price"] == pytest.approx(54000.0)


@pytest.mark.anyio
async def test_start_grid_places_initial_order(dca_manager, repos, mock_exchange):
    await dca_manager.start_grid(_default_params())
    assert len(mock_exchange.orders_placed) == 1
    assert mock_exchange.orders_placed[0].side == "buy"


@pytest.mark.anyio
async def test_start_grid_market_price_uses_ticker(dca_manager, repos, mock_exchange):
    params = _default_params()
    params["entry_price"] = 0  # use market price
    mock_exchange.ticker_price = 56000.0
    await dca_manager.start_grid(params)
    grid_list = await repos.grids.list_by_status(["active"])
    assert len(grid_list) == 1
    assert grid_list[0]["entry_price"] == pytest.approx(56000.0)


@pytest.mark.anyio
async def test_start_grid_sends_notification(dca_manager, mock_notifier):
    await dca_manager.start_grid(_default_params())
    assert mock_notifier.was_called("grid_started")


@pytest.mark.anyio
async def test_start_grid_rejected_by_risk_blocks_exchange_call(
    repos, mock_exchange, order_manager, mock_notifier
):
    strict_risk = RiskSettings(
        max_total_capital=0,
        max_capital_per_coin=0,
        max_simultaneous_grids=0,
        min_wallet_balance=0,
        daily_loss_limit=1_000_000,
    )
    risk = RiskManager(strict_risk, repos)
    manager = DCAManager(
        exchange=mock_exchange,
        repos=repos,
        order_manager=order_manager,
        notifier=mock_notifier,
        risk=risk,
    )
    with pytest.raises(ValueError):
        await manager.start_grid(_default_params())
    assert len(mock_exchange.orders_placed) == 0


@pytest.mark.anyio
async def test_start_grid_exchange_failure_rolls_back_grid(
    dca_manager, repos, mock_exchange
):
    """On order failure the grid row must be deleted entirely — not left as STOPPED."""
    mock_exchange.fail_on_place = True
    with pytest.raises(ValueError, match="Exchange rejected"):
        await dca_manager.start_grid(_default_params())
    all_grids = await repos.grids.list_all()
    assert len(all_grids) == 0, "Grid row should be deleted after a failed start"


# ---------------------------------------------------------------------------
# pause / resume
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_pause_active_grid(dca_manager, repos):
    grid_id = await dca_manager.start_grid(_default_params())
    await dca_manager.pause_grid(grid_id)
    grid = await repos.grids.get(grid_id)
    assert grid["status"] == GridStatus.PAUSED.value


@pytest.mark.anyio
async def test_pause_non_active_grid_raises(dca_manager, repos):
    grid_id = await dca_manager.start_grid(_default_params())
    await dca_manager.pause_grid(grid_id)
    with pytest.raises(ValueError, match="not active"):
        await dca_manager.pause_grid(grid_id)


@pytest.mark.anyio
async def test_resume_paused_grid(dca_manager, repos):
    grid_id = await dca_manager.start_grid(_default_params())
    await dca_manager.pause_grid(grid_id)
    await dca_manager.resume_grid(grid_id)
    grid = await repos.grids.get(grid_id)
    assert grid["status"] == GridStatus.ACTIVE.value


@pytest.mark.anyio
async def test_resume_non_paused_grid_raises(dca_manager, repos):
    grid_id = await dca_manager.start_grid(_default_params())
    with pytest.raises(ValueError, match="not paused"):
        await dca_manager.resume_grid(grid_id)


# ---------------------------------------------------------------------------
# stop_grid
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_stop_grid_marks_stopped(dca_manager, repos):
    grid_id = await dca_manager.start_grid(_default_params())
    await dca_manager.stop_grid(grid_id, reason="test")
    grid = await repos.grids.get(grid_id)
    assert grid["status"] == GridStatus.STOPPED.value


@pytest.mark.anyio
async def test_stop_grid_cancels_all_pending_orders(dca_manager, repos, mock_exchange):
    grid_id = await dca_manager.start_grid(_default_params())
    buy_order = _make_order_record(grid_id, "buy", OrderStatus.OPEN.value, "EXBUY")
    sell_order = _make_order_record(grid_id, "sell", OrderStatus.OPEN.value, "EXSELL")
    await repos.orders.create(buy_order)
    await repos.orders.create(sell_order)
    await dca_manager.stop_grid(grid_id, reason="test")
    assert "EXBUY" in mock_exchange.cancelled
    assert "EXSELL" in mock_exchange.cancelled


@pytest.mark.anyio
async def test_stop_already_stopped_grid_is_idempotent(dca_manager, repos):
    grid_id = await dca_manager.start_grid(_default_params())
    await dca_manager.stop_grid(grid_id)
    await dca_manager.stop_grid(grid_id)
    grid = await repos.grids.get(grid_id)
    assert grid["status"] == GridStatus.STOPPED.value


# ---------------------------------------------------------------------------
# handle_order_filled — buy fill
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_handle_buy_filled_updates_position(dca_manager, repos):
    grid = _make_active_grid(new_id("grd"))
    await repos.grids.create(grid)
    order = _make_order_record(grid.grid_id, "buy", OrderStatus.OPEN.value, "EX001")
    order.order_id = new_id("ord")
    await repos.orders.create(order)

    await dca_manager.handle_order_filled(order.order_id, fill_price=54000.0, fill_qty=0.00185)

    updated = await repos.grids.get(grid.grid_id)
    assert updated["current_level"] == 2
    assert updated["total_quantity"] > grid.total_quantity
    assert updated["next_buy_price"] == pytest.approx(54000.0 * 0.95)
    assert updated["next_sell_price"] > 0


@pytest.mark.anyio
async def test_handle_buy_filled_records_trade_history(dca_manager, repos):
    grid = _make_active_grid(new_id("grd"))
    await repos.grids.create(grid)
    order = _make_order_record(grid.grid_id, "buy", OrderStatus.OPEN.value, "EX002")
    await repos.orders.create(order)

    await dca_manager.handle_order_filled(order.order_id, fill_price=54000.0, fill_qty=0.001)

    trades = await repos.trade_history.list_for_grid(grid.grid_id)
    assert len(trades) == 1
    assert trades[0]["side"] == "buy"


# ---------------------------------------------------------------------------
# handle_order_filled — sell fill
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_handle_sell_filled_records_pnl(dca_manager, repos):
    grid = _make_active_grid(new_id("grd"))
    await repos.grids.create(grid)
    sell_order = _make_order_record(grid.grid_id, "sell", OrderStatus.OPEN.value, "EX003")
    await repos.orders.create(sell_order)

    sell_price = 57780.0
    sell_qty = 0.00277
    await dca_manager.handle_order_filled(sell_order.order_id, fill_price=sell_price, fill_qty=sell_qty)

    updated = await repos.grids.get(grid.grid_id)
    expected_pnl = sell_qty * (sell_price - grid.average_entry_price)
    assert updated["realized_profit"] == pytest.approx(expected_pnl, rel=1e-4)
    assert updated["completed_cycles"] == 1


@pytest.mark.anyio
async def test_handle_sell_filled_full_position_marks_completed(dca_manager, repos):
    grid = _make_active_grid(new_id("grd"))
    await repos.grids.create(grid)
    sell_order = _make_order_record(grid.grid_id, "sell", OrderStatus.OPEN.value, "EX004")
    await repos.orders.create(sell_order)

    await dca_manager.handle_order_filled(
        sell_order.order_id,
        fill_price=57780.0,
        fill_qty=grid.total_quantity,
    )

    updated = await repos.grids.get(grid.grid_id)
    assert updated["status"] == GridStatus.COMPLETED.value
    assert updated["total_quantity"] == pytest.approx(0.0)


# ---------------------------------------------------------------------------
# check_grid_triggers
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_check_triggers_skips_paused_grid(dca_manager, repos, mock_exchange):
    grid = _make_active_grid(new_id("grd"))
    grid.status = GridStatus.PAUSED.value
    await repos.grids.create(grid)

    before = len(mock_exchange.orders_placed)
    await dca_manager.check_grid_triggers(grid.grid_id, 40000.0)
    assert len(mock_exchange.orders_placed) == before


@pytest.mark.anyio
async def test_check_triggers_skips_level_zero_grid(dca_manager, repos, mock_exchange):
    grid = _make_active_grid(new_id("grd"))
    grid.current_level = 0
    await repos.grids.create(grid)

    before = len(mock_exchange.orders_placed)
    await dca_manager.check_grid_triggers(grid.grid_id, 40000.0)
    assert len(mock_exchange.orders_placed) == before


@pytest.mark.anyio
async def test_check_triggers_dip_buy_fires(dca_manager, repos, mock_exchange):
    grid = _make_active_grid(new_id("grd"))
    await repos.grids.create(grid)

    before = len(mock_exchange.orders_placed)
    await dca_manager.check_grid_triggers(grid.grid_id, 51000.0)
    assert len(mock_exchange.orders_placed) == before + 1
    assert mock_exchange.orders_placed[-1].side == "buy"


@pytest.mark.anyio
async def test_check_triggers_profit_sell_fires(dca_manager, repos, mock_exchange):
    grid = _make_active_grid(new_id("grd"))
    await repos.grids.create(grid)

    before = len(mock_exchange.orders_placed)
    await dca_manager.check_grid_triggers(grid.grid_id, 58000.0)
    assert len(mock_exchange.orders_placed) == before + 1
    assert mock_exchange.orders_placed[-1].side == "sell"


@pytest.mark.anyio
async def test_check_triggers_stop_loss_fires(dca_manager, repos, mock_exchange):
    grid = _make_active_grid(new_id("grd"))
    await repos.grids.create(grid)

    before = len(mock_exchange.orders_placed)
    await dca_manager.check_grid_triggers(grid.grid_id, 26000.0)
    assert len(mock_exchange.orders_placed) == before + 1
    assert mock_exchange.orders_placed[-1].side == "sell"

    updated = await repos.grids.get(grid.grid_id)
    assert updated["status"] == GridStatus.STOPPED.value


@pytest.mark.anyio
async def test_check_triggers_no_duplicate_buy_when_one_pending(dca_manager, repos, mock_exchange):
    grid = _make_active_grid(new_id("grd"))
    await repos.grids.create(grid)
    pending_buy = _make_order_record(grid.grid_id, "buy", OrderStatus.OPEN.value)
    await repos.orders.create(pending_buy)

    before = len(mock_exchange.orders_placed)
    await dca_manager.check_grid_triggers(grid.grid_id, 51000.0)
    assert len(mock_exchange.orders_placed) == before


@pytest.mark.anyio
async def test_check_triggers_no_duplicate_sell_when_one_pending(dca_manager, repos, mock_exchange):
    grid = _make_active_grid(new_id("grd"))
    await repos.grids.create(grid)
    pending_sell = _make_order_record(grid.grid_id, "sell", OrderStatus.OPEN.value)
    await repos.orders.create(pending_sell)

    before = len(mock_exchange.orders_placed)
    await dca_manager.check_grid_triggers(grid.grid_id, 58000.0)
    assert len(mock_exchange.orders_placed) == before


@pytest.mark.anyio
async def test_check_triggers_max_levels_prevents_dip_buy(dca_manager, repos, mock_exchange):
    grid = _make_active_grid(new_id("grd"))
    grid.current_level = grid.max_levels
    await repos.grids.create(grid)

    before = len(mock_exchange.orders_placed)
    await dca_manager.check_grid_triggers(grid.grid_id, 51000.0)
    assert len(mock_exchange.orders_placed) == before


# ---------------------------------------------------------------------------
# Regression: _execute_stop_loss's synchronous-fill path must not deadlock
# on the per-grid asyncio.Lock already held by check_grid_triggers().
#
# Root cause (fixed): _execute_stop_loss(), called from inside
# check_grid_triggers()'s `async with self._grid_lock(grid_id):` block,
# used to call the public handle_order_filled() when the exchange returned
# an immediate FILLED status. handle_order_filled() itself acquires the
# same per-grid lock — asyncio.Lock is not reentrant, so that coroutine
# blocked forever. In production this freezes PriceMonitor's entire tick
# loop, since it awaits check_grid_triggers() sequentially per grid.
#
# Every test below wraps the call in asyncio.wait_for() with a short
# timeout so a regression fails fast with a clear TimeoutError instead of
# hanging the whole suite again.
# ---------------------------------------------------------------------------

@pytest.mark.anyio
async def test_stop_loss_synchronous_fill_does_not_deadlock(dca_manager, repos, mock_exchange):
    """The exact scenario that used to hang forever: MockExchange's default
    place_order() returns FILLED immediately, so _execute_stop_loss() takes
    the synchronous-fill branch while still holding check_grid_triggers()'s
    per-grid lock."""
    grid = _make_active_grid(new_id("grd"))
    await repos.grids.create(grid)

    # 50% stop-loss from avg_entry 54000 triggers at/below 27000.
    await asyncio.wait_for(
        dca_manager.check_grid_triggers(grid.grid_id, 26000.0), timeout=5.0
    )

    assert len(mock_exchange.orders_placed) == 1
    assert mock_exchange.orders_placed[-1].side == "sell"
    assert mock_exchange.orders_placed[-1].status == OrderStatus.FILLED.value

    updated = await repos.grids.get(grid.grid_id)
    assert updated["status"] == GridStatus.STOPPED.value, (
        "synchronous fill must finalize the grid to STOPPED, not leave it STOPPING"
    )
    assert updated["total_quantity"] == 0.0


@pytest.mark.anyio
async def test_stop_loss_synchronous_fill_records_trade_history_once(dca_manager, repos, mock_exchange):
    """The fill applied by _handle_order_filled_locked() during the
    synchronous-fill path must be recorded exactly once — proving the
    lock-splitting refactor didn't also break the idempotency guard that
    normally lives inside handle_order_filled()."""
    grid = _make_active_grid(new_id("grd"))
    await repos.grids.create(grid)

    await asyncio.wait_for(
        dca_manager.check_grid_triggers(grid.grid_id, 26000.0), timeout=5.0
    )

    trades = await repos.trade_history.list_for_grid(grid.grid_id)
    sell_trades = [t for t in trades if t["side"] == "sell"]
    assert len(sell_trades) == 1, "the synchronous fill must be recorded exactly once"

    # A later, external call to the PUBLIC handle_order_filled() for the same
    # order (e.g. OrderMonitor's reconciliation pass picking it up again)
    # must be a safe no-op, not a double-apply and not a second deadlock.
    filled_order_id = sell_trades[0]["order_id"]
    await asyncio.wait_for(
        dca_manager.handle_order_filled(filled_order_id, fill_price=26000.0, fill_qty=grid.total_quantity),
        timeout=5.0,
    )
    trades_after = await repos.trade_history.list_for_grid(grid.grid_id)
    assert len([t for t in trades_after if t["side"] == "sell"]) == 1, (
        "re-processing the same fill externally must not double-apply"
    )


@pytest.mark.anyio
async def test_stop_loss_non_synchronous_fill_still_marks_grid_stopping(dca_manager, repos, mock_exchange):
    """Control case: when the exchange does NOT fill immediately (e.g. a
    real limit/market order still working), the grid must be marked
    STOPPING (not STOPPED) and wait for a later handle_order_filled() call
    from OrderMonitor/RecoveryManager — this path was never part of the
    deadlock and must be completely unaffected by the fix."""
    grid = _make_active_grid(new_id("grd"))
    await repos.grids.create(grid)
    # Any value < full quantity makes MockExchange return PARTIALLY_FILLED
    # instead of FILLED, exercising the non-synchronous branch.
    mock_exchange.partial_fill_qty = 0.0001

    await asyncio.wait_for(
        dca_manager.check_grid_triggers(grid.grid_id, 26000.0), timeout=5.0
    )

    mid_state = await repos.grids.get(grid.grid_id)
    assert mid_state["status"] == GridStatus.STOPPING.value
    assert mid_state["total_quantity"] > 0, "holdings must not be zeroed until the fill is confirmed"

    # Now simulate OrderMonitor confirming the fill later, via the public,
    # lock-acquiring handle_order_filled() — this must complete normally.
    orders = await repos.orders.list_for_grid(grid.grid_id)
    sell_order = next(o for o in orders if o["side"] == "sell")
    await asyncio.wait_for(
        dca_manager.handle_order_filled(
            sell_order["order_id"], fill_price=26000.0, fill_qty=grid.total_quantity
        ),
        timeout=5.0,
    )

    final_state = await repos.grids.get(grid.grid_id)
    assert final_state["status"] == GridStatus.STOPPED.value
    assert final_state["total_quantity"] == 0.0


@pytest.mark.anyio
async def test_stop_loss_synchronous_fill_zero_remainder_and_order_state(dca_manager, repos, mock_exchange):
    """Explicit zero-remainder + order-state check for the synchronous
    stop-loss path: total_quantity/total_investment must be fully zeroed,
    realized_profit and completed_cycles must be updated exactly once, and
    the underlying order record must be marked FILLED — proving the
    STOPPING-before-fill fix didn't disturb order-state handling."""
    grid = _make_active_grid(new_id("grd"))
    await repos.grids.create(grid)

    await asyncio.wait_for(
        dca_manager.check_grid_triggers(grid.grid_id, 26000.0), timeout=5.0
    )

    final = await repos.grids.get(grid.grid_id)
    assert final["status"] == GridStatus.STOPPED.value
    assert final["total_quantity"] == 0.0
    assert final["total_investment"] == 0.0
    assert final["completed_cycles"] == 1

    orders = await repos.orders.list_for_grid(grid.grid_id)
    sell_order = next(o for o in orders if o["side"] == "sell")
    assert sell_order["status"] == OrderStatus.FILLED.value



    """Sanity check that normal (non-stop-loss) trigger handling — which
    never called handle_order_filled from inside the lock — behaves
    identically after the fix. Guards against the refactor accidentally
    touching call sites it shouldn't have."""
    grid = _make_active_grid(new_id("grd"))
    await repos.grids.create(grid)

    await asyncio.wait_for(dca_manager.check_grid_triggers(grid.grid_id, 51000.0), timeout=5.0)
    assert mock_exchange.orders_placed[-1].side == "buy"
    dip_order = next(
        o for o in await repos.orders.list_for_grid(grid.grid_id) if o["side"] == "buy"
    )
    await asyncio.wait_for(
        dca_manager.handle_order_filled(dip_order["order_id"], fill_price=51000.0, fill_qty=0.001),
        timeout=5.0,
    )

    await asyncio.wait_for(dca_manager.check_grid_triggers(grid.grid_id, 58000.0), timeout=5.0)
    assert mock_exchange.orders_placed[-1].side == "sell"

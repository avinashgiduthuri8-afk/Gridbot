"""Integration tests for DCAManager using in-memory DB and MockExchange."""

from __future__ import annotations

import pytest

from config.constants import GridStatus, OrderStatus
from config.settings import RiskSettings
from exchange.exceptions import ExchangeTimeoutError
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


@pytest.mark.anyio
async def test_start_grid_timeout_preserves_grid_and_uncertain_order(
    dca_manager, repos, mock_exchange
):
    mock_exchange.place_exception = ExchangeTimeoutError("timed out after acceptance")

    with pytest.raises(ExchangeTimeoutError):
        await dca_manager.start_grid(_default_params())

    grids = await repos.grids.list_all()
    assert len(grids) == 1
    assert grids[0]["status"] == GridStatus.ACTIVE.value

    orders = await repos.orders.list_all()
    assert len(orders) == 1
    assert orders[0]["status"] == OrderStatus.UNKNOWN.value
    assert orders[0]["client_order_id"] == orders[0]["order_id"]


@pytest.mark.anyio
async def test_start_grid_db_persistence_failure_keeps_exchange_submission_tracked(
    dca_manager, repos, mock_exchange
):
    original_update_status = repos.orders.update_status
    call_count = 0

    async def flaky_update_status(*args, **kwargs):
        nonlocal call_count
        call_count += 1
        if call_count == 2:
            raise RuntimeError("simulated DB failure after exchange acceptance")
        return await original_update_status(*args, **kwargs)

    repos.orders.update_status = flaky_update_status  # type: ignore[method-assign]

    grid_id = await dca_manager.start_grid(_default_params())

    grids = await repos.grids.list_all()
    assert len(grids) == 1
    assert grids[0]["grid_id"] == grid_id

    orders = await repos.orders.list_all()
    assert len(orders) == 1
    assert orders[0]["grid_id"] == grid_id
    assert orders[0]["client_order_id"] == orders[0]["order_id"]
    assert orders[0]["status"] == OrderStatus.SUBMITTED.value
    assert orders[0]["exchange_order_id"] is None


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

"""Tests for Trailing Take-Profit: peak tracking, pullback-triggered sell,
priority vs. stop-loss, and the fixed-profit-sell fallback when trailing is
disabled."""

from __future__ import annotations

import pytest

from risk.risk_manager import RiskManager
from trading.dca_manager import DCAManager
from trading.mixed_order_manager import MixedOrderManager
from trading.order_manager import OrderManager

pytestmark = pytest.mark.anyio


async def _make_dca_manager(repos, mock_exchange, mock_notifier, permissive_risk_settings):
    risk = RiskManager(permissive_risk_settings, repos)
    await risk.load_emergency_stop()
    real_om = OrderManager(mock_exchange, repos)
    paper_om = OrderManager(mock_exchange, repos)
    mixed_om = MixedOrderManager(real=real_om, paper=paper_om, repos=repos)
    return DCAManager(
        exchange=mock_exchange, repos=repos, order_manager=mixed_om,
        notifier=mock_notifier, risk=risk,
    )


async def _start_trailing_grid(dca, repos, trailing_percentage=3.0, entry_price=100.0):
    grid_id = await dca.start_grid({
        "symbol": "BTCINR", "entry_price": entry_price, "base_investment": 500.0,
        "dip_buy_amount": 100.0, "dip_percentage": 5.0,
        "profit_sell_amount": 200.0, "profit_percentage": 5.0,
        "max_levels": 5, "stop_loss_percentage": 20.0, "mode": "real",
        "trailing_enabled": True, "trailing_percentage": trailing_percentage,
    })
    orders = await repos.orders.list_for_grid(grid_id)
    await dca.handle_order_filled(orders[0]["order_id"], fill_price=entry_price, fill_qty=orders[0]["quantity"])
    return grid_id


async def test_trailing_activates_instead_of_immediate_sell(repos, mock_exchange, mock_notifier, permissive_risk_settings):
    dca = await _make_dca_manager(repos, mock_exchange, mock_notifier, permissive_risk_settings)
    grid_id = await _start_trailing_grid(dca, repos)

    # Price crosses the profit target (avg_entry=100, profit_percentage=5% -> target=105)
    await dca.check_grid_triggers(grid_id, 106.0)

    grid = await repos.grids.get(grid_id)
    assert grid["trailing_peak_price"] == 106.0, "trailing must activate and record the peak, not sell immediately"
    orders = await repos.orders.list_for_grid(grid_id)
    sell_orders = [o for o in orders if o["side"] == "sell"]
    assert not sell_orders, "no sell should be placed the moment trailing activates"
    assert mock_notifier.was_called("trailing_activated")


async def test_trailing_peak_tracks_upward_movement(repos, mock_exchange, mock_notifier, permissive_risk_settings):
    dca = await _make_dca_manager(repos, mock_exchange, mock_notifier, permissive_risk_settings)
    grid_id = await _start_trailing_grid(dca, repos)

    await dca.check_grid_triggers(grid_id, 106.0)  # activates, peak=106
    await dca.check_grid_triggers(grid_id, 110.0)  # price keeps rising
    await dca.check_grid_triggers(grid_id, 115.0)

    grid = await repos.grids.get(grid_id)
    assert grid["trailing_peak_price"] == 115.0, "peak must update to the highest price seen"
    orders = await repos.orders.list_for_grid(grid_id)
    assert not [o for o in orders if o["side"] == "sell"], "still no sell while price keeps climbing"


async def test_trailing_sells_on_pullback_past_threshold(repos, mock_exchange, mock_notifier, permissive_risk_settings):
    dca = await _make_dca_manager(repos, mock_exchange, mock_notifier, permissive_risk_settings)
    grid_id = await _start_trailing_grid(dca, repos, trailing_percentage=3.0)

    await dca.check_grid_triggers(grid_id, 106.0)  # activate, peak=106
    await dca.check_grid_triggers(grid_id, 120.0)  # peak=120

    # Pullback of exactly 3% from 120 = 116.4 -> should trigger the sell
    await dca.check_grid_triggers(grid_id, 116.0)

    orders = await repos.orders.list_for_grid(grid_id)
    sell_orders = [o for o in orders if o["side"] == "sell"]
    assert sell_orders, "a 3%+ pullback from the peak must trigger the sell"

    grid = await repos.grids.get(grid_id)
    assert grid["trailing_peak_price"] is None, "trailing state must reset after the sell fires"


async def test_trailing_does_not_sell_within_the_band(repos, mock_exchange, mock_notifier, permissive_risk_settings):
    dca = await _make_dca_manager(repos, mock_exchange, mock_notifier, permissive_risk_settings)
    grid_id = await _start_trailing_grid(dca, repos, trailing_percentage=5.0)

    await dca.check_grid_triggers(grid_id, 106.0)  # activate, peak=106
    await dca.check_grid_triggers(grid_id, 120.0)  # peak=120

    # Pullback of only 2% from 120 = 117.6 -> must NOT trigger (band is 5%)
    await dca.check_grid_triggers(grid_id, 118.0)

    orders = await repos.orders.list_for_grid(grid_id)
    assert not [o for o in orders if o["side"] == "sell"], "must keep waiting within the trailing band"
    grid = await repos.grids.get(grid_id)
    assert grid["trailing_peak_price"] == 120.0, "peak must be unchanged (not overwritten by a lower price)"


async def test_stop_loss_takes_priority_over_active_trailing(repos, mock_exchange, mock_notifier, permissive_risk_settings):
    dca = await _make_dca_manager(repos, mock_exchange, mock_notifier, permissive_risk_settings)
    grid_id = await _start_trailing_grid(dca, repos, trailing_percentage=3.0)

    await dca.check_grid_triggers(grid_id, 106.0)  # trailing activates, peak=106

    # Crash straight through the stop-loss level (avg_entry=100, stop_loss=20% -> 80)
    await dca.check_grid_triggers(grid_id, 75.0)

    grid = await repos.grids.get(grid_id)
    assert grid["status"] == "stopped", "stop-loss must still fire and close the grid even mid-trail"


async def test_trailing_disabled_falls_back_to_immediate_profit_sell(repos, mock_exchange, mock_notifier, permissive_risk_settings):
    """Regression guard: a normal (non-trailing) grid's existing behavior
    must be completely unaffected by this feature."""
    dca = await _make_dca_manager(repos, mock_exchange, mock_notifier, permissive_risk_settings)
    grid_id = await dca.start_grid({
        "symbol": "BTCINR", "entry_price": 100.0, "base_investment": 500.0,
        "dip_buy_amount": 100.0, "dip_percentage": 5.0,
        "profit_sell_amount": 200.0, "profit_percentage": 5.0,
        "max_levels": 5, "stop_loss_percentage": 20.0, "mode": "real",
        "trailing_enabled": False,
    })
    orders = await repos.orders.list_for_grid(grid_id)
    await dca.handle_order_filled(orders[0]["order_id"], fill_price=100.0, fill_qty=orders[0]["quantity"])

    await dca.check_grid_triggers(grid_id, 106.0)  # crosses the 105 profit target

    orders_after = await repos.orders.list_for_grid(grid_id)
    sell_orders = [o for o in orders_after if o["side"] == "sell"]
    assert sell_orders, "without trailing enabled, crossing the profit target must sell immediately"
    grid = await repos.grids.get(grid_id)
    assert grid["trailing_peak_price"] is None
    assert not mock_notifier.was_called("trailing_activated")


async def test_trailing_can_reactivate_for_a_second_cycle(repos, mock_exchange, mock_notifier, permissive_risk_settings):
    """After one trailing-triggered sell completes, the next profit cycle
    must be able to trail independently rather than being stuck."""
    dca = await _make_dca_manager(repos, mock_exchange, mock_notifier, permissive_risk_settings)
    grid_id = await _start_trailing_grid(dca, repos, trailing_percentage=3.0)

    # First cycle: activate, peak, pullback -> sell
    await dca.check_grid_triggers(grid_id, 106.0)
    await dca.check_grid_triggers(grid_id, 120.0)
    await dca.check_grid_triggers(grid_id, 116.0)
    first_sell_orders = [o for o in (await repos.orders.list_for_grid(grid_id)) if o["side"] == "sell"]
    assert len(first_sell_orders) == 1

    # Fill that sell so the grid has a fresh average_entry_price/next_sell_price for cycle 2
    await dca.handle_order_filled(
        first_sell_orders[0]["order_id"], fill_price=116.0, fill_qty=first_sell_orders[0]["quantity"],
    )
    grid_after_sell = await repos.grids.get(grid_id)
    assert grid_after_sell["trailing_peak_price"] is None

    if grid_after_sell["total_quantity"] > 0:
        # Second cycle: new profit target based on the same avg entry (a sell doesn't change cost basis)
        next_target = grid_after_sell["next_sell_price"]
        await dca.check_grid_triggers(grid_id, next_target + 1.0)
        grid_cycle2 = await repos.grids.get(grid_id)
        assert grid_cycle2["trailing_peak_price"] is not None, "trailing must reactivate cleanly for the next cycle"


async def test_trailing_state_survives_process_restart(repos, mock_exchange, mock_notifier, permissive_risk_settings):
    """trailing_peak_price is a plain DB column, not in-memory state — a
    brand-new DCAManager instance (as created on every process restart)
    must pick up an already-active trailing cycle from the DB and keep
    tracking/triggering correctly, with no special recovery step needed."""
    dca_before_restart = await _make_dca_manager(repos, mock_exchange, mock_notifier, permissive_risk_settings)
    grid_id = await _start_trailing_grid(dca_before_restart, repos, trailing_percentage=3.0)

    # Activate trailing and track a peak, all before the "restart".
    await dca_before_restart.check_grid_triggers(grid_id, 106.0)
    await dca_before_restart.check_grid_triggers(grid_id, 120.0)
    grid_before = await repos.grids.get(grid_id)
    assert grid_before["trailing_peak_price"] == 120.0

    # Simulate a process restart: a completely fresh DCAManager instance,
    # same underlying repos/DB — no shared in-memory state whatsoever.
    dca_after_restart = await _make_dca_manager(repos, mock_exchange, mock_notifier, permissive_risk_settings)

    # The new instance must still see the peak already tracked...
    grid_seen_by_new_instance = await repos.grids.get(grid_id)
    assert grid_seen_by_new_instance["trailing_peak_price"] == 120.0

    # ...continue tracking a new higher peak...
    await dca_after_restart.check_grid_triggers(grid_id, 130.0)
    assert (await repos.grids.get(grid_id))["trailing_peak_price"] == 130.0

    # ...and still correctly fire the trailing-stop sell on pullback.
    await dca_after_restart.check_grid_triggers(grid_id, 126.0)  # 3.08% pullback from 130
    orders = await repos.orders.list_for_grid(grid_id)
    sell_orders = [o for o in orders if o["side"] == "sell"]
    assert sell_orders, "trailing-stop sell must still fire correctly after a simulated restart"
    grid_after = await repos.grids.get(grid_id)
    assert grid_after["trailing_peak_price"] is None


async def test_trailing_resets_after_dust_writeoff_sell(repos, mock_exchange, mock_notifier, permissive_risk_settings):
    """If the trailing-stop sell fires but the remaining position is dust
    (below the exchange's minimum sellable quantity), _execute_profit_sell
    writes it off and closes the grid — trailing_peak_price must still
    reset to None rather than being left stuck on a now-closed grid."""
    from config.constants import GridStatus
    from storage.models import DCAGridRecord
    from utils.helpers import new_id, now_iso

    dca = await _make_dca_manager(repos, mock_exchange, mock_notifier, permissive_risk_settings)
    now = now_iso()
    grid = DCAGridRecord(
        grid_id=new_id("grd"), symbol="BTCINR", status=GridStatus.ACTIVE.value,
        entry_price=100.0, base_investment=500.0, dip_buy_amount=100.0,
        dip_percentage=5.0, profit_sell_amount=200.0, profit_percentage=5.0,
        max_levels=5, stop_loss_percentage=20.0, current_level=1,
        # Dust: below mock_exchange's min_quantity=0.001.
        total_quantity=0.0003, total_investment=0.03,
        average_entry_price=100.0, last_buy_price=100.0,
        next_buy_price=95.0, next_sell_price=105.0,
        realized_profit=0.0, completed_cycles=0, created_at=now, updated_at=now,
        trailing_enabled=True, trailing_percentage=3.0, trailing_peak_price=120.0,
    )
    await repos.grids.create(grid)

    # Pullback past the trail threshold, triggering _handle_trailing_tick
    # -> _execute_profit_sell -> dust write-off (position too small to sell).
    await dca.check_grid_triggers(grid.grid_id, 116.0)

    updated = await repos.grids.get(grid.grid_id)
    assert updated["status"] == GridStatus.STOPPED.value, "dust write-off must close the grid"
    assert updated["trailing_peak_price"] is None, "trailing state must reset even when the sell resolves as a dust write-off"
    orders = await repos.orders.list_for_grid(grid.grid_id)
    assert not [o for o in orders if o["side"] == "sell"], "no real order should be placed for unsellable dust"

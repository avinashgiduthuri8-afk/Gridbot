"""Tests for /adjustgrid: adjusting a running grid's parameters without
stopping it, including the critical next_buy_price/next_sell_price
recompute when dip_percentage/profit_percentage change."""

from __future__ import annotations

import pytest

import bot_telegram.handlers as handlers_mod

pytestmark = pytest.mark.anyio


class FakeMessage:
    def __init__(self):
        self.replies: list[str] = []

    async def reply_text(self, text: str, **kwargs) -> None:
        self.replies.append(text)


class FakeUser:
    def __init__(self, user_id: int):
        self.id = user_id


class FakeUpdate:
    def __init__(self, user_id: int = 111):
        self.effective_user = FakeUser(user_id)
        self.message = FakeMessage()


class FakeContext:
    def __init__(self, args=None):
        self.args = args or []


def _stub_app():
    class _StubApp:
        def __init__(self):
            self.handlers = []
        def add_handler(self, h):
            self.handlers.append(h)
    return _StubApp()


def _get_adjustgrid_cmd(app_context):
    stub_app = _stub_app()
    handlers_mod.register_handlers(stub_app, app_context)
    return next(h.callback for h in stub_app.handlers if getattr(h, "command", None) == "adjustgrid")


async def _seed_grid(app_context, repos):
    grid_id = await app_context.dca_manager.start_grid({
        "symbol": "BTCINR", "entry_price": 100.0, "base_investment": 500.0,
        "dip_buy_amount": 100.0, "dip_percentage": 5.0,
        "profit_sell_amount": 150.0, "profit_percentage": 7.0,
        "max_levels": 5, "stop_loss_percentage": 50.0, "mode": "real",
    })
    orders = await repos.orders.list_for_grid(grid_id)
    await app_context.dca_manager.handle_order_filled(
        orders[0]["order_id"], fill_price=100.0, fill_qty=orders[0]["quantity"],
    )
    return grid_id


async def test_adjust_dip_percentage_recomputes_next_buy_price(app_context, repos):
    adjustgrid = _get_adjustgrid_cmd(app_context)
    grid_id = await _seed_grid(app_context, repos)

    update = FakeUpdate()
    await adjustgrid(update, FakeContext(args=[grid_id, "dip_percentage", "10"]))

    assert "updated to 10.0%" in update.message.replies[-1]
    assert "Next dip-buy price updated" in update.message.replies[-1]
    grid = await repos.grids.get(grid_id)
    assert grid["dip_percentage"] == 10.0
    assert abs(grid["next_buy_price"] - 90.0) < 0.01  # last_buy_price=100, dip=10% -> 90


async def test_adjust_profit_percentage_recomputes_next_sell_price(app_context, repos):
    adjustgrid = _get_adjustgrid_cmd(app_context)
    grid_id = await _seed_grid(app_context, repos)

    update = FakeUpdate()
    await adjustgrid(update, FakeContext(args=[grid_id, "profit_percentage", "15"]))

    grid = await repos.grids.get(grid_id)
    assert grid["profit_percentage"] == 15.0
    assert abs(grid["next_sell_price"] - 115.0) < 0.01  # avg_entry=100, profit=15% -> 115


async def test_adjusted_dip_percentage_changes_real_trigger_behavior(app_context, repos):
    """Integration guard: the recompute must actually change what fires on
    the next price tick, not just update a DB field cosmetically."""
    grid_id = await _seed_grid(app_context, repos)
    dca = app_context.dca_manager

    await dca.adjust_grid(grid_id, "dip_percentage", 10.0)  # new threshold: 90, not the original 95

    await dca.check_grid_triggers(grid_id, 92.0)  # would have triggered the old 5%/95 threshold
    orders_at_92 = await repos.orders.list_for_grid(grid_id)
    assert len(orders_at_92) == 1, "must not dip-buy at 92 once widened to a 10% threshold"

    await dca.check_grid_triggers(grid_id, 89.0)  # below the new 90 threshold
    orders_at_89 = await repos.orders.list_for_grid(grid_id)
    assert len(orders_at_89) == 2, "must dip-buy at 89, below the new 10% threshold"


async def test_adjust_simple_field_no_recompute_needed(app_context, repos):
    adjustgrid = _get_adjustgrid_cmd(app_context)
    grid_id = await _seed_grid(app_context, repos)

    update = FakeUpdate()
    await adjustgrid(update, FakeContext(args=[grid_id, "dip_buy_amount", "250"]))

    grid = await repos.grids.get(grid_id)
    assert grid["dip_buy_amount"] == 250.0


async def test_lowering_max_levels_below_current_level_warns(app_context, repos):
    adjustgrid = _get_adjustgrid_cmd(app_context)
    grid_id = await _seed_grid(app_context, repos)  # current_level is now 1

    update = FakeUpdate()
    await adjustgrid(update, FakeContext(args=[grid_id, "max_levels", "1"]))

    assert "no further dip buys" in update.message.replies[-1]


async def test_toggle_trailing_enabled(app_context, repos):
    adjustgrid = _get_adjustgrid_cmd(app_context)
    grid_id = await _seed_grid(app_context, repos)

    update = FakeUpdate()
    await adjustgrid(update, FakeContext(args=[grid_id, "trailing_enabled", "true"]))

    grid = await repos.grids.get(grid_id)
    assert grid["trailing_enabled"] in (1, True)


async def test_rejects_malformed_grid_id(app_context, repos):
    adjustgrid = _get_adjustgrid_cmd(app_context)

    update = FakeUpdate()
    await adjustgrid(update, FakeContext(args=["<script>bad", "dip_percentage", "5"]))

    assert "doesn't look like a valid grid ID" in update.message.replies[-1]


async def test_rejects_unknown_field(app_context, repos):
    adjustgrid = _get_adjustgrid_cmd(app_context)
    grid_id = await _seed_grid(app_context, repos)

    update = FakeUpdate()
    await adjustgrid(update, FakeContext(args=[grid_id, "symbol", "ETHINR"]))

    assert "Unknown field" in update.message.replies[-1]


async def test_rejects_out_of_range_percentage(app_context, repos):
    adjustgrid = _get_adjustgrid_cmd(app_context)
    grid_id = await _seed_grid(app_context, repos)

    update = FakeUpdate()
    await adjustgrid(update, FakeContext(args=[grid_id, "dip_percentage", "150"]))

    assert "Invalid value" in update.message.replies[-1]
    grid = await repos.grids.get(grid_id)
    assert grid["dip_percentage"] == 5.0, "rejected value must not be applied"


async def test_cannot_adjust_a_stopped_grid(app_context, repos):
    adjustgrid = _get_adjustgrid_cmd(app_context)
    grid_id = await _seed_grid(app_context, repos)
    await app_context.dca_manager.stop_grid(grid_id)

    update = FakeUpdate()
    await adjustgrid(update, FakeContext(args=[grid_id, "dip_percentage", "5"]))

    assert "stopped" in update.message.replies[-1].lower()

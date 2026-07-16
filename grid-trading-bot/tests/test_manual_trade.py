"""Tests for the /manualbuy and /manualsell commands: confirmation flow,
grid_id format validation (HTML-injection guard), and the asymmetric risk
gating (buys blocked by emergency stop, sells never blocked)."""

from __future__ import annotations

import pytest
import bot_telegram.handlers as handlers_mod

pytestmark = pytest.mark.anyio


class FakeMessage:
    def __init__(self, text: str = ""):
        self.text = text
        self.replies: list[str] = []
        self.markups: list = []

    async def reply_text(self, text: str, reply_markup=None, **kwargs) -> None:
        self.replies.append(text)
        self.markups.append(reply_markup)


class FakeUser:
    def __init__(self, user_id: int):
        self.id = user_id


class FakeCallbackQuery:
    def __init__(self, data: str, user_id: int):
        self.data = data
        self.from_user = FakeUser(user_id)
        self.edited: list[str] = []
        self.answered: list[tuple] = []

    async def answer(self, text: str | None = None, show_alert: bool = False) -> None:
        self.answered.append((text, show_alert))

    async def edit_message_text(self, text: str, **kwargs) -> None:
        self.edited.append(text)


class FakeUpdate:
    def __init__(self, user_id: int = 111):
        self.effective_user = FakeUser(user_id)
        self.message = FakeMessage()
        self.callback_query: FakeCallbackQuery | None = None


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


async def _seed_grid(app_context, repos, symbol="BTCINR", entry_price=100.0):
    grid_id = await app_context.dca_manager.start_grid({
        "symbol": symbol, "entry_price": entry_price, "base_investment": 500.0,
        "dip_buy_amount": 100.0, "dip_percentage": 5.0,
        "profit_sell_amount": 150.0, "profit_percentage": 7.0,
        "max_levels": 5, "stop_loss_percentage": 50.0, "mode": "real",
    })
    orders = await repos.orders.list_for_grid(grid_id)
    await app_context.dca_manager.handle_order_filled(
        orders[0]["order_id"], fill_price=entry_price, fill_qty=orders[0]["quantity"],
    )
    return grid_id


async def test_manualbuy_shows_confirmation_without_placing_order(app_context, repos):
    grid_id = await _seed_grid(app_context, repos)
    stub_app = _stub_app()
    handlers_mod.register_handlers(stub_app, app_context)
    manualbuy = next(h.callback for h in stub_app.handlers if getattr(h, "command", None) == "manualbuy")

    update = FakeUpdate(user_id=111)
    ctx = FakeContext(args=[grid_id, "200"])
    await manualbuy(update, ctx)

    assert "Confirm Manual Buy" in update.message.replies[-1]
    orders = await repos.orders.list_for_grid(grid_id)
    assert len(orders) == 1, "no order should be placed before confirmation"


async def test_manualbuy_confirm_places_order(app_context, repos):
    stub_app = _stub_app()
    handlers_mod.register_handlers(stub_app, app_context)
    manualbuy = next(h.callback for h in stub_app.handlers if getattr(h, "command", None) == "manualbuy")
    mtrade_cb = next(h.callback for h in stub_app.handlers if getattr(h, "pattern", None) == "^mtrade:")

    grid_id = await _seed_grid(app_context, repos)
    update = FakeUpdate(user_id=111)
    await manualbuy(update, FakeContext(args=[grid_id, "200"]))
    confirm_data = update.message.markups[-1].rows[0][0].callback_data

    cb_update = FakeUpdate(user_id=111)
    cb_update.callback_query = FakeCallbackQuery(confirm_data, 111)
    await mtrade_cb(cb_update, FakeContext())

    assert "Manual buy placed" in cb_update.callback_query.edited[-1]
    orders = await repos.orders.list_for_grid(grid_id)
    assert len(orders) == 2


async def test_manualbuy_cancel_places_no_order(app_context, repos):
    stub_app = _stub_app()
    handlers_mod.register_handlers(stub_app, app_context)
    manualbuy = next(h.callback for h in stub_app.handlers if getattr(h, "command", None) == "manualbuy")
    mtrade_cb = next(h.callback for h in stub_app.handlers if getattr(h, "pattern", None) == "^mtrade:")

    grid_id = await _seed_grid(app_context, repos)
    update = FakeUpdate(user_id=111)
    await manualbuy(update, FakeContext(args=[grid_id, "200"]))
    cancel_data = update.message.markups[-1].rows[0][1].callback_data

    cb_update = FakeUpdate(user_id=111)
    cb_update.callback_query = FakeCallbackQuery(cancel_data, 111)
    await mtrade_cb(cb_update, FakeContext())

    assert "cancelled" in cb_update.callback_query.edited[-1].lower()
    orders = await repos.orders.list_for_grid(grid_id)
    assert len(orders) == 1


async def test_manualsell_no_amount_sells_entire_position(app_context, repos):
    stub_app = _stub_app()
    handlers_mod.register_handlers(stub_app, app_context)
    manualsell = next(h.callback for h in stub_app.handlers if getattr(h, "command", None) == "manualsell")
    mtrade_cb = next(h.callback for h in stub_app.handlers if getattr(h, "pattern", None) == "^mtrade:")

    grid_id = await _seed_grid(app_context, repos)
    update = FakeUpdate(user_id=111)
    await manualsell(update, FakeContext(args=[grid_id]))
    assert "ENTIRE remaining position" in update.message.replies[-1]

    confirm_data = update.message.markups[-1].rows[0][0].callback_data
    assert confirm_data.endswith(":ALL")

    cb_update = FakeUpdate(user_id=111)
    cb_update.callback_query = FakeCallbackQuery(confirm_data, 111)
    await mtrade_cb(cb_update, FakeContext())
    assert "Manual sell placed" in cb_update.callback_query.edited[-1]


async def test_manualbuy_rejects_malformed_grid_id(app_context, repos):
    stub_app = _stub_app()
    handlers_mod.register_handlers(stub_app, app_context)
    manualbuy = next(h.callback for h in stub_app.handlers if getattr(h, "command", None) == "manualbuy")

    update = FakeUpdate(user_id=111)
    await manualbuy(update, FakeContext(args=["<script>bad", "100"]))

    assert "doesn't look like a valid grid ID" in update.message.replies[-1]


async def test_manualbuy_blocked_by_emergency_stop(app_context, repos):
    stub_app = _stub_app()
    handlers_mod.register_handlers(stub_app, app_context)
    manualbuy = next(h.callback for h in stub_app.handlers if getattr(h, "command", None) == "manualbuy")
    mtrade_cb = next(h.callback for h in stub_app.handlers if getattr(h, "pattern", None) == "^mtrade:")

    grid_id = await _seed_grid(app_context, repos)
    await app_context.risk_manager.trigger_emergency_stop()

    update = FakeUpdate(user_id=111)
    await manualbuy(update, FakeContext(args=[grid_id, "500"]))
    confirm_data = update.message.markups[-1].rows[0][0].callback_data

    cb_update = FakeUpdate(user_id=111)
    cb_update.callback_query = FakeCallbackQuery(confirm_data, 111)
    await mtrade_cb(cb_update, FakeContext())

    assert "❌" in cb_update.callback_query.edited[-1]
    assert "Emergency" in cb_update.callback_query.edited[-1]

    await app_context.risk_manager.clear_emergency_stop()


async def test_manualsell_not_blocked_by_emergency_stop(app_context, repos):
    stub_app = _stub_app()
    handlers_mod.register_handlers(stub_app, app_context)
    manualsell = next(h.callback for h in stub_app.handlers if getattr(h, "command", None) == "manualsell")
    mtrade_cb = next(h.callback for h in stub_app.handlers if getattr(h, "pattern", None) == "^mtrade:")

    grid_id = await _seed_grid(app_context, repos)
    await app_context.risk_manager.trigger_emergency_stop()

    update = FakeUpdate(user_id=111)
    await manualsell(update, FakeContext(args=[grid_id, "300"]))
    confirm_data = update.message.markups[-1].rows[0][0].callback_data

    cb_update = FakeUpdate(user_id=111)
    cb_update.callback_query = FakeCallbackQuery(confirm_data, 111)
    await mtrade_cb(cb_update, FakeContext())

    assert "Manual sell placed" in cb_update.callback_query.edited[-1], \
        "sells must never be blocked by emergency stop"

    await app_context.risk_manager.clear_emergency_stop()


async def test_unauthorized_user_rejected_on_confirm_callback(app_context, repos):
    stub_app = _stub_app()
    handlers_mod.register_handlers(stub_app, app_context)
    manualbuy = next(h.callback for h in stub_app.handlers if getattr(h, "command", None) == "manualbuy")
    mtrade_cb = next(h.callback for h in stub_app.handlers if getattr(h, "pattern", None) == "^mtrade:")

    grid_id = await _seed_grid(app_context, repos)
    update = FakeUpdate(user_id=111)
    await manualbuy(update, FakeContext(args=[grid_id, "50"]))
    confirm_data = update.message.markups[-1].rows[0][0].callback_data

    cb_update = FakeUpdate(user_id=999)  # not owner (111), not in allowed_ids (222)
    cb_update.callback_query = FakeCallbackQuery(confirm_data, 999)
    await mtrade_cb(cb_update, FakeContext())

    assert cb_update.callback_query.answered[-1][0] == "Not authorized."
    assert not cb_update.callback_query.edited
    orders = await repos.orders.list_for_grid(grid_id)
    assert len(orders) == 1, "unauthorized confirm must not place an order"

"""Tests for the /newgrid conversation flow: Default Grid, Custom Grid, and
the choice menu between them.

These drive the actual ConversationHandler callback functions directly
(bypassing python-telegram-bot's dispatcher, which isn't needed to exercise
the handler logic itself) using lightweight fake Update/CallbackQuery
objects, against the real DCAManager/RiskManager/Repositories stack via the
`app_context` fixture in conftest.py.
"""

from __future__ import annotations

import pytest
from telegram.ext import ConversationHandler

import bot_telegram.conversations as conv_mod

pytestmark = pytest.mark.anyio


# ---------------------------------------------------------------------------
# Fakes
# ---------------------------------------------------------------------------


class FakeMessage:
    def __init__(self, text: str = ""):
        self.text = text
        self.replies: list[str] = []

    async def reply_text(self, text: str, **kwargs) -> "FakeMessage":
        reply = FakeMessage()
        reply.sent_text = text
        self.replies.append(text)
        return reply

    async def edit_text(self, text: str, **kwargs) -> None:
        self.sent_text = text

    async def delete(self) -> None:
        pass


class FakeUser:
    def __init__(self, user_id: int):
        self.id = user_id


class FakeCallbackQuery:
    def __init__(self, data: str, user_id: int):
        self.data = data
        self.from_user = FakeUser(user_id)
        self.edited: list[str] = []
        self.markups: list = []

    async def answer(self, *args, **kwargs) -> None:
        pass

    async def edit_message_text(self, text: str, reply_markup=None, **kwargs) -> None:
        self.edited.append(text)
        self.markups.append(reply_markup)


class FakeChat:
    def __init__(self, chat_id: int):
        self.id = chat_id


class FakeBot:
    def __init__(self):
        self.sent_messages: list[tuple[int, str]] = []

    async def send_message(self, chat_id: int, text: str, **kwargs) -> None:
        self.sent_messages.append((chat_id, text))


class FakeUpdate:
    def __init__(self, text: str = "", user_id: int = 111, chat_id: int | None = None):
        self.effective_user = FakeUser(user_id)
        self.effective_chat = FakeChat(chat_id if chat_id is not None else user_id)
        self.message = FakeMessage(text)
        self.callback_query: FakeCallbackQuery | None = None


class FakeContext:
    def __init__(self):
        self.user_data: dict = {}
        self.bot = FakeBot()


def _find_callback(handler, state):
    for h in handler.states[state]:
        cb = getattr(h, "callback", None)
        if cb is not None:
            return cb
    raise KeyError(state)


# ---------------------------------------------------------------------------
# Entry menu
# ---------------------------------------------------------------------------


async def test_newgrid_shows_default_custom_menu(app_context):
    handler = conv_mod.build_newgrid_conversation(app_context)
    entry_fn = handler.entry_points[0].callback
    ctx = FakeContext()
    update = FakeUpdate(text="/newgrid", user_id=111)

    next_state = await entry_fn(update, ctx)

    assert next_state == conv_mod.GRID_SETUP_MODE
    assert "Default Grid" in update.message.replies[-1]
    assert "Custom Grid" in update.message.replies[-1]


async def test_newgrid_rejects_unauthorized_user(app_context):
    handler = conv_mod.build_newgrid_conversation(app_context)
    entry_fn = handler.entry_points[0].callback
    ctx = FakeContext()
    update = FakeUpdate(text="/newgrid", user_id=999)  # not owner (111), not in allowed_ids (222)

    next_state = await entry_fn(update, ctx)

    assert next_state == ConversationHandler.END
    assert "not authorized" in update.message.replies[-1].lower()


# ---------------------------------------------------------------------------
# Default Grid
# ---------------------------------------------------------------------------


async def test_default_grid_creates_working_grid_from_coin_only(app_context, repos):
    """The core requirement: only a coin symbol as input produces a
    fully-configured, running grid using the saved defaults."""
    handler = conv_mod.build_newgrid_conversation(app_context)
    ctx = FakeContext()

    await handler.entry_points[0].callback(FakeUpdate(text="/newgrid", user_id=111), ctx)

    mode_choice_update = FakeUpdate(user_id=111)
    mode_choice_update.callback_query = FakeCallbackQuery("grid_setup_mode:default", 111)
    next_state = await _find_callback(handler, conv_mod.GRID_SETUP_MODE)(mode_choice_update, ctx)
    assert next_state == conv_mod.DEFAULT_COIN

    coin_update = FakeUpdate(text="BTCINR", user_id=111)
    next_state = await _find_callback(handler, conv_mod.DEFAULT_COIN)(coin_update, ctx)
    assert next_state == conv_mod.SELECT_MODE  # no saved mode yet

    for field, expected in [
        ("symbol", "BTCINR"), ("base_investment", 500.0), ("dip_buy_amount", 100.0),
        ("dip_percentage", 5.0), ("profit_sell_amount", 120.0), ("profit_percentage", 7.0),
        ("max_levels", 5), ("stop_loss_percentage", 50.0),
    ]:
        assert ctx.user_data[field] == expected, f"{field} should be {expected}, got {ctx.user_data[field]}"

    mode_update = FakeUpdate(user_id=111)
    mode_update.callback_query = FakeCallbackQuery("pick_mode:paper", 111)
    next_state = await _find_callback(handler, conv_mod.SELECT_MODE)(mode_update, ctx)
    assert next_state == conv_mod.CONFIRM

    confirm_update = FakeUpdate(user_id=111)
    confirm_update.callback_query = FakeCallbackQuery("confirm_grid:yes", 111)
    await _find_callback(handler, conv_mod.CONFIRM)(confirm_update, ctx)

    assert "Grid Started" in confirm_update.callback_query.edited[-1]
    grids = await repos.grids.list_all()
    assert len(grids) == 1
    assert grids[0]["symbol"] == "BTCINR"
    assert grids[0]["base_investment"] == 500.0


async def test_default_grid_remembers_mode_after_first_use(app_context, repos):
    """After the mode is chosen once, subsequent Default Grid creations skip
    mode selection entirely — true 1-step creation."""
    handler = conv_mod.build_newgrid_conversation(app_context)

    # First grid: establishes last_mode=paper (see previous test for the full trace)
    ctx1 = FakeContext()
    await handler.entry_points[0].callback(FakeUpdate(text="/newgrid", user_id=111), ctx1)
    u1 = FakeUpdate(user_id=111)
    u1.callback_query = FakeCallbackQuery("grid_setup_mode:default", 111)
    await _find_callback(handler, conv_mod.GRID_SETUP_MODE)(u1, ctx1)
    u2 = FakeUpdate(text="BTCINR", user_id=111)
    await _find_callback(handler, conv_mod.DEFAULT_COIN)(u2, ctx1)
    u3 = FakeUpdate(user_id=111)
    u3.callback_query = FakeCallbackQuery("pick_mode:paper", 111)
    await _find_callback(handler, conv_mod.SELECT_MODE)(u3, ctx1)
    u4 = FakeUpdate(user_id=111)
    u4.callback_query = FakeCallbackQuery("confirm_grid:yes", 111)
    await _find_callback(handler, conv_mod.CONFIRM)(u4, ctx1)

    # Second grid, different coin: mode step must be skipped entirely
    ctx2 = FakeContext()
    await handler.entry_points[0].callback(FakeUpdate(text="/newgrid", user_id=111), ctx2)
    v1 = FakeUpdate(user_id=111)
    v1.callback_query = FakeCallbackQuery("grid_setup_mode:default", 111)
    await _find_callback(handler, conv_mod.GRID_SETUP_MODE)(v1, ctx2)
    v2 = FakeUpdate(text="ETHINR", user_id=111)
    next_state = await _find_callback(handler, conv_mod.DEFAULT_COIN)(v2, ctx2)

    assert next_state == conv_mod.CONFIRM, "saved mode must skip SELECT_MODE entirely"
    assert ctx2.user_data["mode"] == "paper"


async def test_default_grid_rejects_malformed_symbol(app_context):
    handler = conv_mod.build_newgrid_conversation(app_context)
    ctx = FakeContext()
    await handler.entry_points[0].callback(FakeUpdate(text="/newgrid", user_id=111), ctx)
    u1 = FakeUpdate(user_id=111)
    u1.callback_query = FakeCallbackQuery("grid_setup_mode:default", 111)
    await _find_callback(handler, conv_mod.GRID_SETUP_MODE)(u1, ctx)

    bad_update = FakeUpdate(text="BTC<script>INR", user_id=111)
    next_state = await _find_callback(handler, conv_mod.DEFAULT_COIN)(bad_update, ctx)

    assert next_state == conv_mod.DEFAULT_COIN, "must re-prompt, not proceed with a malformed symbol"
    assert "letters/numbers only" in bad_update.message.replies[-1]


async def test_default_grid_validation_failure_hints_at_defaults_command(app_context, repos):
    """If a saved default fails exchange validation (e.g. base_investment
    too small for a coin's minimum order size), the error must point the
    user at /defaults, not just '/newgrid to start over'."""
    # Force a coin whose minimum order value exceeds the saved base_investment (500).
    from exchange.base import MarketInfo
    app_context.exchange.market_info_override = MarketInfo(
        symbol="BTCINR", base_currency_precision=2, target_currency_precision=6,
        min_quantity=0.0001, min_amount=5000.0, step_size=0.0001,
    )

    handler = conv_mod.build_newgrid_conversation(app_context)
    ctx = FakeContext()
    await handler.entry_points[0].callback(FakeUpdate(text="/newgrid", user_id=111), ctx)
    u1 = FakeUpdate(user_id=111)
    u1.callback_query = FakeCallbackQuery("grid_setup_mode:default", 111)
    await _find_callback(handler, conv_mod.GRID_SETUP_MODE)(u1, ctx)
    u2 = FakeUpdate(text="BTCINR", user_id=111)
    await _find_callback(handler, conv_mod.DEFAULT_COIN)(u2, ctx)
    u3 = FakeUpdate(user_id=111)
    u3.callback_query = FakeCallbackQuery("pick_mode:paper", 111)
    await _find_callback(handler, conv_mod.SELECT_MODE)(u3, ctx)

    u4 = FakeUpdate(user_id=111)
    u4.callback_query = FakeCallbackQuery("confirm_grid:yes", 111)
    await _find_callback(handler, conv_mod.CONFIRM)(u4, ctx)

    final_message = u4.callback_query.edited[-1]
    assert "does not meet exchange rules" in final_message
    assert "/defaults" in final_message
    grids = await repos.grids.list_all()
    assert len(grids) == 0, "no grid should be created when validation fails"


# ---------------------------------------------------------------------------
# Custom Grid — must remain unchanged
# ---------------------------------------------------------------------------


async def test_custom_grid_full_flow_unchanged(app_context, repos):
    handler = conv_mod.build_newgrid_conversation(app_context)
    ctx = FakeContext()
    await handler.entry_points[0].callback(FakeUpdate(text="/newgrid", user_id=111), ctx)

    u1 = FakeUpdate(user_id=111)
    u1.callback_query = FakeCallbackQuery("grid_setup_mode:custom", 111)
    next_state = await _find_callback(handler, conv_mod.GRID_SETUP_MODE)(u1, ctx)
    assert next_state == conv_mod.SELECT_COIN
    assert ctx.user_data["_source"] == "custom"

    u2 = FakeUpdate(user_id=111)
    u2.callback_query = FakeCallbackQuery("pick_coin:BTCINR", 111)
    next_state = await _find_callback(handler, conv_mod.SELECT_COIN)(u2, ctx)
    assert next_state == conv_mod.ENTRY_PRICE

    steps = [
        (conv_mod.ENTRY_PRICE, "0", conv_mod.BASE_INVESTMENT),
        (conv_mod.BASE_INVESTMENT, "500", conv_mod.DIP_BUY_AMOUNT),
        (conv_mod.DIP_BUY_AMOUNT, "100", conv_mod.DIP_PERCENTAGE),
        (conv_mod.DIP_PERCENTAGE, "5", conv_mod.PROFIT_SELL_AMOUNT),
        (conv_mod.PROFIT_SELL_AMOUNT, "150", conv_mod.PROFIT_PERCENTAGE),
        (conv_mod.PROFIT_PERCENTAGE, "7", conv_mod.MAX_LEVELS),
        (conv_mod.MAX_LEVELS, "10", conv_mod.STOP_LOSS),
        (conv_mod.STOP_LOSS, "50", conv_mod.TRAILING_CHOICE),
    ]
    for state, text, expected_next in steps:
        update = FakeUpdate(text=text, user_id=111)
        next_state = await _find_callback(handler, state)(update, ctx)
        assert next_state == expected_next, f"step {state} -> expected {expected_next}, got {next_state}"

    # Skip trailing -> straight to mode selection, exactly as before this feature existed
    u_trailing = FakeUpdate(user_id=111)
    u_trailing.callback_query = FakeCallbackQuery("trailing_choice:no", 111)
    next_state = await _find_callback(handler, conv_mod.TRAILING_CHOICE)(u_trailing, ctx)
    assert next_state == conv_mod.SELECT_MODE
    assert ctx.user_data["trailing_enabled"] is False

    u3 = FakeUpdate(user_id=111)
    u3.callback_query = FakeCallbackQuery("pick_mode:real", 111)
    next_state = await _find_callback(handler, conv_mod.SELECT_MODE)(u3, ctx)
    assert next_state == conv_mod.CONFIRM

    u4 = FakeUpdate(user_id=111)
    u4.callback_query = FakeCallbackQuery("confirm_grid:yes", 111)
    await _find_callback(handler, conv_mod.CONFIRM)(u4, ctx)

    assert "Grid Started" in u4.callback_query.edited[-1]
    grids = await repos.grids.list_all()
    assert len(grids) == 1
    assert grids[0]["max_levels"] == 10
    assert grids[0]["profit_sell_amount"] == 150.0
    assert grids[0]["trailing_enabled"] == 0


async def test_custom_grid_with_trailing_enabled(app_context, repos):
    """Enabling trailing take-profit persists the flag and percentage, and
    the confirmation summary reflects it."""
    handler = conv_mod.build_newgrid_conversation(app_context)
    ctx = FakeContext()
    await handler.entry_points[0].callback(FakeUpdate(text="/newgrid", user_id=111), ctx)
    u1 = FakeUpdate(user_id=111)
    u1.callback_query = FakeCallbackQuery("grid_setup_mode:custom", 111)
    await _find_callback(handler, conv_mod.GRID_SETUP_MODE)(u1, ctx)
    u2 = FakeUpdate(user_id=111)
    u2.callback_query = FakeCallbackQuery("pick_coin:ETHINR", 111)
    await _find_callback(handler, conv_mod.SELECT_COIN)(u2, ctx)

    for state, text in [
        (conv_mod.ENTRY_PRICE, "0"), (conv_mod.BASE_INVESTMENT, "500"),
        (conv_mod.DIP_BUY_AMOUNT, "100"), (conv_mod.DIP_PERCENTAGE, "5"),
        (conv_mod.PROFIT_SELL_AMOUNT, "150"), (conv_mod.PROFIT_PERCENTAGE, "7"),
        (conv_mod.MAX_LEVELS, "10"), (conv_mod.STOP_LOSS, "50"),
    ]:
        update = FakeUpdate(text=text, user_id=111)
        await _find_callback(handler, state)(update, ctx)

    u_trailing = FakeUpdate(user_id=111)
    u_trailing.callback_query = FakeCallbackQuery("trailing_choice:yes", 111)
    next_state = await _find_callback(handler, conv_mod.TRAILING_CHOICE)(u_trailing, ctx)
    assert next_state == conv_mod.TRAILING_PERCENTAGE

    pct_update = FakeUpdate(text="2", user_id=111)
    next_state = await _find_callback(handler, conv_mod.TRAILING_PERCENTAGE)(pct_update, ctx)
    assert next_state == conv_mod.SELECT_MODE
    assert ctx.user_data["trailing_enabled"] is True
    assert ctx.user_data["trailing_percentage"] == 2.0

    u3 = FakeUpdate(user_id=111)
    u3.callback_query = FakeCallbackQuery("pick_mode:paper", 111)
    next_state = await _find_callback(handler, conv_mod.SELECT_MODE)(u3, ctx)
    assert next_state == conv_mod.CONFIRM
    assert "Trailing take-profit: 2.0% pullback" in u3.callback_query.edited[-1]

    u4 = FakeUpdate(user_id=111)
    u4.callback_query = FakeCallbackQuery("confirm_grid:yes", 111)
    await _find_callback(handler, conv_mod.CONFIRM)(u4, ctx)

    grids = await repos.grids.list_all()
    assert len(grids) == 1
    assert grids[0]["trailing_enabled"] == 1
    assert grids[0]["trailing_percentage"] == 2.0


async def test_custom_grid_rejects_invalid_trailing_percentage(app_context):
    handler = conv_mod.build_newgrid_conversation(app_context)
    ctx = FakeContext()
    await handler.entry_points[0].callback(FakeUpdate(text="/newgrid", user_id=111), ctx)
    u1 = FakeUpdate(user_id=111)
    u1.callback_query = FakeCallbackQuery("grid_setup_mode:custom", 111)
    await _find_callback(handler, conv_mod.GRID_SETUP_MODE)(u1, ctx)
    u2 = FakeUpdate(user_id=111)
    u2.callback_query = FakeCallbackQuery("pick_coin:BTCINR", 111)
    await _find_callback(handler, conv_mod.SELECT_COIN)(u2, ctx)
    for state, text in [
        (conv_mod.ENTRY_PRICE, "0"), (conv_mod.BASE_INVESTMENT, "500"),
        (conv_mod.DIP_BUY_AMOUNT, "100"), (conv_mod.DIP_PERCENTAGE, "5"),
        (conv_mod.PROFIT_SELL_AMOUNT, "150"), (conv_mod.PROFIT_PERCENTAGE, "7"),
        (conv_mod.MAX_LEVELS, "10"), (conv_mod.STOP_LOSS, "50"),
    ]:
        update = FakeUpdate(text=text, user_id=111)
        await _find_callback(handler, state)(update, ctx)
    u_trailing = FakeUpdate(user_id=111)
    u_trailing.callback_query = FakeCallbackQuery("trailing_choice:yes", 111)
    await _find_callback(handler, conv_mod.TRAILING_CHOICE)(u_trailing, ctx)

    bad_update = FakeUpdate(text="150", user_id=111)  # out of 0-50 range
    next_state = await _find_callback(handler, conv_mod.TRAILING_PERCENTAGE)(bad_update, ctx)
    assert next_state == conv_mod.TRAILING_PERCENTAGE
    assert "between 0 and 50" in bad_update.message.replies[-1]


async def test_default_grid_never_enables_trailing(app_context, repos):
    """Default Grid stays intentionally simple — trailing is Custom Grid only."""
    handler = conv_mod.build_newgrid_conversation(app_context)
    ctx = FakeContext()
    await handler.entry_points[0].callback(FakeUpdate(text="/newgrid", user_id=111), ctx)
    u1 = FakeUpdate(user_id=111)
    u1.callback_query = FakeCallbackQuery("grid_setup_mode:default", 111)
    await _find_callback(handler, conv_mod.GRID_SETUP_MODE)(u1, ctx)
    u2 = FakeUpdate(text="BTCINR", user_id=111)
    await _find_callback(handler, conv_mod.DEFAULT_COIN)(u2, ctx)
    assert ctx.user_data["trailing_enabled"] is False
    assert ctx.user_data["trailing_percentage"] is None


async def test_custom_grid_can_enable_trailing_take_profit(app_context, repos):
    """Companion to test_custom_grid_full_flow_unchanged, which only
    exercises the 'skip trailing' branch — this covers 'enable trailing'."""
    handler = conv_mod.build_newgrid_conversation(app_context)
    ctx = FakeContext()
    await handler.entry_points[0].callback(FakeUpdate(text="/newgrid", user_id=111), ctx)

    u1 = FakeUpdate(user_id=111)
    u1.callback_query = FakeCallbackQuery("grid_setup_mode:custom", 111)
    await _find_callback(handler, conv_mod.GRID_SETUP_MODE)(u1, ctx)
    u2 = FakeUpdate(user_id=111)
    u2.callback_query = FakeCallbackQuery("pick_coin:BTCINR", 111)
    await _find_callback(handler, conv_mod.SELECT_COIN)(u2, ctx)

    for state, text in [
        (conv_mod.ENTRY_PRICE, "0"), (conv_mod.BASE_INVESTMENT, "500"),
        (conv_mod.DIP_BUY_AMOUNT, "100"), (conv_mod.DIP_PERCENTAGE, "5"),
        (conv_mod.PROFIT_SELL_AMOUNT, "150"), (conv_mod.PROFIT_PERCENTAGE, "7"),
        (conv_mod.MAX_LEVELS, "10"), (conv_mod.STOP_LOSS, "50"),
    ]:
        update = FakeUpdate(text=text, user_id=111)
        await _find_callback(handler, state)(update, ctx)

    u_trailing = FakeUpdate(user_id=111)
    u_trailing.callback_query = FakeCallbackQuery("trailing_choice:yes", 111)
    next_state = await _find_callback(handler, conv_mod.TRAILING_CHOICE)(u_trailing, ctx)
    assert next_state == conv_mod.TRAILING_PERCENTAGE

    pct_update = FakeUpdate(text="4", user_id=111)
    next_state = await _find_callback(handler, conv_mod.TRAILING_PERCENTAGE)(pct_update, ctx)
    assert next_state == conv_mod.SELECT_MODE
    assert ctx.user_data["trailing_enabled"] is True
    assert ctx.user_data["trailing_percentage"] == 4.0

    u3 = FakeUpdate(user_id=111)
    u3.callback_query = FakeCallbackQuery("pick_mode:real", 111)
    await _find_callback(handler, conv_mod.SELECT_MODE)(u3, ctx)
    u4 = FakeUpdate(user_id=111)
    u4.callback_query = FakeCallbackQuery("confirm_grid:yes", 111)
    await _find_callback(handler, conv_mod.CONFIRM)(u4, ctx)

    assert "Grid Started" in u4.callback_query.edited[-1]
    grids = await repos.grids.list_all()
    assert len(grids) == 1
    assert grids[0]["trailing_enabled"] == 1 or grids[0]["trailing_enabled"] is True
    assert grids[0]["trailing_percentage"] == 4.0


async def test_custom_grid_never_modifies_saved_defaults(app_context, repos):
    """Regression guard: running Custom Grid must not read from or write to
    the grid_defaults table at all."""
    from config.constants import QUICK_GRID_DEFAULTS_SEED

    await repos.grid_defaults.get_or_seed(QUICK_GRID_DEFAULTS_SEED)

    handler = conv_mod.build_newgrid_conversation(app_context)
    ctx = FakeContext()
    await handler.entry_points[0].callback(FakeUpdate(text="/newgrid", user_id=111), ctx)
    u1 = FakeUpdate(user_id=111)
    u1.callback_query = FakeCallbackQuery("grid_setup_mode:custom", 111)
    await _find_callback(handler, conv_mod.GRID_SETUP_MODE)(u1, ctx)
    u2 = FakeUpdate(user_id=111)
    u2.callback_query = FakeCallbackQuery("pick_coin:ETHINR", 111)
    await _find_callback(handler, conv_mod.SELECT_COIN)(u2, ctx)

    for state, text in [
        (conv_mod.ENTRY_PRICE, "0"), (conv_mod.BASE_INVESTMENT, "999"),
        (conv_mod.DIP_BUY_AMOUNT, "222"), (conv_mod.DIP_PERCENTAGE, "9"),
        (conv_mod.PROFIT_SELL_AMOUNT, "333"), (conv_mod.PROFIT_PERCENTAGE, "11"),
        (conv_mod.MAX_LEVELS, "20"), (conv_mod.STOP_LOSS, "40"),
    ]:
        update = FakeUpdate(text=text, user_id=111)
        await _find_callback(handler, state)(update, ctx)

    u_trailing = FakeUpdate(user_id=111)
    u_trailing.callback_query = FakeCallbackQuery("trailing_choice:no", 111)
    await _find_callback(handler, conv_mod.TRAILING_CHOICE)(u_trailing, ctx)

    u3 = FakeUpdate(user_id=111)
    u3.callback_query = FakeCallbackQuery("pick_mode:paper", 111)
    await _find_callback(handler, conv_mod.SELECT_MODE)(u3, ctx)
    u4 = FakeUpdate(user_id=111)
    u4.callback_query = FakeCallbackQuery("confirm_grid:yes", 111)
    await _find_callback(handler, conv_mod.CONFIRM)(u4, ctx)

    defaults_after = await repos.grid_defaults.get()
    assert defaults_after["base_investment"] == 500.0, "Custom Grid must never touch saved defaults"
    assert defaults_after["max_levels"] == 5
    assert defaults_after["last_mode"] is None, "Custom Grid mode choice must not be persisted as the default"


# ---------------------------------------------------------------------------
# Fallback / wedge-recovery — regression coverage for the "/newgrid only
# works once per deployment" bug. Root cause: button-only states
# (GRID_SETUP_MODE, SELECT_COIN, TRAILING_CHOICE, SELECT_MODE, CONFIRM) had
# no escape hatch other than an exact button tap, and there was no
# conversation_timeout, so any deviation from the happy path wedged the
# conversation for that (chat, user) permanently until process restart.
# ---------------------------------------------------------------------------


def _fallback_callback(handler, name: str):
    for h in handler.fallbacks:
        cb = getattr(h, "callback", None)
        if cb is not None and cb.__name__ == name:
            return cb
    raise KeyError(name)


def test_conversation_has_timeout_and_recovery_fallbacks():
    """Configuration guard: the three ingredients of the fix must all be
    present, so a future refactor can't silently drop one of them."""
    handler = conv_mod.build_newgrid_conversation(app_context=None)  # noqa: not called, just built

    assert handler.conversation_timeout == 300

    fallback_names = {h.callback.__name__ for h in handler.fallbacks if getattr(h, "callback", None)}
    assert fallback_names == {"cancel", "start", "unexpected_command"}

    timeout_handlers = handler.states[ConversationHandler.TIMEOUT]
    assert any(h.callback.__name__ == "conversation_timed_out" for h in timeout_handlers)


async def test_newgrid_full_flow_then_newgrid_again_starts_cleanly(app_context, repos):
    """/newgrid -> complete flow -> /newgrid again.

    Before the fix this worked too (END always cleared PTB's per-user
    state), but it's the baseline the other wedge tests are contrasted
    against, so it's pinned here explicitly.
    """
    handler = conv_mod.build_newgrid_conversation(app_context)
    ctx1 = FakeContext()
    await handler.entry_points[0].callback(FakeUpdate(text="/newgrid", user_id=111), ctx1)
    u1 = FakeUpdate(user_id=111)
    u1.callback_query = FakeCallbackQuery("grid_setup_mode:default", 111)
    await _find_callback(handler, conv_mod.GRID_SETUP_MODE)(u1, ctx1)
    u2 = FakeUpdate(text="BTCINR", user_id=111)
    await _find_callback(handler, conv_mod.DEFAULT_COIN)(u2, ctx1)
    u3 = FakeUpdate(user_id=111)
    u3.callback_query = FakeCallbackQuery("pick_mode:paper", 111)
    await _find_callback(handler, conv_mod.SELECT_MODE)(u3, ctx1)
    u4 = FakeUpdate(user_id=111)
    u4.callback_query = FakeCallbackQuery("confirm_grid:yes", 111)
    end_state = await _find_callback(handler, conv_mod.CONFIRM)(u4, ctx1)
    assert end_state == ConversationHandler.END

    grids = await repos.grids.list_all()
    assert len(grids) == 1

    # A fresh /newgrid must behave identically to the very first call.
    ctx2 = FakeContext()
    next_state = await handler.entry_points[0].callback(
        FakeUpdate(text="/newgrid", user_id=111), ctx2
    )
    assert next_state == conv_mod.GRID_SETUP_MODE


async def test_newgrid_then_other_command_recovers_via_fallback(app_context):
    """/newgrid -> user sends another command -> /newgrid.

    Simulates a user typing e.g. /status instead of tapping the Default/
    Custom button while in GRID_SETUP_MODE — a button-only state that has
    no in-state handler for arbitrary commands. Before the fix this
    silently wedged the conversation forever; now the catch-all fallback
    must end it cleanly so a subsequent /newgrid works.
    """
    handler = conv_mod.build_newgrid_conversation(app_context)
    ctx = FakeContext()
    await handler.entry_points[0].callback(FakeUpdate(text="/newgrid", user_id=111), ctx)

    stray_command = FakeUpdate(text="/status", user_id=111)
    end_state = await _fallback_callback(handler, "unexpected_command")(stray_command, ctx)

    assert end_state == ConversationHandler.END
    assert "isn't part of this flow" in stray_command.message.replies[-1]
    assert "/newgrid" in stray_command.message.replies[-1]

    # Recovery: /newgrid must work again immediately, not just after a restart.
    ctx2 = FakeContext()
    next_state = await handler.entry_points[0].callback(
        FakeUpdate(text="/newgrid", user_id=111), ctx2
    )
    assert next_state == conv_mod.GRID_SETUP_MODE


async def test_newgrid_invalid_input_recovers_without_wedging(app_context, repos):
    """/newgrid -> invalid/unexpected input -> recovery.

    Covers a text-input state (DEFAULT_COIN): a malformed symbol must
    re-prompt in the same state rather than ending or wedging, and the
    flow must still be completable afterwards with valid input.
    """
    handler = conv_mod.build_newgrid_conversation(app_context)
    ctx = FakeContext()
    await handler.entry_points[0].callback(FakeUpdate(text="/newgrid", user_id=111), ctx)
    u1 = FakeUpdate(user_id=111)
    u1.callback_query = FakeCallbackQuery("grid_setup_mode:default", 111)
    await _find_callback(handler, conv_mod.GRID_SETUP_MODE)(u1, ctx)

    bad = FakeUpdate(text="not-a-symbol!!", user_id=111)
    state_after_bad = await _find_callback(handler, conv_mod.DEFAULT_COIN)(bad, ctx)
    assert state_after_bad == conv_mod.DEFAULT_COIN, "must re-prompt, not wedge or end"

    good = FakeUpdate(text="BTCINR", user_id=111)
    state_after_good = await _find_callback(handler, conv_mod.DEFAULT_COIN)(good, ctx)
    assert state_after_good == conv_mod.SELECT_MODE

    u3 = FakeUpdate(user_id=111)
    u3.callback_query = FakeCallbackQuery("pick_mode:paper", 111)
    await _find_callback(handler, conv_mod.SELECT_MODE)(u3, ctx)
    u4 = FakeUpdate(user_id=111)
    u4.callback_query = FakeCallbackQuery("confirm_grid:yes", 111)
    end_state = await _find_callback(handler, conv_mod.CONFIRM)(u4, ctx)

    assert end_state == ConversationHandler.END
    grids = await repos.grids.list_all()
    assert len(grids) == 1, "flow must still complete normally after recovering from bad input"


async def test_conversation_timeout_ends_state_and_notifies_user(app_context):
    """conversation_timeout -> /newgrid.

    PTB re-dispatches the last update to the ConversationHandler.TIMEOUT
    handler after 300s of inactivity. This must always return END (so the
    per-user state is cleared) and best-effort notify the user, regardless
    of whether the last update was a Message or a CallbackQuery.
    """
    handler = conv_mod.build_newgrid_conversation(app_context)
    timeout_cb = next(
        h.callback for h in handler.states[ConversationHandler.TIMEOUT]
        if h.callback.__name__ == "conversation_timed_out"
    )

    ctx = FakeContext()
    stale_update = FakeUpdate(user_id=111)  # stands in for a stale Message or CallbackQuery update
    end_state = await timeout_cb(stale_update, ctx)

    assert end_state == ConversationHandler.END
    assert len(ctx.bot.sent_messages) == 1
    chat_id, text = ctx.bot.sent_messages[0]
    assert chat_id == stale_update.effective_chat.id
    assert "timed out" in text.lower()
    assert "/newgrid" in text

    # Recovery: /newgrid must work again immediately after a timeout.
    ctx2 = FakeContext()
    next_state = await handler.entry_points[0].callback(
        FakeUpdate(text="/newgrid", user_id=111), ctx2
    )
    assert next_state == conv_mod.GRID_SETUP_MODE


async def test_conversation_timeout_handler_survives_notification_failure(app_context):
    """If the timeout notification itself fails to send (e.g. user blocked
    the bot), the state must still clear — a failed notify must never
    recreate the wedge this fix removes."""
    handler = conv_mod.build_newgrid_conversation(app_context)
    timeout_cb = next(
        h.callback for h in handler.states[ConversationHandler.TIMEOUT]
        if h.callback.__name__ == "conversation_timed_out"
    )

    class BoomBot(FakeBot):
        async def send_message(self, chat_id: int, text: str, **kwargs) -> None:
            raise RuntimeError("user blocked the bot")

    ctx = FakeContext()
    ctx.bot = BoomBot()
    end_state = await timeout_cb(FakeUpdate(user_id=111), ctx)

    assert end_state == ConversationHandler.END


async def test_cancel_still_works_then_newgrid_recovers(app_context):
    """/cancel -> /newgrid: the pre-existing cancel path must keep working
    unchanged, and starting over afterwards must succeed."""
    handler = conv_mod.build_newgrid_conversation(app_context)
    ctx = FakeContext()
    await handler.entry_points[0].callback(FakeUpdate(text="/newgrid", user_id=111), ctx)

    cancel_update = FakeUpdate(text="/cancel", user_id=111)
    end_state = await _fallback_callback(handler, "cancel")(cancel_update, ctx)

    assert end_state == ConversationHandler.END
    assert "cancelled" in cancel_update.message.replies[-1].lower()

    ctx2 = FakeContext()
    next_state = await handler.entry_points[0].callback(
        FakeUpdate(text="/newgrid", user_id=111), ctx2
    )
    assert next_state == conv_mod.GRID_SETUP_MODE


async def test_newgrid_fallback_restarts_flow_from_button_only_state(app_context):
    """The /newgrid fallback (distinct from the entry_points /newgrid) must
    itself be reachable from mid-conversation and restart the menu, since
    this is the direct fix for state-machine re-entrancy from a button-only
    state such as SELECT_MODE."""
    handler = conv_mod.build_newgrid_conversation(app_context)
    ctx = FakeContext()
    await handler.entry_points[0].callback(FakeUpdate(text="/newgrid", user_id=111), ctx)
    u1 = FakeUpdate(user_id=111)
    u1.callback_query = FakeCallbackQuery("grid_setup_mode:custom", 111)
    await _find_callback(handler, conv_mod.GRID_SETUP_MODE)(u1, ctx)  # now in SELECT_COIN

    restart_update = FakeUpdate(text="/newgrid", user_id=111)
    next_state = await _fallback_callback(handler, "start")(restart_update, ctx)

    assert next_state == conv_mod.GRID_SETUP_MODE
    assert ctx.user_data == {}, "restarting must clear stale user_data from the abandoned attempt"

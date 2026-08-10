"""Reusable inline and reply keyboards for the DCA grid bot."""

from __future__ import annotations

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup

POPULAR_COINS = ["BTCINR", "ETHINR", "BNBINR", "SOLINR", "DOGEINR", "XRPINR"]


def coin_selection_keyboard() -> InlineKeyboardMarkup:
    buttons = [
        InlineKeyboardButton(coin, callback_data=f"pick_coin:{coin}")
        for coin in POPULAR_COINS
    ]
    rows = [buttons[i : i + 3] for i in range(0, len(buttons), 3)]
    rows.append(
        [InlineKeyboardButton("✏️ Type a different symbol…", callback_data="pick_coin:custom")]
    )
    return InlineKeyboardMarkup(rows)


def grid_mode_choice_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [InlineKeyboardButton("1️⃣ Default Grid", callback_data="grid_setup_mode:default")],
            [InlineKeyboardButton("2️⃣ Custom Grid", callback_data="grid_setup_mode:custom")],
        ]
    )


def trailing_choice_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [InlineKeyboardButton("✅ Enable trailing", callback_data="trailing_choice:yes")],
            [InlineKeyboardButton("Skip — fixed profit target", callback_data="trailing_choice:no")],
        ]
    )


def confirm_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton("✅ Confirm & Start", callback_data="confirm_grid:yes"),
                InlineKeyboardButton("❌ Cancel", callback_data="confirm_grid:no"),
            ]
        ]
    )


def grid_action_keyboard(grid_id: str, status: str) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    if status == "active":
        rows.append(
            [InlineKeyboardButton("⏸ Pause", callback_data=f"grid_action:pause:{grid_id}")]
        )
    elif status == "paused":
        rows.append(
            [InlineKeyboardButton("▶️ Resume", callback_data=f"grid_action:resume:{grid_id}")]
        )
    if status in ("active", "paused"):
        rows.append(
            [InlineKeyboardButton("🛑 Stop", callback_data=f"grid_action:stop:{grid_id}")]
        )
    return InlineKeyboardMarkup(rows) if rows else InlineKeyboardMarkup([[]])


def clear_emergency_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton("✅ Yes, re-enable trading", callback_data="emergency:clear"),
                InlineKeyboardButton("❌ Cancel", callback_data="emergency:cancel"),
            ]
        ]
    )


def trading_mode_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton("🟢 Paper Trade", callback_data="pick_mode:paper"),
                InlineKeyboardButton("🔴 Real Trade", callback_data="pick_mode:real"),
            ]
        ]
    )


def manual_trade_confirm_keyboard(action: str, grid_id: str, amount: float | None) -> InlineKeyboardMarkup:
    """action is 'buy' or 'sell'; amount=None means 'sell entire position'
    (only valid for sell). Encoded compactly in callback_data since
    Telegram caps it at 64 bytes: mtrade:<action>:<grid_id>:<amount|ALL>.
    """
    amount_token = "ALL" if amount is None else f"{amount:.2f}"
    data = f"mtrade:{action}:{grid_id}:{amount_token}"
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton("✅ Confirm", callback_data=data),
                InlineKeyboardButton("❌ Cancel", callback_data="mtrade:cancel:-:-"),
            ]
        ]
    )


def restorelist_pagination_keyboard(current_page: int, total_pages: int) -> InlineKeyboardMarkup | None:
    """Prev/Next buttons for /restorelist. Returns None when there's only
    one page (no point showing disabled-looking buttons for nothing)."""
    if total_pages <= 1:
        return None
    row = []
    if current_page > 1:
        row.append(InlineKeyboardButton("◀️ Prev", callback_data=f"restorelist_page:{current_page - 1}"))
    if current_page < total_pages:
        row.append(InlineKeyboardButton("Next ▶️", callback_data=f"restorelist_page:{current_page + 1}"))
    return InlineKeyboardMarkup([row])


def restore_confirm_keyboard(file_id: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton("⚠️ Yes, stage this restore", callback_data=f"restorebackup_confirm:{file_id}"),
                InlineKeyboardButton("❌ Cancel", callback_data="restorebackup_confirm:cancel"),
            ]
        ]
    )


def main_menu_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        [
            ["/newgrid", "/grids"],
            ["/status", "/positions"],
            ["/profit", "/summary"],
            ["/logs", "/help"],
        ],
        resize_keyboard=True,
    )

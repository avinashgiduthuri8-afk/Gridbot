"""Reusable inline/reply keyboards for the interactive /startgrid flow and
quick actions."""

from __future__ import annotations

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup

POPULAR_COINS = ["BTCINR", "ETHINR", "SOLINR", "DOGEINR", "XRPINR", "MATICINR"]


def coin_selection_keyboard() -> InlineKeyboardMarkup:
    buttons = [InlineKeyboardButton(coin, callback_data=f"pick_coin:{coin}") for coin in POPULAR_COINS]
    rows = [buttons[i : i + 3] for i in range(0, len(buttons), 3)]
    rows.append([InlineKeyboardButton("Type a different symbol...", callback_data="pick_coin:custom")])
    return InlineKeyboardMarkup(rows)


def grid_type_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton("Arithmetic (equal ₹ spacing)", callback_data="grid_type:arithmetic"),
                InlineKeyboardButton("Geometric (equal % spacing)", callback_data="grid_type:geometric"),
            ]
        ]
    )


def confirm_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton("✅ Confirm & Create", callback_data="confirm_grid:yes"),
                InlineKeyboardButton("❌ Cancel", callback_data="confirm_grid:no"),
            ]
        ]
    )


def grid_action_keyboard(grid_id: str, status: str) -> InlineKeyboardMarkup:
    rows = []
    if status == "active":
        rows.append([InlineKeyboardButton("⏸ Pause", callback_data=f"grid_action:pause:{grid_id}")])
    elif status == "paused":
        rows.append([InlineKeyboardButton("▶️ Resume", callback_data=f"grid_action:resume:{grid_id}")])
    if status in ("active", "paused"):
        rows.append([InlineKeyboardButton("🛑 Stop", callback_data=f"grid_action:stop:{grid_id}")])
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


def main_menu_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        [
            ["/startgrid", "/grids"],
            ["/status", "/positions"],
            ["/profit", "/settings"],
            ["/help"],
        ],
        resize_keyboard=True,
    )

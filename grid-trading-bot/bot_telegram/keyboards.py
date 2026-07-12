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

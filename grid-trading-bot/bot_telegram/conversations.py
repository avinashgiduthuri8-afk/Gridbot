"""ConversationHandler implementing the guided /startgrid flow:

Select Coin -> Upper Price -> Lower Price -> Grid Levels -> Investment/Grid
-> Grid Type -> Summary -> Confirm -> Create Grid
"""

from __future__ import annotations

from telegram import Update
from telegram.ext import (
    CallbackQueryHandler,
    ContextTypes,
    ConversationHandler,
    MessageHandler,
    filters,
)

from config.constants import GridType
from grid.generator import GridValidationError, validate_grid_params
from bot_telegram.keyboards import coin_selection_keyboard, confirm_keyboard, grid_type_keyboard
from trading.grid_manager import GridManagerError
from utils.logger import get_logger

log = get_logger("telegram")

SELECT_COIN, CUSTOM_COIN, UPPER_PRICE, LOWER_PRICE, GRID_LEVELS, INVESTMENT, GRID_TYPE, CONFIRM = range(8)


def build_startgrid_conversation(app_context: "BotAppContext") -> ConversationHandler:
    async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        if not app_context.is_authorized(update.effective_user.id):
            await update.message.reply_text("You are not authorized to use this bot.")
            return ConversationHandler.END
        context.user_data.clear()
        await update.message.reply_text(
            "Let's set up a new grid. Select a coin, or choose 'Type a different symbol...'.",
            reply_markup=coin_selection_keyboard(),
        )
        return SELECT_COIN

    async def coin_chosen(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        query = update.callback_query
        await query.answer()
        _, coin = query.data.split(":", 1)
        if coin == "custom":
            await query.edit_message_text("Type the trading symbol, e.g. BTCINR:")
            return CUSTOM_COIN
        context.user_data["symbol"] = coin
        await query.edit_message_text(f"Coin: {coin}\n\nEnter the UPPER price of the grid (₹):")
        return UPPER_PRICE

    async def custom_coin_entered(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        symbol = update.message.text.strip().upper()
        context.user_data["symbol"] = symbol
        await update.message.reply_text(f"Coin: {symbol}\n\nEnter the UPPER price of the grid (₹):")
        return UPPER_PRICE

    async def upper_price_entered(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        try:
            context.user_data["upper_price"] = float(update.message.text.strip())
        except ValueError:
            await update.message.reply_text("Please enter a valid number for the upper price.")
            return UPPER_PRICE
        await update.message.reply_text("Enter the LOWER price of the grid (₹):")
        return LOWER_PRICE

    async def lower_price_entered(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        try:
            context.user_data["lower_price"] = float(update.message.text.strip())
        except ValueError:
            await update.message.reply_text("Please enter a valid number for the lower price.")
            return LOWER_PRICE
        await update.message.reply_text("Enter the number of grid levels (3-50):")
        return GRID_LEVELS

    async def grid_levels_entered(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        try:
            context.user_data["grid_levels"] = int(update.message.text.strip())
        except ValueError:
            await update.message.reply_text("Please enter a whole number for grid levels.")
            return GRID_LEVELS
        await update.message.reply_text("Enter the investment amount per grid order (₹):")
        return INVESTMENT

    async def investment_entered(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        try:
            context.user_data["investment_per_grid"] = float(update.message.text.strip())
        except ValueError:
            await update.message.reply_text("Please enter a valid number for investment per grid.")
            return INVESTMENT
        await update.message.reply_text("Choose the grid type:", reply_markup=grid_type_keyboard())
        return GRID_TYPE

    async def grid_type_chosen(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        query = update.callback_query
        await query.answer()
        _, grid_type = query.data.split(":", 1)
        context.user_data["grid_type"] = grid_type

        data = context.user_data
        try:
            validate_grid_params(
                data["upper_price"], data["lower_price"], data["grid_levels"], data["investment_per_grid"]
            )
        except GridValidationError as exc:
            await query.edit_message_text(f"Invalid configuration: {exc}\n\nUse /startgrid to try again.")
            return ConversationHandler.END

        total_investment = data["investment_per_grid"] * max(data["grid_levels"] - 1, 0)
        summary = (
            "<b>Grid Summary</b>\n\n"
            f"Coin: <b>{data['symbol']}</b>\n"
            f"Type: {grid_type}\n"
            f"Range: ₹{data['lower_price']:,.2f} – ₹{data['upper_price']:,.2f}\n"
            f"Levels: {data['grid_levels']}\n"
            f"Investment/grid: ₹{data['investment_per_grid']:,.2f}\n"
            f"Estimated total capital required: ₹{total_investment:,.2f}\n\n"
            "Confirm to create this grid?"
        )
        await query.edit_message_text(summary, parse_mode="HTML", reply_markup=confirm_keyboard())
        return CONFIRM

    async def confirm(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        query = update.callback_query
        await query.answer()
        _, choice = query.data.split(":", 1)
        if choice == "no":
            await query.edit_message_text("Grid creation cancelled.")
            return ConversationHandler.END

        data = context.user_data
        try:
            record = await app_context.grid_manager.start_grid(
                symbol=data["symbol"],
                upper_price=data["upper_price"],
                lower_price=data["lower_price"],
                grid_levels=data["grid_levels"],
                investment_per_grid=data["investment_per_grid"],
                grid_type=GridType(data["grid_type"]),
            )
            await query.edit_message_text(
                f"✅ Grid created: <code>{record.grid_id}</code> for {record.symbol}.",
                parse_mode="HTML",
            )
        except GridManagerError as exc:
            await query.edit_message_text(f"❌ Could not start grid: {exc}")
        except Exception as exc:  # noqa: BLE001
            log.exception("Unexpected error creating grid")
            await query.edit_message_text(f"❌ Unexpected error creating grid: {exc}")
        return ConversationHandler.END

    async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        await update.message.reply_text("Cancelled.")
        return ConversationHandler.END

    return ConversationHandler(
        entry_points=[MessageHandler(filters.Regex("^/startgrid$"), start)],
        states={
            SELECT_COIN: [CallbackQueryHandler(coin_chosen, pattern="^pick_coin:")],
            CUSTOM_COIN: [MessageHandler(filters.TEXT & ~filters.COMMAND, custom_coin_entered)],
            UPPER_PRICE: [MessageHandler(filters.TEXT & ~filters.COMMAND, upper_price_entered)],
            LOWER_PRICE: [MessageHandler(filters.TEXT & ~filters.COMMAND, lower_price_entered)],
            GRID_LEVELS: [MessageHandler(filters.TEXT & ~filters.COMMAND, grid_levels_entered)],
            INVESTMENT: [MessageHandler(filters.TEXT & ~filters.COMMAND, investment_entered)],
            GRID_TYPE: [CallbackQueryHandler(grid_type_chosen, pattern="^grid_type:")],
            CONFIRM: [CallbackQueryHandler(confirm, pattern="^confirm_grid:")],
        },
        fallbacks=[MessageHandler(filters.Regex("^/cancel$"), cancel)],
        name="startgrid_conversation",
        persistent=False,
    )

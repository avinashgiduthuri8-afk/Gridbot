"""Command handlers for all non-conversation Telegram commands."""

from __future__ import annotations

import csv
import io
import os

from telegram import InputFile, Update
from telegram.ext import CallbackQueryHandler, CommandHandler, ContextTypes

from bot_telegram.formatters import (
    format_daily_summary,
    format_grid_list,
    format_grid_summary,
    format_logs,
    format_positions,
    format_profit_summary,
    format_settings,
    format_trade_history,
)
from bot_telegram.keyboards import clear_emergency_keyboard, grid_action_keyboard, main_menu_keyboard
from trading.grid_manager import GridManagerError
from utils.helpers import now_iso
from utils.logger import get_logger

log = get_logger("telegram")

HELP_TEXT = (
    "<b>Manual Grid Trading Bot</b>\n\n"
    "<b>Grid control</b>\n"
    "/startgrid — start a new grid (guided setup)\n"
    "/stopgrid &lt;grid_id&gt; — stop a running grid\n"
    "/pause &lt;grid_id&gt; — pause a grid (cancels resting orders)\n"
    "/resume &lt;grid_id&gt; — resume a paused grid\n\n"
    "<b>Monitoring</b>\n"
    "/status — overview of the bot and wallet\n"
    "/grids — list all grids\n"
    "/positions — list open positions\n"
    "/profit — realized profit summary\n"
    "/summary — today's P&amp;L, lifetime profit, and grid standings\n"
    "/history &lt;symbol&gt; — recent buy/sell fills for a coin\n"
    "/export — download full trade history as a CSV file\n"
    "/backup — download the raw SQLite database file\n"
    "/logs — recent log entries\n\n"
    "<b>Emergency control</b>\n"
    "/emergencystop — immediately halt all new trades and grid starts\n"
    "/clearemergency — re-enable trading (requires confirmation)\n\n"
    "<b>Configuration</b>\n"
    "/settings — view saved per-coin settings\n"
    "/setinvestment &lt;symbol&gt; &lt;amount&gt; — update investment per grid order\n"
    "/setlevels &lt;symbol&gt; &lt;levels&gt; — update grid level count for future grids\n"
    "/setrange &lt;symbol&gt; &lt;lower&gt; &lt;upper&gt; — update default price range\n\n"
    "The bot never scans markets or recommends coins — you always choose what to trade."
)


def register_handlers(app, app_context: "BotAppContext") -> None:
    def authorized(handler):
        async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE):
            user = update.effective_user
            if user is None or not app_context.is_authorized(user.id):
                if update.message:
                    await update.message.reply_text("You are not authorized to use this bot.")
                return
            return await handler(update, context)

        return wrapper

    @authorized
    async def start_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        await update.message.reply_text(
            "Welcome to your Manual Grid Trading Bot for CoinDCX.\n\n"
            "You choose the coin and range — the bot manages the grid.\n"
            "Use /help to see all commands.",
            reply_markup=main_menu_keyboard(),
        )

    @authorized
    async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        await update.message.reply_text(HELP_TEXT, parse_mode="HTML")

    @authorized
    async def status_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        repos = app_context.repos
        active_grids = await repos.grids.list_by_status(["active", "paused"])
        try:
            balance = await app_context.exchange.get_balance("INR")
            balance_line = f"₹{balance.balance:,.2f} (locked ₹{balance.locked_balance:,.2f})"
        except Exception as exc:  # noqa: BLE001
            balance_line = f"Unavailable ({exc})"
        emergency = "ACTIVE 🚨" if app_context.risk_manager.emergency_stopped else "off"
        await update.message.reply_text(
            "<b>Bot Status</b>\n"
            f"Active/paused grids: {len(active_grids)}\n"
            f"INR wallet balance: {balance_line}\n"
            f"Emergency stop: {emergency}",
            parse_mode="HTML",
        )

    @authorized
    async def grids_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        grids = await app_context.repos.grids.list_all()
        await update.message.reply_text(format_grid_list(grids), parse_mode="HTML")
        for g in grids:
            if g["status"] in ("active", "paused"):
                await update.message.reply_text(
                    format_grid_summary(g), parse_mode="HTML",
                    reply_markup=grid_action_keyboard(g["grid_id"], g["status"]),
                )

    @authorized
    async def positions_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        positions = await app_context.repos.positions.list_all_open()
        await update.message.reply_text(format_positions(positions), parse_mode="HTML")

    @authorized
    async def profit_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        grids = await app_context.repos.grids.list_all()
        total = await app_context.repos.trade_history.total_realized_pnl()
        await update.message.reply_text(format_profit_summary(grids, total), parse_mode="HTML")

    @authorized
    async def summary_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        today = now_iso()[:10]
        daily_stats = await app_context.repos.daily_stats.get(today)
        active_grids = await app_context.repos.grids.list_by_status(["active", "paused"])
        lifetime_realized = await app_context.repos.trade_history.total_realized_pnl()
        text = format_daily_summary(today, daily_stats, active_grids, lifetime_realized)
        await update.message.reply_text(text, parse_mode="HTML")

    @authorized
    async def history_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not context.args:
            await update.message.reply_text("Usage: /history <symbol>")
            return
        symbol = context.args[0].upper()
        trades = await app_context.repos.trade_history.list_for_symbol(symbol, limit=20)
        await update.message.reply_text(format_trade_history(symbol, trades), parse_mode="HTML")

    @authorized
    async def export_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        trades = await app_context.repos.trade_history.list_all()
        if not trades:
            await update.message.reply_text("No trade history to export yet.")
            return

        buffer = io.StringIO()
        fieldnames = [
            "trade_id", "grid_id", "order_id", "symbol", "side",
            "price", "quantity", "fee", "pnl", "executed_at",
        ]
        writer = csv.DictWriter(buffer, fieldnames=fieldnames)
        writer.writeheader()
        for trade in trades:
            writer.writerow({key: trade.get(key, "") for key in fieldnames})

        csv_bytes = buffer.getvalue().encode("utf-8")
        filename = f"trade_history_{now_iso()[:10]}.csv"
        await update.message.reply_document(
            document=InputFile(io.BytesIO(csv_bytes), filename=filename),
            caption=f"Exported {len(trades)} trade(s).",
        )

    @authorized
    async def backup_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        db_path = app_context.settings.database_path
        if not os.path.exists(db_path):
            await update.message.reply_text("Database file not found — no data yet.")
            return
        size_kb = os.path.getsize(db_path) / 1024
        filename = f"grid_bot_backup_{now_iso()[:10]}.db"
        with open(db_path, "rb") as f:
            await update.message.reply_document(
                document=InputFile(f, filename=filename),
                caption=f"SQLite database backup ({size_kb:.1f} KB). Store safely — contains all grid configs and history.",
            )

    @authorized
    async def settings_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        configs = await app_context.repos.coin_configs.all()
        await update.message.reply_text(format_settings(configs), parse_mode="HTML")

    @authorized
    async def logs_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        logs = await app_context.repos.logs.recent(limit=25)
        await update.message.reply_text(format_logs(logs), parse_mode="HTML")

    @authorized
    async def stopgrid_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not context.args:
            await update.message.reply_text("Usage: /stopgrid <grid_id>")
            return
        try:
            await app_context.grid_manager.stop_grid(context.args[0])
            await update.message.reply_text("Grid stopped.")
        except GridManagerError as exc:
            await update.message.reply_text(f"Error: {exc}")

    @authorized
    async def pause_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not context.args:
            await update.message.reply_text("Usage: /pause <grid_id>")
            return
        try:
            await app_context.grid_manager.pause_grid(context.args[0])
            await update.message.reply_text("Grid paused.")
        except GridManagerError as exc:
            await update.message.reply_text(f"Error: {exc}")

    @authorized
    async def resume_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not context.args:
            await update.message.reply_text("Usage: /resume <grid_id>")
            return
        try:
            await app_context.grid_manager.resume_grid(context.args[0])
            await update.message.reply_text("Grid resumed.")
        except GridManagerError as exc:
            await update.message.reply_text(f"Error: {exc}")

    @authorized
    async def setinvestment_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if len(context.args) != 2:
            await update.message.reply_text("Usage: /setinvestment <symbol> <amount>")
            return
        symbol, amount = context.args[0].upper(), context.args[1]
        try:
            amount_f = float(amount)
        except ValueError:
            await update.message.reply_text("Amount must be a number.")
            return
        config = await app_context.repos.coin_configs.get(symbol)
        if not config:
            await update.message.reply_text(f"No saved settings for {symbol} yet. Use /startgrid first.")
            return
        await app_context.repos.coin_configs.upsert(
            symbol=symbol, grid_levels=config["grid_levels"], investment_per_grid=amount_f,
            upper_price=config["upper_price"], lower_price=config["lower_price"], grid_type=config["grid_type"],
        )
        await update.message.reply_text(f"Investment per grid for {symbol} updated to ₹{amount_f:,.2f}.")

    @authorized
    async def setlevels_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if len(context.args) != 2:
            await update.message.reply_text("Usage: /setlevels <symbol> <levels>")
            return
        symbol = context.args[0].upper()
        try:
            levels = int(context.args[1])
        except ValueError:
            await update.message.reply_text("Levels must be a whole number.")
            return
        config = await app_context.repos.coin_configs.get(symbol)
        if not config:
            await update.message.reply_text(f"No saved settings for {symbol} yet. Use /startgrid first.")
            return
        await app_context.repos.coin_configs.upsert(
            symbol=symbol, grid_levels=levels, investment_per_grid=config["investment_per_grid"],
            upper_price=config["upper_price"], lower_price=config["lower_price"], grid_type=config["grid_type"],
        )
        await update.message.reply_text(f"Grid levels for {symbol} updated to {levels} (applies to future grids).")

    @authorized
    async def setrange_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if len(context.args) != 3:
            await update.message.reply_text("Usage: /setrange <symbol> <lower> <upper>")
            return
        symbol = context.args[0].upper()
        try:
            lower_f, upper_f = float(context.args[1]), float(context.args[2])
        except ValueError:
            await update.message.reply_text("Lower and upper must be numbers.")
            return
        if upper_f <= lower_f:
            await update.message.reply_text("Upper price must be greater than lower price.")
            return
        config = await app_context.repos.coin_configs.get(symbol)
        if not config:
            await update.message.reply_text(f"No saved settings for {symbol} yet. Use /startgrid first.")
            return
        await app_context.repos.coin_configs.upsert(
            symbol=symbol, grid_levels=config["grid_levels"], investment_per_grid=config["investment_per_grid"],
            upper_price=upper_f, lower_price=lower_f, grid_type=config["grid_type"],
        )
        await update.message.reply_text(f"Range for {symbol} updated to ₹{lower_f:,.2f}-₹{upper_f:,.2f}.")

    @authorized
    async def emergencystop_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if app_context.risk_manager.emergency_stopped:
            await update.message.reply_text(
                "🚨 Emergency stop is already active. No new trades or grids are permitted.\n"
                "Use /clearemergency to re-enable trading."
            )
            return
        app_context.risk_manager.trigger_emergency_stop()
        log.warning("Emergency stop triggered by user %s", update.effective_user.id)
        await update.message.reply_text(
            "🚨 <b>EMERGENCY STOP ACTIVATED</b>\n\n"
            "All new grid starts and order placements are now blocked.\n"
            "Running grids will not place any further orders.\n\n"
            "Use /clearemergency to re-enable trading when you are ready.",
            parse_mode="HTML",
        )
        await app_context.notifier.send(
            "🚨 Emergency stop activated via Telegram. All new trades are blocked."
        )

    @authorized
    async def clearemergency_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not app_context.risk_manager.emergency_stopped:
            await update.message.reply_text("Emergency stop is not active — trading is already enabled.")
            return
        await update.message.reply_text(
            "⚠️ <b>Re-enable trading?</b>\n\n"
            "This will lift the emergency stop and allow new trades and grid starts.\n"
            "Are you sure?",
            parse_mode="HTML",
            reply_markup=clear_emergency_keyboard(),
        )

    async def emergency_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        query = update.callback_query
        if not app_context.is_authorized(query.from_user.id):
            await query.answer("Not authorized.", show_alert=True)
            return
        await query.answer()
        action = query.data.split(":")[1]
        if action == "clear":
            app_context.risk_manager.clear_emergency_stop()
            log.info("Emergency stop cleared by user %s", query.from_user.id)
            await query.edit_message_text(
                "✅ Emergency stop cleared. Trading is now re-enabled.\n\n"
                "Paused grids will not auto-resume — use /resume <grid_id> to restart each one manually.",
                parse_mode="HTML",
            )
            await app_context.notifier.send(
                "✅ Emergency stop cleared via Telegram. Trading is re-enabled."
            )
        elif action == "cancel":
            await query.edit_message_text("Cancelled. Emergency stop remains active.")

    async def grid_action_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        query = update.callback_query
        if not app_context.is_authorized(query.from_user.id):
            await query.answer("Not authorized.", show_alert=True)
            return
        await query.answer()
        _, action, grid_id = query.data.split(":", 2)
        try:
            if action == "pause":
                await app_context.grid_manager.pause_grid(grid_id)
                await query.edit_message_text(f"Grid {grid_id} paused.")
            elif action == "resume":
                await app_context.grid_manager.resume_grid(grid_id)
                await query.edit_message_text(f"Grid {grid_id} resumed.")
            elif action == "stop":
                await app_context.grid_manager.stop_grid(grid_id)
                await query.edit_message_text(f"Grid {grid_id} stopped.")
        except GridManagerError as exc:
            await query.edit_message_text(f"Error: {exc}")

    app.add_handler(CommandHandler("start", start_cmd))
    app.add_handler(CommandHandler("help", help_cmd))
    app.add_handler(CommandHandler("status", status_cmd))
    app.add_handler(CommandHandler("grids", grids_cmd))
    app.add_handler(CommandHandler("positions", positions_cmd))
    app.add_handler(CommandHandler("profit", profit_cmd))
    app.add_handler(CommandHandler("summary", summary_cmd))
    app.add_handler(CommandHandler("history", history_cmd))
    app.add_handler(CommandHandler("export", export_cmd))
    app.add_handler(CommandHandler("backup", backup_cmd))
    app.add_handler(CommandHandler("settings", settings_cmd))
    app.add_handler(CommandHandler("logs", logs_cmd))
    app.add_handler(CommandHandler("stopgrid", stopgrid_cmd))
    app.add_handler(CommandHandler("pause", pause_cmd))
    app.add_handler(CommandHandler("resume", resume_cmd))
    app.add_handler(CommandHandler("setinvestment", setinvestment_cmd))
    app.add_handler(CommandHandler("setlevels", setlevels_cmd))
    app.add_handler(CommandHandler("setrange", setrange_cmd))
    app.add_handler(CommandHandler("emergencystop", emergencystop_cmd))
    app.add_handler(CommandHandler("clearemergency", clearemergency_cmd))
    app.add_handler(CallbackQueryHandler(emergency_callback, pattern="^emergency:"))
    app.add_handler(CallbackQueryHandler(grid_action_callback, pattern="^grid_action:"))

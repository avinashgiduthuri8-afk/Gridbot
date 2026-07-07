"""Command handlers for all non-conversation Telegram commands."""

from __future__ import annotations

import csv
import io
import os

from telegram import InputFile, Update
from telegram.ext import CallbackQueryHandler, CommandHandler, ContextTypes

from bot_telegram.formatters import (
    format_coin_info,
    format_daily_summary,
    format_grid_list,
    format_grid_summary,
    format_logs,
    format_monitor_status,
    format_paper_grids,
    format_positions,
    format_profit_summary,
    format_trade_history,
    format_wallet_balance,
)
from exchange.exceptions import ExchangeAuthError, ExchangeError
from bot_telegram.keyboards import clear_emergency_keyboard, grid_action_keyboard, main_menu_keyboard
from utils.helpers import now_iso
from utils.logger import get_logger

log = get_logger("telegram")

HELP_TEXT = (
    "<b>Manual DCA Grid Trading Bot</b>\n\n"
    "<b>Grid control</b>\n"
    "/newgrid — start a new DCA grid (guided 10-step setup, choose paper or real)\n"
    "/stopgrid &lt;grid_id&gt; — stop a running grid\n"
    "/pause &lt;grid_id&gt; — pause a grid\n"
    "/resume &lt;grid_id&gt; — resume a paused grid\n\n"
    "<b>Monitoring</b>\n"
    "/status — bot overview and wallet balance\n"
    "/balance — full real wallet breakdown with asset market values and unrealized P&amp;L\n"
    "/coininfo &lt;symbol&gt; — validate a pair and preview investment rules (e.g. /coininfo BNBINR)\n"
    "/paper — paper-trade grids with simulated realized + unrealized P&amp;L\n"
    "/grids — list all grids with DCA state\n"
    "/positions — coins currently held across all grids\n"
    "/profit — realized profit summary per grid\n"
    "/summary — today's P&amp;L and active grid standings\n"
    "/history &lt;symbol&gt; — recent buy/sell fills for a coin\n"
    "/monitor — price monitor status and active coins\n"
    "/monitor &lt;seconds&gt; — change refresh interval (2/5/10/15/30)\n"
    "/export — download full trade history as CSV\n"
    "/backup — download raw SQLite database\n"
    "/logs — recent log entries\n\n"
    "<b>Emergency control</b>\n"
    "/emergencystop — block all new trades immediately\n"
    "/clearemergency — re-enable trading (requires confirmation)\n\n"
    "<b>Price alerts</b>\n"
    "/alert &lt;symbol&gt; &lt;price&gt; — notify when price crosses a target\n"
    "/alerts — list all active price alerts\n"
    "/delalert &lt;symbol&gt; — cancel all alerts for a coin\n\n"
    "The bot never scans markets or recommends coins — you choose what to trade."
)


def register_handlers(app, app_context: "BotAppContext") -> None:  # noqa: F821
    def authorized(handler):
        async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE):
            user = update.effective_user
            if user is None or not app_context.is_authorized(user.id):
                if update.message:
                    await update.message.reply_text("You are not authorized to use this bot.")
                return
            return await handler(update, context)
        return wrapper

    # ------------------------------------------------------------------
    # Info
    # ------------------------------------------------------------------

    @authorized
    async def start_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        await update.message.reply_text(
            "👋 Welcome to your <b>Manual DCA Grid Trading Bot</b> for CoinDCX.\n\n"
            "You set the coin and parameters — the bot manages dip buys, "
            "average price tracking, profit sells, and stop loss automatically.\n\n"
            "Use /newgrid to create your first DCA grid, or /help for all commands.",
            parse_mode="HTML",
            reply_markup=main_menu_keyboard(),
        )

    @authorized
    async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        await update.message.reply_text(HELP_TEXT, parse_mode="HTML")

    # ------------------------------------------------------------------
    # Status and monitoring
    # ------------------------------------------------------------------

    @authorized
    async def status_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        active_grids = await app_context.repos.grids.list_by_status(["active", "paused"])
        try:
            balance = await app_context.exchange.get_balance("INR")
            balance_line = f"₹{balance.balance:,.2f} (locked ₹{balance.locked_balance:,.2f})"
        except Exception as exc:  # noqa: BLE001
            balance_line = f"Unavailable ({exc})"
        emergency = "ACTIVE 🚨" if app_context.risk_manager.emergency_stopped else "off"
        total_invested = sum(float(g["total_investment"] or 0) for g in active_grids)
        await update.message.reply_text(
            "<b>Bot Status</b>\n"
            f"Active/paused grids: {len(active_grids)}\n"
            f"Total capital deployed: ₹{total_invested:,.2f}\n"
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
                    format_grid_summary(g),
                    parse_mode="HTML",
                    reply_markup=grid_action_keyboard(g["grid_id"], g["status"]),
                )

    @authorized
    async def positions_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        grids = await app_context.repos.grids.list_all()
        await update.message.reply_text(format_positions(grids), parse_mode="HTML")

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
            await update.message.reply_text("Usage: /history <symbol>\nExample: /history BTCINR")
            return
        symbol = context.args[0].upper()
        trades = await app_context.repos.trade_history.list_for_symbol(symbol, limit=20)
        await update.message.reply_text(format_trade_history(symbol, trades), parse_mode="HTML")

    @authorized
    async def balance_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        await update.message.reply_text("⏳ Fetching wallet balance…")
        try:
            balances = await app_context.exchange.get_balances()
        except ExchangeAuthError:
            await update.message.reply_text(
                "❌ Authentication failed. Check your CoinDCX API key and secret."
            )
            return
        except ExchangeError as exc:
            await update.message.reply_text(f"❌ Could not fetch wallet: {exc}")
            return

        crypto_items = [
            b for b in balances
            if b.currency.upper() != "INR" and (b.balance + b.locked_balance) > 0
        ]

        # Batch-fetch prices in one API call where possible
        symbols = {f"{b.currency.upper()}INR" for b in crypto_items}
        prices: dict[str, float] = {}
        try:
            tickers = await app_context.exchange.get_tickers_batch(symbols)
            for sym, ticker in tickers.items():
                currency = sym.replace("INR", "")
                prices[currency] = ticker.last_price
        except Exception:  # noqa: BLE001
            # Fall back to individual fetches
            for b in crypto_items:
                sym = f"{b.currency.upper()}INR"
                try:
                    ticker = await app_context.exchange.get_ticker(sym)
                    prices[b.currency.upper()] = ticker.last_price
                except Exception:  # noqa: BLE001
                    pass

        # Fetch active grids for unrealized P&L computation
        try:
            active_grids = await app_context.repos.grids.list_by_status(["active", "paused"])
        except Exception:  # noqa: BLE001
            active_grids = []

        text = format_wallet_balance(balances, prices, grids=active_grids)
        await update.message.reply_text(text, parse_mode="HTML")

    @authorized
    async def coininfo_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """/coininfo <symbol> — validate a pair and show market + investment info."""
        from trading.coin_validator import CoinValidator
        from config.constants import (
            DEFAULT_BASE_INVESTMENT,
            DEFAULT_DIP_BUY_AMOUNT,
            DEFAULT_PROFIT_SELL_AMOUNT,
        )

        if not context.args:
            await update.message.reply_text(
                "Usage: /coininfo &lt;symbol&gt;\nExample: <code>/coininfo BNBINR</code>",
                parse_mode="HTML",
            )
            return

        symbol = context.args[0].strip().upper()
        if not symbol.endswith("INR"):
            symbol = symbol + "INR"

        await update.message.reply_text(f"⏳ Looking up <b>{symbol}</b>…", parse_mode="HTML")

        validator = CoinValidator(app_context.exchange)

        # 1. Validate pair
        valid, reason = await validator.validate_pair(symbol)
        if not valid:
            await update.message.reply_text(reason, parse_mode="HTML")
            return

        # 2. Fetch live data
        try:
            market_info = await app_context.exchange.get_market_info(symbol)
            extended_ticker = await app_context.exchange.get_extended_ticker(symbol)
        except ExchangeError as exc:
            await update.message.reply_text(f"❌ Could not fetch data for {symbol}: {exc}")
            return

        price = extended_ticker.last_price
        if price <= 0:
            await update.message.reply_text(
                f"❌ {symbol} returned a zero price — the pair may be delisted or suspended."
            )
            return

        # 3. Validate investment amounts at the current price
        base_result = await validator.validate_investment(symbol, DEFAULT_BASE_INVESTMENT, price)
        dip_result = await validator.validate_investment(symbol, DEFAULT_DIP_BUY_AMOUNT, price)
        profit_result = await validator.validate_investment(symbol, DEFAULT_PROFIT_SELL_AMOUNT, price)

        text = format_coin_info(
            symbol=symbol,
            market_info=market_info,
            extended_ticker=extended_ticker,
            base_validation=base_result,
            dip_validation=dip_result,
            profit_validation=profit_result,
        )
        await update.message.reply_text(text, parse_mode="HTML")

    @authorized
    async def paper_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        all_grids = await app_context.repos.grids.list_all()
        paper_grids = [g for g in all_grids if g.get("mode") == "paper"]

        prices: dict[str, float] = {}
        for g in paper_grids:
            if g["status"] in ("active", "paused") and g["total_quantity"] > 0:
                symbol = g["symbol"]
                if symbol not in prices:
                    try:
                        ticker = await app_context.exchange.get_ticker(symbol)
                        prices[symbol] = ticker.last_price
                    except Exception:  # noqa: BLE001
                        pass

        text = format_paper_grids(all_grids, prices)
        await update.message.reply_text(text, parse_mode="HTML")

    @authorized
    async def monitor_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Show price monitor status, or change the refresh interval."""
        from storage.repositories import VALID_MONITOR_INTERVALS

        if context.args:
            # /monitor <seconds> — change the interval
            raw = context.args[0].strip()
            try:
                seconds = int(raw)
            except ValueError:
                await update.message.reply_text(
                    f"❌ Invalid interval <code>{raw}</code>.\n"
                    f"Allowed: {', '.join(str(v) for v in VALID_MONITOR_INTERVALS)} seconds.",
                    parse_mode="HTML",
                )
                return
            try:
                await app_context.price_monitor.set_interval(seconds)
            except ValueError as exc:
                await update.message.reply_text(f"❌ {exc}", parse_mode="HTML")
                return
            await update.message.reply_text(
                f"✅ Price monitor interval updated to <b>{seconds}s</b>.\n"
                "Change takes effect at the start of the next cycle.",
                parse_mode="HTML",
            )
            return

        # /monitor — show status
        status = app_context.price_monitor.get_status()
        await update.message.reply_text(
            format_monitor_status(status),
            parse_mode="HTML",
        )

    @authorized
    async def logs_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        entries = await app_context.repos.logs.recent(limit=25)
        await update.message.reply_text(format_logs(entries), parse_mode="HTML")

    # ------------------------------------------------------------------
    # Export / backup
    # ------------------------------------------------------------------

    @authorized
    async def export_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        trades = await app_context.repos.trade_history.list_all()
        if not trades:
            await update.message.reply_text("No trade history to export yet.")
            return
        buffer = io.StringIO()
        fieldnames = [
            "trade_id", "grid_id", "order_id", "symbol", "side",
            "price", "quantity", "investment_inr", "fee", "pnl", "executed_at",
        ]
        writer = csv.DictWriter(buffer, fieldnames=fieldnames)
        writer.writeheader()
        for trade in trades:
            writer.writerow({k: trade.get(k, "") for k in fieldnames})
        csv_bytes = buffer.getvalue().encode("utf-8")
        filename = f"dca_trade_history_{now_iso()[:10]}.csv"
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
        filename = f"dca_bot_backup_{now_iso()[:10]}.db"
        with open(db_path, "rb") as f:
            await update.message.reply_document(
                document=InputFile(f, filename=filename),
                caption=f"SQLite backup ({size_kb:.1f} KB). Keep it safe — contains all grids and history.",
            )

    # ------------------------------------------------------------------
    # Grid control
    # ------------------------------------------------------------------

    @authorized
    async def stopgrid_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not context.args:
            await update.message.reply_text("Usage: /stopgrid <grid_id>")
            return
        grid_id = context.args[0]
        try:
            await app_context.dca_manager.stop_grid(grid_id, reason="manual")
            await update.message.reply_text(f"🛑 Grid <code>{grid_id}</code> stopped.", parse_mode="HTML")
        except ValueError as exc:
            await update.message.reply_text(f"Error: {exc}")

    @authorized
    async def pause_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not context.args:
            await update.message.reply_text("Usage: /pause <grid_id>")
            return
        grid_id = context.args[0]
        try:
            await app_context.dca_manager.pause_grid(grid_id)
            await update.message.reply_text(f"⏸ Grid <code>{grid_id}</code> paused.", parse_mode="HTML")
        except ValueError as exc:
            await update.message.reply_text(f"Error: {exc}")

    @authorized
    async def resume_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not context.args:
            await update.message.reply_text("Usage: /resume <grid_id>")
            return
        grid_id = context.args[0]
        try:
            await app_context.dca_manager.resume_grid(grid_id)
            await update.message.reply_text(f"▶️ Grid <code>{grid_id}</code> resumed.", parse_mode="HTML")
        except ValueError as exc:
            await update.message.reply_text(f"Error: {exc}")

    # ------------------------------------------------------------------
    # Price alerts
    # ------------------------------------------------------------------

    @authorized
    async def alert_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if len(context.args) != 2:
            await update.message.reply_text("Usage: /alert <symbol> <price>\nExample: /alert BTCINR 6500000")
            return
        symbol = context.args[0].upper()
        try:
            target = float(context.args[1].replace(",", ""))
        except ValueError:
            await update.message.reply_text("Price must be a number.")
            return
        try:
            ticker = await app_context.exchange.get_ticker(symbol)
            current = ticker.last_price
        except Exception as exc:  # noqa: BLE001
            await update.message.reply_text(f"Could not fetch price for {symbol}: {exc}")
            return
        try:
            direction = app_context.alert_manager.add(symbol, target, current, now_iso())
        except ValueError as exc:
            await update.message.reply_text(str(exc))
            return
        arrow = "📈" if direction == "above" else "📉"
        await update.message.reply_text(
            f"{arrow} Alert set for <b>{symbol}</b>\n"
            f"Target: ₹{target:,.2f} ({direction})\n"
            f"Current: ₹{current:,.2f}\n\n"
            "You'll be notified when the price crosses this level.",
            parse_mode="HTML",
        )

    @authorized
    async def alerts_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        alerts = app_context.alert_manager.list_all()
        if not alerts:
            await update.message.reply_text("No active price alerts.")
            return
        lines = ["<b>Active Price Alerts</b>\n"]
        for a in alerts:
            arrow = "📈" if a.direction == "above" else "📉"
            lines.append(
                f"{arrow} <b>{a.symbol}</b> — ₹{a.target_price:,.2f} "
                f"({a.direction}) set {a.set_at[:10]}"
            )
        await update.message.reply_text("\n".join(lines), parse_mode="HTML")

    @authorized
    async def delalert_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not context.args:
            await update.message.reply_text("Usage: /delalert <symbol>")
            return
        symbol = context.args[0].upper()
        removed = app_context.alert_manager.delete(symbol)
        if removed:
            await update.message.reply_text(f"Removed {removed} alert(s) for {symbol}.")
        else:
            await update.message.reply_text(f"No active alerts found for {symbol}.")

    # ------------------------------------------------------------------
    # Emergency stop
    # ------------------------------------------------------------------

    @authorized
    async def emergencystop_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if app_context.risk_manager.emergency_stopped:
            await update.message.reply_text(
                "🚨 Emergency stop is already active.\nUse /clearemergency to re-enable trading."
            )
            return
        app_context.risk_manager.trigger_emergency_stop()
        log.warning("Emergency stop triggered by user %s", update.effective_user.id)
        await update.message.reply_text(
            "🚨 <b>EMERGENCY STOP ACTIVATED</b>\n\n"
            "All new order placements and grid starts are now blocked.\n\n"
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

    # ------------------------------------------------------------------
    # Callback handlers
    # ------------------------------------------------------------------

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
                "✅ Emergency stop cleared. Trading is re-enabled.\n\n"
                "Paused grids will not auto-resume — use /resume <grid_id> to restart each one.",
                parse_mode="HTML",
            )
            await app_context.notifier.send("✅ Emergency stop cleared via Telegram.")
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
                await app_context.dca_manager.pause_grid(grid_id)
                await query.edit_message_text(f"⏸ Grid <code>{grid_id}</code> paused.", parse_mode="HTML")
            elif action == "resume":
                await app_context.dca_manager.resume_grid(grid_id)
                await query.edit_message_text(f"▶️ Grid <code>{grid_id}</code> resumed.", parse_mode="HTML")
            elif action == "stop":
                await app_context.dca_manager.stop_grid(grid_id, reason="manual")
                await query.edit_message_text(f"🛑 Grid <code>{grid_id}</code> stopped.", parse_mode="HTML")
        except ValueError as exc:
            await query.edit_message_text(f"Error: {exc}")

    # ------------------------------------------------------------------
    # Register
    # ------------------------------------------------------------------

    app.add_handler(CommandHandler("start", start_cmd))
    app.add_handler(CommandHandler("help", help_cmd))
    app.add_handler(CommandHandler("status", status_cmd))
    app.add_handler(CommandHandler("balance", balance_cmd))
    app.add_handler(CommandHandler("coininfo", coininfo_cmd))
    app.add_handler(CommandHandler("paper", paper_cmd))
    app.add_handler(CommandHandler("grids", grids_cmd))
    app.add_handler(CommandHandler("positions", positions_cmd))
    app.add_handler(CommandHandler("profit", profit_cmd))
    app.add_handler(CommandHandler("summary", summary_cmd))
    app.add_handler(CommandHandler("history", history_cmd))
    app.add_handler(CommandHandler("monitor", monitor_cmd))
    app.add_handler(CommandHandler("export", export_cmd))
    app.add_handler(CommandHandler("backup", backup_cmd))
    app.add_handler(CommandHandler("logs", logs_cmd))
    app.add_handler(CommandHandler("stopgrid", stopgrid_cmd))
    app.add_handler(CommandHandler("pause", pause_cmd))
    app.add_handler(CommandHandler("resume", resume_cmd))
    app.add_handler(CommandHandler("alert", alert_cmd))
    app.add_handler(CommandHandler("alerts", alerts_cmd))
    app.add_handler(CommandHandler("delalert", delalert_cmd))
    app.add_handler(CommandHandler("emergencystop", emergencystop_cmd))
    app.add_handler(CommandHandler("clearemergency", clearemergency_cmd))
    app.add_handler(CallbackQueryHandler(emergency_callback, pattern="^emergency:"))
    app.add_handler(CallbackQueryHandler(grid_action_callback, pattern="^grid_action:"))

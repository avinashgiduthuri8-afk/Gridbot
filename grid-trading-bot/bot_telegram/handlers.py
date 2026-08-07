"""Command handlers for all non-conversation Telegram commands."""

from __future__ import annotations

import csv
import io

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
from bot_telegram.keyboards import (
    clear_emergency_keyboard,
    grid_action_keyboard,
    main_menu_keyboard,
    manual_trade_confirm_keyboard,
    restore_confirm_keyboard,
    restorelist_pagination_keyboard,
)
from utils.helpers import now_iso
from utils.logger import get_logger

log = get_logger("telegram")

HELP_TEXT = (
    "<b>Manual DCA Grid Trading Bot</b>\n\n"
    "<b>Grid control</b>\n"
    "/newgrid — start a new DCA grid; choose <b>Default Grid</b> (just pick a "
    "coin, uses your saved defaults) or <b>Custom Grid</b> (full 11-step setup)\n"
    "/defaults — view or edit your saved Default Grid settings\n"
    "/stopgrid &lt;grid_id&gt; — stop a running grid\n"
    "/pause &lt;grid_id&gt; — pause a grid\n"
    "/resume &lt;grid_id&gt; — resume a paused grid\n"
    "/manualbuy &lt;grid_id&gt; &lt;inr_amount&gt; — place an extra buy right now, "
    "outside the automatic dip-buy ladder (asks for confirmation, same risk checks apply)\n"
    "/manualsell &lt;grid_id&gt; [inr_amount] — sell part or all of a position right "
    "now, regardless of current profit (asks for confirmation; omit the amount to sell everything)\n"
    "/adjustgrid &lt;grid_id&gt; &lt;field&gt; &lt;value&gt; — change one setting on a "
    "running grid without stopping it (dip/profit amounts and percentages, max "
    "levels, stop loss, trailing take-profit)\n\n"
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
    "\n"    "/backupstatus — check automatic Google Drive backup status (if enabled)\n"
    "/restorelist [page] — browse available Google Drive backups (newest first, 10 per page)\n"
    "/verifybackup &lt;number|latest&gt; — download and verify a backup is intact "
    "and restorable (integrity check + confirms core tables are present)\n"
    "/restorebackup &lt;number|latest&gt; — stage a full database restore from a "
    "backup; applies automatically on the next bot restart, never immediately "
    "(/restorebackup cancel to back out of a staged restore)\n"
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
        from config.constants import SYMBOL_PATTERN

        if not context.args:
            await update.message.reply_text("Usage: /history <symbol>\nExample: /history BTCINR")
            return
        symbol = context.args[0].upper()
        if not SYMBOL_PATTERN.match(symbol):
            # Reject before it's ever interpolated into an HTML-formatted
            # reply — unlike /alert, this command has no exchange lookup
            # gating it, so a malformed symbol would otherwise reach
            # format_trade_history() unfiltered and could break Telegram's
            # HTML entity parsing for this reply.
            await update.message.reply_text(
                "Symbol must be letters/numbers only. Example: /history BTCINR"
            )
            return
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

        from config.constants import SYMBOL_PATTERN

        symbol = context.args[0].strip().upper()
        if not symbol.endswith("INR"):
            symbol = symbol + "INR"
        if not SYMBOL_PATTERN.match(symbol):
            await update.message.reply_text(
                "Symbol must be letters/numbers only. Example: /coininfo BNBINR"
            )
            return

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
        # Disabled: sending raw SQLite database via Telegram is a security risk.
        await update.message.reply_text(
            "Database backup via Telegram has been disabled for security reasons."
        )

    @authorized
    async def backupstatus_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        from datetime import datetime, timezone

        def _time_ago(iso_str: str | None) -> str:
            if not iso_str:
                return "never"
            try:
                then = datetime.fromisoformat(iso_str)
            except ValueError:
                return iso_str
            delta = datetime.now(timezone.utc) - then
            seconds = delta.total_seconds()
            if seconds < 60:
                return f"{int(seconds)}s ago"
            if seconds < 3600:
                return f"{int(seconds // 60)}m ago"
            if seconds < 86400:
                return f"{seconds / 3600:.1f}h ago"
            return f"{seconds / 86400:.1f}d ago"

        backup_cfg = app_context.settings.backup
        if not backup_cfg.enabled:
            await update.message.reply_text(
                "☁️ <b>Drive Backup Status</b>\n\n"
                "Disabled. Set <code>GDRIVE_BACKUP_ENABLED=true</code> in .env to turn it on "
                "— see the README's \"Automatic Google Drive backup\" section.",
                parse_mode="HTML",
            )
            return

        status = await app_context.repos.monitor_settings.get_backup_status()
        lines = ["☁️ <b>Drive Backup Status</b>\n"]
        lines.append(f"Enabled: yes (every {backup_cfg.interval_hours:.1f}h, retaining {backup_cfg.retention_count} most recent)")

        if status is None:
            lines.append("\nNo backup has run yet — the first one fires "
                         f"~{backup_cfg.interval_hours:.1f}h after this bot started.")
        else:
            last_success_at = status.get("last_success_at")
            last_success_file = status.get("last_success_file_id")
            last_error_at = status.get("last_error_at")
            last_error_msg = status.get("last_error_message")

            if last_success_at:
                lines.append(f"\n✅ Last successful backup: {_time_ago(last_success_at)}")
                lines.append(f"   File ID: <code>{last_success_file}</code>")
            else:
                lines.append("\n⚠️ No successful backup recorded yet.")

            if last_error_at:
                # Only worth surfacing prominently if it's more recent than
                # the last success — otherwise it's a stale, already-resolved failure.
                is_more_recent = (not last_success_at) or (last_error_at > last_success_at)
                marker = "🔴" if is_more_recent else "ℹ️"
                lines.append(f"\n{marker} Last error: {_time_ago(last_error_at)}")
                lines.append(f"   {last_error_msg}")

        if app_context.drive_backup_manager is not None:
            try:
                backups = await app_context.drive_backup_manager.list_backups()
                lines.append(f"\n📁 {len(backups)} backup(s) currently in the Drive folder.")
            except Exception as exc:  # noqa: BLE001
                lines.append(f"\n⚠️ Could not reach Google Drive to confirm folder contents: {exc}")

        await update.message.reply_text("\n".join(lines), parse_mode="HTML")

    _RESTORELIST_PAGE_SIZE = 10

    def _human_size(num_bytes) -> str:
        try:
            n = float(num_bytes)
        except (TypeError, ValueError):
            return "unknown size"
        if n < 1024:
            return f"{n:.0f} B"
        if n < 1024 * 1024:
            return f"{n / 1024:.1f} KB"
        return f"{n / (1024 * 1024):.1f} MB"

    def _format_backup_datetime(created_time) -> str:
        if not created_time:
            return "unknown date"
        try:
            from datetime import datetime
            # Drive's createdTime is RFC3339, e.g. "2026-07-17T06:00:00.123Z"
            dt = datetime.fromisoformat(str(created_time).replace("Z", "+00:00"))
            return dt.strftime("%Y-%m-%d %H:%M UTC")
        except (ValueError, TypeError):
            return str(created_time)

    def _render_restorelist_page(backups: list, page: int) -> tuple[str, object]:
        """Shared by the command and the pagination callback. backups is
        expected oldest-first (as returned by list_backups()) — sorted
        newest-first here. Defensive against malformed entries (missing
        fields, non-numeric size) — never raises on bad metadata, just
        falls back to "unknown".
        """
        newest_first = list(reversed(backups))
        total = len(newest_first)
        page_size = _RESTORELIST_PAGE_SIZE
        total_pages = max(1, (total + page_size - 1) // page_size)
        page = max(1, min(page, total_pages))

        start = (page - 1) * page_size
        page_items = newest_first[start:start + page_size]

        lines = [f"📦 <b>Backup Restore List</b> (Page {page}/{total_pages})", f"Total backups: {total}\n"]
        for offset, backup in enumerate(page_items):
            number = start + offset + 1
            props = backup.get("properties") or {}
            backup_type = props.get("backup_type", "auto").capitalize()
            schema_version = props.get("schema_version", "unknown")
            lines.append(
                f"{number}. {_format_backup_datetime(backup.get('createdTime'))}\n"
                f"   <code>{backup.get('name', 'unknown')}</code>\n"
                f"   {_human_size(backup.get('size'))} | Schema v{schema_version} | {backup_type}"
            )

        text = "\n".join(lines)
        keyboard = restorelist_pagination_keyboard(page, total_pages)
        return text, keyboard

    @authorized
    async def restorelist_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not app_context.settings.backup.enabled or app_context.drive_backup_manager is None:
            await update.message.reply_text(
                "Google Drive backup isn't enabled — nothing to list. "
                "Set GDRIVE_BACKUP_ENABLED=true in .env; see the README's "
                "\"Automatic Google Drive backup\" section."
            )
            return

        try:
            backups = await app_context.drive_backup_manager.list_backups()
        except Exception as exc:  # noqa: BLE001
            await update.message.reply_text(
                f"⚠️ Could not reach Google Drive to list backups: {exc}\n\n"
                "This doesn't affect trading — only the ability to browse backups right now."
            )
            return

        if not backups:
            await update.message.reply_text(
                "📦 No backups found in the Drive folder yet.\n"
                "The first automatic one will appear after the configured backup interval, "
                "or check /backupstatus for details."
            )
            return

        page = 1
        if context.args:
            try:
                page = int(context.args[0])
            except ValueError:
                pass  # silently fall back to page 1 rather than error on a typo'd arg

        text, keyboard = _render_restorelist_page(backups, page)
        await update.message.reply_text(text, parse_mode="HTML", reply_markup=keyboard)

    async def restorelist_page_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        query = update.callback_query
        if not app_context.is_authorized(query.from_user.id):
            await query.answer("Not authorized.", show_alert=True)
            return
        await query.answer()

        if app_context.drive_backup_manager is None:
            await query.edit_message_text("Google Drive backup isn't enabled.")
            return

        _, page_str = query.data.split(":", 1)
        try:
            page = int(page_str)
        except ValueError:
            page = 1

        try:
            backups = await app_context.drive_backup_manager.list_backups()
        except Exception as exc:  # noqa: BLE001
            await query.edit_message_text(f"⚠️ Could not reach Google Drive to list backups: {exc}")
            return

        if not backups:
            await query.edit_message_text("📦 No backups found in the Drive folder.")
            return

        text, keyboard = _render_restorelist_page(backups, page)
        await query.edit_message_text(text, parse_mode="HTML", reply_markup=keyboard)

    def _resolve_backup_target(backups: list, arg: str) -> tuple[dict | None, str | None]:
        """Resolve a 'latest' or numeric CLI argument against the same
        newest-first numbering /restorelist shows. Returns (target, None)
        on success or (None, error_message) on failure — shared by
        /verifybackup and /restorebackup so the two can never number
        backups differently.
        """
        newest_first = list(reversed(backups))
        if arg.lower() == "latest":
            return newest_first[0], None
        try:
            index = int(arg)
        except ValueError:
            return None, "Backup number must be an integer, or 'latest'."
        if not (1 <= index <= len(newest_first)):
            return None, (
                f"No backup #{index} — there are {len(newest_first)} backups. "
                "Use /restorelist to see valid numbers."
            )
        return newest_first[index - 1], None

    @authorized
    async def verifybackup_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not app_context.settings.backup.enabled or app_context.drive_backup_manager is None:
            await update.message.reply_text(
                "Google Drive backup isn't enabled — nothing to verify."
            )
            return
        if not context.args:
            await update.message.reply_text(
                "Usage: /verifybackup <number>\n"
                "Use the number shown in /restorelist, or /verifybackup latest "
                "for the most recent backup.\n\n"
                "This downloads the backup and checks it's an intact, restorable "
                "database — not just that it exists in Drive."
            )
            return

        try:
            backups = await app_context.drive_backup_manager.list_backups()
        except Exception as exc:  # noqa: BLE001
            await update.message.reply_text(f"⚠️ Could not reach Google Drive to look up that backup: {exc}")
            return
        if not backups:
            await update.message.reply_text("📦 No backups found in the Drive folder to verify.")
            return

        target, error = _resolve_backup_target(backups, context.args[0])
        if error:
            await update.message.reply_text(error)
            return

        progress_msg = await update.message.reply_text(
            f"⏳ Downloading and verifying <code>{target.get('name', target['id'])}</code>…",
            parse_mode="HTML",
        )

        try:
            result = await app_context.drive_backup_manager.verify_backup_by_id(target["id"])
        except Exception as exc:  # noqa: BLE001
            await progress_msg.edit_text(f"⚠️ Could not verify this backup: {exc}")
            return

        if result["valid"]:
            lines = [
                f"✅ <b>Backup Verified</b>\n",
                f"File: <code>{target.get('name', target['id'])}</code>",
                f"Integrity check: {result['integrity_check']}",
                f"Schema version: {result.get('schema_version', 'unknown')}",
            ]
            row_counts = result.get("row_counts", {})
            if row_counts:
                counts_str = ", ".join(f"{k}: {v}" for k, v in row_counts.items())
                lines.append(f"Row counts: {counts_str}")
            if result.get("missing_optional_tables"):
                lines.append(
                    f"\nℹ️ Missing non-critical tables (normal for an older backup): "
                    f"{', '.join(result['missing_optional_tables'])}"
                )
            await progress_msg.edit_text("\n".join(lines), parse_mode="HTML")
        else:
            lines = [
                f"❌ <b>Backup FAILED Verification</b>\n",
                f"File: <code>{target.get('name', target['id'])}</code>",
                f"This backup should NOT be relied on for a restore.",
            ]
            if result.get("error"):
                lines.append(f"\nReason: {result['error']}")
            if result.get("missing_critical_tables"):
                lines.append(f"Missing critical tables: {', '.join(result['missing_critical_tables'])}")
            if result.get("integrity_check") and result["integrity_check"] != "ok":
                lines.append(f"SQLite integrity check: {result['integrity_check']}")
            await progress_msg.edit_text("\n".join(lines), parse_mode="HTML")

    @authorized
    async def restorebackup_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        from storage.restore import cancel_pending_restore, get_pending_restore

        if not app_context.settings.backup.enabled or app_context.drive_backup_manager is None:
            await update.message.reply_text("Google Drive backup isn't enabled — nothing to restore from.")
            return

        if not context.args:
            pending = get_pending_restore(app_context.settings.database_path)
            if pending:
                await update.message.reply_text(
                    f"⏳ A restore is already staged from <code>{pending.get('source_name')}</code> "
                    "and will be applied the next time this bot restarts.\n\n"
                    "Restart now to apply it, or /restorebackup cancel to back out.",
                    parse_mode="HTML",
                )
                return
            await update.message.reply_text(
                "Usage: /restorebackup <number|latest>\n"
                "Use the number shown in /restorelist.\n\n"
                "⚠️ This replaces your ENTIRE database (all grids, orders, and "
                "history) with the chosen backup — but only after you restart the "
                "bot; nothing changes while it's running. Your current database is "
                "backed up first, automatically.\n\n"
                "/restorebackup cancel — cancel a pending staged restore"
            )
            return

        if context.args[0].lower() == "cancel":
            cancelled = cancel_pending_restore(app_context.settings.database_path)
            await update.message.reply_text(
                "✅ Pending restore cancelled." if cancelled else "There was no pending restore to cancel."
            )
            return

        try:
            backups = await app_context.drive_backup_manager.list_backups()
        except Exception as exc:  # noqa: BLE001
            await update.message.reply_text(f"⚠️ Could not reach Google Drive to look up that backup: {exc}")
            return
        if not backups:
            await update.message.reply_text("📦 No backups found in the Drive folder to restore from.")
            return

        target, error = _resolve_backup_target(backups, context.args[0])
        if error:
            await update.message.reply_text(error)
            return

        await update.message.reply_text(
            f"⚠️ <b>Confirm Database Restore</b>\n\n"
            f"Backup: <code>{target.get('name', target['id'])}</code>\n"
            f"Taken: {_format_backup_datetime(target.get('createdTime'))}\n\n"
            "This will <b>replace your entire database</b> — every grid, order, "
            "and trade record — with this backup's contents, the next time the "
            "bot restarts. It does not happen immediately, and does not affect "
            "this running session at all.\n\n"
            "Your current database is backed up automatically before the swap, "
            "so this can be undone by restoring that file manually if needed.\n\n"
            "Are you sure?",
            parse_mode="HTML",
            reply_markup=restore_confirm_keyboard(target["id"]),
        )

    async def restorebackup_confirm_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        query = update.callback_query
        if not app_context.is_authorized(query.from_user.id):
            await query.answer("Not authorized.", show_alert=True)
            return
        await query.answer()

        _, file_id = query.data.split(":", 1)
        if file_id == "cancel":
            await query.edit_message_text("❌ Restore cancelled — nothing was changed.")
            return

        if app_context.drive_backup_manager is None:
            await query.edit_message_text("Google Drive backup isn't enabled.")
            return

        from storage.restore import stage_restore

        try:
            backups = await app_context.drive_backup_manager.list_backups()
            source = next((b for b in backups if b["id"] == file_id), None)
            source_name = source.get("name", file_id) if source else file_id

            await query.edit_message_text("⏳ Downloading and verifying the backup before staging it…")
            await stage_restore(
                app_context.drive_backup_manager, file_id,
                app_context.settings.database_path, source_name,
            )
        except Exception as exc:  # noqa: BLE001
            await query.edit_message_text(f"⚠️ Could not stage this restore: {exc}")
            return

        await query.edit_message_text(
            f"✅ <b>Restore staged</b> from <code>{source_name}</code>.\n\n"
            "Nothing has changed yet — this will apply automatically the "
            "<b>next time the bot restarts</b>. Your current database will be "
            "backed up first at that point, and you'll get a confirmation "
            "message once it's done.\n\n"
            "Changed your mind? /restorebackup cancel",
            parse_mode="HTML",
        )

    # ------------------------------------------------------------------
    # Grid control
    # ------------------------------------------------------------------

    @authorized
    async def stopgrid_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        from config.constants import GRID_ID_PATTERN

        if not context.args:
            await update.message.reply_text("Usage: /stopgrid <grid_id>")
            return
        grid_id = context.args[0]
        if not GRID_ID_PATTERN.match(grid_id):
            # Reject before it's ever echoed into an HTML-formatted reply —
            # same class of gap fixed for coin symbols in /history/coininfo.
            await update.message.reply_text(
                "That doesn't look like a valid grid ID. Use /grids to see all grid IDs."
            )
            return
        grid = await app_context.repos.grids.get(grid_id)
        if not grid:
            await update.message.reply_text(
                f"❌ Grid <code>{grid_id}</code> not found. Use /grids to see all grid IDs.",
                parse_mode="HTML",
            )
            return
        try:
            await app_context.dca_manager.stop_grid(grid_id, reason="manual")
            await update.message.reply_text(f"🛑 Grid <code>{grid_id}</code> stopped.", parse_mode="HTML")
        except ValueError as exc:
            await update.message.reply_text(f"Error: {exc}")

    @authorized
    async def pause_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        from config.constants import GRID_ID_PATTERN

        if not context.args:
            await update.message.reply_text("Usage: /pause <grid_id>")
            return
        grid_id = context.args[0]
        if not GRID_ID_PATTERN.match(grid_id):
            await update.message.reply_text(
                "That doesn't look like a valid grid ID. Use /grids to see all grid IDs."
            )
            return
        grid = await app_context.repos.grids.get(grid_id)
        if not grid:
            await update.message.reply_text(
                f"❌ Grid <code>{grid_id}</code> not found. Use /grids to see all grid IDs.",
                parse_mode="HTML",
            )
            return
        try:
            await app_context.dca_manager.pause_grid(grid_id)
            await update.message.reply_text(f"⏸ Grid <code>{grid_id}</code> paused.", parse_mode="HTML")
        except ValueError as exc:
            await update.message.reply_text(f"Error: {exc}")

    @authorized
    async def resume_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        from config.constants import GRID_ID_PATTERN

        if not context.args:
            await update.message.reply_text("Usage: /resume <grid_id>")
            return
        grid_id = context.args[0]
        if not GRID_ID_PATTERN.match(grid_id):
            await update.message.reply_text(
                "That doesn't look like a valid grid ID. Use /grids to see all grid IDs."
            )
            return
        grid = await app_context.repos.grids.get(grid_id)
        if not grid:
            await update.message.reply_text(
                f"❌ Grid <code>{grid_id}</code> not found. Use /grids to see all grid IDs.",
                parse_mode="HTML",
            )
            return
        try:
            await app_context.dca_manager.resume_grid(grid_id)
            await update.message.reply_text(f"▶️ Grid <code>{grid_id}</code> resumed.", parse_mode="HTML")
        except ValueError as exc:
            await update.message.reply_text(f"Error: {exc}")

    # ------------------------------------------------------------------
    # Manual Buy/Sell
    # ------------------------------------------------------------------

    @authorized
    async def manualbuy_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        from config.constants import GRID_ID_PATTERN

        if len(context.args) != 2:
            await update.message.reply_text(
                "Usage: /manualbuy <grid_id> <inr_amount>\n"
                "Example: /manualbuy grd_1234567890_abc123 500"
            )
            return
        grid_id, raw_amount = context.args
        if not GRID_ID_PATTERN.match(grid_id):
            await update.message.reply_text(
                "That doesn't look like a valid grid ID. Use /grids to see all grid IDs."
            )
            return
        try:
            amount = float(raw_amount.replace(",", ""))
            if amount <= 0:
                raise ValueError
        except ValueError:
            await update.message.reply_text(f"Invalid amount: {raw_amount}")
            return

        grid = await app_context.repos.grids.get(grid_id)
        if not grid:
            await update.message.reply_text(
                f"❌ Grid <code>{grid_id}</code> not found. Use /grids to see all grid IDs.",
                parse_mode="HTML",
            )
            return
        if grid["status"] != "active":
            await update.message.reply_text(
                f"❌ Grid <code>{grid_id}</code> is {grid['status']}, not active — cannot buy.",
                parse_mode="HTML",
            )
            return

        try:
            ticker = await app_context.exchange.get_ticker(grid["symbol"])
            price_line = f"Current price: {ticker.last_price:,.2f}\n"
        except Exception:  # noqa: BLE001
            price_line = ""

        await update.message.reply_text(
            f"🟢 <b>Confirm Manual Buy</b>\n\n"
            f"Grid: <code>{grid_id}</code> ({grid['symbol']})\n"
            f"{price_line}"
            f"Amount: ₹{amount:,.2f}\n\n"
            "This goes through the same risk checks as an automatic dip-buy "
            "(emergency stop / daily loss limit / capital caps all apply).",
            parse_mode="HTML",
            reply_markup=manual_trade_confirm_keyboard("buy", grid_id, amount),
        )

    @authorized
    async def manualsell_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        from config.constants import GRID_ID_PATTERN

        if len(context.args) not in (1, 2):
            await update.message.reply_text(
                "Usage: /manualsell <grid_id> [inr_amount]\n"
                "Omit the amount to sell the entire position.\n"
                "Example: /manualsell grd_1234567890_abc123 300\n"
                "Example: /manualsell grd_1234567890_abc123"
            )
            return
        grid_id = context.args[0]
        if not GRID_ID_PATTERN.match(grid_id):
            await update.message.reply_text(
                "That doesn't look like a valid grid ID. Use /grids to see all grid IDs."
            )
            return

        amount: float | None = None
        if len(context.args) == 2:
            try:
                amount = float(context.args[1].replace(",", ""))
                if amount <= 0:
                    raise ValueError
            except ValueError:
                await update.message.reply_text(f"Invalid amount: {context.args[1]}")
                return

        grid = await app_context.repos.grids.get(grid_id)
        if not grid:
            await update.message.reply_text(
                f"❌ Grid <code>{grid_id}</code> not found. Use /grids to see all grid IDs.",
                parse_mode="HTML",
            )
            return
        if grid["status"] != "active":
            await update.message.reply_text(
                f"❌ Grid <code>{grid_id}</code> is {grid['status']}, not active — cannot sell.",
                parse_mode="HTML",
            )
            return
        if grid["total_quantity"] <= 0:
            await update.message.reply_text(
                f"❌ Grid <code>{grid_id}</code> has no open position to sell.",
                parse_mode="HTML",
            )
            return

        amount_label = f"₹{amount:,.2f}" if amount is not None else "the ENTIRE remaining position"
        await update.message.reply_text(
            f"🔴 <b>Confirm Manual Sell</b>\n\n"
            f"Grid: <code>{grid_id}</code> ({grid['symbol']})\n"
            f"Current position: {grid['total_quantity']:.8g} units\n"
            f"Selling: {amount_label}\n\n"
            "Manual sells are never blocked by emergency stop or risk limits "
            "(reducing a position is always allowed).",
            parse_mode="HTML",
            reply_markup=manual_trade_confirm_keyboard("sell", grid_id, amount),
        )

    async def manual_trade_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        query = update.callback_query
        if not app_context.is_authorized(query.from_user.id):
            await query.answer("Not authorized.", show_alert=True)
            return
        await query.answer()

        from config.constants import GRID_ID_PATTERN

        _, action, grid_id, amount_token = query.data.split(":", 3)

        if action == "cancel":
            await query.edit_message_text("❌ Manual trade cancelled.")
            return

        # Defense in depth: re-validate the grid_id shape even though it was
        # already checked when the button was created — a stale/forwarded
        # callback_data should never reach the DB layer unvalidated.
        if not GRID_ID_PATTERN.match(grid_id):
            await query.edit_message_text("Invalid grid reference — please try the command again.")
            return

        amount = None if amount_token == "ALL" else float(amount_token)

        try:
            if action == "buy":
                order = await app_context.dca_manager.manual_buy(grid_id, amount)
                await query.edit_message_text(
                    f"✅ Manual buy placed: order <code>{order.order_id}</code>",
                    parse_mode="HTML",
                )
            else:
                result = await app_context.dca_manager.manual_sell(grid_id, amount)
                await query.edit_message_text(result.message, parse_mode="HTML")
        except ValueError as exc:
            await query.edit_message_text(f"❌ {exc}")

    @authorized
    async def adjustgrid_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        from config.constants import GRID_ID_PATTERN

        adjustable_fields = {
            "dip_buy_amount": ("Dip buy amount", float, "₹{:,.2f}"),
            "dip_percentage": ("Dip percentage", float, "{}%"),
            "profit_sell_amount": ("Profit sell amount", float, "₹{:,.2f}"),
            "profit_percentage": ("Profit percentage", float, "{}%"),
            "max_levels": ("Max grid levels", int, "{}"),
            "stop_loss_percentage": ("Stop loss", float, "{}%"),
            "trailing_enabled": ("Trailing take-profit", None, "{}"),
            "trailing_percentage": ("Trailing percentage", float, "{}%"),
        }

        if len(context.args) != 3:
            await update.message.reply_text(
                "Usage: /adjustgrid <grid_id> <field> <value>\n"
                "Fields: " + ", ".join(adjustable_fields.keys()) + "\n\n"
                "Example: /adjustgrid grd_1234567890_abc123 dip_percentage 6\n"
                "Example: /adjustgrid grd_1234567890_abc123 trailing_enabled true"
            )
            return

        grid_id, field, raw_value = context.args
        field = field.lower()

        if not GRID_ID_PATTERN.match(grid_id):
            await update.message.reply_text(
                "That doesn't look like a valid grid ID. Use /grids to see all grid IDs."
            )
            return
        if field not in adjustable_fields:
            await update.message.reply_text(
                f"Unknown field '{field}'. Valid fields: " + ", ".join(adjustable_fields.keys())
            )
            return

        label, cast, fmt = adjustable_fields[field]

        if field == "trailing_enabled":
            value_str = raw_value.lower()
            if value_str in ("true", "yes", "on", "1"):
                value = True
            elif value_str in ("false", "no", "off", "0"):
                value = False
            else:
                await update.message.reply_text(
                    "trailing_enabled must be true/false (or yes/no, on/off)."
                )
                return
        else:
            try:
                value = cast(raw_value.replace(",", "").replace("%", ""))
                if value <= 0:
                    raise ValueError
                if field == "max_levels" and value > 50:
                    raise ValueError
                if field in (
                    "dip_percentage", "profit_percentage",
                    "stop_loss_percentage", "trailing_percentage",
                ) and not (0 < value < 100):
                    raise ValueError
            except ValueError:
                await update.message.reply_text(f"Invalid value for {label}: {raw_value}")
                return

        try:
            updated_grid = await app_context.dca_manager.adjust_grid(grid_id, field, value)
        except ValueError as exc:
            await update.message.reply_text(f"❌ {exc}")
            return

        shown = fmt.format(value) if fmt != "{}" or field != "trailing_enabled" else str(value)
        extra_note = ""
        if field == "dip_percentage":
            extra_note = f"\nNext dip-buy price updated to ₹{updated_grid['next_buy_price']:,.2f}."
        elif field == "profit_percentage":
            extra_note = f"\nNext profit-sell price updated to ₹{updated_grid['next_sell_price']:,.2f}."
        elif field == "max_levels" and updated_grid["current_level"] >= value:
            extra_note = "\n⚠️ Current level already meets or exceeds this — no further dip buys will occur."

        await update.message.reply_text(
            f"✅ Grid <code>{grid_id}</code>: {label} updated to {shown}.{extra_note}",
            parse_mode="HTML",
        )

    # ------------------------------------------------------------------
    # Price alerts
    # ------------------------------------------------------------------

    @authorized
    async def defaults_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        from config.constants import QUICK_GRID_DEFAULTS_SEED

        editable_fields = {
            "base_investment": ("Base investment", float, "₹{:,.2f}"),
            "dip_buy_amount": ("Dip buy amount", float, "₹{:,.2f}"),
            "dip_percentage": ("Dip percentage", float, "{}%"),
            "profit_sell_amount": ("Profit sell amount", float, "₹{:,.2f}"),
            "profit_percentage": ("Profit percentage", float, "{}%"),
            "max_levels": ("Max grid levels", int, "{}"),
            "stop_loss_percentage": ("Stop loss", float, "{}%"),
        }

        if not context.args:
            d = await app_context.repos.grid_defaults.get_or_seed(QUICK_GRID_DEFAULTS_SEED)
            mode_label = (
                "🟢 Paper" if d.get("last_mode") == "paper"
                else "🔴 Real" if d.get("last_mode") == "real"
                else "Not set — will be asked each time"
            )
            lines = ["<b>⚙️ Default Grid Settings</b>\n"]
            for field, (label, _cast, fmt) in editable_fields.items():
                lines.append(f"{label}: <b>{fmt.format(d[field])}</b>")
            lines.append(f"Trade mode: <b>{mode_label}</b>")
            lines.append(
                "\nTo edit: <code>/defaults set &lt;field&gt; &lt;value&gt;</code>\n"
                "Fields: " + ", ".join(editable_fields.keys()) + ", last_mode\n\n"
                "Example: <code>/defaults set base_investment 750</code>\n"
                "Example: <code>/defaults set last_mode paper</code> "
                "(or <code>ask</code> to be prompted every time)"
            )
            await update.message.reply_text("\n".join(lines), parse_mode="HTML")
            return

        if len(context.args) < 1 or context.args[0].lower() != "set":
            await update.message.reply_text(
                "Usage: /defaults\nOr: /defaults set <field> <value>"
            )
            return
        if len(context.args) != 3:
            await update.message.reply_text(
                "Usage: /defaults set <field> <value>\n"
                "Example: /defaults set base_investment 750"
            )
            return

        _, field, raw_value = context.args
        field = field.lower()

        if field == "last_mode":
            value = raw_value.lower()
            if value == "ask":
                value = None
            elif value not in ("paper", "real"):
                await update.message.reply_text(
                    "last_mode must be 'paper', 'real', or 'ask'."
                )
                return
            await app_context.repos.grid_defaults.get_or_seed(QUICK_GRID_DEFAULTS_SEED)
            await app_context.repos.grid_defaults.update(last_mode=value)
            shown = value or "ask (prompted each time)"
            await update.message.reply_text(f"✅ Default trade mode set to: {shown}")
            return

        if field not in editable_fields:
            await update.message.reply_text(
                f"Unknown field '{field}'. Valid fields: "
                + ", ".join(editable_fields.keys()) + ", last_mode"
            )
            return

        label, cast, fmt = editable_fields[field]
        try:
            value = cast(raw_value.replace(",", "").replace("%", ""))
            if value <= 0:
                raise ValueError
            if field == "max_levels" and value > 50:
                raise ValueError
            if field in ("dip_percentage", "profit_percentage", "stop_loss_percentage") and not (0 < value < 100):
                raise ValueError
        except ValueError:
            await update.message.reply_text(f"Invalid value for {label}: {raw_value}")
            return

        await app_context.repos.grid_defaults.get_or_seed(QUICK_GRID_DEFAULTS_SEED)
        updated = await app_context.repos.grid_defaults.update(**{field: value})
        await update.message.reply_text(
            f"✅ {label} updated to: {fmt.format(updated[field])}"
        )

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
            direction = await app_context.alert_manager.add_and_persist(symbol, target, current, now_iso())
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
        removed = await app_context.alert_manager.delete_and_persist(symbol)
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
        await app_context.risk_manager.trigger_emergency_stop()
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
            await app_context.risk_manager.clear_emergency_stop()
            log.info("Emergency stop cleared by user %s", query.from_user.id)
            await query.edit_message_text(
                "✅ Emergency stop cleared. Trading is re-enabled.\n\n"
                "Paused grids will not auto-resume — use /resume <grid_id> to restart each one.",
                parse_mode="HTML",
            )
            await app_context.notifier.emergency_cleared(user_id=query.from_user.id)
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
    app.add_handler(CommandHandler("backupstatus", backupstatus_cmd))
    app.add_handler(CommandHandler("restorelist", restorelist_cmd))
    app.add_handler(CommandHandler("verifybackup", verifybackup_cmd))
    app.add_handler(CommandHandler("restorebackup", restorebackup_cmd))
    app.add_handler(CommandHandler("logs", logs_cmd))
    app.add_handler(CommandHandler("defaults", defaults_cmd))
    app.add_handler(CommandHandler("stopgrid", stopgrid_cmd))
    app.add_handler(CommandHandler("pause", pause_cmd))
    app.add_handler(CommandHandler("resume", resume_cmd))
    app.add_handler(CommandHandler("manualbuy", manualbuy_cmd))
    app.add_handler(CommandHandler("manualsell", manualsell_cmd))
    app.add_handler(CommandHandler("adjustgrid", adjustgrid_cmd))
    app.add_handler(CommandHandler("alert", alert_cmd))
    app.add_handler(CommandHandler("alerts", alerts_cmd))
    app.add_handler(CommandHandler("delalert", delalert_cmd))
    app.add_handler(CommandHandler("emergencystop", emergencystop_cmd))
    app.add_handler(CommandHandler("clearemergency", clearemergency_cmd))
    app.add_handler(CallbackQueryHandler(emergency_callback, pattern="^emergency:"))
    app.add_handler(CallbackQueryHandler(grid_action_callback, pattern="^grid_action:"))
    app.add_handler(CallbackQueryHandler(manual_trade_callback, pattern="^mtrade:"))
    app.add_handler(CallbackQueryHandler(restorelist_page_callback, pattern="^restorelist_page:"))
    app.add_handler(CallbackQueryHandler(restorebackup_confirm_callback, pattern="^restorebackup_confirm:"))

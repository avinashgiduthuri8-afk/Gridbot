"""Telegram notification sender for the DCA grid bot.

Decoupled from the bot's command handlers so any subsystem (DCA manager,
order monitor, recovery) can push notifications without depending on the
python-telegram-bot Application object directly.
"""

from __future__ import annotations

import asyncio
import time

from telegram import Bot
from telegram.constants import ParseMode
from telegram.error import TelegramError

from config.constants import TELEGRAM_MAX_MESSAGE_LENGTH
from utils.helpers import fmt_price
from utils.logger import get_logger

log = get_logger("telegram")

# Minimum seconds between repeated sync-error notifications for the same context.
# Prevents message floods during sustained API degradation.
_SYNC_ERROR_COOLDOWN_SECONDS = 600  # 10 minutes


class Notifier:
    def __init__(self, bot: Bot | None, chat_ids: tuple[int, ...]) -> None:
        self._bot = bot
        self._chat_ids = chat_ids
        # Tracks when each sync-error context was last notified (monotonic seconds).
        self._last_sync_error_notified: dict[str, float] = {}

    async def send(self, message: str) -> None:
        if not self._bot or not self._chat_ids:
            return
        """Send *message* to all configured chat IDs concurrently.

        Messages longer than Telegram's limit are truncated at a tag-safe
        boundary so the HTML parser is not left mid-tag.
        """
        if len(message) > TELEGRAM_MAX_MESSAGE_LENGTH:
            # Reserve enough room for the truncation notice and strip any
            # partially-written HTML tag so Telegram's parser doesn't choke.
            cutoff = TELEGRAM_MAX_MESSAGE_LENGTH - 40
            snippet = message[:cutoff]
            # Walk back from the cut to avoid splitting inside an HTML tag.
            last_open = snippet.rfind("<")
            if last_open != -1 and ">" not in snippet[last_open:]:
                snippet = snippet[:last_open]
            message = snippet.rstrip() + "\n\n<i>… message truncated</i>"

        await asyncio.gather(
            *[self._send_to(chat_id, message) for chat_id in self._chat_ids],
            return_exceptions=True,
        )

    async def _send_to(self, chat_id: int, message: str) -> None:
        try:
            await self._bot.send_message(
                chat_id=chat_id, text=message, parse_mode=ParseMode.HTML
            )
        except TelegramError as exc:
            log.error("Failed to notify chat %s: %s", chat_id, exc)

    # ------------------------------------------------------------------
    # Grid lifecycle events
    # ------------------------------------------------------------------

    async def grid_started(
        self,
        symbol: str,
        grid_id: str,
        entry_price: float,
        base_investment: float,
        dip_pct: float,
        profit_pct: float,
        max_levels: int,
        next_sell_price: float,
    ) -> None:
        await self.send(
            f"🟢 <b>DCA Grid Started</b>\n"
            f"Coin: <b>{symbol}</b> | Grid: <code>{grid_id}</code>\n"
            f"Entry: {fmt_price(entry_price)} | Investment: ₹{base_investment:,.2f}\n"
            f"Dip: {dip_pct}% | Profit: {profit_pct}% | Max levels: {max_levels}\n"
            f"First profit target: {fmt_price(next_sell_price)}"
        )

    async def grid_paused(self, symbol: str, grid_id: str) -> None:
        await self.send(
            f"⏸ <b>Grid Paused</b>\n"
            f"Coin: <b>{symbol}</b> | Grid: <code>{grid_id}</code>"
        )

    async def grid_resumed(self, symbol: str, grid_id: str) -> None:
        await self.send(
            f"▶️ <b>Grid Resumed</b>\n"
            f"Coin: <b>{symbol}</b> | Grid: <code>{grid_id}</code>"
        )

    async def grid_stopped(self, symbol: str, grid_id: str, reason: str) -> None:
        await self.send(
            f"🛑 <b>Grid Stopped</b>\n"
            f"Coin: <b>{symbol}</b> | Grid: <code>{grid_id}</code>\n"
            f"Reason: {reason}"
        )

    async def grid_completed(
        self, symbol: str, grid_id: str, cycles: int, total_profit: float
    ) -> None:
        await self.send(
            f"🏁 <b>Grid Completed</b>\n"
            f"Coin: <b>{symbol}</b> | Grid: <code>{grid_id}</code>\n"
            f"Sell cycles: {cycles}\n"
            f"Total realized profit: ₹{total_profit:,.2f}"
        )

    # ------------------------------------------------------------------
    # DCA trade events
    # ------------------------------------------------------------------

    async def dip_buy_executed(
        self,
        symbol: str,
        grid_id: str,
        level: int,
        quantity: float,
        buy_price: float,
        investment_inr: float,
        avg_entry_price: float,
        next_buy_price: float,
        next_sell_price: float,
    ) -> None:
        await self.send(
            f"💸 <b>Dip Buy #{level} Executed</b>\n"
            f"Coin: <b>{symbol}</b> | Grid: <code>{grid_id}</code>\n"
            f"Price: {fmt_price(buy_price)} | Qty: {quantity:.8g} | Cost: ₹{investment_inr:,.2f}\n"
            f"Avg entry: {fmt_price(avg_entry_price)}\n"
            f"Next buy: {fmt_price(next_buy_price)} | Sell target: {fmt_price(next_sell_price)}"
        )

    async def profit_sell_executed(
        self,
        symbol: str,
        grid_id: str,
        quantity: float,
        sell_price: float,
        avg_entry_price: float,
        pnl: float,
        total_realized: float,
        cycles: int,
        next_sell_price: float,
    ) -> None:
        emoji = "💰" if pnl >= 0 else "⚠️"
        await self.send(
            f"{emoji} <b>Profit Sell Executed</b>\n"
            f"Coin: <b>{symbol}</b> | Grid: <code>{grid_id}</code>\n"
            f"Qty sold: {quantity:.8g} @ {fmt_price(sell_price)}\n"
            f"Avg entry: {fmt_price(avg_entry_price)} | PnL: ₹{pnl:+,.2f}\n"
            f"Total realized: ₹{total_realized:,.2f} | Cycles: {cycles}\n"
            f"Next sell target: {fmt_price(next_sell_price)}"
        )

    async def stop_loss_triggered(
        self,
        symbol: str,
        grid_id: str,
        sell_price: float,
        avg_entry_price: float,
        quantity: float,
        pnl: float,
    ) -> None:
        await self.send(
            f"🚨 <b>Stop Loss Triggered</b>\n"
            f"Coin: <b>{symbol}</b> | Grid: <code>{grid_id}</code>\n"
            f"Sell price: {fmt_price(sell_price)} | Avg entry: {fmt_price(avg_entry_price)}\n"
            f"Qty sold: {quantity:.8g} | Loss: ₹{pnl:,.2f}\n"
            f"Grid has been stopped automatically."
        )

    async def avg_entry_updated(
        self,
        symbol: str,
        grid_id: str,
        avg_entry: float,
        total_qty: float,
        total_investment: float,
    ) -> None:
        await self.send(
            f"📊 <b>Position Updated</b>\n"
            f"Coin: <b>{symbol}</b> | Grid: <code>{grid_id}</code>\n"
            f"Avg entry: {fmt_price(avg_entry)}\n"
            f"Total qty: {total_qty:.8g} | Total invested: ₹{total_investment:,.2f}"
        )

    async def price_alert_triggered(self, symbol: str, price: float, target: float, direction: str) -> None:
        arrow = "📈" if direction == "above" else "📉"
        await self.send(
            f"{arrow} <b>Price Alert</b>\n"
            f"<b>{symbol}</b> has crossed {fmt_price(target)}\n"
            f"Current price: {fmt_price(price)}"
        )

    async def trailing_activated(
        self, symbol: str, grid_id: str, peak_price: float, trailing_percentage: float,
    ) -> None:
        """Called by DCAManager the moment a profit target is reached on a
        trailing-enabled grid, instead of selling immediately. Was
        previously called with no matching method defined here at all —
        would have raised AttributeError the first time any trailing grid
        ever reached its profit target.
        """
        await self.send(
            f"🎯 <b>Trailing Take-Profit Activated</b>\n"
            f"Coin: <b>{symbol}</b> | Grid: <code>{grid_id}</code>\n"
            f"Peak price: {fmt_price(peak_price)}\n"
            f"Will sell if price pulls back {trailing_percentage}% from the peak."
        )

    # ------------------------------------------------------------------
    # System events
    # ------------------------------------------------------------------

    # ------------------------------------------------------------------
    # Order lifecycle events
    # ------------------------------------------------------------------

    async def order_submitted(
        self,
        symbol: str,
        grid_id: str,
        order_id: str,
        side: str,
        quantity: float,
        price: float,
        mode: str = "real",
    ) -> None:
        mode_tag = "🟢 Paper" if mode == "paper" else "🔴 Real"
        side_emoji = "💸" if side == "buy" else "💰"
        await self.send(
            f"{side_emoji} <b>Order Submitted</b> [{mode_tag}]\n"
            f"Coin: <b>{symbol}</b> | Grid: <code>{grid_id}</code>\n"
            f"Order: <code>{order_id}</code> | Side: {side.upper()}\n"
            f"Qty: {quantity:.6f} @ ₹{price:,.2f}"
        )

    async def partial_fill_received(
        self,
        symbol: str,
        grid_id: str,
        order_id: str,
        side: str,
        filled_qty: float,
        total_qty: float,
        fill_price: float,
        mode: str = "real",
    ) -> None:
        remaining = total_qty - filled_qty
        pct = (filled_qty / total_qty * 100) if total_qty > 0 else 0
        mode_tag = "🟢 Paper" if mode == "paper" else "🔴 Real"
        await self.send(
            f"⏳ <b>Partial Fill</b> [{mode_tag}]\n"
            f"Coin: <b>{symbol}</b> | Grid: <code>{grid_id}</code>\n"
            f"Order: <code>{order_id}</code> | Side: {side.upper()}\n"
            f"Filled: {filled_qty:.6f} of {total_qty:.6f} ({pct:.1f}%) @ ₹{fill_price:,.2f}\n"
            f"Remaining: {remaining:.6f}"
        )

    async def order_cancelled(
        self,
        symbol: str,
        grid_id: str,
        order_id: str,
        side: str,
        mode: str = "real",
    ) -> None:
        mode_tag = "🟢 Paper" if mode == "paper" else "🔴 Real"
        await self.send(
            f"🚫 <b>Order Cancelled</b> [{mode_tag}]\n"
            f"Coin: <b>{symbol}</b> | Grid: <code>{grid_id}</code>\n"
            f"Order: <code>{order_id}</code> | Side: {side.upper()}"
        )

    async def order_failed(
        self,
        symbol: str,
        grid_id: str,
        order_id: str,
        side: str,
        reason: str,
        mode: str = "real",
    ) -> None:
        mode_tag = "🟢 Paper" if mode == "paper" else "🔴 Real"
        await self.send(
            f"❌ <b>Order Failed</b> [{mode_tag}]\n"
            f"Coin: <b>{symbol}</b> | Grid: <code>{grid_id}</code>\n"
            f"Order: <code>{order_id}</code> | Side: {side.upper()}\n"
            f"Reason: <code>{reason[:200]}</code>"
        )

    async def dust_position_written_off(
        self,
        symbol: str,
        grid_id: str,
        quantity: float,
        value_inr: float,
        unit_label: str,
    ) -> None:
        await self.send(
            f"⚠️ Remaining position is below the exchange's minimum sellable "
            f"quantity.\n\n"
            f"Remaining:\n"
            f"• {quantity:.8f} {unit_label}\n"
            f"• ≈ ₹{value_inr:,.2f}\n\n"
            f"Position has been written off as exchange dust. Grid "
            f"<code>{grid_id}</code> closed successfully."
        )

    # ------------------------------------------------------------------
    # System events
    # ------------------------------------------------------------------

    async def recovery_complete(
        self,
        active_count: int,
        reconciled: int,
        orphans_linked: int = 0,
        fills_recovered: int = 0,
        zombie_grids: int = 0,
    ) -> None:
        if active_count > 0 or reconciled > 0:
            lines = [
                "🔄 <b>Recovery Complete</b>",
                f"Active/paused grids: {active_count}",
                f"Orders reconciled:   {reconciled}",
            ]
            if fills_recovered:
                lines.append(f"Offline fills found: {fills_recovered}")
            if orphans_linked:
                lines.append(f"Orphan orders linked: {orphans_linked}")
            if zombie_grids:
                lines.append(f"⚠️ Zombie grids needing review: {zombie_grids}")
            await self.send("\n".join(lines))
        else:
            await self.send("🔄 <b>Recovery Complete</b>\nNo active grids to restore.")

    async def sync_completed(self, synced: int, fills_found: int) -> None:
        if fills_found > 0:
            await self.send(
                f"🔃 <b>Order Sync</b>\n"
                f"Synced {synced} order(s). Detected {fills_found} new fill(s)."
            )

    async def sync_error(self, context: str, message: str) -> None:
        """Send a sync-error notification, suppressing repeats within the cooldown window.

        During sustained API degradation the monitor may call this every few seconds.
        We send the first occurrence immediately, then stay silent for
        ``_SYNC_ERROR_COOLDOWN_SECONDS`` before sending again for the same context.
        """
        now = time.monotonic()
        last = self._last_sync_error_notified.get(context, 0.0)
        if now - last < _SYNC_ERROR_COOLDOWN_SECONDS:
            log.warning(
                "Suppressing repeated sync-error notification for '%s' "
                "(last sent %.0fs ago, cooldown %ds)",
                context,
                now - last,
                _SYNC_ERROR_COOLDOWN_SECONDS,
            )
            return
        self._last_sync_error_notified[context] = now
        await self.send(
            f"⚠️ <b>Sync Error — {context}</b>\n<code>{message[:200]}</code>"
        )

    async def emergency_cleared(self, user_id: int | None = None) -> None:
        """Notify that the emergency stop has been lifted and trading may resume."""
        who = f" by user <code>{user_id}</code>" if user_id else ""
        await self.send(
            f"✅ <b>Emergency Stop Cleared{who}</b>\n"
            "Trading will resume on the next grid trigger."
        )

    async def grid_deleted(self, symbol: str, grid_id: str) -> None:
        """Notify that a grid was permanently deleted."""
        await self.send(
            f"🗑 <b>Grid Deleted</b>\n"
            f"Coin: <b>{symbol}</b> | Grid: <code>{grid_id}</code>"
        )

    async def drive_backup_completed(self, file_id: str) -> None:
        """Notify that a scheduled Google Drive backup succeeded."""
        await self.send(
            f"☁️ <b>Drive Backup Complete</b>\n"
            f"Database snapshot uploaded (id <code>{file_id}</code>)."
        )

    async def restore_applied(self, source_name: str, backup_of_previous_db: str | None) -> None:
        """Notify that a staged /restorebackup was applied on this startup.
        Sent once the notifier itself is available, since the actual file
        swap happens earlier in startup, before Telegram is connected.
        """
        lines = [
            "🔄 <b>Database Restored</b>\n",
            f"Restored from: <code>{source_name}</code>",
            "\nThis startup replaced the previous database with this backup — "
            "all grids, orders, and history now reflect that backup's state.",
        ]
        if backup_of_previous_db:
            lines.append(f"\nYour previous database was saved to:\n<code>{backup_of_previous_db}</code>")
        await self.send("\n".join(lines))

    async def drive_backup_failed(self, reason: str) -> None:
        """Notify that a scheduled Google Drive backup failed.

        Suppresses repeats using the same cooldown as sync_error, since a
        persistent misconfiguration (bad credentials, folder not shared)
        would otherwise fire on every backup interval.
        """
        await self.sync_error(context="Drive backup", message=reason)

    async def orphan_orders_detected(self, orphans: list[dict]) -> None:
        """Notify the user about exchange orders that have no local DB record.

        These may be orders placed outside the bot, or orders whose DB write
        failed before the bot crashed.  The user should review them on CoinDCX
        and cancel any that are unexpected.
        """
        lines = [
            f"⚠️ <b>{len(orphans)} Orphan Order(s) Detected on Exchange</b>\n",
            "These open orders have no matching local record.\n"
            "If you did not place them manually, cancel them on CoinDCX to avoid "
            "unintended fills.\n",
        ]
        for o in orphans:
            side = str(o.get("side", "?")).upper()
            symbol = o.get("symbol", "?")
            qty = float(o.get("quantity", 0))
            price = float(o.get("price", 0))
            ex_id = o.get("exchange_order_id", "?")
            price_str = f" @ ₹{price:,.4f}" if price > 0 else ""
            lines.append(
                f"• {side} {symbol} qty {qty:.8g}{price_str}\n"
                f"  Exchange ID: <code>{ex_id}</code>"
            )
        await self.send("\n".join(lines))

    async def error(self, context: str, message: str) -> None:
        await self.send(f"❌ <b>Error — {context}</b>\n<code>{message[:300]}</code>")

    async def daily_summary(self, text: str) -> None:
        await self.send(f"📊 <b>Daily Summary</b>\n{text}")

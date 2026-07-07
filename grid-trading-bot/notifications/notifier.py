"""Telegram notification sender for the DCA grid bot.

Decoupled from the bot's command handlers so any subsystem (DCA manager,
order monitor, recovery) can push notifications without depending on the
python-telegram-bot Application object directly.
"""

from __future__ import annotations

from telegram import Bot
from telegram.constants import ParseMode
from telegram.error import TelegramError

from config.constants import TELEGRAM_MAX_MESSAGE_LENGTH
from utils.logger import get_logger

log = get_logger("telegram")


class Notifier:
    def __init__(self, bot: Bot, chat_ids: tuple[int, ...]) -> None:
        self._bot = bot
        self._chat_ids = chat_ids

    async def send(self, message: str) -> None:
        if len(message) > TELEGRAM_MAX_MESSAGE_LENGTH:
            message = message[: TELEGRAM_MAX_MESSAGE_LENGTH - 20] + "\n...(truncated)"
        for chat_id in self._chat_ids:
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
            f"Entry: ₹{entry_price:,.2f} | Investment: ₹{base_investment:,.2f}\n"
            f"Dip: {dip_pct}% | Profit: {profit_pct}% | Max levels: {max_levels}\n"
            f"First profit target: ₹{next_sell_price:,.2f}"
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
            f"Price: ₹{buy_price:,.2f} | Qty: {quantity:.6f} | Cost: ₹{investment_inr:,.2f}\n"
            f"Avg entry: ₹{avg_entry_price:,.2f}\n"
            f"Next buy: ₹{next_buy_price:,.2f} | Sell target: ₹{next_sell_price:,.2f}"
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
            f"Qty sold: {quantity:.6f} @ ₹{sell_price:,.2f}\n"
            f"Avg entry: ₹{avg_entry_price:,.2f} | PnL: ₹{pnl:+,.2f}\n"
            f"Total realized: ₹{total_realized:,.2f} | Cycles: {cycles}\n"
            f"Next sell target: ₹{next_sell_price:,.2f}"
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
            f"Sell price: ₹{sell_price:,.2f} | Avg entry: ₹{avg_entry_price:,.2f}\n"
            f"Qty sold: {quantity:.6f} | Loss: ₹{pnl:,.2f}\n"
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
            f"Avg entry: ₹{avg_entry:,.2f}\n"
            f"Total qty: {total_qty:.6f} | Total invested: ₹{total_investment:,.2f}"
        )

    async def price_alert_triggered(self, symbol: str, price: float, target: float, direction: str) -> None:
        arrow = "📈" if direction == "above" else "📉"
        await self.send(
            f"{arrow} <b>Price Alert</b>\n"
            f"<b>{symbol}</b> has crossed ₹{target:,.2f}\n"
            f"Current price: ₹{price:,.2f}"
        )

    # ------------------------------------------------------------------
    # System events
    # ------------------------------------------------------------------

    async def recovery_complete(self, active_count: int, reconciled: int) -> None:
        if active_count > 0:
            await self.send(
                f"🔄 <b>Recovery Complete</b>\n"
                f"Restored {active_count} active grid(s). "
                f"Reconciled {reconciled} open order(s)."
            )
        else:
            await self.send("🔄 <b>Recovery Complete</b>\nNo active grids to restore.")

    async def error(self, context: str, message: str) -> None:
        await self.send(f"❌ <b>Error — {context}</b>\n<code>{message[:300]}</code>")

    async def daily_summary(self, text: str) -> None:
        await self.send(f"📊 <b>Daily Summary</b>\n{text}")

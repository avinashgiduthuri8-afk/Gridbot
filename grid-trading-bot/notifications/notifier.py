"""Telegram notification sender. Decoupled from the bot's command handlers
so any subsystem (grid manager, order monitor, recovery) can push
notifications without depending on python-telegram-bot's Application object
directly.
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
                await self._bot.send_message(chat_id=chat_id, text=message, parse_mode=ParseMode.HTML)
            except TelegramError as exc:
                log.error("Failed to notify chat %s: %s", chat_id, exc)

    async def grid_started(self, symbol: str, grid_id: str, levels: int, investment: float) -> None:
        await self.send(
            f"🟢 <b>Grid Started</b>\n"
            f"Coin: <b>{symbol}</b>\nGrid ID: <code>{grid_id}</code>\n"
            f"Levels: {levels}\nInvestment/grid: ₹{investment:,.2f}"
        )

    async def grid_paused(self, symbol: str, grid_id: str) -> None:
        await self.send(f"⏸ <b>Grid Paused</b>\nCoin: <b>{symbol}</b>\nGrid ID: <code>{grid_id}</code>")

    async def grid_resumed(self, symbol: str, grid_id: str) -> None:
        await self.send(f"▶️ <b>Grid Resumed</b>\nCoin: <b>{symbol}</b>\nGrid ID: <code>{grid_id}</code>")

    async def grid_stopped(self, symbol: str, grid_id: str, reason: str) -> None:
        await self.send(
            f"🛑 <b>Grid Stopped</b>\nCoin: <b>{symbol}</b>\nGrid ID: <code>{grid_id}</code>\nReason: {reason}"
        )

    async def buy_executed(self, symbol: str, price: float, quantity: float, grid_id: str) -> None:
        await self.send(
            f"✅ <b>Buy Executed</b>\nCoin: <b>{symbol}</b>\nPrice: ₹{price:,.2f}\n"
            f"Quantity: {quantity}\nGrid: <code>{grid_id}</code>"
        )

    async def sell_executed(self, symbol: str, price: float, quantity: float, profit: float, grid_id: str) -> None:
        emoji = "💰" if profit >= 0 else "⚠️"
        await self.send(
            f"{emoji} <b>Sell Executed</b>\nCoin: <b>{symbol}</b>\nPrice: ₹{price:,.2f}\n"
            f"Quantity: {quantity}\nProfit: ₹{profit:,.2f}\nGrid: <code>{grid_id}</code>"
        )

    async def profit_update(self, symbol: str, grid_id: str, realized_profit: float) -> None:
        await self.send(
            f"📈 <b>Profit Update</b>\nCoin: <b>{symbol}</b>\nGrid: <code>{grid_id}</code>\n"
            f"Realized profit: ₹{realized_profit:,.2f}"
        )

    async def grid_completed(self, symbol: str, grid_id: str, cycles: int, total_profit: float) -> None:
        await self.send(
            f"🏁 <b>Grid Completed</b>\nCoin: <b>{symbol}</b>\nGrid: <code>{grid_id}</code>\n"
            f"Completed cycles: {cycles}\nTotal profit: ₹{total_profit:,.2f}"
        )

    async def error(self, context: str, message: str) -> None:
        await self.send(f"❌ <b>Error — {context}</b>\n<code>{message}</code>")

    async def daily_summary(self, text: str) -> None:
        await self.send(f"📊 <b>Daily Summary</b>\n{text}")

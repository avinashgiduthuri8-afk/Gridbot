"""Telegram Dispatcher for Real-Time Institutional Stock Signals.

Dispatches formatted HTML alert cards with trade geometry, sector alpha,
and direct links to Screener.in, NSE India, and TradingView.
Operates in silent mock mode if bot token is not provided.
"""

from __future__ import annotations

import os
from typing import Any
import httpx

from engine.signals.scoring import ScoredSignal
from utils.logger import get_logger

log = get_logger("scanner")


class TelegramNotifier:
    """Dispatches high-conviction Indian stock alerts directly to Telegram channels."""

    def __init__(
        self,
        bot_token: str | None = None,
        chat_id: str | None = None,
        timeout: float = 8.0,
    ) -> None:
        self.bot_token = bot_token or os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
        self.chat_id = chat_id or os.getenv("TELEGRAM_CHAT_ID", "").strip()
        self.timeout = timeout
        self.is_configured = bool(self.bot_token and self.chat_id)

        if not self.is_configured:
            log.info("TelegramNotifier running in silent mock mode (no TELEGRAM_BOT_TOKEN provided).")

    async def send_signal_alert(self, sig: ScoredSignal) -> bool:
        """Formats and sends an institutional signal alert to Telegram."""
        if not self.is_configured:
            log.info("[MOCK TELEGRAM ALERT] %s: %s | Score: %.1f | Entry: ₹%.2f | R:R %.2fx",
                     sig.symbol, sig.signal_type.value, sig.total_score, sig.risk_reward.entry_price, sig.risk_reward.rr_ratio)
            return True

        clean_sym = sig.symbol.replace(".NS", "").replace(".BO", "")
        rr = sig.risk_reward

        # Build formatted HTML message
        lines = [
            f"🚨 <b>NSE HIGH CONVICTION SIGNAL: {clean_sym}</b>",
            f"<b>Setup:</b> {sig.signal_type.value.replace('_', ' ')} (Score: <b>{sig.total_score:.1f}/100</b>)",
            f"<b>Confidence:</b> <code>{sig.confidence}</code> | <b>Sector:</b> {sig.sector}",
            "",
            f"🎯 <b>Entry:</b> ₹{rr.entry_price:,.2f}",
            f"🛑 <b>Stop Loss:</b> ₹{rr.stop_loss:,.2f} (-{rr.risk_percentage:.1f}%)",
            f"✅ <b>Target 1 (2.0R):</b> ₹{rr.target_1:,.2f} (+{rr.reward_percentage:.1f}%)",
            f"🚀 <b>Target 2 (3.5R):</b> ₹{rr.target_2:,.2f}",
            f"⚖️ <b>Risk/Reward Ratio:</b> <b>{rr.rr_ratio:.1f}x</b>",
            "",
            f"💡 <b>Why Buy:</b> {sig.setup_reason or 'Triple Timeframe Alignment'}",
            f"📊 <b>Confirmation:</b> {sig.confirmation_reason or 'Volume Expansion + VWAP Support'}",
        ]

        if sig.rejection_risks:
            lines.append(f"⚠️ <b>Risk Note:</b> {sig.rejection_risks[0]}")

        lines.extend([
            "",
            f"🔗 <a href='https://www.nseindia.com/get-quotes/equity?symbol={cleanSym}'>NSE India</a> | "
            f"<a href='https://www.screener.in/company/{cleanSym}/consolidated/'>Screener.in</a> | "
            f"<a href='https://in.tradingview.com/chart/?symbol=NSE:{cleanSym}'>TradingView</a>"
        ])

        msg_text = "\n".join(lines)
        return await self._dispatch_message(msg_text)

    async def _dispatch_message(self, text: str) -> bool:
        url = f"https://api.telegram.org/bot{self.bot_token}/sendMessage"
        payload = {
            "chat_id": self.chat_id,
            "text": text,
            "parse_mode": "HTML",
            "disable_web_page_preview": True,
        }

        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                resp = await client.post(url, json=payload)
                if resp.status_code == 200:
                    log.info("Telegram alert dispatched successfully.")
                    return True
                log.warning("Telegram API error status %d: %s", resp.status_code, resp.text)
                return False
        except Exception as exc:
            log.warning("Failed to send Telegram alert: %s", exc)
            return False

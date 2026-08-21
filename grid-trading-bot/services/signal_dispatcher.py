"""Master Signal Dispatcher & Outbound Event Bus Engine for Indian Equities.

Transforms high-conviction signals into standardized institutional trade instructions,
signs payloads with HMAC-SHA256, and broadcasts asynchronously to downstream execution bots
(Zerodha, Dhan, Fyers, Custom workers) over Webhooks and real-time WebSocket pub/sub streams.
"""

from __future__ import annotations

import asyncio
import hashlib
import hmac
import json
import time
import uuid
from datetime import datetime, timezone, timedelta
from typing import Any
import httpx
from fastapi import WebSocket

from engine.signals.scoring import ScoredSignal
from schemas.signal_dispatch import BotRegistration, DispatchReceipt, SignalOrderPayload
from storage.repositories.bot_registry import BotRegistryRepository
from utils.helpers import now_iso
from utils.logger import get_logger

log = get_logger("scanner")


class WebSocketConnectionManager:
    """Manages real-time WebSocket subscriber connections for low-latency signal broadcast."""

    def __init__(self) -> None:
        self._active_connections: list[WebSocket] = []

    async def connect(self, websocket: WebSocket) -> None:
        await websocket.accept()
        self._active_connections.append(websocket)
        log.info("WebSocket bot subscriber connected. Active clients: %d", len(self._active_connections))

    def disconnect(self, websocket: WebSocket) -> None:
        if websocket in self._active_connections:
            self._active_connections.remove(websocket)
            log.info("WebSocket bot subscriber disconnected. Active clients: %d", len(self._active_connections))

    async def broadcast(self, data: dict[str, Any]) -> None:
        if not self._active_connections:
            return

        dead_connections: list[WebSocket] = []
        for ws in self._active_connections:
            try:
                await ws.send_json(data)
            except Exception:
                dead_connections.append(ws)

        for dead in dead_connections:
            self.disconnect(dead)


class SignalDispatcherService:
    """Master dispatcher orchestrating outbound webhook delivery and WebSocket broadcasting."""

    def __init__(
        self,
        bot_repo: BotRegistryRepository | None = None,
        timeout: float = 6.0,
        max_retries: int = 3,
    ) -> None:
        self.bot_repo = bot_repo
        self.timeout = timeout
        self.max_retries = max_retries
        self.ws_manager = WebSocketConnectionManager()

    @staticmethod
    def generate_hmac_signature(payload_str: str, secret_key: str) -> str:
        """Computes HMAC-SHA256 signature for payload verification."""
        if not secret_key:
            return ""
        return hmac.new(
            secret_key.encode("utf-8"),
            payload_str.encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()

    def create_order_payload(self, sig: ScoredSignal) -> SignalOrderPayload:
        """Converts internal ScoredSignal into institutional SignalOrderPayload."""
        clean_sym = sig.symbol.replace(".NS", "").replace(".BO", "").strip().upper()
        now_dt = datetime.now(timezone.utc)
        sig_id = f"SIG-{clean_sym}-{now_dt.strftime('%Y%m%d-%H%M%S')}"

        # 4-hour default validity for intraday / swing signals
        expiry_dt = (now_dt + timedelta(hours=4)).isoformat()

        # Extract confluence factors
        confluence = {
            "sector": sig.sector,
            "sector_rank": sig.sector_rank,
            "market_regime": sig.market_regime,
            "setup_reason": sig.setup_reason,
            "confirmation_reason": sig.confirmation_reason,
            "rejection_risks": sig.rejection_risks,
            "score_breakdown": sig.breakdown.to_dict(),
        }

        # Trailing strategy recommendation based on setup
        stype = sig.signal_type.value if hasattr(sig.signal_type, "value") else str(sig.signal_type)
        trailing = "TRAIL_20_EMA_DAILY"
        if "VCP" in stype or "DELIVERY" in stype:
            trailing = "ATR_CHANDELIER"
        elif "PULLBACK" in stype:
            trailing = "STEP_1R"

        return SignalOrderPayload(
            signal_id=sig_id,
            timestamp_ist=now_iso(),
            symbol=clean_sym,
            exchange="NSE",
            instrument_type="EQUITY_CASH",
            action="BUY",
            order_type="LIMIT",
            entry_price=sig.risk_reward.entry_price,
            stop_loss=sig.risk_reward.stop_loss,
            target_1=sig.risk_reward.target_1,
            target_2=sig.risk_reward.target_2,
            risk_per_share=sig.risk_reward.risk_amount,
            recommended_rr_ratio=sig.risk_reward.rr_ratio,
            trailing_strategy=trailing,
            setup_type=stype,
            confidence_score=sig.total_score,
            confluence_factors=confluence,
            validity_expiry_ist=expiry_dt,
        )

    async def dispatch_signal(self, sig: ScoredSignal) -> list[DispatchReceipt]:
        """Dispatches signal to all active matching webhook bots and WebSocket subscribers."""
        payload = self.create_order_payload(sig)
        payload_dict = payload.to_dict()
        payload_json = json.dumps(payload_dict, sort_keys=True)

        # 1. Broadcast over WebSocket PubSub to active clients
        await self.ws_manager.broadcast({
            "event": "NEW_SIGNAL",
            "data": payload_dict,
        })

        if not self.bot_repo:
            log.info("[LOCAL DISPATCH] Dispatched %s via WebSocket stream.", payload.symbol)
            return []

        # 2. Fetch active registered bots
        active_bots = await self.bot_repo.list_bots(active_only=True)
        receipts: list[DispatchReceipt] = []

        tasks = []
        for bot in active_bots:
            # Check setup filter and min confidence score
            stype = payload.setup_type
            is_subscribed = "ALL" in bot.subscribed_setups or stype in bot.subscribed_setups
            if is_subscribed and payload.confidence_score >= bot.min_confidence_score:
                tasks.append(self._send_to_bot(bot, payload, payload_json))

        if tasks:
            receipts = await asyncio.gather(*tasks)
            for r in receipts:
                await self.bot_repo.save_receipt(r)

        return receipts

    async def test_ping_bot(self, bot: BotRegistration) -> DispatchReceipt:
        """Sends a lightweight test ping to a downstream bot to verify webhook connectivity."""
        ping_payload = {
            "event": "TEST_PING",
            "bot_id": bot.bot_id,
            "bot_name": bot.name,
            "timestamp": now_iso(),
            "message": "PROJECT-BETA Master Signal Dispatcher Ping",
        }
        payload_json = json.dumps(ping_payload, sort_keys=True)
        sig = self.generate_hmac_signature(payload_json, bot.secret_key)

        headers = {
            "Content-Type": "application/json",
            "User-Agent": "PROJECT-BETA-MasterDispatcher/1.0",
            "X-Signature-SHA256": sig,
            "X-Event-Type": "TEST_PING",
        }

        t0 = time.perf_counter()
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                resp = await client.post(bot.webhook_url, content=payload_json, headers=headers)
                latency = (time.perf_counter() - t0) * 1000.0
                status = "SUCCESS" if 200 <= resp.status_code < 300 else "FAILED"
                return DispatchReceipt(
                    dispatch_id=f"PING-{uuid.uuid4().hex[:8]}",
                    signal_id="TEST_PING",
                    bot_id=bot.bot_id,
                    timestamp=now_iso(),
                    status=status,
                    response_code=resp.status_code,
                    latency_ms=latency,
                    error_message=None if status == "SUCCESS" else resp.text[:200],
                )
        except Exception as exc:
            latency = (time.perf_counter() - t0) * 1000.0
            return DispatchReceipt(
                dispatch_id=f"PING-{uuid.uuid4().hex[:8]}",
                signal_id="TEST_PING",
                bot_id=bot.bot_id,
                timestamp=now_iso(),
                status="FAILED",
                response_code=0,
                latency_ms=latency,
                error_message=str(exc)[:200],
            )

    async def _send_to_bot(
        self,
        bot: BotRegistration,
        payload: SignalOrderPayload,
        payload_json: str,
    ) -> DispatchReceipt:
        """Sends HTTP POST to bot webhook with HMAC-SHA256 signature and retry logic."""
        signature = self.generate_hmac_signature(payload_json, bot.secret_key)
        headers = {
            "Content-Type": "application/json",
            "User-Agent": "PROJECT-BETA-MasterDispatcher/1.0",
            "X-Signature-SHA256": signature,
            "X-Signal-ID": payload.signal_id,
            "X-Symbol": payload.symbol,
            "X-Event-Type": "SIGNAL_ORDER",
        }

        last_error = None
        last_code = 0
        t0 = time.perf_counter()

        for attempt in range(1, self.max_retries + 1):
            try:
                async with httpx.AsyncClient(timeout=self.timeout) as client:
                    resp = await client.post(bot.webhook_url, content=payload_json, headers=headers)
                    latency = (time.perf_counter() - t0) * 1000.0
                    last_code = resp.status_code

                    if 200 <= resp.status_code < 300:
                        log.info("Successfully dispatched %s to bot %s (%s) in %.1fms",
                                 payload.symbol, bot.name, bot.bot_id, latency)
                        return DispatchReceipt(
                            dispatch_id=f"DISP-{uuid.uuid4().hex[:8]}",
                            signal_id=payload.signal_id,
                            bot_id=bot.bot_id,
                            timestamp=now_iso(),
                            status="SUCCESS",
                            response_code=resp.status_code,
                            latency_ms=latency,
                            error_message=None,
                        )

                    last_error = f"HTTP {resp.status_code}: {resp.text[:150]}"
                    log.warning("Bot %s responded with status %d on attempt %d: %s",
                                bot.name, resp.status_code, attempt, last_error)

            except Exception as exc:
                last_error = str(exc)
                log.warning("Connection error dispatching to bot %s on attempt %d: %s",
                            bot.name, attempt, last_error)

            if attempt < self.max_retries:
                await asyncio.sleep(0.5 * (2 ** (attempt - 1)))

        latency = (time.perf_counter() - t0) * 1000.0
        return DispatchReceipt(
            dispatch_id=f"DISP-{uuid.uuid4().hex[:8]}",
            signal_id=payload.signal_id,
            bot_id=bot.bot_id,
            timestamp=now_iso(),
            status="FAILED",
            response_code=last_code,
            latency_ms=latency,
            error_message=last_error,
        )

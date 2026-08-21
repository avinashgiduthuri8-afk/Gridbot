"""Master Signal Dispatcher & Execution Bot API Routers.

Provides REST and WebSocket endpoints for downstream bot registration,
webhook health checks, delivery receipt audits, and real-time signal streaming.
"""

from __future__ import annotations

import uuid
from typing import Any
from fastapi import APIRouter, Depends, HTTPException, WebSocket, WebSocketDisconnect, status
from pydantic import BaseModel, Field

from dashboard.deps import get_repos
from schemas.signal_dispatch import BotRegistration, DispatchReceipt
from services.signal_dispatcher import SignalDispatcherService
from storage.repositories import Repositories
from utils.helpers import now_iso
from utils.logger import get_logger

log = get_logger("scanner")

router = APIRouter(tags=["dispatch"])

# Global singleton dispatcher instance
_dispatcher = SignalDispatcherService()


class CreateBotRequest(BaseModel):
    name: str = Field(..., description="Bot label / name (e.g. Zerodha Worker #1)")
    target_broker: str = Field("Custom", description="Zerodha, Dhan, Fyers, Custom, etc.")
    webhook_url: str = Field(..., description="HTTP POST destination endpoint")
    secret_key: str = Field("", description="HMAC-SHA256 Secret key for signing")
    subscribed_setups: list[str] = Field(default_factory=lambda: ["ALL"])
    min_confidence_score: float = Field(75.0, ge=0.0, le=100.0)
    is_active: bool = True


@router.post("/dispatch/bots", summary="Register Downstream Execution Bot")
async def register_bot(
    req: CreateBotRequest,
    repos: Repositories = Depends(get_repos),
) -> dict[str, Any]:
    """Registers a new downstream bot to automatically receive trade instructions."""
    secret = req.secret_key or uuid.uuid4().hex
    bot = BotRegistration(
        bot_id=f"BOT-{uuid.uuid4().hex[:8].upper()}",
        name=req.name,
        target_broker=req.target_broker,
        webhook_url=req.webhook_url,
        secret_key=secret,
        subscribed_setups=req.subscribed_setups,
        min_confidence_score=req.min_confidence_score,
        is_active=req.is_active,
        created_at=now_iso(),
    )
    saved_bot = await repos.bots.register_bot(bot)
    return saved_bot.to_dict()


@router.get("/dispatch/bots", summary="List Registered Execution Bots")
async def list_bots(
    active_only: bool = False,
    repos: Repositories = Depends(get_repos),
) -> list[dict[str, Any]]:
    """Lists all configured execution bots with their subscription rules."""
    bots = await repos.bots.list_bots(active_only=active_only)
    return [b.to_dict() for b in bots]


@router.delete("/dispatch/bots/{bot_id}", summary="Unregister Execution Bot")
async def delete_bot(
    bot_id: str,
    repos: Repositories = Depends(get_repos),
) -> dict[str, Any]:
    """Deletes an execution bot from the dispatcher registry."""
    success = await repos.bots.delete_bot(bot_id)
    if not success:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Bot not found")
    return {"deleted": True, "bot_id": bot_id}


@router.post("/dispatch/test-ping/{bot_id}", summary="Send Test Ping to Bot Webhook")
async def test_ping_bot(
    bot_id: str,
    repos: Repositories = Depends(get_repos),
) -> dict[str, Any]:
    """Dispatches a test HMAC-signed payload to verify webhook latency and connectivity."""
    bot = await repos.bots.get_bot(bot_id)
    if not bot:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Bot not found")

    receipt = await _dispatcher.test_ping_bot(bot)
    await repos.bots.save_receipt(receipt)
    return receipt.to_dict()


@router.get("/dispatch/logs", summary="Recent Dispatch Delivery Receipts")
async def get_dispatch_logs(
    limit: int = 50,
    repos: Repositories = Depends(get_repos),
) -> list[dict[str, Any]]:
    """Retrieves recent signal delivery attempts, HTTP status codes, and latencies."""
    receipts = await repos.bots.list_receipts(limit=limit)
    return [r.to_dict() for r in receipts]


@router.websocket("/dispatch/stream")
async def dispatch_websocket_stream(websocket: WebSocket) -> None:
    """Real-time low-latency WebSocket feed for local execution bots."""
    await _dispatcher.ws_manager.connect(websocket)
    try:
        while True:
            # Keep alive loop
            data = await websocket.receive_text()
            if data == "ping":
                await websocket.send_text("pong")
    except WebSocketDisconnect:
        _dispatcher.ws_manager.disconnect(websocket)
    except Exception:
        _dispatcher.ws_manager.disconnect(websocket)

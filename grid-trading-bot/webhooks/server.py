"""CoinDCX order-update webhook receiver — optional, opt-in, off by default.

**Read this before enabling WEBHOOK_ENABLED=true in production.**

This was built without network access to CoinDCX's live API documentation,
so two things here are *assumptions*, not confirmed facts, and should be
verified against CoinDCX's current docs before you trust this with real
capital:

  1. The signature scheme. This reuses the same HMAC-SHA256 construction
     CoinDCX's REST API already uses for authenticating outbound requests
     (see exchange/coindcx.py) as a reasonable starting guess for how they'd
     sign an inbound webhook too — but confirm the actual header name and
     digest encoding they use, if any, against their real webhook docs.
  2. The payload shape. parse_order_update() below expects fields named
     like CoinDCX's REST order-status responses (id/status/filled_quantity/
     avg_price) — again a reasonable guess, not a confirmed webhook payload.

Because of that uncertainty, this is designed as a pure *accelerant*, never
a replacement for the existing polling in trading/order_monitor.py: a
missed, malformed, or wrongly-shaped webhook is silently caught by the next
poll cycle regardless, since handle_order_filled() is idempotent (guarded
on trade_history existence) and safe to race against the poller for the
same order.

Two layers, deliberately kept separate for testability:
  - verify_signature / parse_order_update / handle_order_update: pure
    functions and one small async function with no aiohttp dependency at
    all — fully unit-testable without aiohttp installed.
  - create_app / run_webhook_server: the thin aiohttp-specific plumbing
    around that core logic.
"""

from __future__ import annotations

import asyncio
import hashlib
import hmac
import json
from typing import Any

from utils.logger import get_logger

log = get_logger("exchange")

SIGNATURE_HEADER = "X-Webhook-Signature"


class WebhookAuthError(Exception):
    """Raised when an incoming webhook request fails signature verification."""


def verify_signature(raw_body: bytes, signature: str | None, secret: str) -> None:
    """Raise WebhookAuthError unless signature is a valid HMAC-SHA256 of
    raw_body using secret. Uses hmac.compare_digest (constant-time) to avoid
    leaking timing information about how much of the signature matched.
    """
    if not signature:
        raise WebhookAuthError("Missing signature header")
    expected = hmac.new(secret.encode(), raw_body, hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expected, signature):
        raise WebhookAuthError("Signature does not match expected HMAC")


def parse_order_update(raw_body: bytes) -> dict[str, Any]:
    """Parse a webhook body into {exchange_order_id, status, raw_status,
    filled_quantity, filled_price}. Raises ValueError on anything
    unusable — never raises on a merely-unrecognized status, since new
    exchange statuses should be logged and ignored, not crash the receiver.
    """
    try:
        data = json.loads(raw_body)
    except json.JSONDecodeError as exc:
        raise ValueError(f"Invalid JSON payload: {exc}") from exc

    if not isinstance(data, dict):
        raise ValueError("Payload must be a JSON object")

    exchange_order_id = str(data.get("id") or data.get("order_id") or "").strip()
    if not exchange_order_id:
        raise ValueError("Payload missing an order id (expected 'id' or 'order_id')")

    # Reuse exchange/coindcx.py's status map as the single source of truth
    # rather than duplicating it here and risking the two drifting apart.
    from exchange.coindcx import _STATUS_MAP

    raw_status = str(data.get("status", "")).lower()
    status = _STATUS_MAP.get(raw_status)
    if status is None:
        log.warning(
            "Webhook: unrecognized order status %r for exchange order %s — "
            "ignoring this update (not a hard failure; the next poll cycle "
            "will pick up the real status).",
            raw_status, exchange_order_id,
        )
        status = "open"

    return {
        "exchange_order_id": exchange_order_id,
        "status": status,
        "raw_status": raw_status,
        "filled_quantity": float(data.get("filled_quantity", 0) or 0),
        "filled_price": float(data.get("avg_price", 0) or data.get("price_per_unit", 0) or 0),
    }


async def handle_order_update(payload: dict[str, Any], repos, dca_manager, notifier) -> str:
    """Look up the local order for this webhook update and apply a fill (or
    partial fill) if indicated. Returns a short string describing what
    happened, for logging/testing — never raises for a normal "nothing to
    do here" case (unknown order, non-fill status).

    Idempotent by construction: handle_order_filled() itself guards on
    trade_history existence, so calling this twice for the same fill (e.g.
    once from a webhook, once from the next poll cycle) is safe.
    """
    order = await repos.orders.get_by_exchange_order_id(payload["exchange_order_id"])
    if order is None:
        log.warning(
            "Webhook: no local order found for exchange_order_id=%s (status=%s) — "
            "ignoring. If this ID is real, the recovery orphan-check will "
            "eventually surface it for manual review.",
            payload["exchange_order_id"], payload["raw_status"],
        )
        return "unknown_order"

    if payload["status"] == "filled":
        fill_qty = payload["filled_quantity"] or order["quantity"]
        fill_price = payload["filled_price"] or order["price"]
        await dca_manager.handle_order_filled(
            order_id=order["order_id"], fill_price=fill_price, fill_qty=fill_qty,
        )
        log.info(
            "Webhook: applied fill order=%s exchange_id=%s qty=%.8f @ ₹%.2f",
            order["order_id"], payload["exchange_order_id"], fill_qty, fill_price,
        )
        return "filled_applied"

    if payload["status"] == "partially_filled":
        new_filled_qty = payload["filled_quantity"]
        if new_filled_qty <= float(order["filled_quantity"] or 0):
            # Nothing new — avoid re-notifying for a duplicate/out-of-order webhook.
            return "partial_no_change"
        await repos.orders.update_status(
            order["order_id"], "partially_filled",
            filled_quantity=new_filled_qty, filled_price=payload["filled_price"],
        )
        grid = await repos.grids.get(order["grid_id"])
        await notifier.partial_fill_received(
            symbol=order["symbol"], grid_id=order["grid_id"], order_id=order["order_id"],
            side=order["side"], filled_qty=new_filled_qty,
            total_qty=float(order["quantity"]), fill_price=payload["filled_price"],
            mode=(grid or {}).get("mode", "real"),
        )
        return "partial_applied"

    return f"ignored_status_{payload['status']}"


# ---------------------------------------------------------------------------
# aiohttp-specific plumbing (thin — the logic above is what's actually tested)
# ---------------------------------------------------------------------------


async def create_app(repos, dca_manager, notifier, secret: str, path: str):
    """Build the aiohttp Application. Import is local so aiohttp is only
    required when webhooks are actually enabled (see main.py)."""
    from aiohttp import web

    async def handle_order_update_route(request: "web.Request") -> "web.Response":
        raw_body = await request.read()
        signature = request.headers.get(SIGNATURE_HEADER)
        try:
            verify_signature(raw_body, signature, secret)
        except WebhookAuthError as exc:
            log.warning("Webhook request rejected (auth): %s", exc)
            return web.json_response({"error": str(exc)}, status=401)

        try:
            payload = parse_order_update(raw_body)
        except ValueError as exc:
            log.warning("Webhook request rejected (payload): %s", exc)
            return web.json_response({"error": str(exc)}, status=400)

        result = await handle_order_update(payload, repos, dca_manager, notifier)
        return web.json_response({"result": result}, status=200)

    async def health(request: "web.Request") -> "web.Response":
        return web.json_response({"status": "ok"})

    app = web.Application()
    app.router.add_post(path, handle_order_update_route)
    app.router.add_get("/webhooks/health", health)
    return app


async def run_webhook_server(
    repos, dca_manager, notifier, secret: str, host: str, port: int, path: str,
) -> None:
    """Long-running background task: starts the aiohttp server and keeps it
    alive until cancelled. Follows the same run_X_loop pattern as the other
    background tasks in main.py (daily summary, alert checks, Drive backup).
    """
    from aiohttp import web

    app = await create_app(repos, dca_manager, notifier, secret, path)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, host, port)
    await site.start()
    log.info("Webhook server listening on %s:%d%s (health check at /webhooks/health)", host, port, path)
    try:
        while True:
            await asyncio.sleep(3600)
    finally:
        await runner.cleanup()

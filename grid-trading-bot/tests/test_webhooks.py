"""Tests for the CoinDCX webhook receiver's core logic (signature
verification, payload parsing, order lookup + fill application).

Deliberately tests only webhooks/server.py's framework-agnostic functions
(verify_signature, parse_order_update, handle_order_update) — aiohttp
itself isn't required to run these, since create_app/run_webhook_server
are thin plumbing around this core, not logic worth testing in isolation.

IMPORTANT: see webhooks/server.py's module docstring. The signature scheme
and payload shape assumed here were not verified against CoinDCX's live
webhook documentation. These tests confirm the receiver behaves correctly
*given* those assumptions — they cannot confirm the assumptions themselves
match what CoinDCX actually sends.
"""

from __future__ import annotations

import hashlib
import hmac

import pytest

from webhooks.server import WebhookAuthError, handle_order_update, parse_order_update, verify_signature

pytestmark = pytest.mark.anyio

SECRET = "test-secret"


def _sign(body: bytes, secret: str = SECRET) -> str:
    return hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()


# ---------------------------------------------------------------------------
# Signature verification
# ---------------------------------------------------------------------------


def test_valid_signature_accepted():
    body = b'{"id":"EX123","status":"filled"}'
    verify_signature(body, _sign(body), SECRET)  # must not raise


def test_invalid_signature_rejected():
    body = b'{"id":"EX123","status":"filled"}'
    with pytest.raises(WebhookAuthError):
        verify_signature(body, "not-the-right-signature", SECRET)


def test_missing_signature_rejected():
    body = b'{"id":"EX123","status":"filled"}'
    with pytest.raises(WebhookAuthError):
        verify_signature(body, None, SECRET)


def test_signature_for_different_body_rejected():
    """A signature valid for one body must not validate a different body —
    guards against a naive implementation that only checks format."""
    signed_for_other_body = _sign(b'{"id":"OTHER","status":"filled"}')
    with pytest.raises(WebhookAuthError):
        verify_signature(b'{"id":"EX123","status":"filled"}', signed_for_other_body, SECRET)


# ---------------------------------------------------------------------------
# Payload parsing
# ---------------------------------------------------------------------------


def test_parses_well_formed_payload():
    payload = parse_order_update(
        b'{"id":"EX123","status":"filled","filled_quantity":"1.5","avg_price":"54000.5"}'
    )
    assert payload["exchange_order_id"] == "EX123"
    assert payload["status"] == "filled"
    assert payload["filled_quantity"] == 1.5
    assert payload["filled_price"] == 54000.5


def test_rejects_invalid_json():
    with pytest.raises(ValueError):
        parse_order_update(b"not json at all")


def test_rejects_payload_missing_order_id():
    with pytest.raises(ValueError):
        parse_order_update(b'{"status":"filled"}')


def test_unrecognized_status_does_not_crash():
    """An unknown/new exchange status must be logged and defaulted, never
    raise — a status CoinDCX adds in the future shouldn't take the receiver
    down."""
    payload = parse_order_update(b'{"id":"EX999","status":"some_brand_new_status"}')
    assert payload["exchange_order_id"] == "EX999"
    assert payload["status"] == "open"


# ---------------------------------------------------------------------------
# handle_order_update — full integration against the real DCAManager/repos
# ---------------------------------------------------------------------------


async def _seed_grid_with_open_order(app_context, repos):
    grid_id = await app_context.dca_manager.start_grid({
        "symbol": "BTCINR", "entry_price": 100.0, "base_investment": 500.0,
        "dip_buy_amount": 100.0, "dip_percentage": 5.0,
        "profit_sell_amount": 150.0, "profit_percentage": 7.0,
        "max_levels": 5, "stop_loss_percentage": 50.0, "mode": "real",
    })
    orders = await repos.orders.list_for_grid(grid_id)
    return grid_id, orders[0]


async def test_webhook_fill_applies_to_real_order_and_advances_grid(app_context, repos):
    grid_id, order_row = await _seed_grid_with_open_order(app_context, repos)

    payload = {
        "exchange_order_id": order_row["exchange_order_id"], "status": "filled",
        "raw_status": "filled", "filled_quantity": order_row["quantity"], "filled_price": 101.5,
    }
    result = await handle_order_update(payload, repos, app_context.dca_manager, app_context.notifier)

    assert result == "filled_applied"
    grid = await repos.grids.get(grid_id)
    assert grid["current_level"] == 1


async def test_webhook_for_unknown_order_is_ignored_safely(app_context, repos):
    payload = {
        "exchange_order_id": "TOTALLY_UNKNOWN_ID", "status": "filled",
        "raw_status": "filled", "filled_quantity": 1.0, "filled_price": 100.0,
    }
    result = await handle_order_update(payload, repos, app_context.dca_manager, app_context.notifier)
    assert result == "unknown_order"


async def test_webhook_fill_is_idempotent(app_context, repos):
    """Calling handle_order_update twice for the same fill (e.g. a retried
    webhook, or a race with the existing poll-based order monitor) must not
    apply the fill twice."""
    grid_id, order_row = await _seed_grid_with_open_order(app_context, repos)
    payload = {
        "exchange_order_id": order_row["exchange_order_id"], "status": "filled",
        "raw_status": "filled", "filled_quantity": order_row["quantity"], "filled_price": 101.5,
    }

    await handle_order_update(payload, repos, app_context.dca_manager, app_context.notifier)
    await handle_order_update(payload, repos, app_context.dca_manager, app_context.notifier)

    grid = await repos.grids.get(grid_id)
    assert grid["current_level"] == 1, "must not double-apply the same fill"


async def test_webhook_partial_fill_does_not_advance_grid_level(app_context, repos):
    grid_id, order_row = await _seed_grid_with_open_order(app_context, repos)
    # MockExchange returns an already-fully-filled order at placement time by
    # default (see conftest.py) — reset to "not yet filled" so this test can
    # accurately simulate a webhook reporting the *first* partial fill.
    await repos.orders.update_status(
        order_row["order_id"], "open", filled_quantity=0.0, filled_price=0.0,
    )

    payload = {
        "exchange_order_id": order_row["exchange_order_id"], "status": "partially_filled",
        "raw_status": "partially_filled", "filled_quantity": order_row["quantity"] / 2,
        "filled_price": 100.5,
    }
    result = await handle_order_update(payload, repos, app_context.dca_manager, app_context.notifier)

    assert result == "partial_applied"
    grid = await repos.grids.get(grid_id)
    assert grid["current_level"] == 0, "a partial fill must not advance grid level — only a full fill does"
    order_after = await repos.orders.get(order_row["order_id"])
    assert order_after["status"] == "partially_filled"

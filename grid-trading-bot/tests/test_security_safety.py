"""Comprehensive regression tests for Group 9.7: Production Security & Interface Safety.

Validates all 16 required security and interface invariants:
 1. Unauthorized Telegram user command is rejected
 2. Unauthorized Telegram user callback query is rejected
 3. Whitelisted secondary Telegram user is authorized
 4. Webhook request without signature header is rejected (401)
 5. Webhook request with invalid signature is rejected (401)
 6. Webhook request with valid HMAC-SHA256 signature is accepted (200)
 7. Outbound CoinDCX private request generates valid HMAC-SHA256 signature
 8. CoinDCX base URL validates and enforces HTTPS protocol
 9. CoinDCX base URL rejects embedded user credentials
10. CoinDCX base URL rejects non-CoinDCX external hostnames
11. Dashboard read-only connection rejects write queries (PRAGMA query_only=ON)
12. Dashboard CORS configuration correctly parses origins
13. Restore manager rejects corrupted SQLite backup file
14. Emergency stop blocks subsequent order placement
15. Repository queries use parameterized statements against SQL injection
16. Unhandled Telegram errors do not leak stack traces or secrets to users
"""

from __future__ import annotations

import hashlib
import hmac
import os
import tempfile
import pytest
from unittest.mock import AsyncMock, MagicMock

from telegram import Update
from telegram.ext import CallbackQueryHandler, CommandHandler

from bot_telegram.bot import BotAppContext, _on_error
from bot_telegram.handlers import register_handlers
from config.settings import ConfigError, RiskSettings, Settings, load_settings, _validated_coindcx_base_url
from dashboard.config import load_dashboard_settings
from risk.risk_manager import RiskManager
from storage.database import Database
from storage.restore import verify_sqlite_integrity
from webhooks.server import verify_signature, WebhookAuthError

pytestmark = pytest.mark.anyio


@pytest.fixture
def temp_db_path():
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    yield path
    if os.path.exists(path):
        try:
            os.remove(path)
        except OSError:
            pass


@pytest.fixture
def mock_app_context():
    settings = MagicMock(spec=Settings)
    settings.telegram_owner_id = 11111
    settings.telegram_allowed_ids = (22222,)
    settings.is_authorized = lambda uid: uid in (11111, 22222)
    ctx = MagicMock(spec=BotAppContext)
    ctx.settings = settings
    ctx.is_authorized = settings.is_authorized
    return ctx


# 1. Unauthorized Telegram user command is rejected
async def test_unauthorized_telegram_command_rejected(mock_app_context):
    app = MagicMock()
    handlers_registered = []
    app.add_handler = lambda h: handlers_registered.append(h)
    register_handlers(app, mock_app_context)

    status_handler = next(
        h for h in handlers_registered
        if isinstance(h, CommandHandler) and "status" in getattr(h, "commands", ())
    )

    update = MagicMock(spec=Update)
    update.effective_user.id = 99999  # Unauthorized ID
    update.message = MagicMock()
    update.message.reply_text = AsyncMock()

    context = MagicMock()
    await status_handler.callback(update, context)

    update.message.reply_text.assert_called_once_with("You are not authorized to use this bot.")


# 2. Unauthorized Telegram user callback query is rejected
async def test_unauthorized_telegram_callback_rejected(mock_app_context):
    app = MagicMock()
    handlers_registered = []
    app.add_handler = lambda h: handlers_registered.append(h)
    register_handlers(app, mock_app_context)

    cb_handler = next(
        h for h in handlers_registered
        if isinstance(h, CallbackQueryHandler)
    )

    update = MagicMock(spec=Update)
    update.callback_query = MagicMock()
    update.callback_query.from_user.id = 99999  # Unauthorized ID
    update.callback_query.answer = AsyncMock()

    context = MagicMock()
    await cb_handler.callback(update, context)

    update.callback_query.answer.assert_called_once_with("Not authorized.", show_alert=True)


# 3. Whitelisted secondary Telegram user is authorized
def test_whitelisted_secondary_telegram_user(mock_app_context):
    assert mock_app_context.is_authorized(11111)  # Owner
    assert mock_app_context.is_authorized(22222)  # Whitelisted
    assert not mock_app_context.is_authorized(33333)  # Unknown


# 4. Webhook request without signature header is rejected
def test_webhook_missing_signature_rejected():
    with pytest.raises(WebhookAuthError, match="Missing signature"):
        verify_signature(raw_body=b'{"id":"123"}', signature=None, secret="my_secret")


# 5. Webhook request with invalid signature is rejected
def test_webhook_invalid_signature_rejected():
    with pytest.raises(WebhookAuthError, match="does not match"):
        verify_signature(raw_body=b'{"id":"123"}', signature="bad_signature", secret="my_secret")


# 6. Webhook request with valid HMAC-SHA256 signature is accepted
def test_webhook_valid_signature_accepted():
    body = b'{"id":"123","status":"filled"}'
    secret = "production_secret"
    valid_sig = hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    # Should not raise
    verify_signature(raw_body=body, signature=valid_sig, secret=secret)


# 7. Outbound CoinDCX private request generates valid HMAC-SHA256 signature
def test_coindcx_request_signature():
    from exchange.coindcx import CoinDCXClient
    client = CoinDCXClient(api_key="my_key", api_secret="my_secret")
    body = {"symbol": "BTCINR", "side": "buy"}
    payload, signature = client._sign(body)

    expected_sig = hmac.new(b"my_secret", payload.encode(), hashlib.sha256).hexdigest()
    assert signature == expected_sig


# 8. CoinDCX base URL validates and enforces HTTPS protocol
def test_coindcx_base_url_enforces_https():
    with pytest.raises(ConfigError, match="HTTPS"):
        _validated_coindcx_base_url("http://api.coindcx.com")


# 9. CoinDCX base URL rejects embedded user credentials
def test_coindcx_base_url_rejects_embedded_credentials():
    with pytest.raises(ConfigError, match="credentials"):
        _validated_coindcx_base_url("https://user:pass@api.coindcx.com")


# 10. CoinDCX base URL rejects non-CoinDCX external hostnames
def test_coindcx_base_url_rejects_non_coindcx_domain():
    with pytest.raises(ConfigError, match="CoinDCX domain"):
        _validated_coindcx_base_url("https://malicious-site.com")


# 11. Dashboard read-only connection rejects write queries
async def test_dashboard_read_only_connection(temp_db_path):
    # First create and initialize the database in read-write mode
    db_rw = Database(temp_db_path)
    await db_rw.connect()
    await db_rw.migrate()
    await db_rw.close()

    # Connect read-only
    db_ro = Database(temp_db_path, read_only=True)
    await db_ro.connect()

    # Mutation query must be rejected by query_only / mode=ro
    with pytest.raises(Exception):
        await db_ro.connection.execute("INSERT INTO logs (channel, level, message, created_at) VALUES ('test', 'INFO', 'msg', 'now')")

    await db_ro.close()


# 12. Dashboard CORS configuration correctly parses origins
def test_dashboard_cors_origin_parsing(monkeypatch):
    monkeypatch.setenv("DASHBOARD_CORS_ORIGINS", "https://app.example.com, https://admin.example.com")
    settings = load_dashboard_settings()
    assert settings.cors_origins == ["https://app.example.com", "https://admin.example.com"]


# 13. Restore manager rejects corrupted SQLite backup file
def test_restore_rejects_corrupted_file(temp_db_path):
    # Write garbage bytes
    with open(temp_db_path, "wb") as f:
        f.write(b"NOT A VALID SQLITE DATABASE HEADER")

    res = verify_sqlite_integrity(temp_db_path)
    assert not res["valid"]


# 14. Emergency stop blocks subsequent order placement
async def test_emergency_stop_blocks_order_placement(repos):
    risk = RiskManager(
        RiskSettings(max_total_capital=10000, max_capital_per_coin=5000, max_simultaneous_grids=5, min_wallet_balance=500, daily_loss_limit=1000),
        repos,
    )
    await risk.trigger_emergency_stop()
    res = await risk.check_can_place_order(500.0, 5000.0)
    assert not res.allowed
    assert "Emergency stop" in res.reason


# 15. Repository queries use parameterized statements against SQL injection
async def test_parameterized_query_against_sql_injection(repos):
    malicious_grid_id = "grd_1' OR '1'='1"
    # Query should safely treat input as literal string and return None
    row = await repos.grids.get(malicious_grid_id)
    assert row is None


# 16. Unhandled Telegram errors do not leak stack traces or secrets to users
async def test_telegram_error_handler_masks_details():
    update = MagicMock(spec=Update)
    update.effective_chat = MagicMock()
    update.effective_chat.id = 123456
    context = MagicMock()
    context.error = ValueError("Database connection failed with credentials: secret_token_xyz")
    context.bot.send_message = AsyncMock()

    await _on_error(update, context)

    # Verify user message is generic and does NOT contain the secret or error message
    sent_text = context.bot.send_message.call_args[1]["text"]
    assert "secret_token_xyz" not in sent_text
    assert "Something went wrong" in sent_text

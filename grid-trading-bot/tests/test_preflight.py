"""Unit tests for production deployment preflight script."""

from __future__ import annotations

import os
import sys
from pathlib import Path
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scripts.preflight import run_preflight, mask_status


def test_mask_status_masks_credentials():
    assert mask_status("secret_token_123") == "SET"
    assert mask_status("  ") == "MISSING"
    assert mask_status(None) == "MISSING"
    assert mask_status("") == "MISSING"


def test_preflight_fails_when_secrets_missing(monkeypatch, tmp_path):
    monkeypatch.delenv("TELEGRAM_BOT_TOKEN", raising=False)
    monkeypatch.delenv("TELEGRAM_CHAT_ID", raising=False)
    monkeypatch.delenv("COINDCX_API_KEY", raising=False)
    monkeypatch.delenv("COINDCX_API_SECRET", raising=False)
    monkeypatch.setenv("DATABASE_PATH", str(tmp_path / "test.db"))

    success = run_preflight()
    assert success is False


def test_preflight_passes_with_valid_environment(monkeypatch, tmp_path):
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "mock_bot_token")
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "12345678")
    monkeypatch.setenv("COINDCX_API_KEY", "mock_api_key")
    monkeypatch.setenv("COINDCX_API_SECRET", "mock_api_secret")
    monkeypatch.setenv("DATABASE_PATH", str(tmp_path / "data" / "grid_bot.db"))

    success = run_preflight()
    assert success is True


def test_preflight_fails_on_invalid_backup_config(monkeypatch, tmp_path):
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "mock_bot_token")
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "12345678")
    monkeypatch.setenv("COINDCX_API_KEY", "mock_api_key")
    monkeypatch.setenv("COINDCX_API_SECRET", "mock_api_secret")
    monkeypatch.setenv("DATABASE_PATH", str(tmp_path / "test.db"))
    monkeypatch.setenv("GDRIVE_BACKUP_ENABLED", "true")
    monkeypatch.delenv("GDRIVE_SERVICE_ACCOUNT_JSON", raising=False)
    monkeypatch.delenv("GDRIVE_FOLDER_ID", raising=False)

    success = run_preflight()
    assert success is False


def test_preflight_fails_on_invalid_webhook_config(monkeypatch, tmp_path):
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "mock_bot_token")
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "12345678")
    monkeypatch.setenv("COINDCX_API_KEY", "mock_api_key")
    monkeypatch.setenv("COINDCX_API_SECRET", "mock_api_secret")
    monkeypatch.setenv("DATABASE_PATH", str(tmp_path / "test.db"))
    monkeypatch.setenv("WEBHOOK_ENABLED", "true")
    monkeypatch.delenv("WEBHOOK_SECRET", raising=False)

    success = run_preflight()
    assert success is False


def test_preflight_secret_values_never_printed(monkeypatch, tmp_path, capsys):
    secret_val = "SUPER_SECRET_VALUE_999"
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", secret_val)
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "12345678")
    monkeypatch.setenv("COINDCX_API_KEY", secret_val)
    monkeypatch.setenv("COINDCX_API_SECRET", secret_val)
    monkeypatch.setenv("DATABASE_PATH", str(tmp_path / "test.db"))

    run_preflight()
    captured = capsys.readouterr()
    assert secret_val not in captured.out
    assert "TELEGRAM_BOT_TOKEN ..... SET" in captured.out

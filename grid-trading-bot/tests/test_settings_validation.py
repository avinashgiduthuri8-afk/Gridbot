"""Regression tests for configuration validation."""

from __future__ import annotations

import pytest

from config.settings import ConfigError, load_settings


def _base_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "test-token")
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "123456")
    monkeypatch.setenv("COINDCX_API_KEY", "test-key")
    monkeypatch.setenv("COINDCX_API_SECRET", "test-secret")


@pytest.mark.parametrize(
    "base_url",
    [
        "http://api.coindcx.com",
        "https://evil.example.com",
        "https://api.coindcx.com/v1",
        "https://api.coindcx.com?redirect=1",
        "https://user:pass@api.coindcx.com",
    ],
)
def test_rejects_unsafe_coindcx_base_url(monkeypatch: pytest.MonkeyPatch, base_url: str) -> None:
    _base_env(monkeypatch)
    monkeypatch.setenv("COINDCX_BASE_URL", base_url)

    with pytest.raises(ConfigError, match="COINDCX_BASE_URL"):
        load_settings()


@pytest.mark.parametrize(
    "key,value",
    [
        ("ORDER_POLL_INTERVAL_SECONDS", "0"),
        ("PRICE_POLL_INTERVAL_SECONDS", "-1"),
        ("DAILY_SUMMARY_INTERVAL_SECONDS", "0"),
        ("MIN_WALLET_BALANCE", "-0.01"),
    ],
)
def test_rejects_unsafe_numeric_config(monkeypatch: pytest.MonkeyPatch, key: str, value: str) -> None:
    _base_env(monkeypatch)
    monkeypatch.setenv(key, value)

    with pytest.raises(ConfigError):
        load_settings()


def test_rejects_malformed_allowed_user_ids(monkeypatch: pytest.MonkeyPatch) -> None:
    _base_env(monkeypatch)
    monkeypatch.setenv("TELEGRAM_ALLOWED_USER_IDS", "123,abc,456")

    with pytest.raises(ConfigError, match="TELEGRAM_ALLOWED_USER_IDS"):
        load_settings()


def test_rejects_invalid_owner_id(monkeypatch: pytest.MonkeyPatch) -> None:
    _base_env(monkeypatch)
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "not-an-integer")

    with pytest.raises(ConfigError, match="TELEGRAM_CHAT_ID"):
        load_settings()

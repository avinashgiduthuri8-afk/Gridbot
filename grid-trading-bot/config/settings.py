"""Application configuration loaded from environment variables.

A single frozen `Settings` dataclass is constructed once at startup via
`load_settings()` and passed down explicitly to every component. Nothing in
the app reads `os.environ` directly outside of this module.
"""

from __future__ import annotations

import math
import os
from dataclasses import dataclass, field
from urllib.parse import urlparse

from dotenv import load_dotenv

load_dotenv()


class ConfigError(RuntimeError):
    """Raised when required configuration is missing or invalid."""


def _require(key: str) -> str:
    value = os.getenv(key)
    if not value or not value.strip():
        raise ConfigError(
            f"Missing required environment variable: {key}. "
            f"Copy .env.example to .env and fill it in."
        )
    return value.strip()


def _get_float(key: str, default: float) -> float:
    value = os.getenv(key)
    if value is None or not value.strip():
        return default
    try:
        parsed = float(value)
    except ValueError as exc:
        raise ConfigError(f"Environment variable {key} must be a number, got {value!r}") from exc
    if not math.isfinite(parsed):
        raise ConfigError(f"Environment variable {key} must be a finite number, got {value!r}")
    return parsed


def _get_int(key: str, default: int) -> int:
    value = os.getenv(key)
    if value is None or not value.strip():
        return default
    try:
        return int(value)
    except ValueError as exc:
        raise ConfigError(f"Environment variable {key} must be an integer, got {value!r}") from exc


def _require_int(key: str) -> int:
    value = _require(key)
    try:
        return int(value)
    except ValueError as exc:
        raise ConfigError(f"Environment variable {key} must be an integer, got {value!r}") from exc


def _get_bool(key: str, default: bool) -> bool:
    value = os.getenv(key)
    if value is None or not value.strip():
        return default
    return value.strip().lower() in ("1", "true", "yes", "on")


def _parse_ids(key: str, raw: str) -> tuple[int, ...]:
    if not raw:
        return ()
    ids: list[int] = []
    for chunk in raw.split(","):
        chunk = chunk.strip()
        if chunk:
            try:
                ids.append(int(chunk))
            except ValueError as exc:
                raise ConfigError(
                    f"Environment variable {key} must contain comma-separated integers, got {raw!r}"
                ) from exc
    return tuple(ids)


def _validate_range(key: str, value: float | int, *, minimum: float | int | None = None, maximum: float | int | None = None) -> None:
    if minimum is not None and value < minimum:
        raise ConfigError(f"Environment variable {key} must be >= {minimum}, got {value!r}")
    if maximum is not None and value > maximum:
        raise ConfigError(f"Environment variable {key} must be <= {maximum}, got {value!r}")


def _validated_coindcx_base_url(raw: str) -> str:
    value = raw.strip()
    parsed = urlparse(value)
    if parsed.scheme != "https" or not parsed.netloc:
        raise ConfigError(
            "COINDCX_BASE_URL must be an HTTPS URL pointing to CoinDCX, for example https://api.coindcx.com"
        )
    host = parsed.hostname or ""
    if host != "coindcx.com" and not host.endswith(".coindcx.com"):
        raise ConfigError(
            "COINDCX_BASE_URL must point to a CoinDCX domain such as https://api.coindcx.com"
        )
    if parsed.username or parsed.password or parsed.path not in ("", "/") or parsed.query or parsed.fragment:
        raise ConfigError("COINDCX_BASE_URL must not include credentials, path, query, or fragment")
    return value


@dataclass(frozen=True)
class RiskSettings:
    max_total_capital: float
    max_capital_per_coin: float
    max_simultaneous_grids: int
    min_wallet_balance: float
    daily_loss_limit: float


@dataclass(frozen=True)
class BackupSettings:
    enabled: bool
    interval_hours: float
    service_account_json_path: str
    folder_id: str
    retention_count: int


@dataclass(frozen=True)
class WebhookSettings:
    enabled: bool
    host: str
    port: int
    path: str
    secret: str


@dataclass(frozen=True)
class Settings:
    telegram_bot_token: str
    telegram_owner_id: int
    telegram_allowed_ids: tuple[int, ...]

    coindcx_api_key: str
    coindcx_api_secret: str
    coindcx_base_url: str

    database_path: str
    log_dir: str
    log_level: str

    risk: RiskSettings
    backup: BackupSettings

    order_poll_interval_seconds: int
    price_poll_interval_seconds: int
    daily_summary_interval_seconds: int

    # Defaulted (not a plain required field) specifically so every existing
    # Settings(...) construction site — main.py, and every test that builds
    # a Settings instance directly — keeps working unchanged; webhooks are
    # opt-in and disabled by default. Must stay last: dataclass fields with
    # defaults must follow every field without one.
    webhook: WebhookSettings = field(default_factory=lambda: WebhookSettings(
        enabled=False, host="0.0.0.0", port=8080,
        path="/webhooks/coindcx/order-update", secret="",
    ))

    def is_authorized(self, user_id: int) -> bool:
        return user_id == self.telegram_owner_id or user_id in self.telegram_allowed_ids


def load_settings() -> Settings:
    """Load and validate all configuration. Raises ConfigError if invalid."""
    telegram_owner_id = _require_int("TELEGRAM_CHAT_ID")
    allowed_ids = _parse_ids("TELEGRAM_ALLOWED_USER_IDS", os.getenv("TELEGRAM_ALLOWED_USER_IDS", ""))

    risk = RiskSettings(
        max_total_capital=_get_float("MAX_TOTAL_CAPITAL", 50000),
        max_capital_per_coin=_get_float("MAX_CAPITAL_PER_COIN", 20000),
        max_simultaneous_grids=_get_int("MAX_SIMULTANEOUS_GRIDS", 5),
        min_wallet_balance=_get_float("MIN_WALLET_BALANCE", 500),
        daily_loss_limit=_get_float("DAILY_LOSS_LIMIT", 2000),
    )
    _validate_range("MAX_TOTAL_CAPITAL", risk.max_total_capital, minimum=0)
    _validate_range("MAX_CAPITAL_PER_COIN", risk.max_capital_per_coin, minimum=0)
    _validate_range("MAX_SIMULTANEOUS_GRIDS", risk.max_simultaneous_grids, minimum=1)
    _validate_range("MIN_WALLET_BALANCE", risk.min_wallet_balance, minimum=0)
    _validate_range("DAILY_LOSS_LIMIT", risk.daily_loss_limit, minimum=0)

    backup_enabled = _get_bool("GDRIVE_BACKUP_ENABLED", False)
    backup = BackupSettings(
        enabled=backup_enabled,
        interval_hours=_get_float("GDRIVE_BACKUP_INTERVAL_HOURS", 6.0),
        service_account_json_path=os.getenv("GDRIVE_SERVICE_ACCOUNT_JSON", "").strip(),
        folder_id=os.getenv("GDRIVE_FOLDER_ID", "").strip(),
        retention_count=_get_int("GDRIVE_BACKUP_RETENTION_COUNT", 30),
    )
    if backup_enabled and (not backup.service_account_json_path or not backup.folder_id):
        raise ConfigError(
            "GDRIVE_BACKUP_ENABLED=true requires both GDRIVE_SERVICE_ACCOUNT_JSON "
            "(path to the service account key file) and GDRIVE_FOLDER_ID "
            "(the destination Drive folder, shared with the service account's email)."
        )
    if backup_enabled:
        _validate_range("GDRIVE_BACKUP_INTERVAL_HOURS", backup.interval_hours, minimum=0.1)
        _validate_range("GDRIVE_BACKUP_RETENTION_COUNT", backup.retention_count, minimum=1)

    webhook_enabled = _get_bool("WEBHOOK_ENABLED", False)
    webhook = WebhookSettings(
        enabled=webhook_enabled,
        host=os.getenv("WEBHOOK_HOST", "0.0.0.0").strip(),
        port=_get_int("WEBHOOK_PORT", 8080),
        path=os.getenv("WEBHOOK_PATH", "/webhooks/coindcx/order-update").strip(),
        # Webhook secret must be provided explicitly; never fall back to the CoinDCX API secret.
        secret=os.getenv("WEBHOOK_SECRET", "").strip(),
    )
    if webhook_enabled and not webhook.secret:
        raise ConfigError(
            "WEBHOOK_ENABLED=true requires WEBHOOK_SECRET to be set. Do not reuse COINDCX_API_SECRET."
        )
    if webhook_enabled:
        _validate_range("WEBHOOK_PORT", webhook.port, minimum=1, maximum=65535)

    order_poll_interval_seconds = _get_int("ORDER_POLL_INTERVAL_SECONDS", 8)
    price_poll_interval_seconds = _get_int("PRICE_POLL_INTERVAL_SECONDS", 5)
    daily_summary_interval_seconds = _get_int("DAILY_SUMMARY_INTERVAL_SECONDS", 86400)
    _validate_range("ORDER_POLL_INTERVAL_SECONDS", order_poll_interval_seconds, minimum=1)
    _validate_range("PRICE_POLL_INTERVAL_SECONDS", price_poll_interval_seconds, minimum=1)
    _validate_range("DAILY_SUMMARY_INTERVAL_SECONDS", daily_summary_interval_seconds, minimum=1)

    return Settings(
        telegram_bot_token=_require("TELEGRAM_BOT_TOKEN"),
        telegram_owner_id=telegram_owner_id,
        telegram_allowed_ids=allowed_ids,
        coindcx_api_key=_require("COINDCX_API_KEY"),
        coindcx_api_secret=_require("COINDCX_API_SECRET"),
        coindcx_base_url=_validated_coindcx_base_url(
            os.getenv("COINDCX_BASE_URL", "https://api.coindcx.com")
        ),
        database_path=os.getenv("DATABASE_PATH", "data/grid_bot.db").strip(),
        log_dir=os.getenv("LOG_DIR", "logs").strip(),
        log_level=os.getenv("LOG_LEVEL", "INFO").strip(),
        risk=risk,
        backup=backup,
        webhook=webhook,
        order_poll_interval_seconds=order_poll_interval_seconds,
        price_poll_interval_seconds=price_poll_interval_seconds,
        daily_summary_interval_seconds=daily_summary_interval_seconds,
    )

"""Response models for GET /settings.

Deliberately excludes every secret (telegram_bot_token, coindcx_api_key,
coindcx_api_secret) and identifying fields (telegram_owner_id,
telegram_allowed_ids) — this endpoint exposes only operational/risk
parameters that are safe to display on a dashboard.
"""
from __future__ import annotations

from pydantic import BaseModel


class RiskSettingsResponse(BaseModel):
    max_total_capital: float
    max_capital_per_coin: float
    max_simultaneous_grids: int
    min_wallet_balance: float
    daily_loss_limit: float


class SettingsResponse(BaseModel):
    risk: RiskSettingsResponse
    order_poll_interval_seconds: int
    price_poll_interval_seconds: int
    daily_summary_interval_seconds: int
    monitor_interval_seconds: int | None = None
    emergency_stop_active: bool
    backup_enabled: bool
    webhook_enabled: bool
    grid_defaults: dict | None = None

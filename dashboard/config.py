"""Dashboard configuration.

Deliberately separate from config.settings.load_settings() rather than
extending it: the dashboard is a new, additive, read-only component, and
config.settings.py backs the trading engine's own (heavily tested)
startup path. Keeping the two independent means dashboard configuration
can evolve without any risk of affecting DCAManager/RiskManager/etc.'s
existing, already-tested settings loading.

DATABASE_PATH is read with the exact same env var name and default as
config.settings.py's own database_path, so the dashboard points at the
same SQLite file the bot writes to without any extra configuration in
the common case of both running against the same deployment.
"""
from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class DashboardSettings:
    database_path: str
    host: str
    port: int
    cors_origins: list[str]


def load_dashboard_settings() -> DashboardSettings:
    cors_raw = os.getenv("DASHBOARD_CORS_ORIGINS", "").strip()
    cors_origins = [o.strip() for o in cors_raw.split(",") if o.strip()] if cors_raw else ["*"]
    return DashboardSettings(
        database_path=os.getenv("DATABASE_PATH", "data/grid_bot.db").strip(),
        host=os.getenv("DASHBOARD_HOST", "0.0.0.0").strip(),
        port=int(os.getenv("DASHBOARD_PORT", "8000").strip()),
        cors_origins=cors_origins,
    )

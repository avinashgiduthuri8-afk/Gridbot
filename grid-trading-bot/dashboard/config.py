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
    host: str
    port: int
    cors_origins: list[str]
    static_dir: str | None
    database_path: str


def load_dashboard_settings() -> DashboardSettings:
    cors_raw = os.getenv("DASHBOARD_CORS_ORIGINS", "").strip()
    cors_origins = [o.strip() for o in cors_raw.split(",") if o.strip()] if cors_raw else ["*"]

    # Railway (and most PaaS providers) assign a port at deploy time via the
    # $PORT env var and expect the app to bind to it — DASHBOARD_PORT stays
    # as an explicit override for local/self-hosted runs, but $PORT wins
    # when present so a bare `railway up` works with no extra config.
    port_raw = os.getenv("PORT", "").strip() or os.getenv("DASHBOARD_PORT", "").strip() or "8000"

    # If a built frontend (`vite build` output) is present at this path, the
    # app serves it directly — see app.py. Unset/blank or a missing
    # directory disables this entirely (pure API mode, current default).
    static_dir = os.getenv("DASHBOARD_STATIC_DIR", "dashboard/static").strip() or None

    database_path = os.getenv("DATABASE_PATH", "data/grid_bot.db").strip()

    return DashboardSettings(
        host=os.getenv("DASHBOARD_HOST", "0.0.0.0").strip(),
        port=int(port_raw),
        cors_origins=cors_origins,
        static_dir=static_dir,
        database_path=database_path,
    )

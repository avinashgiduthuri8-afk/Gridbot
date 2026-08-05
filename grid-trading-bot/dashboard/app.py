"""FastAPI application factory for the read-only Grid Bot dashboard.

This process is additive and independent of main.py's Telegram bot
process — it reads the SAME SQLite database (via the exact same
Database/Repositories classes the bot itself uses) but never calls into
DCAManager, OrderManager, PriceMonitor, OrderMonitor, or RiskManager, and
never writes to the database. Run it with:

    uvicorn dashboard.app:app --host 0.0.0.0 --port 8000

or `python -m dashboard.app` for a plain dev-server run.
"""
from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from api.routers import analytics, grids, health, orders, portfolio, positions, settings, trade_history
from config.settings import load_settings
from dashboard.config import load_dashboard_settings
from storage.database import Database
from storage.repositories import Repositories
from utils.logger import get_logger, setup_logging

log = get_logger("trading")


@asynccontextmanager
async def lifespan(app: FastAPI):
    setup_logging()
    dashboard_settings = load_dashboard_settings()

    db = Database(dashboard_settings.database_path)
    await db.connect()
    await db.migrate()  # idempotent — safe whether or not the bot process already ran this

    app.state.db = db
    app.state.repos = Repositories(db)
    # Loaded via config.settings.load_settings() (the SAME loader main.py
    # uses) rather than a second, duplicate settings loader — the
    # dashboard is expected to run in the same environment as the bot
    # (same env vars already set), which is also why this reads risk
    # limits and poll intervals but never a secret (see schemas/settings.py).
    app.state.settings = load_settings()

    log.info("Dashboard started against database %s", dashboard_settings.database_path)
    try:
        yield
    finally:
        await db.close()
        log.info("Dashboard shut down.")


def create_app() -> FastAPI:
    app = FastAPI(
        title="Grid Bot Dashboard API",
        description=(
            "Read-only API over the Grid Bot's trading data. Reuses the "
            "existing repository layer and trading.portfolio_metrics — no "
            "trading logic, and no write operations, live in this phase."
        ),
        version="0.1.0",
        lifespan=lifespan,
    )

    dashboard_settings = load_dashboard_settings()
    app.add_middleware(
        CORSMiddleware,
        allow_origins=dashboard_settings.cors_origins,
        allow_methods=["GET"],
        allow_headers=["*"],
    )

    for router_module in (health, grids, positions, orders, trade_history, portfolio, analytics, settings):
        app.include_router(router_module.router, prefix="/api")

    return app


app = create_app()

if __name__ == "__main__":
    import uvicorn

    _settings = load_dashboard_settings()
    uvicorn.run("dashboard.app:app", host=_settings.host, port=_settings.port)

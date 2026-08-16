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

import sqlite3
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

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

    # Loaded via config.settings.load_settings() rather than a second, duplicate
    # settings loader so there's ONE source of truth for the database path.
    app.state.settings = load_settings()

    db = Database(app.state.settings.database_path, read_only=True)
    try:
        await db.connect()
        app.state.db = db
        app.state.repos = Repositories(db)
    except FileNotFoundError:
        log.warning("Database not found. Dashboard will return 503 until bot creates it.")
        app.state.db = None
        app.state.repos = None

    log.info("Dashboard started read-only against database %s", app.state.settings.database_path)
    try:
        yield
    finally:
        if app.state.db:
            await app.state.db.close()
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
        allow_credentials=False,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.exception_handler(sqlite3.OperationalError)
    async def sqlite_operational_exception_handler(request: Request, exc: sqlite3.OperationalError):
        # Missing tables (empty/unmigrated DB) or broken DB
        return JSONResponse(
            status_code=503,
            content={"detail": "Database unavailable or unmigrated"},
        )

    for router_module in (health, grids, positions, orders, trade_history, portfolio, analytics, settings):
        app.include_router(router_module.router, prefix="/api")

    # Optionally serve a pre-built frontend (`vite build` output) from the
    # same process/origin as the API. This is entirely additive: if
    # static_dir is unset or the directory doesn't exist (the default when
    # running the API alone, e.g. in tests), nothing changes below and the
    # app stays API-only. When present, requests to /assets/* (Vite's
    # hashed JS/CSS bundle) are served directly, and any other non-/api
    # path falls back to index.html so the React app's client-side router
    # (not this backend) decides what to render — the same pattern any
    # SPA host uses. This must be registered last so it never shadows the
    # /api/* routers above.
    static_dir = dashboard_settings.static_dir
    index_path = Path(static_dir) / "index.html" if static_dir else None
    if index_path and index_path.is_file():
        assets_dir = Path(static_dir) / "assets"
        if assets_dir.is_dir():
            app.mount("/assets", StaticFiles(directory=str(assets_dir)), name="dashboard-assets")

        @app.get("/{full_path:path}", include_in_schema=False)
        async def serve_spa(full_path: str):  # noqa: ARG001 — path unused, always serves index.html
            return FileResponse(str(index_path))

        log.info("Serving built frontend from %s", static_dir)
    else:
        log.info("No frontend build found at %s — running in API-only mode", static_dir)

    return app


app = create_app()

if __name__ == "__main__":
    import uvicorn

    _settings = load_dashboard_settings()
    uvicorn.run("dashboard.app:app", host=_settings.host, port=_settings.port)

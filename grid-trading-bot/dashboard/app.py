"""FastAPI application factory for the Grid Bot dashboard.

Supports both embedded execution inside main.py and standalone deployment.
"""
from __future__ import annotations

import os
import sqlite3
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, APIRouter, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from api.routers import analytics, grids, health, orders, portfolio, positions, settings, trade_history
from dashboard.config import load_dashboard_settings
from storage.database import Database
from storage.repositories import Repositories
from utils.logger import get_logger, setup_logging

log = get_logger("trading")


@asynccontextmanager
async def lifespan(app: FastAPI):
    setup_logging()
    dashboard_settings = load_dashboard_settings()
    app.state.dashboard_settings = dashboard_settings
    app.state.settings = dashboard_settings
    read_only = os.getenv("DASHBOARD_READ_ONLY", "false").lower() in ("true", "1")

    if not hasattr(app.state, "db") or app.state.db is None:
        if read_only:
            db = Database(dashboard_settings.database_path, read_only=True)
            try:
                await db.connect()
                app.state.db = db
                app.state.repos = Repositories(db)
            except FileNotFoundError:
                log.warning("Database not found. Dashboard will return 503 until bot creates it.")
                app.state.db = None
                app.state.repos = None
        else:
            db = Database(dashboard_settings.database_path)
            try:
                await db.connect()
                await db.migrate()
                app.state.db = db
                app.state.repos = Repositories(db)
            except Exception as exc:
                log.warning("Database initialization in dashboard: %s", exc)
                app.state.db = None
                app.state.repos = None

    if not read_only and app.state.repos is not None and (not hasattr(app.state, "dca_manager") or app.state.dca_manager is None):
        try:
            from config.settings import load_settings
            from exchange.coindcx import CoinDCXClient
            from exchange.paper_exchange import PaperExchangeClient
            from notifications.notifier import Notifier
            from risk.risk_manager import RiskManager
            from trading.dca_manager import DCAManager
            from trading.mixed_order_manager import MixedOrderManager
            from trading.order_manager import OrderManager

            bot_settings = load_settings()
            exchange = CoinDCXClient(
                api_key=bot_settings.coindcx_api_key,
                api_secret=bot_settings.coindcx_api_secret,
                base_url=bot_settings.coindcx_base_url,
            )
            paper_exchange = PaperExchangeClient(exchange)
            risk_mgr = RiskManager(bot_settings.risk, app.state.repos)
            await risk_mgr.load_emergency_stop()
            real_om = OrderManager(exchange, app.state.repos)
            paper_om = OrderManager(paper_exchange, app.state.repos)
            mixed_om = MixedOrderManager(real=real_om, paper=paper_om, repos=app.state.repos)
            notifier = Notifier(bot=None, chat_ids=())
            dca_mgr = DCAManager(
                exchange=exchange,
                repos=app.state.repos,
                order_manager=mixed_om,
                notifier=notifier,
                risk=risk_mgr,
            )
            app.state.exchange = exchange
            app.state.risk_manager = risk_mgr
            app.state.dca_manager = dca_mgr
        except Exception as exc:
            log.info("Running dashboard in read-only / unconfigured exchange mode: %s", exc)

    log.info("Dashboard started on %s:%d against database %s", dashboard_settings.host, dashboard_settings.port, dashboard_settings.database_path)
    try:
        yield
    finally:
        if hasattr(app.state, "db") and app.state.db:
            await app.state.db.close()
        log.info("Dashboard shut down.")


def create_app() -> FastAPI:
    app = FastAPI(
        title="Grid Bot Dashboard API",
        description="REST API for Grid Bot dashboard monitoring and manual trade execution.",
        version="0.2.0",
        lifespan=lifespan,
    )

    dashboard_settings = load_dashboard_settings()
    read_only = os.getenv("DASHBOARD_READ_ONLY", "false").lower() in ("true", "1")

    app.add_middleware(
        CORSMiddleware,
        allow_origins=dashboard_settings.cors_origins,
        allow_credentials=False,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.exception_handler(sqlite3.OperationalError)
    async def sqlite_operational_exception_handler(request: Request, exc: sqlite3.OperationalError):
        return JSONResponse(
            status_code=503,
            content={"detail": "Database unavailable or unmigrated"},
        )

    for router_module in (health, grids, positions, orders, trade_history, portfolio, analytics, settings):
        if read_only:
            # Filter out non-GET routes in strict read-only mode
            ro_router = APIRouter()
            for route in router_module.router.routes:
                methods = getattr(route, "methods", set()) or set()
                if methods.issubset({"GET", "HEAD", "OPTIONS"}):
                    ro_router.routes.append(route)
            app.include_router(ro_router, prefix="/api")
        else:
            app.include_router(router_module.router, prefix="/api")

    static_dir = dashboard_settings.static_dir
    index_path = Path(static_dir) / "index.html" if static_dir else None
    if index_path and index_path.is_file():
        assets_dir = Path(static_dir) / "assets"
        if assets_dir.is_dir():
            app.mount("/assets", StaticFiles(directory=str(assets_dir)), name="dashboard-assets")

        @app.get("/{full_path:path}", include_in_schema=False)
        async def serve_spa(full_path: str):
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

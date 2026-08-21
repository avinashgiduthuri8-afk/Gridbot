"""Application entrypoint for the Indian Stock Market Scanner (PROJECT-BETA).

Wires together the database, MarketDataProvider, IndianSessionManager,
12-Stage Institutional Stock Scanner, and FastAPI dashboard server.

Run with: python main.py
"""

from __future__ import annotations

import asyncio
import os
import signal
import uvicorn

from dashboard.app import create_app
from dashboard.config import load_dashboard_settings
from engine.data.yahoo_provider import YahooFinanceProvider
from engine.signals.scanner import IndianStockScanner
from services.scanner_service import ScannerService
from storage.database import Database
from storage.repositories import Repositories
from utils.logger import get_logger, setup_logging

log = get_logger("scanner")


async def async_main() -> None:
    setup_logging()
    log.info("Starting Indian Stock Market Scanner (PROJECT-BETA)...")

    settings = load_dashboard_settings()
    db_path = settings.database_path
    os.makedirs(os.path.dirname(db_path) if os.path.dirname(db_path) else ".", exist_ok=True)

    db = Database(db_path)
    await db.connect()
    await db.migrate()
    repos = Repositories(db)

    provider = YahooFinanceProvider()
    scanner = IndianStockScanner(provider=provider)
    scanner_service = ScannerService(provider=provider, scanner=scanner, repo=repos.signals)

    app = create_app()
    app.state.db = db
    app.state.repos = repos
    app.state.scanner_service = scanner_service

    config = uvicorn.Config(
        app,
        host=settings.host,
        port=settings.port,
        log_level="info",
    )
    server = uvicorn.Server(config)

    log.info("Indian Stock Scanner & Dashboard running at http://%s:%d", settings.host, settings.port)
    await server.serve()


def main() -> None:
    try:
        asyncio.run(async_main())
    except (KeyboardInterrupt, SystemExit):
        log.info("Scanner application terminated by user.")


if __name__ == "__main__":
    main()

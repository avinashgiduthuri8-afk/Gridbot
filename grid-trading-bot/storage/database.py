"""SQLite database bootstrap and schema migration for Indian Stock Scanner.

Uses aiosqlite so all I/O stays on the asyncio event loop.
WAL mode is enabled for crash-safe writes and concurrent readers.
"""

from __future__ import annotations

from pathlib import Path
from typing import Awaitable, Callable

import aiosqlite

from utils.helpers import now_iso
from utils.logger import get_logger

log = get_logger("database")

SCHEMA = """
CREATE TABLE IF NOT EXISTS stock_signals (
    signal_id           TEXT PRIMARY KEY,
    symbol              TEXT NOT NULL,
    signal_type         TEXT NOT NULL,
    strength            TEXT NOT NULL,
    score               REAL NOT NULL,
    entry_price         REAL NOT NULL,
    stop_loss           REAL NOT NULL,
    target_1            REAL NOT NULL,
    target_2            REAL NOT NULL,
    risk_reward         REAL NOT NULL,
    market_regime       TEXT NOT NULL,
    sector              TEXT NOT NULL,
    timeframe_summary   TEXT NOT NULL,
    rationale_json      TEXT NOT NULL,
    breakdown_json      TEXT NOT NULL,
    status              TEXT NOT NULL DEFAULT 'OPEN',
    mfe                 REAL NOT NULL DEFAULT 0.0,
    mae                 REAL NOT NULL DEFAULT 0.0,
    outcome_pnl_pct     REAL NOT NULL DEFAULT 0.0,
    created_at          TEXT NOT NULL,
    resolved_at         TEXT
);

CREATE INDEX IF NOT EXISTS idx_stock_signals_symbol ON stock_signals(symbol);
CREATE INDEX IF NOT EXISTS idx_stock_signals_status ON stock_signals(status);
CREATE INDEX IF NOT EXISTS idx_stock_signals_score ON stock_signals(score);

CREATE TABLE IF NOT EXISTS signal_backtests (
    backtest_id         TEXT PRIMARY KEY,
    universe            TEXT NOT NULL,
    start_date          TEXT NOT NULL,
    end_date            TEXT NOT NULL,
    total_signals       INTEGER NOT NULL,
    win_rate_pct        REAL NOT NULL,
    avg_return_pct      REAL NOT NULL,
    profit_factor       REAL NOT NULL,
    max_drawdown_pct    REAL NOT NULL,
    regime_breakdown_json TEXT NOT NULL,
    created_at          TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS registered_bots (
    bot_id              TEXT PRIMARY KEY,
    name                TEXT NOT NULL,
    target_broker       TEXT NOT NULL,
    webhook_url         TEXT NOT NULL,
    secret_key          TEXT NOT NULL,
    subscribed_setups   TEXT NOT NULL,
    min_confidence_score REAL NOT NULL DEFAULT 75.0,
    is_active           INTEGER NOT NULL DEFAULT 1,
    created_at          TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_registered_bots_active ON registered_bots(is_active);

CREATE TABLE IF NOT EXISTS dispatch_receipts (
    dispatch_id         TEXT PRIMARY KEY,
    signal_id           TEXT NOT NULL,
    bot_id              TEXT NOT NULL,
    timestamp           TEXT NOT NULL,
    status              TEXT NOT NULL,
    response_code       INTEGER NOT NULL DEFAULT 0,
    latency_ms          REAL NOT NULL DEFAULT 0.0,
    error_message       TEXT
);

CREATE INDEX IF NOT EXISTS idx_dispatch_receipts_signal ON dispatch_receipts(signal_id);
CREATE INDEX IF NOT EXISTS idx_dispatch_receipts_bot ON dispatch_receipts(bot_id);
CREATE INDEX IF NOT EXISTS idx_dispatch_receipts_time ON dispatch_receipts(timestamp);

CREATE TABLE IF NOT EXISTS schema_version (
    version INTEGER PRIMARY KEY
);
"""


class Database:
    """Async SQLite database manager with WAL mode and migrations."""

    def __init__(self, db_path: str, read_only: bool = False) -> None:
        self.db_path = db_path
        self.read_only = read_only
        self._connection: aiosqlite.Connection | None = None

    @property
    def connection(self) -> aiosqlite.Connection:
        if self._connection is None:
            raise RuntimeError("Database is not connected. Call connect() first.")
        return self._connection

    async def connect(self) -> None:
        if self.read_only:
            uri = f"file:{Path(self.db_path).resolve().as_posix()}?mode=ro"
            self._connection = await aiosqlite.connect(uri, uri=True)
        else:
            self._connection = await aiosqlite.connect(self.db_path)
            await self._connection.execute("PRAGMA journal_mode = WAL;")

        self._connection.row_factory = aiosqlite.Row
        await self._connection.execute("PRAGMA synchronous = NORMAL;")
        await self._connection.execute("PRAGMA busy_timeout = 5000;")
        log.info("Connected to SQLite database at %s (read_only=%s)", self.db_path, self.read_only)

    async def migrate(self) -> None:
        if self.read_only:
            return
        await self.connection.executescript(SCHEMA)
        await self.connection.commit()
        log.info("Database schema initialized successfully.")

    async def close(self) -> None:
        if self._connection:
            await self._connection.close()
            self._connection = None
            log.info("Database connection closed.")

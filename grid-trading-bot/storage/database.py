"""SQLite database bootstrap: connection factory + schema migration.

Uses aiosqlite so the whole engine stays on a single asyncio event loop
without blocking on disk I/O. WAL mode is enabled for crash-safe writes
and to allow concurrent readers while the engine writes.
"""

from __future__ import annotations

from pathlib import Path

import aiosqlite

from utils.logger import get_logger

log = get_logger("database")

SCHEMA = """
CREATE TABLE IF NOT EXISTS settings (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS coin_configs (
    symbol TEXT PRIMARY KEY,
    grid_levels INTEGER NOT NULL,
    investment_per_grid REAL NOT NULL,
    upper_price REAL,
    lower_price REAL,
    grid_type TEXT NOT NULL DEFAULT 'arithmetic',
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS grids (
    grid_id TEXT PRIMARY KEY,
    symbol TEXT NOT NULL,
    grid_type TEXT NOT NULL,
    status TEXT NOT NULL,
    upper_price REAL NOT NULL,
    lower_price REAL NOT NULL,
    grid_levels INTEGER NOT NULL,
    investment_per_grid REAL NOT NULL,
    total_invested REAL NOT NULL DEFAULT 0,
    realized_profit REAL NOT NULL DEFAULT 0,
    completed_cycles INTEGER NOT NULL DEFAULT 0,
    stopped_reason TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_grids_status ON grids(status);
CREATE INDEX IF NOT EXISTS idx_grids_symbol ON grids(symbol);

CREATE TABLE IF NOT EXISTS grid_levels (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    grid_id TEXT NOT NULL,
    level_index INTEGER NOT NULL,
    price REAL NOT NULL,
    side TEXT NOT NULL,
    is_filled INTEGER NOT NULL DEFAULT 0,
    order_id TEXT,
    UNIQUE(grid_id, level_index, side),
    FOREIGN KEY(grid_id) REFERENCES grids(grid_id)
);

CREATE TABLE IF NOT EXISTS orders (
    order_id TEXT PRIMARY KEY,
    grid_id TEXT NOT NULL,
    exchange_order_id TEXT,
    symbol TEXT NOT NULL,
    side TEXT NOT NULL,
    price REAL NOT NULL,
    quantity REAL NOT NULL,
    filled_quantity REAL NOT NULL DEFAULT 0,
    filled_price REAL NOT NULL DEFAULT 0,
    status TEXT NOT NULL,
    level_index INTEGER NOT NULL,
    error_message TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    FOREIGN KEY(grid_id) REFERENCES grids(grid_id)
);

CREATE INDEX IF NOT EXISTS idx_orders_grid ON orders(grid_id);
CREATE INDEX IF NOT EXISTS idx_orders_status ON orders(status);
CREATE INDEX IF NOT EXISTS idx_orders_exchange_id ON orders(exchange_order_id);

CREATE TABLE IF NOT EXISTS positions (
    position_id TEXT PRIMARY KEY,
    grid_id TEXT NOT NULL,
    symbol TEXT NOT NULL,
    entry_order_id TEXT NOT NULL,
    entry_price REAL NOT NULL,
    quantity REAL NOT NULL,
    status TEXT NOT NULL,
    exit_order_id TEXT,
    exit_price REAL,
    realized_pnl REAL,
    created_at TEXT NOT NULL,
    closed_at TEXT,
    FOREIGN KEY(grid_id) REFERENCES grids(grid_id)
);

CREATE INDEX IF NOT EXISTS idx_positions_grid ON positions(grid_id);
CREATE INDEX IF NOT EXISTS idx_positions_status ON positions(status);

CREATE TABLE IF NOT EXISTS trade_history (
    trade_id TEXT PRIMARY KEY,
    grid_id TEXT NOT NULL,
    order_id TEXT NOT NULL,
    symbol TEXT NOT NULL,
    side TEXT NOT NULL,
    price REAL NOT NULL,
    quantity REAL NOT NULL,
    fee REAL NOT NULL DEFAULT 0,
    pnl REAL NOT NULL DEFAULT 0,
    executed_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_trade_history_grid ON trade_history(grid_id);

CREATE TABLE IF NOT EXISTS logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    channel TEXT NOT NULL,
    level TEXT NOT NULL,
    message TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_logs_channel ON logs(channel);

CREATE TABLE IF NOT EXISTS daily_stats (
    date TEXT PRIMARY KEY,
    realized_pnl REAL NOT NULL DEFAULT 0,
    trades_count INTEGER NOT NULL DEFAULT 0,
    updated_at TEXT NOT NULL
);
"""


class Database:
    """Thin async wrapper around a single shared aiosqlite connection."""

    def __init__(self, db_path: str) -> None:
        self._db_path = db_path
        self._conn: aiosqlite.Connection | None = None

    @property
    def connection(self) -> aiosqlite.Connection:
        if self._conn is None:
            raise RuntimeError("Database not connected. Call connect() first.")
        return self._conn

    async def connect(self) -> None:
        Path(self._db_path).parent.mkdir(parents=True, exist_ok=True)
        self._conn = await aiosqlite.connect(self._db_path)
        self._conn.row_factory = aiosqlite.Row
        await self._conn.execute("PRAGMA journal_mode=WAL;")
        await self._conn.execute("PRAGMA foreign_keys=ON;")
        await self._conn.execute("PRAGMA synchronous=NORMAL;")
        await self._conn.commit()
        log.info("Connected to SQLite database at %s", self._db_path)

    async def migrate(self) -> None:
        assert self._conn is not None
        await self._conn.executescript(SCHEMA)
        await self._conn.commit()
        log.info("Database schema migration complete")

    async def close(self) -> None:
        if self._conn is not None:
            await self._conn.close()
            self._conn = None
            log.info("Database connection closed")

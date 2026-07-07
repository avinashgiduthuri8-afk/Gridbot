"""SQLite database bootstrap: connection factory and schema migration.

Uses aiosqlite so all I/O stays on the asyncio event loop.
WAL mode is enabled for crash-safe writes and concurrent readers.
"""

from __future__ import annotations

from pathlib import Path

import aiosqlite

from utils.logger import get_logger

log = get_logger("database")

SCHEMA = """
CREATE TABLE IF NOT EXISTS dca_grids (
    grid_id              TEXT PRIMARY KEY,
    symbol               TEXT NOT NULL,
    status               TEXT NOT NULL DEFAULT 'active',
    mode                 TEXT NOT NULL DEFAULT 'real',

    entry_price          REAL NOT NULL,
    base_investment      REAL NOT NULL,
    dip_buy_amount       REAL NOT NULL,
    dip_percentage       REAL NOT NULL,
    profit_sell_amount   REAL NOT NULL,
    profit_percentage    REAL NOT NULL,
    max_levels           INTEGER NOT NULL,
    stop_loss_percentage REAL NOT NULL,

    current_level        INTEGER NOT NULL DEFAULT 0,
    total_quantity       REAL    NOT NULL DEFAULT 0,
    total_investment     REAL    NOT NULL DEFAULT 0,
    average_entry_price  REAL    NOT NULL DEFAULT 0,
    last_buy_price       REAL    NOT NULL DEFAULT 0,
    next_buy_price       REAL    NOT NULL DEFAULT 0,
    next_sell_price      REAL    NOT NULL DEFAULT 0,
    realized_profit      REAL    NOT NULL DEFAULT 0,
    completed_cycles     INTEGER NOT NULL DEFAULT 0,

    created_at           TEXT NOT NULL,
    updated_at           TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_dca_grids_status ON dca_grids(status);
CREATE INDEX IF NOT EXISTS idx_dca_grids_symbol ON dca_grids(symbol);

CREATE TABLE IF NOT EXISTS orders (
    order_id          TEXT PRIMARY KEY,
    grid_id           TEXT NOT NULL,
    exchange_order_id TEXT,
    symbol            TEXT NOT NULL,
    side              TEXT NOT NULL,
    order_type        TEXT NOT NULL DEFAULT 'market_order',
    price             REAL NOT NULL DEFAULT 0,
    quantity          REAL NOT NULL DEFAULT 0,
    filled_quantity   REAL NOT NULL DEFAULT 0,
    filled_price      REAL NOT NULL DEFAULT 0,
    status            TEXT NOT NULL DEFAULT 'pending',
    created_at        TEXT NOT NULL,
    updated_at        TEXT NOT NULL,
    FOREIGN KEY(grid_id) REFERENCES dca_grids(grid_id)
);

CREATE INDEX IF NOT EXISTS idx_orders_grid   ON orders(grid_id);
CREATE INDEX IF NOT EXISTS idx_orders_status ON orders(status);
CREATE INDEX IF NOT EXISTS idx_orders_ex_id  ON orders(exchange_order_id);

CREATE TABLE IF NOT EXISTS trade_history (
    trade_id       TEXT PRIMARY KEY,
    grid_id        TEXT NOT NULL,
    order_id       TEXT NOT NULL,
    symbol         TEXT NOT NULL,
    side           TEXT NOT NULL,
    price          REAL NOT NULL,
    quantity       REAL NOT NULL,
    investment_inr REAL NOT NULL DEFAULT 0,
    fee            REAL NOT NULL DEFAULT 0,
    pnl            REAL NOT NULL DEFAULT 0,
    executed_at    TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_trade_grid   ON trade_history(grid_id);
CREATE INDEX IF NOT EXISTS idx_trade_symbol ON trade_history(symbol);

CREATE TABLE IF NOT EXISTS daily_stats (
    date         TEXT PRIMARY KEY,
    realized_pnl REAL    NOT NULL DEFAULT 0,
    trades_count INTEGER NOT NULL DEFAULT 0,
    updated_at   TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS logs (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    channel    TEXT NOT NULL,
    level      TEXT NOT NULL,
    message    TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_logs_channel ON logs(channel);
"""

_MIGRATION_STMTS = [
    "ALTER TABLE dca_grids ADD COLUMN mode TEXT NOT NULL DEFAULT 'real'",
]


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
        for stmt in _MIGRATION_STMTS:
            try:
                await self._conn.execute(stmt)
                await self._conn.commit()
            except Exception:
                pass
        log.info("Database schema migration complete")

    async def close(self) -> None:
        if self._conn is not None:
            await self._conn.close()
            self._conn = None
            log.info("Database connection closed")

"""SQLite database bootstrap: connection factory and schema migration.

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
    trailing_enabled     INTEGER NOT NULL DEFAULT 0,
    trailing_percentage  REAL,
    trailing_peak_price  REAL,

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
    fee               REAL NOT NULL DEFAULT 0,
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

CREATE TABLE IF NOT EXISTS monitor_settings (
    key        TEXT PRIMARY KEY,
    value      TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS price_alerts (
    alert_id    TEXT PRIMARY KEY,
    symbol      TEXT NOT NULL,
    target_price REAL NOT NULL,
    direction   TEXT NOT NULL,
    set_at      TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_price_alerts_symbol ON price_alerts(symbol);

CREATE TABLE IF NOT EXISTS grid_defaults (
    id                    INTEGER PRIMARY KEY CHECK (id = 1),
    base_investment       REAL NOT NULL,
    dip_buy_amount        REAL NOT NULL,
    dip_percentage        REAL NOT NULL,
    profit_sell_amount    REAL NOT NULL,
    profit_percentage     REAL NOT NULL,
    max_levels            INTEGER NOT NULL,
    stop_loss_percentage  REAL NOT NULL,
    last_mode             TEXT,
    updated_at            TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS schema_migrations (
    version     INTEGER PRIMARY KEY,
    description TEXT NOT NULL,
    applied_at  TEXT NOT NULL
);
"""

async def _column_exists(conn: aiosqlite.Connection, table: str, column: str) -> bool:
    cur = await conn.execute(f"PRAGMA table_info({table})")
    rows = await cur.fetchall()
    return any(row["name"] == column for row in rows)


async def _migration_001_add_mode_column(conn: aiosqlite.Connection) -> None:
    """dca_grids.mode was added after the initial schema; guard on the
    column's actual presence (not a try/except around the ALTER) so a
    genuine failure — disk full, corrupt DB, permissions — is never
    confused with "already applied" and silently swallowed.
    """
    if not await _column_exists(conn, "dca_grids", "mode"):
        await conn.execute(
            "ALTER TABLE dca_grids ADD COLUMN mode TEXT NOT NULL DEFAULT 'real'"
        )


# Each entry: (version, human-readable description, async fn(conn) -> None).
# Versions are permanent once shipped — never renumber or edit an existing
# entry's behavior after release; add a new numbered migration instead.
async def _migration_002_add_trailing_columns(conn: aiosqlite.Connection) -> None:
    """trailing_enabled/trailing_percentage/trailing_peak_price were added
    after the initial schema for the Trailing Take Profit feature — same
    idempotency-guard pattern as migration 001."""
    if not await _column_exists(conn, "dca_grids", "trailing_enabled"):
        await conn.execute(
            "ALTER TABLE dca_grids ADD COLUMN trailing_enabled INTEGER NOT NULL DEFAULT 0"
        )
    if not await _column_exists(conn, "dca_grids", "trailing_percentage"):
        await conn.execute("ALTER TABLE dca_grids ADD COLUMN trailing_percentage REAL")
    if not await _column_exists(conn, "dca_grids", "trailing_peak_price"):
        await conn.execute("ALTER TABLE dca_grids ADD COLUMN trailing_peak_price REAL")


async def _migration_003_add_idempotent_submission_columns(conn: aiosqlite.Connection) -> None:
    """Persist the identity and audit state required to reconcile a create.

    Existing historical orders intentionally retain a NULL client_order_id:
    they were submitted before this protocol existed and must never be matched
    to a new exchange order by a fabricated identifier.
    """
    if not await _column_exists(conn, "orders", "client_order_id"):
        await conn.execute("ALTER TABLE orders ADD COLUMN client_order_id TEXT")
    if not await _column_exists(conn, "orders", "reconciliation_status"):
        await conn.execute(
            "ALTER TABLE orders ADD COLUMN reconciliation_status TEXT NOT NULL DEFAULT 'not_needed'"
        )
    if not await _column_exists(conn, "orders", "reconciliation_retry_count"):
        await conn.execute(
            "ALTER TABLE orders ADD COLUMN reconciliation_retry_count INTEGER NOT NULL DEFAULT 0"
        )
    await conn.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS idx_orders_client_order_id "
        "ON orders(client_order_id) WHERE client_order_id IS NOT NULL"
    )


async def _migration_004_add_order_fee_column(conn: aiosqlite.Connection) -> None:
    """Persist per-order exchange fees so realised P&L can be net of fees."""
    if not await _column_exists(conn, "orders", "fee"):
        await conn.execute(
            "ALTER TABLE orders ADD COLUMN fee REAL NOT NULL DEFAULT 0"
        )


_MIGRATIONS: list[tuple[int, str, Callable[[aiosqlite.Connection], Awaitable[None]]]] = [
    (1, "Add mode column to dca_grids", _migration_001_add_mode_column),
    (2, "Add trailing take-profit columns to dca_grids", _migration_002_add_trailing_columns),
    (3, "Add idempotent CoinDCX order submission fields", _migration_003_add_idempotent_submission_columns),
    (4, "Add per-order fee column", _migration_004_add_order_fee_column),
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
        resolved_path = Path(self._db_path).resolve()
        existed_before = resolved_path.exists()

        self._conn = await aiosqlite.connect(self._db_path)
        self._conn.row_factory = aiosqlite.Row
        await self._conn.execute("PRAGMA journal_mode=WAL;")
        await self._conn.execute("PRAGMA foreign_keys=ON;")
        await self._conn.execute("PRAGMA synchronous=NORMAL;")
        await self._conn.execute("PRAGMA busy_timeout=5000;")
        await self._conn.commit()
        log.info(
            "Connected to SQLite database at %s (resolved: %s, pre-existing file: %s)",
            self._db_path, resolved_path, existed_before,
        )
        if not existed_before:
            log.warning(
                "No pre-existing database file was found at %s — a brand-new, "
                "empty database was just created. If you expected existing "
                "grids/history to be here, this likely means DATABASE_PATH "
                "or the mounted volume does not point at the same location "
                "as the previous deployment.",
                resolved_path,
            )

    async def migrate(self) -> None:
        assert self._conn is not None
        await self._conn.executescript(SCHEMA)
        await self._conn.commit()

        cur = await self._conn.execute("SELECT version FROM schema_migrations")
        applied = {row["version"] for row in await cur.fetchall()}

        for version, description, fn in _MIGRATIONS:
            if version in applied:
                continue
            try:
                await fn(self._conn)
            except Exception:
                # A genuine migration failure must stop startup, not be logged
                # and silently skipped — running against a half-migrated
                # schema is worse than refusing to start.
                log.exception(
                    "Migration %d (%s) FAILED — aborting startup. "
                    "Database may need manual inspection.",
                    version, description,
                )
                raise
            await self._conn.execute(
                "INSERT INTO schema_migrations (version, description, applied_at) "
                "VALUES (?, ?, ?)",
                (version, description, now_iso()),
            )
            await self._conn.commit()
            log.info("Migration %d applied: %s", version, description)

        current_version = max(applied | {v for v, _, _ in _MIGRATIONS}, default=0)
        log.info("Database schema migration complete (schema_version=%d)", current_version)

    async def close(self) -> None:
        if self._conn is not None:
            await self._conn.close()
            self._conn = None
            log.info("Database connection closed")

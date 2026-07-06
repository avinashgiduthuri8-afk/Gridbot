"""Dataclasses mirroring the SQLite tables. Kept intentionally simple —
these are plain data containers, not ORM entities.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class GridRecord:
    grid_id: str
    symbol: str
    grid_type: str
    status: str
    upper_price: float
    lower_price: float
    grid_levels: int
    investment_per_grid: float
    created_at: str
    updated_at: str
    total_invested: float = 0.0
    realized_profit: float = 0.0
    completed_cycles: int = 0
    stopped_reason: str | None = None


@dataclass
class GridLevelRecord:
    id: int | None
    grid_id: str
    level_index: int
    price: float
    side: str
    is_filled: bool
    order_id: str | None = None


@dataclass
class OrderRecord:
    order_id: str
    grid_id: str
    exchange_order_id: str | None
    symbol: str
    side: str
    price: float
    quantity: float
    status: str
    level_index: int
    created_at: str
    updated_at: str
    filled_quantity: float = 0.0
    filled_price: float = 0.0
    error_message: str | None = None


@dataclass
class PositionRecord:
    position_id: str
    grid_id: str
    symbol: str
    entry_order_id: str
    entry_price: float
    quantity: float
    status: str
    created_at: str
    exit_order_id: str | None = None
    exit_price: float | None = None
    realized_pnl: float | None = None
    closed_at: str | None = None


@dataclass
class TradeHistoryRecord:
    trade_id: str
    grid_id: str
    order_id: str
    symbol: str
    side: str
    price: float
    quantity: float
    fee: float
    pnl: float
    executed_at: str


@dataclass
class LogRecord:
    id: int | None
    channel: str
    level: str
    message: str
    created_at: str

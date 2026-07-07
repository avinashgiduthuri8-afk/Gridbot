"""Dataclasses mirroring the SQLite tables.

Plain data containers — not ORM entities. Each field maps directly to a
column in the corresponding table, making (de)serialisation trivial.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class DCAGridRecord:
    grid_id: str
    symbol: str
    status: str

    entry_price: float
    base_investment: float
    dip_buy_amount: float
    dip_percentage: float
    profit_sell_amount: float
    profit_percentage: float
    max_levels: int
    stop_loss_percentage: float

    current_level: int
    total_quantity: float
    total_investment: float
    average_entry_price: float
    last_buy_price: float
    next_buy_price: float
    next_sell_price: float
    realized_profit: float
    completed_cycles: int

    created_at: str
    updated_at: str
    mode: str = "real"


@dataclass
class OrderRecord:
    order_id: str
    grid_id: str
    exchange_order_id: str | None
    symbol: str
    side: str
    order_type: str
    price: float
    quantity: float
    filled_quantity: float
    filled_price: float
    status: str
    created_at: str
    updated_at: str


@dataclass
class TradeHistoryRecord:
    trade_id: str
    grid_id: str
    order_id: str
    symbol: str
    side: str
    price: float
    quantity: float
    investment_inr: float
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

"""Response models for GET /trade-history.

Field names and types mirror storage.models.TradeHistoryRecord.
"""
from __future__ import annotations

from pydantic import BaseModel


class TradeResponse(BaseModel):
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


class TradeHistoryResponse(BaseModel):
    trades: list[TradeResponse]
    count: int

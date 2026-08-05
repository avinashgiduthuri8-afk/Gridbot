"""Response models for GET /orders.

Field names and types mirror storage.models.OrderRecord.
"""
from __future__ import annotations

from pydantic import BaseModel


class OrderResponse(BaseModel):
    order_id: str
    grid_id: str
    exchange_order_id: str | None = None
    symbol: str
    side: str
    order_type: str
    price: float
    quantity: float
    filled_quantity: float
    filled_price: float
    status: str
    fee: float
    reconciliation_status: str
    created_at: str
    updated_at: str


class OrderListResponse(BaseModel):
    orders: list[OrderResponse]
    count: int

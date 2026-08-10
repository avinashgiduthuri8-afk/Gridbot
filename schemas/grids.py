"""Response models for GET /grids.

Field names and types mirror storage.models.DCAGridRecord exactly — this
schema is a read-only view over that record, not a new shape.
"""
from __future__ import annotations

from pydantic import BaseModel, Field


class GridResponse(BaseModel):
    grid_id: str
    symbol: str
    status: str
    mode: str

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

    trailing_enabled: bool
    trailing_percentage: float | None = None
    trailing_peak_price: float | None = None

    created_at: str
    updated_at: str


class GridListResponse(BaseModel):
    grids: list[GridResponse]
    count: int = Field(description="Number of grids in this response")

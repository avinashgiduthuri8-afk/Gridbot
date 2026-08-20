"""Request and Response models for /grids."""
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


class CreateGridRequest(BaseModel):
    symbol: str
    entry_price: float = 0.0
    base_investment: float
    dip_buy_amount: float
    dip_percentage: float
    profit_sell_amount: float
    profit_percentage: float
    max_levels: int
    stop_loss_percentage: float
    mode: str = "paper"
    trailing_enabled: bool = False
    trailing_percentage: float | None = None


class CreateGridResponse(BaseModel):
    grid_id: str
    symbol: str
    mode: str
    status: str
    message: str


class ManualBuyRequest(BaseModel):
    inr_amount: float


class ManualSellRequest(BaseModel):
    inr_amount: float | None = None


class ManualTradeResponse(BaseModel):
    success: bool
    grid_id: str
    symbol: str
    side: str
    quantity: float
    price: float
    inr_amount: float
    mode: str
    order_id: str | None = None
    message: str


class GridActionResponse(BaseModel):
    success: bool
    grid_id: str
    action: str
    message: str

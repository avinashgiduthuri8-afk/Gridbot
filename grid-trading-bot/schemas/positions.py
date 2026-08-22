"""Response models for GET /positions.

A "position" is an ACTIVE or PAUSED grid that currently holds a nonzero
quantity — i.e. an open, live position, as distinct from the full grid
list (which also includes completed/stopped grids with no holding).

Phase 3 is read-only and does not wire in a live price feed (PriceMonitor
is explicitly out of scope for this phase), so unrealized P&L is computed
via trading.portfolio_metrics.grid_pnl_breakdown() with whatever price (if
any) is supplied to the endpoint — current_price=None correctly yields
unrealized=0.0 rather than a fabricated number. See the /positions router
docstring for how a price can be supplied.
"""
from __future__ import annotations

from pydantic import BaseModel


class PositionResponse(BaseModel):
    grid_id: str
    symbol: str
    status: str
    mode: str

    quantity: float
    average_entry_price: float
    invested: float

    current_price: float | None = None
    realized_pnl: float
    unrealized_pnl: float
    combined_pnl: float

    current_level: int
    max_levels: int
    trailing_enabled: bool
    trailing_peak_price: float | None = None


class PositionListResponse(BaseModel):
    positions: list[PositionResponse]
    count: int

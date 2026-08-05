"""Response models for GET /portfolio.

Field names mirror trading.portfolio_metrics.portfolio_totals()'s return
dict exactly — this schema documents that dict's shape for OpenAPI/Swagger,
it doesn't compute anything itself.
"""
from __future__ import annotations

from pydantic import BaseModel


class PortfolioResponse(BaseModel):
    total_realized: float
    total_unrealized: float
    total_invested: float
    combined_total: float
    portfolio_return_pct: float

    active_grid_count: int
    paused_grid_count: int
    completed_grid_count: int
    stopped_grid_count: int

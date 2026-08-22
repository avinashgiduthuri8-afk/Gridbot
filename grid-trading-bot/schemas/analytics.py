"""Response models for GET /analytics.

Field names mirror replay.report.TradingSummary exactly, since the
analytics endpoint reuses that dataclass's computation (win rate, profit
factor, drawdown, etc.) rather than re-deriving the same math.
"""
from __future__ import annotations

from pydantic import BaseModel


class AnalyticsResponse(BaseModel):
    total_buys: int
    total_sells: int
    total_dust_writeoffs: int
    total_realized_profit: float
    win_rate_pct: float
    max_drawdown_pct: float
    profit_factor: float | None = None
    completed_cycles: int

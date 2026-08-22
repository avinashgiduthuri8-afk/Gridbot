"""GET /analytics — win rate, profit factor, drawdown, and other trading
analytics, reused from replay.report.build_trading_summary rather than
re-derived here."""
from __future__ import annotations

from fastapi import APIRouter, Depends

from dashboard.deps import get_repos
from schemas.analytics import AnalyticsResponse
from services import dashboard_service
from storage.repositories import Repositories

router = APIRouter(tags=["analytics"])


@router.get("/analytics", response_model=AnalyticsResponse, summary="Trading analytics")
async def get_analytics(repos: Repositories = Depends(get_repos)) -> AnalyticsResponse:
    summary = await dashboard_service.get_analytics(repos)
    return AnalyticsResponse(
        total_buys=summary.total_buys,
        total_sells=summary.total_sells,
        total_dust_writeoffs=summary.total_dust_writeoffs,
        total_realized_profit=summary.total_realized_profit,
        win_rate_pct=summary.win_rate_pct,
        max_drawdown_pct=summary.max_drawdown_pct,
        profit_factor=summary.profit_factor,
        completed_cycles=summary.completed_cycles,
    )

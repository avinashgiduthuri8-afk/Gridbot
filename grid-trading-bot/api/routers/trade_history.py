"""GET /trade-history — every recorded trade, optionally filtered by grid_id."""
from __future__ import annotations

from fastapi import APIRouter, Depends, Query

from dashboard.deps import get_repos
from schemas.trade_history import TradeHistoryResponse, TradeResponse
from services import dashboard_service
from storage.repositories import Repositories

router = APIRouter(tags=["trade-history"])


@router.get("/trade-history", response_model=TradeHistoryResponse, summary="List trade history")
async def list_trade_history(
    grid_id: str | None = Query(default=None, description="Filter to one grid's trades"),
    limit: int = Query(default=200, ge=1, le=1000),
    repos: Repositories = Depends(get_repos),
) -> TradeHistoryResponse:
    trades = await dashboard_service.list_trade_history(repos, grid_id=grid_id, limit=limit)
    return TradeHistoryResponse(trades=[TradeResponse(**t) for t in trades], count=len(trades))

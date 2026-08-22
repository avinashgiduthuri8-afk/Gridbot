"""GET /portfolio — aggregate portfolio totals across every grid."""
from __future__ import annotations

from fastapi import APIRouter, Depends, Query

from dashboard.deps import get_repos, parse_price_overrides
from schemas.portfolio import PortfolioResponse
from services import dashboard_service
from storage.repositories import Repositories

router = APIRouter(tags=["portfolio"])


@router.get(
    "/portfolio", response_model=PortfolioResponse, summary="Portfolio totals",
    description=(
        "Aggregate realized/unrealized/combined P&L and grid counts by "
        "status, via trading.portfolio_metrics.portfolio_totals(). Like "
        "/positions, unrealized P&L is 0.0 unless prices are supplied."
    ),
)
async def get_portfolio(
    prices: str | None = Query(default=None, description="Optional 'SYMBOL:price,...' override"),
    repos: Repositories = Depends(get_repos),
) -> PortfolioResponse:
    price_map = parse_price_overrides(prices)
    result = await dashboard_service.get_portfolio(repos, price_map)
    return PortfolioResponse(**result)

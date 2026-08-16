"""GET /positions — every open (ACTIVE/PAUSED, nonzero-quantity) grid."""
from __future__ import annotations

from fastapi import APIRouter, Depends, Query

from dashboard.deps import get_repos, parse_price_overrides
from schemas.positions import PositionListResponse, PositionResponse
from services import dashboard_service
from storage.repositories import Repositories

router = APIRouter(tags=["positions"])


    "/positions", response_model=PositionListResponse, summary="List open positions",
    description=(
        "Every ACTIVE/PAUSED grid. "
        "This read-only phase has no live price feed, so unrealized P&L "
        "is 0.0 unless a price is supplied via the optional `prices` query "
        "parameter, e.g. ?prices=BTCINR:5000000,ETHINR:280000."
    ),
)
async def list_positions(
    prices: str | None = Query(default=None, description="Optional 'SYMBOL:price,...' override"),
    repos: Repositories = Depends(get_repos),
) -> PositionListResponse:
    price_map = parse_price_overrides(prices)
    positions = await dashboard_service.list_positions(repos, price_map)
    return PositionListResponse(
        positions=[PositionResponse(**p) for p in positions], count=len(positions),
    )

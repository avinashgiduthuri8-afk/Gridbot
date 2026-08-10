"""GET /orders — every order, optionally filtered by grid_id."""
from __future__ import annotations

from fastapi import APIRouter, Depends, Query

from dashboard.deps import get_repos
from schemas.orders import OrderListResponse, OrderResponse
from services import dashboard_service
from storage.repositories import Repositories

router = APIRouter(tags=["orders"])


@router.get("/orders", response_model=OrderListResponse, summary="List orders")
async def list_orders(
    grid_id: str | None = Query(default=None, description="Filter to one grid's orders"),
    limit: int = Query(default=200, ge=1, le=1000, description="Max rows when grid_id is not given"),
    repos: Repositories = Depends(get_repos),
) -> OrderListResponse:
    orders = await dashboard_service.list_orders(repos, grid_id=grid_id, limit=limit)
    return OrderListResponse(orders=[OrderResponse(**o) for o in orders], count=len(orders))

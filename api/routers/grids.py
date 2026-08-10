"""GET /grids — list every grid, and GET /grids/{grid_id} for one."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status

from dashboard.deps import get_repos
from schemas.grids import GridListResponse, GridResponse
from services import dashboard_service
from storage.repositories import Repositories

router = APIRouter(tags=["grids"])


@router.get("/grids", response_model=GridListResponse, summary="List every grid")
async def list_grids(repos: Repositories = Depends(get_repos)) -> GridListResponse:
    grids = await dashboard_service.list_grids(repos)
    return GridListResponse(grids=[GridResponse(**g) for g in grids], count=len(grids))


@router.get(
    "/grids/{grid_id}", response_model=GridResponse, summary="Get one grid by ID",
    responses={404: {"description": "Grid not found"}},
)
async def get_grid(grid_id: str, repos: Repositories = Depends(get_repos)) -> GridResponse:
    grid = await dashboard_service.get_grid(repos, grid_id)
    if grid is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Grid {grid_id!r} not found")
    return GridResponse(**grid)

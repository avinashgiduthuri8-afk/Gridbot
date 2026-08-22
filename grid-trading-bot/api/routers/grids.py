"""Endpoints for /grids: listing, details, creation, manual orders, and actions."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status

from dashboard.deps import get_dca_manager, get_repos
from schemas.grids import (
    CreateGridRequest,
    CreateGridResponse,
    GridActionResponse,
    GridListResponse,
    GridResponse,
    ManualBuyRequest,
    ManualSellRequest,
    ManualTradeResponse,
)
from services import dashboard_service
from storage.repositories import Repositories
from utils.logger import get_logger

log = get_logger("trading")

router = APIRouter(tags=["grids"])


@router.get("/grids", response_model=GridListResponse, summary="List every grid")
async def list_grids(repos: Repositories = Depends(get_repos)) -> GridListResponse:
    grids = await dashboard_service.list_grids(repos)
    return GridListResponse(grids=[GridResponse(**g) for g in grids], count=len(grids))


@router.get(
    "/grids/{grid_id}",
    response_model=GridResponse,
    summary="Get one grid by ID",
    responses={404: {"description": "Grid not found"}},
)
async def get_grid(grid_id: str, repos: Repositories = Depends(get_repos)) -> GridResponse:
    grid = await dashboard_service.get_grid(repos, grid_id)
    if grid is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Grid {grid_id!r} not found")
    return GridResponse(**grid)


@router.post("/grids", response_model=CreateGridResponse, summary="Create and start a new DCA grid")
async def create_grid(
    request: CreateGridRequest,
    dca_manager=Depends(get_dca_manager),
) -> CreateGridResponse:
    mode = (request.mode or "paper").strip().lower()
    if mode not in ("paper", "real"):
        mode = "paper"

    params = {
        "symbol": request.symbol.strip().upper(),
        "entry_price": float(request.entry_price),
        "base_investment": float(request.base_investment),
        "dip_buy_amount": float(request.dip_buy_amount),
        "dip_percentage": float(request.dip_percentage),
        "profit_sell_amount": float(request.profit_sell_amount),
        "profit_percentage": float(request.profit_percentage),
        "max_levels": int(request.max_levels),
        "stop_loss_percentage": float(request.stop_loss_percentage),
        "mode": mode,
        "trailing_enabled": bool(request.trailing_enabled),
        "trailing_percentage": float(request.trailing_percentage) if request.trailing_percentage else None,
    }

    try:
        grid_id = await dca_manager.start_grid(params)
        return CreateGridResponse(
            grid_id=grid_id,
            symbol=params["symbol"],
            mode=mode,
            status="active",
            message=f"Grid {grid_id} created and started in {mode.upper()} mode.",
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc
    except Exception as exc:
        log.exception("Failed to start grid")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to start grid: {exc}",
        ) from exc


@router.post("/grids/{grid_id}/manual-buy", response_model=ManualTradeResponse, summary="Manual Buy on active grid")
async def manual_buy(
    grid_id: str,
    body: ManualBuyRequest,
    dca_manager=Depends(get_dca_manager),
    repos: Repositories = Depends(get_repos),
) -> ManualTradeResponse:
    if body.inr_amount <= 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="inr_amount must be greater than zero.",
        )

    grid = await repos.grids.get(grid_id)
    if not grid:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Grid {grid_id} not found.")

    try:
        order = await dca_manager.manual_buy(grid_id, body.inr_amount)
        return ManualTradeResponse(
            success=True,
            grid_id=grid_id,
            symbol=grid["symbol"],
            side="buy",
            quantity=order.quantity,
            price=order.price,
            inr_amount=body.inr_amount,
            mode=grid.get("mode", "real"),
            order_id=order.order_id,
            message=f"Manual buy order placed: {order.order_id}",
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc
    except Exception as exc:
        log.exception("Manual buy failed")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Manual buy failed: {exc}",
        ) from exc


@router.post("/grids/{grid_id}/manual-sell", response_model=ManualTradeResponse, summary="Manual Sell on active grid")
async def manual_sell(
    grid_id: str,
    body: ManualSellRequest | None = None,
    dca_manager=Depends(get_dca_manager),
    repos: Repositories = Depends(get_repos),
) -> ManualTradeResponse:
    inr_amount = body.inr_amount if body else None
    if inr_amount is not None and inr_amount <= 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="inr_amount must be greater than zero if specified.",
        )

    grid = await repos.grids.get(grid_id)
    if not grid:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Grid {grid_id} not found.")

    try:
        result = await dca_manager.manual_sell(grid_id, inr_amount)
        qty = result.order.quantity if result.order else 0.0
        price = result.order.price if result.order else 0.0
        order_id = result.order.order_id if result.order else None
        return ManualTradeResponse(
            success=True,
            grid_id=grid_id,
            symbol=grid["symbol"],
            side="sell",
            quantity=qty,
            price=price,
            inr_amount=inr_amount or 0.0,
            mode=grid.get("mode", "real"),
            order_id=order_id,
            message=result.message,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc
    except Exception as exc:
        log.exception("Manual sell failed")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Manual sell failed: {exc}",
        ) from exc


@router.post("/grids/{grid_id}/pause", response_model=GridActionResponse, summary="Pause an active grid")
async def pause_grid(
    grid_id: str,
    dca_manager=Depends(get_dca_manager),
    repos: Repositories = Depends(get_repos),
) -> GridActionResponse:
    grid = await repos.grids.get(grid_id)
    if not grid:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Grid {grid_id} not found.")
    try:
        await dca_manager.pause_grid(grid_id)
        return GridActionResponse(
            success=True,
            grid_id=grid_id,
            action="pause",
            message=f"Grid {grid_id} paused.",
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


@router.post("/grids/{grid_id}/resume", response_model=GridActionResponse, summary="Resume a paused grid")
async def resume_grid(
    grid_id: str,
    dca_manager=Depends(get_dca_manager),
    repos: Repositories = Depends(get_repos),
) -> GridActionResponse:
    grid = await repos.grids.get(grid_id)
    if not grid:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Grid {grid_id} not found.")
    try:
        await dca_manager.resume_grid(grid_id)
        return GridActionResponse(
            success=True,
            grid_id=grid_id,
            action="resume",
            message=f"Grid {grid_id} resumed.",
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


@router.post("/grids/{grid_id}/stop", response_model=GridActionResponse, summary="Stop and close a grid")
async def stop_grid(
    grid_id: str,
    dca_manager=Depends(get_dca_manager),
    repos: Repositories = Depends(get_repos),
) -> GridActionResponse:
    grid = await repos.grids.get(grid_id)
    if not grid:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Grid {grid_id} not found.")
    try:
        await dca_manager.stop_grid(grid_id, reason="manual_dashboard")
        return GridActionResponse(
            success=True,
            grid_id=grid_id,
            action="stop",
            message=f"Grid {grid_id} stopped.",
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

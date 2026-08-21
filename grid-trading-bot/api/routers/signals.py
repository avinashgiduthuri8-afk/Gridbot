"""FastAPI router for Stored Signals History, Detail Modals, and Performance Analytics."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Query, Request

from storage.repositories import Repositories

router = APIRouter(prefix="/signals", tags=["Signals History"])


@router.get("")
async def list_signals(
    request: Request,
    limit: int = Query(50, ge=1, le=200),
    status: str | None = None,
    min_score: float | None = None,
) -> list[dict[str, Any]]:
    """Returns stored historical signals with optional filtering by status and minimum score."""
    repos: Repositories = getattr(request.app.state, "repos", None)
    if not repos or not hasattr(repos, "signals"):
        return []
    return await repos.signals.list_signals(limit=limit, status=status, min_score=min_score)


@router.get("/performance")
async def get_performance_stats(request: Request) -> dict[str, Any]:
    """Returns aggregate performance analytics: win rate %, profit factor, average R:R, and MFE/MAE."""
    repos: Repositories = getattr(request.app.state, "repos", None)
    if not repos or not hasattr(repos, "signals"):
        return {
            "total_signals": 0,
            "win_rate_pct": 0.0,
            "avg_rr": 0.0,
            "avg_mfe": 0.0,
            "avg_mae": 0.0,
            "avg_return_pct": 0.0,
        }
    return await repos.signals.get_performance_summary()


@router.get("/{signal_id}")
async def get_signal_detail(request: Request, signal_id: str) -> dict[str, Any]:
    """Retrieves complete scoring breakdown and rationale for a specific signal."""
    repos: Repositories = getattr(request.app.state, "repos", None)
    if not repos or not hasattr(repos, "signals"):
        raise HTTPException(status_code=404, detail="Signal repository unavailable")

    sig = await repos.signals.get_signal(signal_id)
    if not sig:
        raise HTTPException(status_code=404, detail=f"Signal {signal_id} not found")
    return sig

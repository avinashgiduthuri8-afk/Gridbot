"""Live Signal Lifecycle & Performance Ledger REST API Routers.

Endpoints:
- GET /ledger/stats: Overall win rate, total R-multiples, profit factor, setup breakdown
- GET /ledger/active: Currently active unresolved signals
- POST /ledger/evaluate: Checks market prices against active signals and triggers state transitions
"""

from __future__ import annotations

from typing import Any
from fastapi import APIRouter, Depends, Body

from dashboard.deps import get_repos
from storage.repositories import Repositories
from utils.logger import get_logger

log = get_logger("signal_repo")

router = APIRouter(tags=["ledger"])


@router.get("/ledger/stats", summary="Performance Ledger & R-Multiple Statistics")
async def get_ledger_stats(repos: Repositories = Depends(get_repos)) -> dict[str, Any]:
    """Calculates overall win rate, total R generated, profit factor, and breakdown by setup."""
    stats = await repos.ledger.get_ledger_stats()
    return stats.to_dict()


@router.get("/ledger/active", summary="List Active Unresolved Signals")
async def get_active_signals(repos: Repositories = Depends(get_repos)) -> list[dict[str, Any]]:
    """Retrieves all currently active signals tracked by the ledger."""
    return await repos.ledger.get_active_signals()


@router.post("/ledger/evaluate", summary="Evaluate Active Signals Against Quotes")
async def evaluate_active_signals(
    quotes: dict[str, float] = Body(..., description="Map of symbol to current market price"),
    repos: Repositories = Depends(get_repos),
) -> dict[str, Any]:
    """Updates lifecycle states (HIT_T1, HIT_T2, STOPPED_OUT) for active signals."""
    resolved = await repos.ledger.evaluate_active_signals(quotes)
    return {
        "resolved_count": len(resolved),
        "resolved_signals": resolved,
    }

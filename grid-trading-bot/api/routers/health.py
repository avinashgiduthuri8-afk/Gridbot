"""GET /health — basic liveness/readiness check."""
from __future__ import annotations

from fastapi import APIRouter, Depends

from dashboard.deps import get_repos
from schemas.health import HealthResponse
from storage.repositories import Repositories

router = APIRouter(tags=["health"])


@router.get("/health", response_model=HealthResponse, summary="Health check")
async def health_check(repos: Repositories = Depends(get_repos)) -> HealthResponse:
    database_connected = False
    try:
        await repos.db.connection.execute("SELECT 1;")
        database_connected = True
    except Exception:  # noqa: BLE001 — a failed health check must report False, not raise
        database_connected = False
    return HealthResponse(status="ok" if database_connected else "degraded", database_connected=database_connected)

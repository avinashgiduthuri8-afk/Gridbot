"""GET /health — basic liveness/readiness check."""
from __future__ import annotations

from fastapi import APIRouter, Request

from schemas.health import HealthResponse

router = APIRouter(tags=["health"])


@router.get("/health", response_model=HealthResponse, summary="Health check")
async def health_check(request: Request) -> HealthResponse:
    database_connected = False
    repos = getattr(request.app.state, "repos", None)
    if repos is not None:
        try:
            await repos.db.connection.execute("SELECT 1;")
            database_connected = True
        except Exception:  # noqa: BLE001 — a failed health check must report False, not raise
            database_connected = False
    return HealthResponse(status="ok" if database_connected else "degraded", database_connected=database_connected)

"""Shared FastAPI dependencies for Indian Stock Scanner."""

from __future__ import annotations

from fastapi import HTTPException, Request, status

from services.scanner_service import ScannerService
from storage.repositories import Repositories


async def get_repos(request: Request) -> Repositories:
    repos = getattr(request.app.state, "repos", None)
    if repos is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Database unavailable or unmigrated",
        )
    return repos


async def get_scanner_service(request: Request) -> ScannerService:
    svc = getattr(request.app.state, "scanner_service", None)
    if svc is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Indian Stock Scanner service is unavailable",
        )
    return svc


async def get_app_settings(request: Request):
    if hasattr(request.app.state, "dashboard_settings") and request.app.state.dashboard_settings is not None:
        return request.app.state.dashboard_settings
    return getattr(request.app.state, "settings", None)

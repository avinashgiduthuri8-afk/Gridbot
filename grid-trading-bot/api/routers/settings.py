"""GET /settings — operational/risk configuration only; never a secret."""
from __future__ import annotations

from fastapi import APIRouter, Depends

from config.settings import Settings
from dashboard.deps import get_app_settings, get_repos
from schemas.settings import RiskSettingsResponse, SettingsResponse
from services import dashboard_service
from storage.repositories import Repositories

router = APIRouter(tags=["settings"])


@router.get("/settings", response_model=SettingsResponse, summary="Operational settings")
async def get_settings(
    repos: Repositories = Depends(get_repos),
    app_settings: Settings = Depends(get_app_settings),
) -> SettingsResponse:
    result = await dashboard_service.get_settings(repos, app_settings)
    return SettingsResponse(
        risk=RiskSettingsResponse(**result["risk"]),
        order_poll_interval_seconds=result["order_poll_interval_seconds"],
        price_poll_interval_seconds=result["price_poll_interval_seconds"],
        daily_summary_interval_seconds=result["daily_summary_interval_seconds"],
        monitor_interval_seconds=result["monitor_interval_seconds"],
        emergency_stop_active=result["emergency_stop_active"],
        backup_enabled=result["backup_enabled"],
        webhook_enabled=result["webhook_enabled"],
        grid_defaults=result["grid_defaults"],
    )

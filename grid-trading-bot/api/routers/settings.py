"""GET /settings and POST /emergency-stop."""
from __future__ import annotations

from fastapi import APIRouter, Depends

from dashboard.deps import get_app_settings, get_repos, get_risk_manager
from schemas.settings import (
    EmergencyStopRequest,
    EmergencyStopResponse,
    RiskSettingsResponse,
    SettingsResponse,
)
from services import dashboard_service
from storage.repositories import Repositories

router = APIRouter(tags=["settings"])


@router.get("/settings", response_model=SettingsResponse, summary="Operational settings")
async def get_settings(
    repos: Repositories = Depends(get_repos),
    app_settings=Depends(get_app_settings),
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


@router.post("/emergency-stop", response_model=EmergencyStopResponse, summary="Toggle Emergency Stop")
async def toggle_emergency_stop(
    body: EmergencyStopRequest,
    risk_manager=Depends(get_risk_manager),
) -> EmergencyStopResponse:
    if body.enabled:
        await risk_manager.trigger_emergency_stop()
        msg = "Emergency Stop ACTIVATED. All new trading actions are blocked."
    else:
        await risk_manager.clear_emergency_stop()
        msg = "Emergency Stop CLEARED. Trading actions re-enabled."

    return EmergencyStopResponse(
        emergency_stop=risk_manager.emergency_stopped,
        message=msg,
    )

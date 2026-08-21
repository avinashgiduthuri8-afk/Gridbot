"""FastAPI router for Market Regime & India VIX Volatility analytics."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Request

from services.scanner_service import ScannerService

router = APIRouter(prefix="/regime", tags=["Market Regime"])


@router.get("")
async def get_market_regime(request: Request) -> dict[str, Any]:
    """Returns current market regime, NIFTY 50 / Bank NIFTY status, and India VIX."""
    scanner_svc: ScannerService = getattr(request.app.state, "scanner_service", None)
    if not scanner_svc:
        scanner_svc = ScannerService()
        request.app.state.scanner_service = scanner_svc

    regime = await scanner_svc.get_market_regime()
    return {
        "regime": regime.regime.value,
        "nifty_50_change": round(regime.nifty_50_change, 2),
        "nifty_bank_change": round(regime.nifty_bank_change, 2),
        "vix_value": round(regime.vix_value, 2),
        "vix_change": round(regime.vix_change, 2),
        "vix_status": regime.vix_status,
        "nifty_trend": regime.nifty_trend,
        "bank_trend": regime.bank_trend,
        "regime_score": regime.regime_score,
        "long_confidence_multiplier": regime.long_confidence_multiplier,
        "summary": regime.summary,
    }

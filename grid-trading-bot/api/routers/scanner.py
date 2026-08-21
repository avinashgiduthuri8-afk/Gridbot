"""FastAPI router for Indian Stock Scanner execution and session status."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Query, Request
from pydantic import BaseModel

from engine.session.session_manager import IndianSessionManager
from services.scanner_service import ScannerService

router = APIRouter(prefix="/scanner", tags=["Scanner"])


class ScanRequest(BaseModel):
    universe: str = "NIFTY_100"
    max_signals: int = 3


def _format_signal(sig: Any) -> dict[str, Any]:
    return {
        "symbol": sig.symbol,
        "signal_type": sig.signal_type.value if hasattr(sig.signal_type, "value") else str(sig.signal_type),
        "strength": sig.strength.value if hasattr(sig.strength, "value") else str(sig.strength),
        "total_score": sig.total_score,
        "breakdown": sig.breakdown.to_dict() if hasattr(sig.breakdown, "to_dict") else sig.breakdown,
        "risk_reward": {
            "entry_price": sig.risk_reward.entry_price,
            "stop_loss": sig.risk_reward.stop_loss,
            "target_1": sig.risk_reward.target_1,
            "target_2": sig.risk_reward.target_2,
            "risk_amount": sig.risk_reward.risk_amount,
            "reward_amount": sig.risk_reward.reward_amount,
            "risk_percentage": sig.risk_reward.risk_percentage,
            "reward_percentage": sig.risk_reward.reward_percentage,
            "rr_ratio": sig.risk_reward.rr_ratio,
            "is_acceptable": sig.risk_reward.is_acceptable,
            "rejection_reason": sig.risk_reward.rejection_reason,
        },
        "sector": sig.sector,
        "sector_rank": sig.sector_rank,
        "market_regime": sig.market_regime,
        "timeframes_summary": sig.timeframes_summary,
        "rationale": sig.rationale,
        "timestamp": sig.timestamp,
        "is_tradable": sig.is_tradable,
    }


@router.post("/scan")
async def run_scan(request: Request, body: ScanRequest) -> dict[str, Any]:
    """Triggers an on-demand multi-timeframe scan of the selected Indian stock universe."""
    scanner_svc: ScannerService = getattr(request.app.state, "scanner_service", None)
    if not scanner_svc:
        scanner_svc = ScannerService()
        request.app.state.scanner_service = scanner_svc

    repos = getattr(request.app.state, "repos", None)
    result = await scanner_svc.execute_scan(universe=body.universe, max_signals=body.max_signals, repos=repos)

    return {
        "timestamp": result.timestamp,
        "session_info": result.session_info,
        "regime": {
            "regime": result.regime.regime.value,
            "nifty_50_change": round(result.regime.nifty_50_change, 2),
            "nifty_bank_change": round(result.regime.nifty_bank_change, 2),
            "vix_value": round(result.regime.vix_value, 2),
            "vix_status": result.regime.vix_status,
            "summary": result.regime.summary,
        },
        "total_scanned": result.total_scanned,
        "total_passed_liquidity": result.total_passed_liquidity,
        "top_signals": [_format_signal(s) for s in result.top_signals],
        "watchlist": [_format_signal(s) for s in result.watchlist],
        "scan_duration_seconds": result.scan_duration_seconds,
    }


@router.get("/latest")
async def get_latest_scan(request: Request) -> dict[str, Any] | None:
    """Returns the most recent cached scan result."""
    scanner_svc: ScannerService = getattr(request.app.state, "scanner_service", None)
    if not scanner_svc:
        return {"status": "no_scans_yet", "top_signals": [], "watchlist": []}

    result = scanner_svc.get_latest_scan_result()
    if not result:
        return {"status": "no_scans_yet", "top_signals": [], "watchlist": []}

    return {
        "timestamp": result.timestamp,
        "session_info": result.session_info,
        "regime": {
            "regime": result.regime.regime.value,
            "nifty_50_change": round(result.regime.nifty_50_change, 2),
            "nifty_bank_change": round(result.regime.nifty_bank_change, 2),
            "vix_value": round(result.regime.vix_value, 2),
            "vix_status": result.regime.vix_status,
            "summary": result.regime.summary,
        },
        "total_scanned": result.total_scanned,
        "total_passed_liquidity": result.total_passed_liquidity,
        "top_signals": [_format_signal(s) for s in result.top_signals],
        "watchlist": [_format_signal(s) for s in result.watchlist],
        "scan_duration_seconds": result.scan_duration_seconds,
    }


@router.get("/session")
async def get_session_status() -> dict[str, Any]:
    """Returns current IST market session status, holiday information, and trading clock."""
    return IndianSessionManager.get_session_info()

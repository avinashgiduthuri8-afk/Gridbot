"""FastAPI router for Sector Strength & Heatmap Matrix."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Request

from services.scanner_service import ScannerService

router = APIRouter(prefix="/sectors", tags=["Sector Strength"])


@router.get("")
async def get_sector_matrix(request: Request) -> dict[str, Any]:
    """Returns sector performance rankings, relative strength vs NIFTY, and momentum status."""
    scanner_svc: ScannerService = getattr(request.app.state, "scanner_service", None)
    if not scanner_svc:
        scanner_svc = ScannerService()
        request.app.state.scanner_service = scanner_svc

    matrix = await scanner_svc.get_sector_matrix()
    sectors_list = []
    for s in matrix.sectors.values():
        sectors_list.append({
            "sector": s.sector,
            "index_symbol": s.index_symbol,
            "change_pct_1d": round(s.change_pct_1d, 2),
            "change_pct_5d": round(s.change_pct_5d, 2),
            "change_pct_20d": round(s.change_pct_20d, 2),
            "relative_strength": round(s.relative_strength, 2),
            "momentum_rank": s.momentum_rank,
            "status": s.status,
        })

    sectors_list.sort(key=lambda x: x["relative_strength"], reverse=True)

    return {
        "leading_sectors": matrix.leading_sectors,
        "improving_sectors": matrix.improving_sectors,
        "lagging_sectors": matrix.lagging_sectors,
        "sectors": sectors_list,
    }

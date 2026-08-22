"""Shared FastAPI dependencies.

Every endpoint depends on get_repos(), get_dca_manager(), or get_risk_manager()
rather than constructing its own Database/Repositories.
"""
from __future__ import annotations

from fastapi import Request, HTTPException, status

from storage.repositories import Repositories


async def get_repos(request: Request) -> Repositories:
    repos = getattr(request.app.state, "repos", None)
    if repos is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Database unavailable or unmigrated",
        )
    return repos


async def get_dca_manager(request: Request):
    dca_manager = getattr(request.app.state, "dca_manager", None)
    if dca_manager is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Trading engine / DCA manager is unavailable",
        )
    return dca_manager


async def get_risk_manager(request: Request):
    risk_manager = getattr(request.app.state, "risk_manager", None)
    if risk_manager is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Risk manager is unavailable",
        )
    return risk_manager


async def get_app_settings(request: Request):
    if hasattr(request.app.state, "dashboard_settings") and request.app.state.dashboard_settings is not None:
        return request.app.state.dashboard_settings
    return getattr(request.app.state, "settings", None)


def parse_price_overrides(prices: str | None) -> dict[str, float]:
    """Parses an optional 'SYMBOL:price,SYMBOL:price' query param into a dict."""
    if not prices:
        return {}
    result: dict[str, float] = {}
    for pair in prices.split(","):
        pair = pair.strip()
        if not pair or ":" not in pair:
            continue
        symbol, _, value = pair.partition(":")
        try:
            result[symbol.strip().upper()] = float(value.strip())
        except ValueError:
            continue
    return result

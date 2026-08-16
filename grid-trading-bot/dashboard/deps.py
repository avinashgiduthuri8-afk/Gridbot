"""Shared FastAPI dependencies.

Every endpoint depends on get_repos() (and, where needed, get_app_settings())
rather than constructing its own Database/Repositories — both are created
exactly once, at application startup (see dashboard/app.py's lifespan),
and reused for the lifetime of the process. This is the "shared
application context" the dashboard uses instead of opening a new database
connection per request.
"""
from __future__ import annotations

from fastapi import Request, HTTPException, status

from config.settings import Settings
from storage.repositories import Repositories


async def get_repos(request: Request) -> Repositories:
    if not hasattr(request.app.state, "repos") or request.app.state.repos is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Database unavailable or unmigrated"
        )
    return request.app.state.repos


async def get_app_settings(request: Request) -> Settings:
    return request.app.state.settings


def parse_price_overrides(prices: str | None) -> dict[str, float]:
    """Parses an optional "SYMBOL:price,SYMBOL:price" query param into a
    dict, used by both /positions and /portfolio. This phase has no live
    price feed (PriceMonitor integration is out of scope), so unrealized
    P&L is 0.0 / current_price is null for any symbol not explicitly
    supplied here — never a fabricated number."""
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
            continue  # silently skip a malformed entry rather than fail the whole request
    return result

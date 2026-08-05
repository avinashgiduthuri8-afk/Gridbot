"""Dashboard service layer.

Every function here does exactly one thing: call into the existing
repository layer (storage.repositories) and/or existing calculation
functions (trading.portfolio_metrics, replay.report.build_trading_summary),
then shape the result for the API routers. No P&L, ROI, portfolio-total,
or status calculation is implemented here — everything is delegated to
code that already existed before this dashboard, so there is exactly one
place in the codebase that computes each of those numbers.

This module has no FastAPI import and no HTTP-specific concerns (status
codes, path/query parameters) — those live in api/routers/*.py. Kept
separate so this logic is testable and reusable independent of the web
framework, matching how trading/portfolio_metrics.py was split out from
bot_telegram/formatters.py for the same reason.
"""
from __future__ import annotations

from config.settings import Settings
from storage.repositories import Repositories
from trading.portfolio_metrics import grid_pnl_breakdown, portfolio_totals


async def list_grids(repos: Repositories) -> list[dict]:
    return await repos.grids.list_all()


async def get_grid(repos: Repositories, grid_id: str) -> dict | None:
    return await repos.grids.get(grid_id)


async def list_positions(repos: Repositories, prices: dict[str, float] | None = None) -> list[dict]:
    """Every ACTIVE/PAUSED grid holding a nonzero quantity, enriched with a
    P&L breakdown via trading.portfolio_metrics.grid_pnl_breakdown().

    prices, if given, maps symbol -> current price; a symbol with no entry
    (the normal case in this read-only phase, which does not integrate a
    live price feed) yields unrealized_pnl=0.0 and current_price=None,
    exactly as grid_pnl_breakdown() already documents — never a fabricated
    number.
    """
    prices = prices or {}
    all_grids = await repos.grids.list_all()
    positions = []
    for grid in all_grids:
        if grid["status"] not in ("active", "paused"):
            continue
        if grid["total_quantity"] <= 0:
            continue
        price = prices.get(grid["symbol"])
        breakdown = grid_pnl_breakdown(grid, price)
        positions.append({
            "grid_id": grid["grid_id"],
            "symbol": grid["symbol"],
            "status": grid["status"],
            "mode": grid["mode"],
            "quantity": grid["total_quantity"],
            "average_entry_price": grid["average_entry_price"],
            "invested": breakdown["invested"],
            "current_price": price,
            "realized_pnl": breakdown["realized"],
            "unrealized_pnl": breakdown["unrealized"],
            "combined_pnl": breakdown["combined"],
            "current_level": grid["current_level"],
            "max_levels": grid["max_levels"],
            "trailing_enabled": grid["trailing_enabled"],
            "trailing_peak_price": grid["trailing_peak_price"],
        })
    return positions


async def list_orders(repos: Repositories, grid_id: str | None = None, limit: int = 200) -> list[dict]:
    if grid_id is not None:
        return await repos.orders.list_for_grid(grid_id)
    return await repos.orders.list_all(limit=limit)


async def list_trade_history(
    repos: Repositories, grid_id: str | None = None, limit: int = 200,
) -> list[dict]:
    if grid_id is not None:
        return await repos.trade_history.list_for_grid(grid_id, limit=limit)
    return await repos.trade_history.list_all(limit=limit)


async def get_portfolio(repos: Repositories, prices: dict[str, float] | None = None) -> dict:
    """Portfolio totals (trading.portfolio_metrics.portfolio_totals) plus a
    grid-count-by-status breakdown, over every grid regardless of mode."""
    prices = prices or {}
    all_grids = await repos.grids.list_all()
    totals = portfolio_totals(all_grids, prices)

    counts = {"active": 0, "paused": 0, "completed": 0, "stopped": 0}
    for grid in all_grids:
        status = grid["status"]
        if status in counts:
            counts[status] += 1

    return {
        **totals,
        "active_grid_count": counts["active"],
        "paused_grid_count": counts["paused"],
        "completed_grid_count": counts["completed"],
        "stopped_grid_count": counts["stopped"],
    }


async def get_analytics(repos: Repositories):
    """Returns replay.report.TradingSummary — reused as-is rather than
    reimplementing win-rate/profit-factor/drawdown math a second time."""
    from replay.report import build_trading_summary
    return await build_trading_summary(repos)


async def get_settings(repos: Repositories, settings: Settings) -> dict:
    """Operational/risk settings only — never a secret (API keys, bot
    token) or an identifying field (owner/allowed Telegram IDs)."""
    monitor_interval = await repos.monitor_settings.get_interval()
    emergency_stop = await repos.monitor_settings.get_emergency_stop()
    grid_defaults = await repos.grid_defaults.get()

    return {
        "risk": {
            "max_total_capital": settings.risk.max_total_capital,
            "max_capital_per_coin": settings.risk.max_capital_per_coin,
            "max_simultaneous_grids": settings.risk.max_simultaneous_grids,
            "min_wallet_balance": settings.risk.min_wallet_balance,
            "daily_loss_limit": settings.risk.daily_loss_limit,
        },
        "order_poll_interval_seconds": settings.order_poll_interval_seconds,
        "price_poll_interval_seconds": settings.price_poll_interval_seconds,
        "daily_summary_interval_seconds": settings.daily_summary_interval_seconds,
        "monitor_interval_seconds": monitor_interval,
        "emergency_stop_active": emergency_stop,
        "backup_enabled": settings.backup.enabled,
        "webhook_enabled": settings.webhook.enabled,
        "grid_defaults": grid_defaults,
    }

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

import os
from typing import Any

from storage.repositories import Repositories
from trading.portfolio_metrics import grid_pnl_breakdown, portfolio_totals


def _format_grid(grid: dict) -> dict:
    return {
        "grid_id": str(grid["grid_id"]),
        "symbol": str(grid["symbol"]),
        "status": str(grid["status"]),
        "mode": str(grid.get("mode") or "real"),
        "entry_price": float(grid.get("entry_price") or 0.0),
        "base_investment": float(grid.get("base_investment") or 0.0),
        "dip_buy_amount": float(grid.get("dip_buy_amount") or 0.0),
        "dip_percentage": float(grid.get("dip_percentage") or 0.0),
        "profit_sell_amount": float(grid.get("profit_sell_amount") or 0.0),
        "profit_percentage": float(grid.get("profit_percentage") or 0.0),
        "max_levels": int(grid.get("max_levels") or 0),
        "stop_loss_percentage": float(grid.get("stop_loss_percentage") or 0.0),
        "current_level": int(grid.get("current_level") or 0),
        "total_quantity": float(grid.get("total_quantity") or 0.0),
        "total_investment": float(grid.get("total_investment") or 0.0),
        "average_entry_price": float(grid.get("average_entry_price") or 0.0),
        "last_buy_price": float(grid.get("last_buy_price") or 0.0),
        "next_buy_price": float(grid.get("next_buy_price") or 0.0),
        "next_sell_price": float(grid.get("next_sell_price") or 0.0),
        "realized_profit": float(grid.get("realized_profit") or 0.0),
        "completed_cycles": int(grid.get("completed_cycles") or 0),
        "trailing_enabled": bool(grid.get("trailing_enabled")),
        "trailing_percentage": float(grid["trailing_percentage"]) if grid.get("trailing_percentage") is not None else None,
        "trailing_peak_price": float(grid["trailing_peak_price"]) if grid.get("trailing_peak_price") is not None else None,
        "created_at": str(grid.get("created_at") or ""),
        "updated_at": str(grid.get("updated_at") or ""),
    }


async def list_grids(repos: Repositories) -> list[dict]:
    grids = await repos.grids.list_all()
    return [_format_grid(g) for g in grids]


async def get_grid(repos: Repositories, grid_id: str) -> dict | None:
    grid = await repos.grids.get(grid_id)
    return _format_grid(grid) if grid else None


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
        price = prices.get(grid["symbol"])
        breakdown = grid_pnl_breakdown(grid, price)
        positions.append({
            "grid_id": grid["grid_id"],
            "symbol": grid["symbol"],
            "status": grid["status"],
            "mode": grid["mode"],
            "quantity": float(grid["total_quantity"] or 0.0),
            "average_entry_price": float(grid["average_entry_price"] or 0.0),
            "invested": float(breakdown["invested"] or 0.0),
            "current_price": price,
            "realized_pnl": float(breakdown["realized"] or 0.0),
            "unrealized_pnl": float(breakdown["unrealized"] or 0.0),
            "combined_pnl": float(breakdown["combined"] or 0.0),
            "current_level": int(grid["current_level"] or 0),
            "max_levels": int(grid["max_levels"] or 0),
            "trailing_enabled": bool(grid["trailing_enabled"]),
            "trailing_peak_price": float(grid["trailing_peak_price"]) if grid.get("trailing_peak_price") is not None else None,
        })
    return positions


def _format_order(order: dict) -> dict:
    return {
        "order_id": str(order["order_id"]),
        "grid_id": str(order["grid_id"]),
        "exchange_order_id": str(order["exchange_order_id"]) if order.get("exchange_order_id") is not None else None,
        "symbol": str(order["symbol"]),
        "side": str(order["side"]),
        "order_type": str(order["order_type"]),
        "price": float(order.get("price") or 0.0),
        "quantity": float(order.get("quantity") or 0.0),
        "filled_quantity": float(order.get("filled_quantity") or 0.0),
        "filled_price": float(order.get("filled_price") or 0.0),
        "status": str(order["status"]),
        "fee": float(order.get("fee") or 0.0),
        "reconciliation_status": str(order.get("reconciliation_status") or "not_needed"),
        "created_at": str(order.get("created_at") or ""),
        "updated_at": str(order.get("updated_at") or ""),
    }


def _format_trade(trade: dict) -> dict:
    return {
        "trade_id": str(trade["trade_id"]),
        "grid_id": str(trade["grid_id"]),
        "order_id": str(trade["order_id"]),
        "symbol": str(trade["symbol"]),
        "side": str(trade["side"]),
        "price": float(trade.get("price") or 0.0),
        "quantity": float(trade.get("quantity") or 0.0),
        "investment_inr": float(trade.get("investment_inr") or 0.0),
        "fee": float(trade.get("fee") or 0.0),
        "pnl": float(trade.get("pnl") or 0.0),
        "executed_at": str(trade.get("executed_at") or ""),
    }


async def list_orders(repos: Repositories, grid_id: str | None = None, limit: int = 200) -> list[dict]:
    if grid_id is not None:
        rows = await repos.orders.list_for_grid(grid_id)
    else:
        rows = await repos.orders.list_all(limit=limit)
    return [_format_order(r) for r in rows]


async def list_trade_history(
    repos: Repositories, grid_id: str | None = None, limit: int = 200,
) -> list[dict]:
    if grid_id is not None:
        rows = await repos.trade_history.list_for_grid(grid_id, limit=limit)
    else:
        rows = await repos.trade_history.list_all(limit=limit)
    return [_format_trade(r) for r in rows]


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
    # pyrefly: ignore [missing-import]
    from replay.report import build_trading_summary
    return await build_trading_summary(repos)


async def get_settings(repos: Repositories, settings: Any = None) -> dict:
    """Operational/risk settings only — never a secret (API keys, bot
    token) or an identifying field (owner/allowed Telegram IDs)."""
    monitor_interval = await repos.monitor_settings.get_interval()
    emergency_stop = await repos.monitor_settings.get_emergency_stop()
    grid_defaults = await repos.grid_defaults.get()

    risk_obj = getattr(settings, "risk", None)
    if risk_obj is not None:
        risk_data = {
            "max_total_capital": float(risk_obj.max_total_capital),
            "max_capital_per_coin": float(risk_obj.max_capital_per_coin),
            "max_simultaneous_grids": int(risk_obj.max_simultaneous_grids),
            "min_wallet_balance": float(risk_obj.min_wallet_balance),
            "daily_loss_limit": float(risk_obj.daily_loss_limit),
        }
    else:
        def _get_f(k: str, d: float) -> float:
            v = os.getenv(k)
            try:
                return float(v) if v and v.strip() else d
            except ValueError:
                return d

        def _get_i(k: str, d: int) -> int:
            v = os.getenv(k)
            try:
                return int(v) if v and v.strip() else d
            except ValueError:
                return d

        risk_data = {
            "max_total_capital": _get_f("MAX_TOTAL_CAPITAL", 50000.0),
            "max_capital_per_coin": _get_f("MAX_CAPITAL_PER_COIN", 20000.0),
            "max_simultaneous_grids": _get_i("MAX_SIMULTANEOUS_GRIDS", 20),
            "min_wallet_balance": _get_f("MIN_WALLET_BALANCE", 500.0),
            "daily_loss_limit": _get_f("DAILY_LOSS_LIMIT", 2000.0),
        }

    order_poll = getattr(settings, "order_poll_interval_seconds", None)
    if order_poll is None:
        try:
            order_poll = int(os.getenv("ORDER_POLL_INTERVAL_SECONDS", "8"))
        except ValueError:
            order_poll = 8

    price_poll = getattr(settings, "price_poll_interval_seconds", None)
    if price_poll is None:
        try:
            price_poll = int(os.getenv("PRICE_POLL_INTERVAL_SECONDS", "5"))
        except ValueError:
            price_poll = 5

    daily_summary = getattr(settings, "daily_summary_interval_seconds", None)
    if daily_summary is None:
        try:
            daily_summary = int(os.getenv("DAILY_SUMMARY_INTERVAL_SECONDS", "86400"))
        except ValueError:
            daily_summary = 86400

    backup_obj = getattr(settings, "backup", None)
    if backup_obj is not None:
        backup_enabled = bool(backup_obj.enabled)
    else:
        backup_enabled = os.getenv("GDRIVE_BACKUP_ENABLED", "").strip().lower() in ("1", "true", "yes", "on")

    webhook_obj = getattr(settings, "webhook", None)
    if webhook_obj is not None:
        webhook_enabled = bool(webhook_obj.enabled)
    else:
        webhook_enabled = os.getenv("WEBHOOK_ENABLED", "").strip().lower() in ("1", "true", "yes", "on")

    return {
        "risk": risk_data,
        "order_poll_interval_seconds": order_poll,
        "price_poll_interval_seconds": price_poll,
        "daily_summary_interval_seconds": daily_summary,
        "monitor_interval_seconds": monitor_interval,
        "emergency_stop_active": emergency_stop,
        "backup_enabled": backup_enabled,
        "webhook_enabled": webhook_enabled,
        "grid_defaults": grid_defaults,
    }

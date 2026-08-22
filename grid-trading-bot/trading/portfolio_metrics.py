"""Pure, framework-agnostic P&L and portfolio calculations.

Extracted from bot_telegram/formatters.py, where this math was previously
computed inline as part of building Telegram-formatted strings. These
functions take and return plain numbers/dicts — no Telegram markup, no
rendering — so both the Telegram bot and a future dashboard API can call
the exact same calculation instead of one of them re-deriving it (or
worse, reverse-parsing it out of formatted display text).

Every function here reproduces, unchanged, a formula that previously
existed inline in formatters.py — this module is a relocation, not a
behavior change.
"""
from __future__ import annotations


def pnl_pct(pnl: float, invested: float) -> float:
    """P&L as a percentage of invested capital. 0.0 if nothing was invested
    (avoids a division by zero for a grid that hasn't bought anything yet)."""
    if invested <= 0:
        return 0.0
    return (pnl / invested) * 100


def unrealized_pnl(current_price: float, avg_entry_price: float, quantity: float) -> float:
    """Unrealized P&L on a still-held position: (current - avg entry) * qty."""
    return (current_price - avg_entry_price) * quantity


def bot_position_by_currency(grids: list[dict]) -> dict[str, tuple[float, float]]:
    """Aggregates bot-managed (active/paused) positions by base currency.

    Returns {currency: (total_quantity, weighted_cost_sum)} — weighted_cost_sum
    is sum(avg_entry_price * quantity) across every active/paused INR-quoted
    grid for that currency, so callers can derive a blended average entry
    price via weighted_cost_sum / total_quantity.

    Deliberately scoped to bot-managed grid positions only, not a wallet's
    total holdings — a wallet may contain coins bought outside the bot, and
    mixing those into this average would misrepresent the bot's own P&L.
    """
    result: dict[str, tuple[float, float]] = {}
    for g in grids:
        if g.get("status") not in ("active", "paused"):
            continue
        sym: str = g.get("symbol", "")
        avg = float(g.get("average_entry_price", 0) or 0)
        qty = float(g.get("total_quantity", 0) or 0)
        if avg <= 0 or qty <= 0 or not sym.endswith("INR"):
            continue
        currency = sym[:-3]  # strip "INR"
        prev_qty, prev_cost = result.get(currency, (0.0, 0.0))
        result[currency] = (prev_qty + qty, prev_cost + avg * qty)
    return result


def grid_pnl_breakdown(grid: dict, current_price: float | None) -> dict:
    """Per-grid realized/unrealized/combined P&L breakdown.

    current_price=None (price unavailable) yields unrealized=0.0, matching
    formatters.py's prior behavior of omitting the unrealized figure
    entirely when no live price was available for that symbol.
    """
    qty = float(grid.get("total_quantity", 0) or 0)
    avg = float(grid.get("average_entry_price", 0) or 0)
    realized = float(grid.get("realized_profit", 0) or 0)
    invested = float(grid.get("total_investment", 0) or 0)

    unrealized = 0.0
    if qty > 0 and avg > 0 and current_price:
        unrealized = unrealized_pnl(current_price, avg, qty)

    return {
        "realized": realized,
        "unrealized": unrealized,
        "combined": realized + unrealized,
        "invested": invested,
    }


def portfolio_totals(grids: list[dict], prices: dict[str, float]) -> dict:
    """Aggregate P&L totals across a set of grids (e.g. all paper-trade
    grids), reproducing the same math as formatters.format_paper_grids'
    final "Portfolio Totals" section."""
    total_realized = 0.0
    total_unrealized = 0.0
    total_invested = 0.0

    for g in grids:
        breakdown = grid_pnl_breakdown(g, prices.get(g.get("symbol", "")))
        total_realized += breakdown["realized"]
        total_unrealized += breakdown["unrealized"]
        total_invested += breakdown["invested"]

    combined_total = total_realized + total_unrealized
    return {
        "total_realized": total_realized,
        "total_unrealized": total_unrealized,
        "total_invested": total_invested,
        "combined_total": combined_total,
        "portfolio_return_pct": pnl_pct(combined_total, total_invested),
    }

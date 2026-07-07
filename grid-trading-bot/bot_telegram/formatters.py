"""Formatting helpers for DCA grid bot Telegram messages."""

from __future__ import annotations


def _status_emoji(status: str) -> str:
    return {"active": "🟢", "paused": "⏸", "stopped": "🛑", "completed": "🏁"}.get(status, "❓")


def format_grid_summary(grid: dict) -> str:
    status = grid["status"]
    emoji = _status_emoji(status)
    avg = grid["average_entry_price"]
    qty = grid["total_quantity"]
    invested = grid["total_investment"]
    unrealized_note = ""
    if avg > 0 and qty > 0:
        unrealized_note = f"\nHolding: {qty:.6f} coins @ avg ₹{avg:,.2f} (invested ₹{invested:,.2f})"

    next_buy = grid["next_buy_price"]
    next_sell = grid["next_sell_price"]
    targets = ""
    if status == "active" and grid["current_level"] > 0:
        targets = (
            f"\nNext buy: ₹{next_buy:,.2f} | Next sell: ₹{next_sell:,.2f}"
        )

    return (
        f"{emoji} <b>{grid['symbol']}</b> — <code>{grid['grid_id']}</code>\n"
        f"Status: {status.upper()} | Level: {grid['current_level']}/{grid['max_levels']}\n"
        f"Entry: ₹{grid['entry_price']:,.2f} | Dip: {grid['dip_percentage']}% | Profit: {grid['profit_percentage']}%\n"
        f"Stop loss: {grid['stop_loss_percentage']}%"
        f"{unrealized_note}"
        f"{targets}\n"
        f"Realized profit: ₹{grid['realized_profit']:,.2f} | Sell cycles: {grid['completed_cycles']}"
    )


def format_grid_list(grids: list[dict]) -> str:
    if not grids:
        return "No grids found. Use /newgrid to create one."
    lines = ["<b>All DCA Grids</b>\n"]
    for g in grids:
        emoji = _status_emoji(g["status"])
        avg_entry = g["average_entry_price"]
        avg_part = f" | avg ₹{avg_entry:,.2f}" if avg_entry > 0 else ""
        lines.append(
            f"{emoji} <b>{g['symbol']}</b> ({g['status']}) — "
            f"<code>{g['grid_id']}</code>{avg_part} | ₹{g['realized_profit']:,.2f} profit"
        )
    return "\n".join(lines)


def format_positions(grids: list[dict]) -> str:
    active = [g for g in grids if g["total_quantity"] > 0 and g["status"] in ("active", "paused")]
    if not active:
        return "No open positions."
    lines = ["<b>Open Positions</b>\n"]
    for g in active:
        lines.append(
            f"• <b>{g['symbol']}</b>: {g['total_quantity']:.6f} coins "
            f"@ avg ₹{g['average_entry_price']:,.2f} "
            f"(invested ₹{g['total_investment']:,.2f}) "
            f"<code>{g['grid_id']}</code>"
        )
    return "\n".join(lines)


def format_profit_summary(grids: list[dict], total_realized: float) -> str:
    lines = [f"<b>💰 Total Realized Profit:</b> ₹{total_realized:,.2f}\n"]
    if not grids:
        lines.append("No grids yet.")
    for g in grids:
        emoji = _status_emoji(g["status"])
        lines.append(
            f"{emoji} <b>{g['symbol']}</b>: ₹{g['realized_profit']:,.2f} "
            f"({g['completed_cycles']} sell cycle(s)) — {g['status']}"
        )
    return "\n".join(lines)


def format_daily_summary(
    date: str,
    daily_stats: dict | None,
    active_grids: list[dict],
    lifetime_realized: float,
) -> str:
    today_pnl = daily_stats["realized_pnl"] if daily_stats else 0.0
    today_trades = daily_stats["trades_count"] if daily_stats else 0
    pnl_emoji = "📈" if today_pnl >= 0 else "📉"

    lines = [
        f"<b>Date:</b> {date}",
        f"{pnl_emoji} <b>Today's realized P&amp;L:</b> ₹{today_pnl:,.2f} ({today_trades} trade(s))",
        f"<b>Lifetime realized profit:</b> ₹{lifetime_realized:,.2f}",
        f"<b>Active/paused grids:</b> {len(active_grids)}",
    ]
    if active_grids:
        lines.append("")
        for g in active_grids:
            avg = g["average_entry_price"]
            avg_part = f" avg ₹{avg:,.2f}" if avg > 0 else ""
            lines.append(
                f"• <b>{g['symbol']}</b> ({g['status']}) lvl {g['current_level']}/{g['max_levels']}"
                f"{avg_part} — ₹{g['realized_profit']:,.2f} profit"
            )
    return "\n".join(lines)


def format_trade_history(symbol: str, trades: list[dict]) -> str:
    if not trades:
        return f"No trade history for {symbol} yet."
    lines = [f"<b>Recent Trades — {symbol}</b>\n"]
    for t in trades:
        side = t["side"].upper()
        pnl_part = f" | pnl ₹{t['pnl']:+,.2f}" if t["side"] == "sell" else ""
        ts = str(t["executed_at"])[:19].replace("T", " ")
        lines.append(
            f"• [{ts}] {side} {t['quantity']:.6f} @ ₹{t['price']:,.2f}"
            f" (₹{t['investment_inr']:,.2f}){pnl_part}"
        )
    return "\n".join(lines)


def format_logs(logs: list[dict]) -> str:
    if not logs:
        return "No recent log entries."
    lines = ["<b>Recent Logs</b>\n"]
    for entry in reversed(logs):
        ts = str(entry["created_at"])[11:19]
        lines.append(
            f"[{ts}] {entry['level']} ({entry['channel']}): {entry['message']}"
        )
    return "\n".join(lines)

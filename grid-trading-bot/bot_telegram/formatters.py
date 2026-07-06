"""Formatting helpers turning DB rows into readable Telegram messages."""

from __future__ import annotations


def format_grid_summary(grid: dict) -> str:
    return (
        f"<b>{grid['symbol']}</b> — <code>{grid['grid_id']}</code>\n"
        f"Status: {grid['status'].upper()}\n"
        f"Type: {grid['grid_type']}\n"
        f"Range: ₹{grid['lower_price']:,.2f} – ₹{grid['upper_price']:,.2f}\n"
        f"Levels: {grid['grid_levels']}\n"
        f"Investment/grid: ₹{grid['investment_per_grid']:,.2f}\n"
        f"Realized profit: ₹{grid['realized_profit']:,.2f}\n"
        f"Completed cycles: {grid['completed_cycles']}"
    )


def format_grid_list(grids: list[dict]) -> str:
    if not grids:
        return "No grids found."
    lines = ["<b>Grids</b>\n"]
    for g in grids:
        lines.append(
            f"• <b>{g['symbol']}</b> ({g['status']}) — "
            f"<code>{g['grid_id']}</code> — profit ₹{g['realized_profit']:,.2f}"
        )
    return "\n".join(lines)


def format_positions(positions: list[dict]) -> str:
    if not positions:
        return "No open positions."
    lines = ["<b>Open Positions</b>\n"]
    for p in positions:
        lines.append(
            f"• {p['symbol']}: {p['quantity']} @ ₹{p['entry_price']:,.2f} "
            f"(grid <code>{p['grid_id']}</code>)"
        )
    return "\n".join(lines)


def format_profit_summary(grids: list[dict], total_realized: float) -> str:
    lines = [f"<b>Total Realized Profit:</b> ₹{total_realized:,.2f}\n"]
    for g in grids:
        lines.append(f"• {g['symbol']}: ₹{g['realized_profit']:,.2f} ({g['completed_cycles']} cycles)")
    return "\n".join(lines) if len(lines) > 1 else lines[0]


def format_settings(coin_configs: list[dict]) -> str:
    if not coin_configs:
        return "No per-coin settings configured yet. Use /startgrid to create one."
    lines = ["<b>Per-Coin Settings</b>\n"]
    for c in coin_configs:
        lines.append(
            f"• <b>{c['symbol']}</b>: levels={c['grid_levels']}, "
            f"investment=₹{c['investment_per_grid']:,.2f}, "
            f"range=₹{c['lower_price']:,.2f}-₹{c['upper_price']:,.2f}, type={c['grid_type']}"
        )
    return "\n".join(lines)


def format_logs(logs: list[dict]) -> str:
    if not logs:
        return "No recent log entries."
    lines = ["<b>Recent Logs</b>\n"]
    for entry in reversed(logs):
        lines.append(f"[{entry['created_at'][11:19]}] {entry['level']} ({entry['channel']}): {entry['message']}")
    return "\n".join(lines)

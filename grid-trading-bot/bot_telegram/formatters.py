"""Formatting helpers for DCA grid bot Telegram messages."""

from __future__ import annotations

from utils.helpers import fmt_price


def _status_emoji(status: str) -> str:
    return {"active": "🟢", "paused": "⏸", "stopped": "🛑", "completed": "🏁"}.get(status, "❓")


def _mode_label(mode: str) -> str:
    return "🟢 Paper Trade" if mode == "paper" else "🔴 Real Trade"


def format_grid_summary(grid: dict) -> str:
    status = grid["status"]
    emoji = _status_emoji(status)
    mode = grid.get("mode", "real")
    avg = grid["average_entry_price"]
    qty = grid["total_quantity"]
    invested = grid["total_investment"]
    unrealized_note = ""
    if avg > 0 and qty > 0:
        unrealized_note = f"\nHolding: {qty:.8g} coins @ avg {fmt_price(avg)} (invested ₹{invested:,.2f})"

    next_buy = grid["next_buy_price"]
    next_sell = grid["next_sell_price"]
    targets = ""
    if status == "active" and grid["current_level"] > 0:
        targets = (
            f"\nNext buy: {fmt_price(next_buy)} | Next sell: {fmt_price(next_sell)}"
        )

    return (
        f"{emoji} <b>{grid['symbol']}</b> — <code>{grid['grid_id']}</code>\n"
        f"Mode: {_mode_label(mode)}\n"
        f"Status: {status.upper()} | Level: {grid['current_level']}/{grid['max_levels']}\n"
        f"Entry: {fmt_price(grid['entry_price'])} | Dip: {grid['dip_percentage']}% | Profit: {grid['profit_percentage']}%\n"
        f"Stop loss: {grid['stop_loss_percentage']}%"
        f"{unrealized_note}"
        f"{targets}\n"
        f"Realized profit: ₹{grid['realized_profit']:,.2f} | Sell cycles: {grid['completed_cycles']}"
    )


def format_wallet_balance(
    balances: list,
    prices: dict[str, float],
    grids: list[dict] | None = None,
) -> str:
    """Format full wallet balance for display.

    Args:
        balances: list of Balance dataclass objects from exchange.get_balances().
        prices:   dict mapping currency (e.g. "BTC") to current INR price per coin.
        grids:    optional list of active grid dicts; used to compute unrealized P&L
                  per asset from the bot's average entry prices.
    """
    inr = next((b for b in balances if b.currency.upper() == "INR"), None)
    crypto_items = [
        b for b in balances
        if b.currency.upper() != "INR" and (b.balance + b.locked_balance) > 0
    ]

    # Compute per-currency unrealized P&L from bot-managed grid positions only.
    # We sum (current_price - avg_entry) * grid.total_quantity across all active/paused
    # grids per currency.  We do NOT apply bot avg entries to total wallet holdings
    # because the wallet may contain coins bought outside the bot.
    # Keys: currency → (total_bot_qty, weighted_sum_cost) used later when we know price.
    bot_position_by_currency: dict[str, tuple[float, float]] = {}
    if grids:
        for g in grids:
            if g.get("status") not in ("active", "paused"):
                continue
            sym: str = g.get("symbol", "")
            avg = float(g.get("average_entry_price", 0) or 0)
            qty = float(g.get("total_quantity", 0) or 0)
            if avg <= 0 or qty <= 0 or not sym.endswith("INR"):
                continue
            currency = sym[:-3]  # strip "INR"
            prev_qty, prev_cost = bot_position_by_currency.get(currency, (0.0, 0.0))
            bot_position_by_currency[currency] = (prev_qty + qty, prev_cost + avg * qty)

    lines = ["<b>💰 Wallet Balance</b>\n"]

    # ── INR ─────────────────────────────────────────────────────────────
    if inr:
        avail_inr = inr.balance
        locked_inr = inr.locked_balance
        total_inr = avail_inr + locked_inr
        lines.append("<b>INR</b>")
        lines.append(f"  Available: ₹{avail_inr:,.2f}")
        lines.append(f"  Locked:    ₹{locked_inr:,.2f}")
        lines.append(f"  Total:     ₹{total_inr:,.2f}")
    else:
        total_inr = 0.0
        lines.append("INR: ₹0.00")

    # ── Crypto assets ────────────────────────────────────────────────────
    total_asset_value = 0.0
    total_unrealized = 0.0

    if crypto_items:
        lines.append("\n<b>Crypto Assets</b>")
        for b in crypto_items:
            currency = b.currency.upper()
            total_qty = b.balance + b.locked_balance
            price = prices.get(currency)

            if price and price > 0:
                value_inr = total_qty * price
                total_asset_value += value_inr

                # Unrealized P&L is computed from bot grid positions only —
                # not from total wallet qty, to avoid mixing bot-managed vs
                # manually-held coins.
                bot_pos = bot_position_by_currency.get(currency)
                pnl_part = ""
                if bot_pos:
                    bot_qty, bot_cost = bot_pos
                    bot_avg = bot_cost / bot_qty if bot_qty > 0 else 0.0
                    unrealized = (price - bot_avg) * bot_qty
                    total_unrealized += unrealized
                    pnl_arrow = "📈" if unrealized >= 0 else "📉"
                    pnl_part = (
                        f"Bot position: {bot_qty:.8g} @ avg ₹{bot_avg:,.2f} "
                        f"| P&L: {pnl_arrow} ₹{unrealized:+,.2f}"
                    )

                lines.append(
                    f"\n  <b>{currency}</b>"
                    f"\n    Available:     {b.balance:.8g}"
                    f"\n    Locked:        {b.locked_balance:.8g}"
                    f"\n    Total:         {total_qty:.8g}"
                    f"\n    Market price:  ₹{price:,.2f}"
                    f"\n    Market value:  ₹{value_inr:,.2f}"
                    + (f"\n    {pnl_part.strip()}" if pnl_part else "")
                )
            else:
                lines.append(
                    f"\n  <b>{currency}</b>"
                    f"\n    Available: {b.balance:.8g}  Locked: {b.locked_balance:.8g}"
                    f"\n    Price: unavailable"
                )

    # ── Totals ────────────────────────────────────────────────────────────
    total_wallet = total_inr + total_asset_value
    lines.append("\n<b>── Portfolio Summary ──</b>")
    lines.append(f"  INR balance:    ₹{total_inr:,.2f}")
    lines.append(f"  Asset value:    ₹{total_asset_value:,.2f}")
    lines.append(f"  <b>Total wallet:   ₹{total_wallet:,.2f}</b>")
    if total_unrealized != 0:
        arrow = "📈" if total_unrealized >= 0 else "📉"
        lines.append(f"  Unrealized P&amp;L: {arrow} ₹{total_unrealized:+,.2f}")

    return "\n".join(lines)


def format_coin_info(
    symbol: str,
    market_info: "MarketInfo",  # noqa: F821
    extended_ticker: "ExtendedTicker",  # noqa: F821
    base_validation: "ValidationResult",  # noqa: F821
    dip_validation: "ValidationResult",  # noqa: F821
    profit_validation: "ValidationResult",  # noqa: F821
) -> str:
    """Format /coininfo output.

    Args:
        symbol:           The trading pair (e.g. BNBINR).
        market_info:      Exchange rules (precision, minimums, status).
        extended_ticker:  Live 24h market snapshot.
        base_validation:  Qty calc for base investment.
        dip_validation:   Qty calc for dip buy amount.
        profit_validation: Qty calc for profit sell amount.
    """
    from config.constants import DEFAULT_BASE_INVESTMENT, DEFAULT_DIP_BUY_AMOUNT, DEFAULT_PROFIT_SELL_AMOUNT

    base_coin = market_info.target_currency_short_name or symbol.replace("INR", "")
    quote = market_info.target_currency_short_name or "INR"

    change_arrow = "📈" if extended_ticker.change_24h >= 0 else "📉"

    def _val_line(label: str, result: "ValidationResult") -> str:
        if result.valid:
            return (
                f"  {label} (₹{result.investment_inr:,.2f}): "
                f"<b>✅ Valid</b> → {result.quantity:.8g} {base_coin}"
            )
        return (
            f"  {label} (₹{result.investment_inr:,.2f}): "
            f"<b>❌ Invalid</b>\n"
            f"    {result.reason}"
        )

    lines = [
        f"<b>🔍 Coin Info — {symbol}</b>",
        f"Status: {'✅ Active' if market_info.is_active else '🚫 ' + market_info.status.upper()}",
        "",
        "<b>Market Data (24h)</b>",
        f"  Price:      ₹{extended_ticker.last_price:,.4f}",
        f"  Change:     {change_arrow} {extended_ticker.change_24h:+.2f}%",
    ]
    if extended_ticker.high_24h > 0:
        lines.append(f"  High:       ₹{extended_ticker.high_24h:,.4f}")
    if extended_ticker.low_24h > 0:
        lines.append(f"  Low:        ₹{extended_ticker.low_24h:,.4f}")
    if extended_ticker.volume_24h > 0:
        lines.append(f"  Volume:     {extended_ticker.volume_24h:.4g} {base_coin}")
    if extended_ticker.bid > 0 or extended_ticker.ask > 0:
        lines.append(f"  Bid / Ask:  ₹{extended_ticker.bid:,.4f} / ₹{extended_ticker.ask:,.4f}")

    lines += [
        "",
        "<b>Exchange Rules</b>",
        f"  Min order value:  ₹{market_info.min_amount:,.2f}",
        f"  Min quantity:     {market_info.min_quantity:.8g} {base_coin}",
        f"  Quantity step:    {market_info.step_size:.8g} {base_coin}",
        f"  Qty precision:    {market_info.target_currency_precision} decimals",
        f"  Price precision:  {market_info.base_currency_precision} decimals",
        "",
        f"<b>Investment Validation</b>  (at ₹{extended_ticker.last_price:,.2f})",
        f"  Using default amounts — /coininfo uses bot defaults:",
        _val_line(f"Base investment  (₹{DEFAULT_BASE_INVESTMENT:,.0f})", base_validation),
        _val_line(f"Dip buy amount   (₹{DEFAULT_DIP_BUY_AMOUNT:,.0f})", dip_validation),
        _val_line(f"Profit sell amt  (₹{DEFAULT_PROFIT_SELL_AMOUNT:,.0f})", profit_validation),
    ]

    all_valid = base_validation.valid and dip_validation.valid and profit_validation.valid
    if all_valid:
        lines.append("")
        lines.append("✅ <b>This pair is ready to use with default amounts.</b>")
    else:
        min_req = max(
            r.min_investment_inr
            for r in (base_validation, dip_validation, profit_validation)
            if not r.valid and r.min_investment_inr > 0
        ) if not all_valid else 0
        if min_req > 0:
            lines.append("")
            lines.append(
                f"⚠️ Minimum investment needed for this pair: <b>₹{min_req:,.2f}</b>"
            )

    return "\n".join(lines)


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
            f"• <b>{g['symbol']}</b>: {g['total_quantity']:.8g} coins "
            f"@ avg {fmt_price(g['average_entry_price'])} "
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
            f"• [{ts}] {side} {t['quantity']:.8g} @ {fmt_price(t['price'])}"
            f" (₹{t['investment_inr']:,.2f}){pnl_part}"
        )
    return "\n".join(lines)


def format_paper_grids(grids: list[dict], prices: dict[str, float]) -> str:
    """Summary of all paper-trade grids with realized and live unrealized P&L."""
    paper = [g for g in grids if g.get("mode") == "paper"]
    if not paper:
        return (
            "No paper trade grids found.\n\n"
            "Use /newgrid and choose 🟢 <b>Paper Trade</b> to simulate a strategy risk-free."
        )

    total_realized = sum(g["realized_profit"] for g in paper)
    total_unrealized = 0.0

    lines = ["<b>🟢 Paper Trade Grids</b>\n"]

    for g in paper:
        status = g["status"]
        emoji = _status_emoji(status)
        symbol = g["symbol"]
        qty = g["total_quantity"]
        avg = g["average_entry_price"]
        realized = g["realized_profit"]
        cycles = g["completed_cycles"]

        unrealized = 0.0
        price_note = ""
        if qty > 0 and avg > 0:
            current = prices.get(symbol)
            if current:
                unrealized = (current - avg) * qty
                total_unrealized += unrealized
                direction = "📈" if unrealized >= 0 else "📉"
                price_note = (
                    f"\n    Current: ₹{current:,.2f} | "
                    f"Unrealized: {direction} ₹{unrealized:+,.2f}"
                )

        realized_note = f"₹{realized:+,.2f}" if realized != 0 else "₹0.00"
        lines.append(
            f"{emoji} <b>{symbol}</b> — <code>{g['grid_id']}</code>\n"
            f"    Status: {status.upper()} | Level: {g['current_level']}/{g['max_levels']}\n"
            f"    Entry: ₹{g['entry_price']:,.2f} | Dip: {g['dip_percentage']}% | "
            f"Profit: {g['profit_percentage']}%\n"
            f"    Realized P&amp;L: {realized_note} ({cycles} sell cycle(s))"
            + (
                f"\n    Holding: {qty:.6f} coins @ avg ₹{avg:,.2f}"
                + price_note
                if qty > 0 else ""
            )
        )

    lines.append("")
    lines.append("<b>── Paper Portfolio Totals ──</b>")
    lines.append(f"Realized P&amp;L:   ₹{total_realized:+,.2f}")
    if total_unrealized != 0:
        direction = "📈" if total_unrealized >= 0 else "📉"
        lines.append(f"Unrealized P&amp;L: {direction} ₹{total_unrealized:+,.2f}")
        lines.append(
            f"Combined P&amp;L:   ₹{(total_realized + total_unrealized):+,.2f}"
        )
    lines.append(f"\nGrids: {len(paper)} total | {sum(1 for g in paper if g['status'] == 'active')} active")

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


def format_monitor_status(status: "MonitorStatus") -> str:  # noqa: F821
    """Format the /monitor command response."""
    from storage.repositories import VALID_MONITOR_INTERVALS

    api_emoji = "✅" if status.api_ok else "⚠️"
    api_label = "OK" if status.api_ok else f"DEGRADED ({status.consecutive_failures} consecutive failure(s))"

    last_str = (
        status.last_refresh.strftime("%H:%M:%S UTC")
        if status.last_refresh
        else "Not yet refreshed"
    )
    next_str = (
        status.next_refresh.strftime("%H:%M:%S UTC")
        if status.next_refresh
        else "—"
    )

    if status.monitored_symbols:
        coins_list = "\n".join(f"  • {sym}" for sym in sorted(status.monitored_symbols))
    else:
        coins_list = "  (none — no active grids)"

    allowed = " / ".join(f"{v}s" for v in VALID_MONITOR_INTERVALS)

    lines = [
        "<b>📡 Price Monitor Status</b>\n",
        f"Refresh interval:   <b>{status.interval_seconds}s</b>  (allowed: {allowed})",
        f"Active coins:       <b>{len(status.monitored_symbols)}</b>",
        f"Total cycles run:   {status.total_cycles}",
        f"Last refresh:       {last_str}",
        f"Next refresh:       {next_str}",
        f"API status:         {api_emoji} {api_label}",
        "",
        "<b>Monitored coins:</b>",
        coins_list,
        "",
        "Use <code>/monitor &lt;seconds&gt;</code> to change the interval.",
        f"Example: <code>/monitor 10</code>",
    ]
    return "\n".join(lines)

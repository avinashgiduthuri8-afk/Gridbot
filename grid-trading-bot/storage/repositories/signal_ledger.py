"""Live Signal Lifecycle Tracker & Performance Ledger for Indian Equities.

Tracks the exact state machine of generated signals:
OPEN / WATCH -> TRIGGERED -> HIT_T1 (+2.0R) -> HIT_T2 (+3.5R) -> STOPPED_OUT (-1.0R) -> EXPIRED

Calculates institutional R-multiple metrics, profit factor, and setup breakdown.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from storage.database import Database
from utils.helpers import now_iso
from utils.logger import get_logger

log = get_logger("signal_repo")


@dataclass
class LedgerStats:
    total_signals: int = 0
    winning_signals: int = 0
    losing_signals: int = 0
    expired_signals: int = 0
    active_signals: int = 0
    win_rate_pct: float = 0.0
    total_r_multiple: float = 0.0
    profit_factor: float = 0.0
    avg_r_per_trade: float = 0.0
    avg_mfe_pct: float = 0.0
    avg_mae_pct: float = 0.0
    setup_breakdown: dict[str, dict[str, Any]] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "total_signals": self.total_signals,
            "winning_signals": self.winning_signals,
            "losing_signals": self.losing_signals,
            "expired_signals": self.expired_signals,
            "active_signals": self.active_signals,
            "win_rate_pct": round(self.win_rate_pct, 1),
            "total_r_multiple": round(self.total_r_multiple, 2),
            "profit_factor": round(self.profit_factor, 2),
            "avg_r_per_trade": round(self.avg_r_per_trade, 2),
            "avg_mfe_pct": round(self.avg_mfe_pct, 2),
            "avg_mae_pct": round(self.avg_mae_pct, 2),
            "setup_breakdown": self.setup_breakdown,
        }


class SignalLedgerRepository:
    """Repository managing signal tracking, R-multiple ledger, and performance stats."""

    def __init__(self, db: Database) -> None:
        self._db = db

    async def get_active_signals(self) -> list[dict[str, Any]]:
        """Retrieves all unresolved OPEN / TRIGGERED signals."""
        sql = "SELECT * FROM stock_signals WHERE status IN ('OPEN', 'TRIGGERED', 'WATCH', 'SETUP', 'CONFIRMED') ORDER BY created_at DESC"
        async with self._db.connection.execute(sql) as cursor:
            rows = await cursor.fetchall()
            return [dict(r) for r in rows]

    async def evaluate_active_signals(self, current_quotes: dict[str, float]) -> list[dict[str, Any]]:
        """Updates lifecycle states for active signals against live market prices."""
        active = await self.get_active_signals()
        resolved: list[dict[str, Any]] = []

        for sig in active:
            sym = sig["symbol"].replace(".NS", "").replace(".BO", "")
            curr_price = current_quotes.get(sym) or current_quotes.get(sig["symbol"])
            if not curr_price:
                continue

            entry = float(sig["entry_price"])
            sl = float(sig["stop_loss"])
            t1 = float(sig["target_1"])
            t2 = float(sig["target_2"])
            risk = entry - sl if entry > sl else (entry * 0.02)

            new_status = sig["status"]
            r_multiple = 0.0

            # 1. Target 2 Hit (+3.5R)
            if curr_price >= t2:
                new_status = "HIT_T2"
                r_multiple = round((t2 - entry) / risk, 2)
            # 2. Target 1 Hit (+2.0R)
            elif curr_price >= t1:
                new_status = "HIT_T1"
                r_multiple = round((t1 - entry) / risk, 2)
            # 3. Stopped Out (-1.0R)
            elif curr_price <= sl:
                new_status = "STOPPED_OUT"
                r_multiple = -1.0

            if new_status != sig["status"]:
                pnl_pct = ((curr_price - entry) / entry) * 100.0
                await self.resolve_signal(
                    signal_id=sig["signal_id"],
                    status=new_status,
                    outcome_pnl_pct=pnl_pct,
                )
                sig["status"] = new_status
                sig["r_multiple"] = r_multiple
                resolved.append(sig)

        return resolved

    async def resolve_signal(self, signal_id: str, status: str, outcome_pnl_pct: float) -> bool:
        """Marks a signal as resolved with outcome PnL."""
        sql = """
        UPDATE stock_signals
        SET status = ?, outcome_pnl_pct = ?, resolved_at = ?
        WHERE signal_id = ?
        """
        async with self._db.connection.execute(sql, (status, outcome_pnl_pct, now_iso(), signal_id)):
            await self._db.connection.commit()
            return True

    async def get_ledger_stats(self) -> LedgerStats:
        """Calculates total win rate, profit factor, R-multiples, and setup breakdown."""
        sql = "SELECT * FROM stock_signals"
        async with self._db.connection.execute(sql) as cursor:
            rows = await cursor.fetchall()

        if not rows:
            return LedgerStats()

        total = len(rows)
        wins = 0
        losses = 0
        expired = 0
        active_count = 0
        total_r = 0.0
        gross_win_r = 0.0
        gross_loss_r = 0.0

        setup_map: dict[str, dict[str, Any]] = {}

        for r in rows:
            status = r["status"]
            stype = r["signal_type"]
            entry = float(r["entry_price"])
            sl = float(r["stop_loss"])
            t1 = float(r["target_1"])
            risk = entry - sl if entry > sl else (entry * 0.02)

            if stype not in setup_map:
                setup_map[stype] = {"total": 0, "wins": 0, "losses": 0, "total_r": 0.0}
            setup_map[stype]["total"] += 1

            if status in ("HIT_T1", "HIT_T2"):
                wins += 1
                r_gain = round((t1 - entry) / risk, 2) if risk > 0 else 2.0
                total_r += r_gain
                gross_win_r += r_gain
                setup_map[stype]["wins"] += 1
                setup_map[stype]["total_r"] += r_gain
            elif status == "STOPPED_OUT":
                losses += 1
                total_r -= 1.0
                gross_loss_r += 1.0
                setup_map[stype]["losses"] += 1
                setup_map[stype]["total_r"] -= 1.0
            elif status == "EXPIRED":
                expired += 1
            else:
                active_count += 1

        resolved_count = wins + losses
        win_rate = (wins / resolved_count * 100.0) if resolved_count > 0 else 0.0
        profit_factor = (gross_win_r / gross_loss_r) if gross_loss_r > 0 else (gross_win_r if gross_win_r > 0 else 0.0)
        avg_r = (total_r / resolved_count) if resolved_count > 0 else 0.0

        return LedgerStats(
            total_signals=total,
            winning_signals=wins,
            losing_signals=losses,
            expired_signals=expired,
            active_signals=active_count,
            win_rate_pct=win_rate,
            total_r_multiple=total_r,
            profit_factor=profit_factor,
            avg_r_per_trade=avg_r,
            setup_breakdown=setup_map,
        )

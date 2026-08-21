"""Signal & Backtest Repository for SQLite persistence.

Handles saving scored signals, tracking MFE/MAE excursions, status transitions,
and querying historical performance analytics.
"""

from __future__ import annotations

import json
from typing import Any

from engine.signals.scoring import ScoredSignal
from storage.database import Database
from utils.helpers import now_iso, new_id
from utils.logger import get_logger

log = get_logger("signal_repo")


class SignalRepository:
    """Repository for managing Indian stock signal persistence and performance stats."""

    def __init__(self, db: Database) -> None:
        self._db = db

    async def save_signal(self, sig: ScoredSignal) -> str:
        """Inserts a new scored signal into stock_signals table."""
        signal_id = new_id("sig")
        sql = """
        INSERT INTO stock_signals (
            signal_id, symbol, signal_type, strength, score,
            entry_price, stop_loss, target_1, target_2, risk_reward,
            market_regime, sector, timeframe_summary, rationale_json, breakdown_json,
            status, mfe, mae, outcome_pnl_pct, created_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """
        params = (
            signal_id,
            sig.symbol,
            sig.signal_type.value if hasattr(sig.signal_type, "value") else str(sig.signal_type),
            sig.strength.value if hasattr(sig.strength, "value") else str(sig.strength),
            float(sig.total_score),
            float(sig.risk_reward.entry_price),
            float(sig.risk_reward.stop_loss),
            float(sig.risk_reward.target_1),
            float(sig.risk_reward.target_2),
            float(sig.risk_reward.rr_ratio),
            str(sig.market_regime),
            str(sig.sector),
            str(sig.timeframes_summary),
            json.dumps(sig.rationale),
            json.dumps(sig.breakdown.to_dict()),
            "OPEN",
            0.0,
            0.0,
            0.0,
            sig.timestamp or now_iso(),
        )
        async with self._db.connection.execute(sql, params):
            await self._db.connection.commit()
        return signal_id

    async def list_signals(
        self,
        limit: int = 50,
        status: str | None = None,
        min_score: float | None = None,
    ) -> list[dict[str, Any]]:
        """Queries signals with optional status and score filters."""
        query = "SELECT * FROM stock_signals WHERE 1=1"
        params: list[Any] = []

        if status:
            query += " AND status = ?"
            params.append(status)
        if min_score is not None:
            query += " AND score >= ?"
            params.append(min_score)

        query += " ORDER BY created_at DESC LIMIT ?"
        params.append(limit)

        async with self._db.connection.execute(query, params) as cursor:
            rows = await cursor.fetchall()
            results = []
            for r in rows:
                d = dict(r)
                d["rationale"] = json.loads(d["rationale_json"]) if d.get("rationale_json") else []
                d["breakdown"] = json.loads(d["breakdown_json"]) if d.get("breakdown_json") else {}
                results.append(d)
            return results

    async def get_signal(self, signal_id: str) -> dict[str, Any] | None:
        """Retrieves a single signal by ID."""
        query = "SELECT * FROM stock_signals WHERE signal_id = ?"
        async with self._db.connection.execute(query, (signal_id,)) as cursor:
            row = await cursor.fetchone()
            if not row:
                return None
            d = dict(row)
            d["rationale"] = json.loads(d["rationale_json"]) if d.get("rationale_json") else []
            d["breakdown"] = json.loads(d["breakdown_json"]) if d.get("breakdown_json") else {}
            return d

    async def update_signal_outcome(
        self,
        signal_id: str,
        status: str,
        mfe: float,
        mae: float,
        outcome_pnl_pct: float,
    ) -> bool:
        """Updates outcome status and excursions for a resolved signal."""
        sql = """
        UPDATE stock_signals
        SET status = ?, mfe = ?, mae = ?, outcome_pnl_pct = ?, resolved_at = ?
        WHERE signal_id = ?
        """
        params = (status, mfe, mae, outcome_pnl_pct, now_iso(), signal_id)
        async with self._db.connection.execute(sql, params) as cursor:
            await self._db.connection.commit()
            return cursor.rowcount > 0

    async def get_performance_summary(self) -> dict[str, Any]:
        """Calculates win rate, average R:R, and profit metrics from resolved signals."""
        sql = """
        SELECT
            COUNT(*) as total_signals,
            SUM(CASE WHEN status IN ('HIT_T1', 'HIT_T2') THEN 1 ELSE 0 END) as winning_signals,
            SUM(CASE WHEN status = 'STOPPED_OUT' THEN 1 ELSE 0 END) as losing_signals,
            AVG(risk_reward) as avg_rr,
            AVG(mfe) as avg_mfe,
            AVG(mae) as avg_mae,
            AVG(outcome_pnl_pct) as avg_return_pct
        FROM stock_signals
        WHERE status != 'OPEN'
        """
        async with self._db.connection.execute(sql) as cursor:
            row = await cursor.fetchone()
            if not row or row["total_signals"] == 0:
                return {
                    "total_signals": 0,
                    "win_rate_pct": 0.0,
                    "avg_rr": 0.0,
                    "avg_mfe": 0.0,
                    "avg_mae": 0.0,
                    "avg_return_pct": 0.0,
                }

            total = row["total_signals"]
            wins = row["winning_signals"] or 0
            win_rate = (wins / total * 100.0) if total > 0 else 0.0

            return {
                "total_signals": total,
                "winning_signals": wins,
                "losing_signals": row["losing_signals"] or 0,
                "win_rate_pct": round(win_rate, 1),
                "avg_rr": round(row["avg_rr"] or 0.0, 2),
                "avg_mfe": round(row["avg_mfe"] or 0.0, 2),
                "avg_mae": round(row["avg_mae"] or 0.0, 2),
                "avg_return_pct": round(row["avg_return_pct"] or 0.0, 2),
            }

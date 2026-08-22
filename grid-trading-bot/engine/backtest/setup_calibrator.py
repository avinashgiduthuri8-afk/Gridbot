"""Setup Expectancy & Diagnostic Calibration Engine for Indian Equities.

Measures statistical performance, win rate, profit factor, and average R-multiples:
1. By Setup Type (VCP, Pocket Pivot, NR7, High Delivery, Breakout, Pullback)
2. By Market Regime (Strong Bullish, Bullish, Neutral, Bearish)
3. By Score Tier (90-100, 85-89, 80-84, <80)

Verifies the monotonic score-to-expectancy calibration curve.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from utils.logger import get_logger

log = get_logger("backtest_evaluator")


@dataclass
class SetupCalibrationResult:
    total_trades: int
    overall_win_rate_pct: float
    overall_profit_factor: float
    overall_total_r: float
    setup_metrics: dict[str, dict[str, Any]] = field(default_factory=dict)
    regime_metrics: dict[str, dict[str, Any]] = field(default_factory=dict)
    score_tier_metrics: dict[str, dict[str, Any]] = field(default_factory=dict)
    is_monotonically_calibrated: bool = True

    def to_dict(self) -> dict[str, Any]:
        return {
            "total_trades": self.total_trades,
            "overall_win_rate_pct": round(self.overall_win_rate_pct, 1),
            "overall_profit_factor": round(self.overall_profit_factor, 2),
            "overall_total_r": round(self.overall_total_r, 2),
            "setup_metrics": self.setup_metrics,
            "regime_metrics": self.regime_metrics,
            "score_tier_metrics": self.score_tier_metrics,
            "is_monotonically_calibrated": self.is_monotonically_calibrated,
        }


class SetupCalibrator:
    """Evaluates setup expectancy and validates score-to-outcome statistical alignment."""

    def calibrate(self, historical_trades: list[dict[str, Any]]) -> SetupCalibrationResult:
        """Computes multidimensional performance matrix from historical trades."""
        if not historical_trades:
            return SetupCalibrationResult(
                total_trades=0,
                overall_win_rate_pct=0.0,
                overall_profit_factor=0.0,
                overall_total_r=0.0,
            )

        total_trades = len(historical_trades)
        wins = 0
        losses = 0
        total_r = 0.0
        gross_win_r = 0.0
        gross_loss_r = 0.0

        setup_map: dict[str, dict[str, Any]] = {}
        regime_map: dict[str, dict[str, Any]] = {}
        tier_map: dict[str, dict[str, Any]] = {
            "TIER_1_90_PLUS": {"total": 0, "wins": 0, "total_r": 0.0},
            "TIER_2_85_89": {"total": 0, "wins": 0, "total_r": 0.0},
            "TIER_3_80_84": {"total": 0, "wins": 0, "total_r": 0.0},
            "TIER_4_BELOW_80": {"total": 0, "wins": 0, "total_r": 0.0},
        }

        for t in historical_trades:
            status = t.get("status", "OPEN")
            stype = t.get("signal_type", "BREAKOUT")
            regime = t.get("market_regime", "NEUTRAL")
            score = float(t.get("score", 80.0))

            entry = float(t.get("entry_price", 100.0))
            sl = float(t.get("stop_loss", 95.0))
            t1 = float(t.get("target_1", 110.0))
            risk = entry - sl if entry > sl else (entry * 0.02)

            # Determine R-multiple outcome
            if status in ("HIT_T1", "HIT_T2", "WIN"):
                wins += 1
                r_gain = round((t1 - entry) / risk, 2) if risk > 0 else 2.0
                total_r += r_gain
                gross_win_r += r_gain
                trade_r = r_gain
                is_win = True
            elif status in ("STOPPED_OUT", "LOSS"):
                losses += 1
                total_r -= 1.0
                gross_loss_r += 1.0
                trade_r = -1.0
                is_win = False
            else:
                trade_r = 0.0
                is_win = False

            # 1. Setup Breakdown
            if stype not in setup_map:
                setup_map[stype] = {"total": 0, "wins": 0, "total_r": 0.0}
            setup_map[stype]["total"] += 1
            if is_win:
                setup_map[stype]["wins"] += 1
            setup_map[stype]["total_r"] += trade_r

            # 2. Regime Breakdown
            if regime not in regime_map:
                regime_map[regime] = {"total": 0, "wins": 0, "total_r": 0.0}
            regime_map[regime]["total"] += 1
            if is_win:
                regime_map[regime]["wins"] += 1
            regime_map[regime]["total_r"] += trade_r

            # 3. Score Tier Breakdown
            if score >= 90.0:
                tier_key = "TIER_1_90_PLUS"
            elif score >= 85.0:
                tier_key = "TIER_2_85_89"
            elif score >= 80.0:
                tier_key = "TIER_3_80_84"
            else:
                tier_key = "TIER_4_BELOW_80"

            tier_map[tier_key]["total"] += 1
            if is_win:
                tier_map[tier_key]["wins"] += 1
            tier_map[tier_key]["total_r"] += trade_r

        resolved_count = wins + losses
        win_rate = (wins / resolved_count * 100.0) if resolved_count > 0 else 0.0
        profit_factor = (gross_win_r / gross_loss_r) if gross_loss_r > 0 else (gross_win_r if gross_win_r > 0 else 0.0)

        # Compute percentages for breakdowns
        for m in (setup_map, regime_map, tier_map):
            for k, val in m.items():
                tot = val["total"]
                w = val["wins"]
                val["win_rate_pct"] = round((w / tot * 100.0) if tot > 0 else 0.0, 1)
                val["avg_r"] = round((val["total_r"] / tot) if tot > 0 else 0.0, 2)

        # Monotonicity check: Tier 1 (90+) win rate >= Tier 3 (80-84) win rate
        t1_wr = tier_map["TIER_1_90_PLUS"]["win_rate_pct"]
        t3_wr = tier_map["TIER_3_80_84"]["win_rate_pct"]
        is_monotonic = t1_wr >= t3_wr if (tier_map["TIER_1_90_PLUS"]["total"] > 0 and tier_map["TIER_3_80_84"]["total"] > 0) else True

        return SetupCalibrationResult(
            total_trades=total_trades,
            overall_win_rate_pct=win_rate,
            overall_profit_factor=profit_factor,
            overall_total_r=total_r,
            setup_metrics=setup_map,
            regime_metrics=regime_map,
            score_tier_metrics=tier_map,
            is_monotonically_calibrated=is_monotonic,
        )

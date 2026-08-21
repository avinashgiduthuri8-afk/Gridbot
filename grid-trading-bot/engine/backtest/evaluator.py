"""Historical Backtest & Performance Evaluation Engine for Indian Stock Scanner.

Simulates forward execution of generated signals across multiple bars to evaluate:
1. Win Rate %
2. Average Return % & Average R:R
3. Profit Factor & Maximum Drawdown
4. Maximum Favorable Excursion (MFE) & Maximum Adverse Excursion (MAE)
5. Regime-specific performance (Bullish / Neutral / Bearish / High Volatility)
6. Setup-specific and Sector-specific performance
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from config.constants import MarketRegime, SignalType
from engine.data.base import OHLCVCandle
from engine.signals.scoring import ScoredSignal
from utils.logger import get_logger

log = get_logger("backtest_evaluator")


@dataclass
class SignalBacktestOutcome:
    signal: ScoredSignal
    status: str                  # HIT_T1, HIT_T2, STOPPED_OUT, EXPIRED
    mfe_pct: float               # Maximum Favorable Excursion %
    mae_pct: float               # Maximum Adverse Excursion %
    realized_pnl_pct: float
    holding_bars: int
    exit_price: float


@dataclass
class BacktestReport:
    total_signals: int = 0
    winning_signals: int = 0
    losing_signals: int = 0
    expired_signals: int = 0

    win_rate_pct: float = 0.0
    profit_factor: float = 0.0
    avg_return_pct: float = 0.0
    avg_mfe_pct: float = 0.0
    avg_mae_pct: float = 0.0
    max_drawdown_pct: float = 0.0
    avg_holding_bars: float = 0.0

    by_regime: dict[str, dict[str, Any]] = field(default_factory=dict)
    by_setup: dict[str, dict[str, Any]] = field(default_factory=dict)
    by_sector: dict[str, dict[str, Any]] = field(default_factory=dict)
    outcomes: list[SignalBacktestOutcome] = field(default_factory=list)


class ScannerBacktestEvaluator:
    """Simulates signal outcomes against future OHLCV price paths."""

    @staticmethod
    def evaluate_signal_forward(
        signal: ScoredSignal,
        forward_candles: list[OHLCVCandle],
        max_holding_bars: int = 15,
    ) -> SignalBacktestOutcome:
        """Tracks the forward price action of a signal until target/stop/expiry."""
        entry = signal.risk_reward.entry_price
        stop = signal.risk_reward.stop_loss
        t1 = signal.risk_reward.target_1
        t2 = signal.risk_reward.target_2

        max_high = entry
        min_low = entry
        status = "EXPIRED"
        realized_pnl = 0.0
        exit_p = entry
        holding_bars = 0

        eval_candles = forward_candles[:max_holding_bars]

        for i, c in enumerate(eval_candles, start=1):
            holding_bars = i
            max_high = max(max_high, c.high)
            min_low = min(min_low, c.low)

            # Check if hit stop loss first (worst case intraday assumption)
            if c.low <= stop:
                status = "STOPPED_OUT"
                exit_p = stop
                realized_pnl = ((stop - entry) / entry * 100.0) if entry > 0 else 0.0
                break

            # Check if hit Target 2
            if c.high >= t2:
                status = "HIT_T2"
                exit_p = t2
                realized_pnl = ((t2 - entry) / entry * 100.0) if entry > 0 else 0.0
                break

            # Check if hit Target 1
            if c.high >= t1:
                status = "HIT_T1"
                exit_p = t1
                realized_pnl = ((t1 - entry) / entry * 100.0) if entry > 0 else 0.0
                break

        if status == "EXPIRED" and eval_candles:
            exit_p = eval_candles[-1].close
            realized_pnl = ((exit_p - entry) / entry * 100.0) if entry > 0 else 0.0

        mfe = ((max_high - entry) / entry * 100.0) if entry > 0 else 0.0
        mae = ((min_low - entry) / entry * 100.0) if entry > 0 else 0.0

        return SignalBacktestOutcome(
            signal=signal,
            status=status,
            mfe_pct=round(mfe, 2),
            mae_pct=round(mae, 2),
            realized_pnl_pct=round(realized_pnl, 2),
            holding_bars=holding_bars,
            exit_price=round(exit_p, 2),
        )

    def generate_report(self, outcomes: list[SignalBacktestOutcome]) -> BacktestReport:
        """Aggregates all signal outcomes into a comprehensive performance report."""
        if not outcomes:
            return BacktestReport()

        total = len(outcomes)
        wins = sum(1 for o in outcomes if o.status in ("HIT_T1", "HIT_T2"))
        losses = sum(1 for o in outcomes if o.status == "STOPPED_OUT")
        expired = sum(1 for o in outcomes if o.status == "EXPIRED")

        win_rate = (wins / total * 100.0) if total > 0 else 0.0
        returns = [o.realized_pnl_pct for o in outcomes]
        avg_return = sum(returns) / total if total > 0 else 0.0

        gross_gains = sum(r for r in returns if r > 0)
        gross_losses = abs(sum(r for r in returns if r < 0))
        profit_factor = (gross_gains / gross_losses) if gross_losses > 0 else (gross_gains if gross_gains > 0 else 1.0)

        avg_mfe = sum(o.mfe_pct for o in outcomes) / total if total > 0 else 0.0
        avg_mae = sum(o.mae_pct for o in outcomes) / total if total > 0 else 0.0
        avg_bars = sum(o.holding_bars for o in outcomes) / total if total > 0 else 0.0

        # Maximum cumulative drawdown calculation
        cum_pnl = 0.0
        peak = 0.0
        max_dd = 0.0
        for r in returns:
            cum_pnl += r
            if cum_pnl > peak:
                peak = cum_pnl
            dd = peak - cum_pnl
            if dd > max_dd:
                max_dd = dd

        # Breakdown by Market Regime
        by_regime: dict[str, dict[str, Any]] = {}
        for r_name in [m.value for m in MarketRegime]:
            subset = [o for o in outcomes if o.signal.market_regime == r_name]
            if subset:
                sub_wins = sum(1 for o in subset if o.status in ("HIT_T1", "HIT_T2"))
                sub_ret = sum(o.realized_pnl_pct for o in subset) / len(subset)
                by_regime[r_name] = {
                    "count": len(subset),
                    "win_rate": round(sub_wins / len(subset) * 100.0, 1),
                    "avg_return": round(sub_ret, 2),
                }

        # Breakdown by Setup Type
        by_setup: dict[str, dict[str, Any]] = {}
        for st in [s.value for s in SignalType]:
            subset = [o for o in outcomes if o.signal.signal_type.value == st]
            if subset:
                sub_wins = sum(1 for o in subset if o.status in ("HIT_T1", "HIT_T2"))
                sub_ret = sum(o.realized_pnl_pct for o in subset) / len(subset)
                by_setup[st] = {
                    "count": len(subset),
                    "win_rate": round(sub_wins / len(subset) * 100.0, 1),
                    "avg_return": round(sub_ret, 2),
                }

        return BacktestReport(
            total_signals=total,
            winning_signals=wins,
            losing_signals=losses,
            expired_signals=expired,
            win_rate_pct=round(win_rate, 1),
            profit_factor=round(profit_factor, 2),
            avg_return_pct=round(avg_return, 2),
            avg_mfe_pct=round(avg_mfe, 2),
            avg_mae_pct=round(avg_mae, 2),
            max_drawdown_pct=round(max_dd, 2),
            avg_holding_bars=round(avg_bars, 1),
            by_regime=by_regime,
            by_setup=by_setup,
            outcomes=outcomes,
        )

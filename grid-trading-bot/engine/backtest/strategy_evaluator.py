"""Multi-Strategy Stock Backtesting & Simulation Engine for Indian Equities.

Simulates candle-by-candle forward execution across institutional strategies:
1. Minervini VCP Breakout (BB Bandwidth <= 8.5% + Volume Expansion)
2. Pocket Pivot Momentum (Stage-2 10/20 EMA bounce with Pocket Volume)
3. NR7 Volatility Squeeze (7-day narrow range compression)
4. High-Delivery Institutional Breakout (Delivery % >= 50% + Volume >= 1.8x)
5. Combined Confluence (Grade-A setups with multi-pillar alignment)

Generates full scorecards, time-series equity curves, and trade journals.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from config.constants import SignalType
from engine.data.base import OHLCVCandle
from engine.indicators.technical import TechnicalIndicatorEngine
from engine.signals.setups import TechnicalSetupDetector
from utils.logger import get_logger

log = get_logger("backtest_evaluator")


@dataclass
class BacktestTradeRecord:
    trade_id: str
    symbol: str
    strategy: str
    entry_date: str
    entry_price: float
    exit_date: str
    exit_price: float
    exit_reason: str              # HIT_T1, HIT_T2, STOPPED_OUT, TRAILING_SL, TIMEOUT
    shares: int
    pnl_amount: float
    pnl_pct: float
    r_multiple: float
    holding_days: int
    is_win: bool
    stop_loss: float
    target_1: float
    target_2: float


@dataclass
class EquityCurvePoint:
    date: str
    portfolio_value: float
    benchmark_value: float
    drawdown_pct: float


@dataclass
class StrategyBacktestResult:
    symbol: str
    strategy: str
    start_date: str
    end_date: str
    initial_capital: float
    final_capital: float
    net_pnl_amount: float
    net_pnl_pct: float

    total_trades: int
    winning_trades: int
    losing_trades: int
    win_rate_pct: float
    profit_factor: float
    expectancy_r: float
    max_drawdown_pct: float
    sharpe_ratio: float

    avg_winner_amount: float
    avg_loser_amount: float
    max_win_streak: int
    max_loss_streak: int
    avg_holding_days: float

    equity_curve: list[EquityCurvePoint] = field(default_factory=list)
    trades: list[BacktestTradeRecord] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "symbol": self.symbol,
            "strategy": self.strategy,
            "start_date": self.start_date,
            "end_date": self.end_date,
            "initial_capital": round(self.initial_capital, 2),
            "final_capital": round(self.final_capital, 2),
            "net_pnl_amount": round(self.net_pnl_amount, 2),
            "net_pnl_pct": round(self.net_pnl_pct, 2),
            "total_trades": self.total_trades,
            "total_signals": self.total_trades,
            "winning_trades": self.winning_trades,
            "winning_signals": self.winning_trades,
            "losing_trades": self.losing_trades,
            "losing_signals": self.losing_trades,
            "win_rate_pct": round(self.win_rate_pct, 1),
            "profit_factor": round(self.profit_factor, 2),
            "expectancy_r": round(self.expectancy_r, 2),
            "max_drawdown_pct": round(self.max_drawdown_pct, 2),
            "sharpe_ratio": round(self.sharpe_ratio, 2),
            "avg_winner_amount": round(self.avg_winner_amount, 2),
            "avg_loser_amount": round(self.avg_loser_amount, 2),
            "max_win_streak": self.max_win_streak,
            "max_loss_streak": self.max_loss_streak,
            "avg_holding_days": round(self.avg_holding_days, 1),
            "equity_curve": [
                {
                    "date": p.date,
                    "portfolio_value": round(p.portfolio_value, 2),
                    "benchmark_value": round(p.benchmark_value, 2),
                    "drawdown_pct": round(p.drawdown_pct, 2),
                }
                for p in self.equity_curve
            ],
            "trades": [
                {
                    "trade_id": t.trade_id,
                    "symbol": t.symbol,
                    "strategy": t.strategy,
                    "entry_date": t.entry_date,
                    "entry_price": round(t.entry_price, 2),
                    "exit_date": t.exit_date,
                    "exit_price": round(t.exit_price, 2),
                    "exit_reason": t.exit_reason,
                    "shares": t.shares,
                    "pnl_amount": round(t.pnl_amount, 2),
                    "pnl_pct": round(t.pnl_pct, 2),
                    "r_multiple": round(t.r_multiple, 2),
                    "holding_days": t.holding_days,
                    "is_win": t.is_win,
                    "stop_loss": round(t.stop_loss, 2),
                    "target_1": round(t.target_1, 2),
                    "target_2": round(t.target_2, 2),
                }
                for t in self.trades
            ],
        }


class MultiStrategyBacktester:
    """Executes multi-strategy historical simulations on candle series."""

    def __init__(self) -> None:
        self.indicator_engine = TechnicalIndicatorEngine()
        self.setup_detector = TechnicalSetupDetector()

    def run_simulation(
        self,
        symbol: str,
        candles: list[OHLCVCandle],
        strategy: str = "VCP_BREAKOUT",
        initial_capital: float = 500000.0,
        risk_pct_per_trade: float = 1.0,
        target_1_rr: float = 2.0,
        target_2_rr: float = 3.5,
        use_trailing_sl: bool = True,
        max_holding_bars: int = 30,
    ) -> StrategyBacktestResult:
        """Simulates strategy candle-by-candle with dynamic risk accounting."""
        if len(candles) < 50:
            # Insufficient data
            return StrategyBacktestResult(
                symbol=symbol,
                strategy=strategy,
                start_date="",
                end_date="",
                initial_capital=initial_capital,
                final_capital=initial_capital,
                net_pnl_amount=0.0,
                net_pnl_pct=0.0,
                total_trades=0,
                winning_trades=0,
                losing_trades=0,
                win_rate_pct=0.0,
                profit_factor=0.0,
                expectancy_r=0.0,
                max_drawdown_pct=0.0,
                sharpe_ratio=0.0,
                avg_winner_amount=0.0,
                avg_loser_amount=0.0,
                max_win_streak=0,
                max_loss_streak=0,
                avg_holding_days=0.0,
            )

        start_date = candles[0].timestamp[:10]
        end_date = candles[-1].timestamp[:10]

        capital = initial_capital
        peak_capital = initial_capital
        max_drawdown_pct = 0.0

        equity_curve: list[EquityCurvePoint] = []
        trades: list[BacktestTradeRecord] = []

        active_trade: dict[str, Any] | None = None
        trade_counter = 0

        # Benchmark baseline (buy and hold)
        initial_price = candles[49].close
        benchmark_capital = initial_capital

        daily_returns: list[float] = []
        prev_capital = initial_capital

        slippage_pct = 0.001  # 0.10% institutional slippage per trade
        pending_signal: dict[str, Any] | None = None

        # Warm-up 50 candles for indicators
        for i in range(49, len(candles)):
            curr_candle = candles[i]
            window = candles[: i + 1]
            snap = self.indicator_engine.compute_snapshot(symbol, window, "1d")

            # Update Benchmark Growth
            benchmark_val = (curr_candle.close / initial_price) * initial_capital if initial_price > 0 else initial_capital

            # 1. Fill Pending Entry at Next-Bar Open (t+1 execution)
            if active_trade is None and pending_signal is not None:
                entry_price = round(curr_candle.open * (1.0 + slippage_pct), 2)
                atr = snap.atr or (entry_price * 0.02)
                stype = pending_signal["strategy"].upper()

                if "VCP" in stype:
                    sl = entry_price - (atr * 1.0)
                elif "NR7" in stype:
                    sl = entry_price - (atr * 0.7)
                elif "POCKET" in stype:
                    sl = (snap.ema_20 or entry_price) - (atr * 0.3)
                else:
                    sl = entry_price - (atr * 1.2)

                sl = round(max(sl, entry_price * 0.94), 2)  # Max 6% SL
                risk_per_share = entry_price - sl

                if risk_per_share > 0:
                    t1 = round(entry_price + (risk_per_share * target_1_rr), 2)
                    t2 = round(entry_price + (risk_per_share * target_2_rr), 2)

                    # Position sizing based on account risk
                    risk_capital = capital * (risk_pct_per_trade / 100.0)
                    shares = max(1, int(risk_capital / risk_per_share))

                    # Cap position size to 25% of total capital
                    max_shares_by_alloc = int((capital * 0.25) / entry_price)
                    shares = min(shares, max(1, max_shares_by_alloc))

                    trade_counter += 1
                    active_trade = {
                        "entry_date": curr_candle.timestamp[:10],
                        "entry_price": entry_price,
                        "stop_loss": sl,
                        "initial_sl": sl,
                        "target_1": t1,
                        "target_2": t2,
                        "risk_per_share": risk_per_share,
                        "shares": shares,
                        "holding_days": 0,
                        "t1_hit": False,
                    }
                pending_signal = None

            # 2. Manage Active Trade
            if active_trade is not None:
                active_trade["holding_days"] += 1
                entry_price = active_trade["entry_price"]
                sl = active_trade["stop_loss"]
                t1 = active_trade["target_1"]
                t2 = active_trade["target_2"]
                risk_per_share = active_trade["risk_per_share"]
                shares = active_trade["shares"]

                exit_reason = None
                exit_price = None

                # Check Stop Loss First (Conservative collision handling)
                if curr_candle.low <= sl:
                    exit_reason = "STOPPED_OUT"
                    raw_exit = min(curr_candle.open, sl) if curr_candle.open < sl else sl
                    exit_price = round(raw_exit * (1.0 - slippage_pct), 2)
                # Check Target 2
                elif curr_candle.high >= t2:
                    exit_reason = "HIT_T2"
                    exit_price = round(t2 * (1.0 - slippage_pct), 2)
                # Check Target 1 (Lock in partial / move SL to Breakeven)
                elif curr_candle.high >= t1 and not active_trade.get("t1_hit"):
                    active_trade["t1_hit"] = True
                    active_trade["stop_loss"] = entry_price  # Move SL to breakeven
                # Check Trailing SL
                elif use_trailing_sl and snap.ema_20 and snap.atr:
                    trail_candidate = snap.ema_20 - (snap.atr * 0.3)
                    if trail_candidate > active_trade["stop_loss"]:
                        active_trade["stop_loss"] = trail_candidate
                # Check Max Holding Timeout
                elif active_trade["holding_days"] >= max_holding_bars:
                    exit_reason = "TIMEOUT"
                    exit_price = round(curr_candle.close * (1.0 - slippage_pct), 2)

                # Execute Exit if triggered
                if exit_reason and exit_price is not None:
                    pnl_amount = (exit_price - entry_price) * shares
                    pnl_pct = ((exit_price - entry_price) / entry_price) * 100.0
                    r_outcome = (exit_price - entry_price) / risk_per_share if risk_per_share > 0 else 0.0

                    capital += pnl_amount
                    is_win = pnl_amount > 0

                    trades.append(
                        BacktestTradeRecord(
                            trade_id=f"T-{trade_counter:03d}",
                            symbol=symbol,
                            strategy=strategy,
                            entry_date=active_trade["entry_date"],
                            entry_price=entry_price,
                            exit_date=curr_candle.timestamp[:10],
                            exit_price=exit_price,
                            exit_reason=exit_reason,
                            shares=shares,
                            pnl_amount=pnl_amount,
                            pnl_pct=pnl_pct,
                            r_multiple=r_outcome,
                            holding_days=active_trade["holding_days"],
                            is_win=is_win,
                            stop_loss=active_trade["initial_sl"],
                            target_1=t1,
                            target_2=t2,
                        )
                    )
                    active_trade = None

            # 3. Check for New Entry Setup (Signal generated at t close, to be filled at t+1 open)
            if active_trade is None and pending_signal is None and i < len(candles) - 1:
                is_entry = False
                stype = strategy.upper()

                if "VCP" in stype:
                    vcp = self.setup_detector._detect_vcp(snap)
                    is_entry = vcp.is_triggered
                elif "POCKET" in stype:
                    pp = self.setup_detector._detect_pocket_pivot(snap)
                    is_entry = pp.is_triggered
                elif "NR7" in stype:
                    nr7 = self.setup_detector._detect_nr7(snap)
                    is_entry = nr7.is_triggered
                elif "DELIVERY" in stype:
                    # In historical backtest without separate delivery feed, require breakout with volume
                    hdb = self.setup_detector._detect_high_delivery_breakout(snap, None, delivery_pct=None)
                    is_entry = hdb.is_triggered
                elif "COMBINED" in stype:
                    setups = self.setup_detector.evaluate_all_setups(snap, None, delivery_pct=None)
                    is_entry = len(setups) > 0 and setups[0].quality_score >= 13.5
                else:
                    bo = self.setup_detector._detect_breakout(snap)
                    is_entry = bo.is_triggered

                if is_entry:
                    pending_signal = {"strategy": strategy}

            # 3. Track Equity Curve & Daily Drawdown
            if capital > peak_capital:
                peak_capital = capital
            curr_dd = ((peak_capital - capital) / peak_capital * 100.0) if peak_capital > 0 else 0.0
            if curr_dd > max_drawdown_pct:
                max_drawdown_pct = curr_dd

            equity_curve.append(
                EquityCurvePoint(
                    date=curr_candle.timestamp[:10],
                    portfolio_value=capital,
                    benchmark_value=benchmark_val,
                    drawdown_pct=curr_dd,
                )
            )

            # Daily return tracking for Sharpe
            daily_ret = (capital - prev_capital) / prev_capital if prev_capital > 0 else 0.0
            daily_returns.append(daily_ret)
            prev_capital = capital

        # 4. Performance Statistics Calculation
        total_trades = len(trades)
        winning_trades = sum(1 for t in trades if t.is_win)
        losing_trades = sum(1 for t in trades if not t.is_win)
        win_rate_pct = (winning_trades / total_trades * 100.0) if total_trades > 0 else 0.0

        gross_profits = sum(t.pnl_amount for t in trades if t.pnl_amount > 0)
        gross_losses = abs(sum(t.pnl_amount for t in trades if t.pnl_amount < 0))
        profit_factor = (gross_profits / gross_losses) if gross_losses > 0 else (gross_profits if gross_profits > 0 else 0.0)

        total_r = sum(t.r_multiple for t in trades)
        expectancy_r = (total_r / total_trades) if total_trades > 0 else 0.0

        avg_winner = (gross_profits / winning_trades) if winning_trades > 0 else 0.0
        avg_loser = (gross_losses / losing_trades) if losing_trades > 0 else 0.0
        avg_holding = (sum(t.holding_days for t in trades) / total_trades) if total_trades > 0 else 0.0

        # Streaks
        cur_w_streak = 0
        max_w_streak = 0
        cur_l_streak = 0
        max_l_streak = 0

        for t in trades:
            if t.is_win:
                cur_w_streak += 1
                cur_l_streak = 0
                max_w_streak = max(max_w_streak, cur_w_streak)
            else:
                cur_l_streak += 1
                cur_w_streak = 0
                max_l_streak = max(max_l_streak, cur_l_streak)

        # Sharpe Ratio (Annualized with 252 days)
        if len(daily_returns) > 1:
            mean_ret = sum(daily_returns) / len(daily_returns)
            variance = sum((r - mean_ret) ** 2 for r in daily_returns) / (len(daily_returns) - 1)
            std_dev = math.sqrt(variance)
            sharpe = (mean_ret / std_dev * math.sqrt(252)) if std_dev > 0 else 0.0
        else:
            sharpe = 0.0

        net_pnl_amt = capital - initial_capital
        net_pnl_pct = (net_pnl_amt / initial_capital * 100.0) if initial_capital > 0 else 0.0

        return StrategyBacktestResult(
            symbol=symbol,
            strategy=strategy,
            start_date=start_date,
            end_date=end_date,
            initial_capital=initial_capital,
            final_capital=capital,
            net_pnl_amount=net_pnl_amt,
            net_pnl_pct=net_pnl_pct,
            total_trades=total_trades,
            winning_trades=winning_trades,
            losing_trades=losing_trades,
            win_rate_pct=win_rate_pct,
            profit_factor=profit_factor,
            expectancy_r=expectancy_r,
            max_drawdown_pct=max_drawdown_pct,
            sharpe_ratio=sharpe,
            avg_winner_amount=avg_winner,
            avg_loser_amount=avg_loser,
            max_win_streak=max_w_streak,
            max_loss_streak=max_l_streak,
            avg_holding_days=avg_holding,
            equity_curve=equity_curve,
            trades=trades,
        )

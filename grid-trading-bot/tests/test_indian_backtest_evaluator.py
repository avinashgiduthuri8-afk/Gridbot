"""Tests for Scanner Backtest & MFE/MAE Evaluator."""

from datetime import datetime, timezone

from config.constants import SignalStrength, SignalType
from engine.backtest.evaluator import ScannerBacktestEvaluator
from engine.data.base import OHLCVCandle
from engine.risk_reward.rr_calculator import RiskRewardPlan
from engine.signals.scoring import ScoreBreakdown, ScoredSignal


def _make_forward_candles(prices: list[float]) -> list[OHLCVCandle]:
    candles = []
    for p in prices:
        candles.append(
            OHLCVCandle(
                timestamp=datetime.now(timezone.utc),
                open=p * 0.998,
                high=p * 1.008,
                low=p * 0.992,
                close=p,
                volume=100000.0,
            )
        )
    return candles


def test_backtest_signal_hits_target_1():
    evaluator = ScannerBacktestEvaluator()
    sig = ScoredSignal(
        symbol="TCS",
        signal_type=SignalType.BREAKOUT,
        strength=SignalStrength.VERY_STRONG,
        total_score=92.0,
        breakdown=ScoreBreakdown(total_score=92.0),
        risk_reward=RiskRewardPlan(
            symbol="TCS",
            entry_price=3000.0,
            stop_loss=2940.0,
            target_1=3120.0,
            target_2=3200.0,
            risk_amount=60.0,
            reward_amount=120.0,
            risk_percentage=2.0,
            reward_percentage=4.0,
            rr_ratio=2.0,
            is_acceptable=True,
        ),
        market_regime="STRONG_BULLISH",
    )

    # Future price rises from 3000 to 3130 -> hits T1
    forward_candles = _make_forward_candles([3020.0, 3050.0, 3080.0, 3130.0, 3140.0])
    outcome = evaluator.evaluate_signal_forward(sig, forward_candles)

    assert outcome.status == "HIT_T1"
    assert outcome.realized_pnl_pct == 4.0
    assert outcome.mfe_pct > 4.0
    assert outcome.holding_bars == 4


def test_backtest_signal_stopped_out():
    evaluator = ScannerBacktestEvaluator()
    sig = ScoredSignal(
        symbol="INFY",
        signal_type=SignalType.PULLBACK,
        strength=SignalStrength.STRONG,
        total_score=85.0,
        breakdown=ScoreBreakdown(total_score=85.0),
        risk_reward=RiskRewardPlan(
            symbol="INFY",
            entry_price=1500.0,
            stop_loss=1470.0,
            target_1=1560.0,
            target_2=1600.0,
            risk_amount=30.0,
            reward_amount=60.0,
            risk_percentage=2.0,
            reward_percentage=4.0,
            rr_ratio=2.0,
            is_acceptable=True,
        ),
        market_regime="NEUTRAL",
    )

    # Future price drops to 1460 -> stopped out
    forward_candles = _make_forward_candles([1490.0, 1480.0, 1465.0, 1450.0])
    outcome = evaluator.evaluate_signal_forward(sig, forward_candles)

    assert outcome.status == "STOPPED_OUT"
    assert outcome.realized_pnl_pct == -2.0
    assert outcome.mae_pct < 0.0


def test_backtest_report_generation():
    evaluator = ScannerBacktestEvaluator()
    # Build multiple outcomes
    outcomes = []
    # 2 winning outcomes, 1 losing outcome
    for i in range(2):
        sig = ScoredSignal(
            symbol=f"STOCK_{i}",
            signal_type=SignalType.BREAKOUT,
            strength=SignalStrength.STRONG,
            total_score=85.0,
            breakdown=ScoreBreakdown(total_score=85.0),
            risk_reward=RiskRewardPlan(
                symbol=f"STOCK_{i}", entry_price=100.0, stop_loss=98.0, target_1=104.0, target_2=108.0,
                risk_amount=2.0, reward_amount=4.0, risk_percentage=2.0, reward_percentage=4.0, rr_ratio=2.0, is_acceptable=True
            ),
            market_regime="BULLISH",
        )
        outcomes.append(evaluator.evaluate_signal_forward(sig, _make_forward_candles([101.0, 103.0, 105.0])))

    sig_loss = ScoredSignal(
        symbol="STOCK_LOSS",
        signal_type=SignalType.BREAKOUT,
        strength=SignalStrength.VALID,
        total_score=75.0,
        breakdown=ScoreBreakdown(total_score=75.0),
        risk_reward=RiskRewardPlan(
            symbol="STOCK_LOSS", entry_price=100.0, stop_loss=98.0, target_1=104.0, target_2=108.0,
            risk_amount=2.0, reward_amount=4.0, risk_percentage=2.0, reward_percentage=4.0, rr_ratio=2.0, is_acceptable=True
        ),
        market_regime="BEARISH",
    )
    outcomes.append(evaluator.evaluate_signal_forward(sig_loss, _make_forward_candles([99.0, 97.0])))

    report = evaluator.generate_report(outcomes)
    assert report.total_signals == 3
    assert report.winning_signals == 2
    assert report.losing_signals == 1
    assert report.win_rate_pct == 66.7
    assert report.profit_factor > 1.0

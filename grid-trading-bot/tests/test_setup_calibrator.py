"""Tests for Setup Calibration and Monotonic Score Curve."""

from engine.backtest.setup_calibrator import SetupCalibrator


def test_setup_calibrator_expectancy_and_tiers():
    calibrator = SetupCalibrator()

    mock_trades = [
        # Tier 1: Score 92 -> 3 Wins, 0 Losses (100% win rate)
        {"status": "HIT_T1", "signal_type": "VCP_BREAKOUT", "market_regime": "STRONG_BULLISH", "score": 94.0, "entry_price": 100.0, "stop_loss": 95.0, "target_1": 110.0},
        {"status": "HIT_T1", "signal_type": "VCP_BREAKOUT", "market_regime": "STRONG_BULLISH", "score": 92.0, "entry_price": 100.0, "stop_loss": 95.0, "target_1": 110.0},
        {"status": "HIT_T2", "signal_type": "HIGH_DELIVERY_BREAKOUT", "market_regime": "BULLISH", "score": 91.0, "entry_price": 100.0, "stop_loss": 95.0, "target_1": 110.0},

        # Tier 2: Score 86 -> 2 Wins, 1 Loss (66.7% win rate)
        {"status": "HIT_T1", "signal_type": "POCKET_PIVOT", "market_regime": "BULLISH", "score": 88.0, "entry_price": 100.0, "stop_loss": 95.0, "target_1": 110.0},
        {"status": "HIT_T1", "signal_type": "NR7_COMPRESSION", "market_regime": "BULLISH", "score": 86.0, "entry_price": 100.0, "stop_loss": 95.0, "target_1": 110.0},
        {"status": "STOPPED_OUT", "signal_type": "BREAKOUT", "market_regime": "NEUTRAL", "score": 85.0, "entry_price": 100.0, "stop_loss": 95.0, "target_1": 110.0},

        # Tier 3: Score 81 -> 1 Win, 2 Losses (33.3% win rate)
        {"status": "HIT_T1", "signal_type": "PULLBACK", "market_regime": "NEUTRAL", "score": 82.0, "entry_price": 100.0, "stop_loss": 95.0, "target_1": 110.0},
        {"status": "STOPPED_OUT", "signal_type": "BREAKOUT", "market_regime": "NEUTRAL", "score": 81.0, "entry_price": 100.0, "stop_loss": 95.0, "target_1": 110.0},
        {"status": "STOPPED_OUT", "signal_type": "PULLBACK", "market_regime": "BEARISH", "score": 80.0, "entry_price": 100.0, "stop_loss": 95.0, "target_1": 110.0},
    ]

    result = calibrator.calibrate(mock_trades)

    assert result.total_trades == 9
    assert result.overall_win_rate_pct == (6 / 9 * 100.0)
    assert result.overall_total_r > 0
    assert result.is_monotonically_calibrated is True

    # Tier 1 win rate (100%) > Tier 3 win rate (33.3%)
    t1_wr = result.score_tier_metrics["TIER_1_90_PLUS"]["win_rate_pct"]
    t3_wr = result.score_tier_metrics["TIER_3_80_84"]["win_rate_pct"]
    assert t1_wr == 100.0
    assert t3_wr == 33.3
    assert t1_wr > t3_wr

    # Setup metrics
    assert "VCP_BREAKOUT" in result.setup_metrics
    assert result.setup_metrics["VCP_BREAKOUT"]["wins"] == 2

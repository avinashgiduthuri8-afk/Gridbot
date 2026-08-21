"""Tests for Scanner Daemon and Telegram Notifier."""

import pytest
from unittest.mock import MagicMock

from config.constants import SignalStrength, SignalType
from engine.signals.scoring import ScoredSignal, ScoreBreakdown
from engine.risk_reward.rr_calculator import RiskRewardPlan
from services.scanner_daemon import ScannerDaemon
from services.telegram_notifier import TelegramNotifier


@pytest.mark.asyncio
async def test_telegram_notifier_mock_dispatch():
    notifier = TelegramNotifier(bot_token="", chat_id="")
    assert not notifier.is_configured

    sig = ScoredSignal(
        symbol="RELIANCE.NS",
        signal_type=SignalType.VCP_BREAKOUT,
        strength=SignalStrength.STRONG,
        total_score=86.5,
        breakdown=ScoreBreakdown(
            technical_trend=18.0,
            momentum=14.0,
            volume=14.0,
            price_action=13.0,
            multi_timeframe=14.0,
            market_regime=9.0,
            sector_strength=4.5,
            news_sentiment=4.0,
            total_score=86.5,
        ),
        risk_reward=RiskRewardPlan(
            symbol="RELIANCE.NS",
            entry_price=3000.0,
            stop_loss=2910.0,
            target_1=3180.0,
            target_2=3315.0,
            risk_amount=90.0,
            reward_amount=180.0,
            risk_percentage=3.0,
            reward_percentage=6.0,
            rr_ratio=2.0,
            is_acceptable=True,
        ),
        confidence="HIGH",
        sector="Energy",
        sector_rank=1,
        market_regime="BULLISH",
        setup_reason="VCP contraction breakout",
        confirmation_reason="2.1x volume",
        rationale=["High Alpha", "Clean Squeeze"],
        timestamp="2026-08-21T10:00:00Z",
    )

    success = await notifier.send_signal_alert(sig)
    assert success is True


@pytest.mark.asyncio
async def test_scanner_daemon_lifecycle():
    mock_scanner = MagicMock()
    daemon = ScannerDaemon(
        scanner=mock_scanner,
        interval_seconds=60,
        universe_name="NIFTY_50",
    )

    assert not daemon.is_running
    daemon.start()
    assert daemon.is_running
    daemon.stop()
    assert not daemon.is_running

"""Tests for Signal Ledger, Lifecycle Transitions, and Performance Stats."""

import pytest
from httpx import AsyncClient, ASGITransport

from dashboard.app import create_app
from storage.database import Database
from storage.repositories import Repositories
from storage.repositories.signal_ledger import SignalLedgerRepository
from storage.repositories.signals import SignalRepository
from engine.signals.scoring import ScoredSignal, ScoreBreakdown
from engine.risk_reward.rr_calculator import RiskRewardPlan
from config.constants import SignalStrength, SignalType


@pytest.fixture
async def test_db():
    db = Database(":memory:")
    await db.connect()
    await db.migrate()
    yield db
    await db.close()


@pytest.mark.asyncio
async def test_signal_ledger_r_multiple_calculations(test_db):
    sig_repo = SignalRepository(test_db)
    ledger_repo = SignalLedgerRepository(test_db)

    # 1. Create a winning signal (Hits Target 1: Entry 1000, SL 950, T1 1100 -> +2.0R)
    sig1 = ScoredSignal(
        symbol="TCS.NS",
        signal_type=SignalType.VCP_BREAKOUT,
        strength=SignalStrength.STRONG,
        total_score=85.0,
        breakdown=ScoreBreakdown(),
        risk_reward=RiskRewardPlan(
            symbol="TCS.NS",
            entry_price=1000.0,
            stop_loss=950.0,
            target_1=1100.0,
            target_2=1175.0,
            risk_amount=50.0,
            reward_amount=100.0,
            risk_percentage=5.0,
            reward_percentage=10.0,
            rr_ratio=2.0,
            is_acceptable=True,
        ),
        confidence="HIGH",
        sector="IT",
        sector_rank=1,
        market_regime="BULLISH",
        timestamp="2026-08-21T10:00:00Z",
    )
    sig_id1 = await sig_repo.save_signal(sig1)
    await ledger_repo.resolve_signal(sig_id1, "HIT_T1", 10.0)

    # 2. Create a stopped out signal (Entry 2000, SL 1900, T1 2200 -> -1.0R)
    sig2 = ScoredSignal(
        symbol="INFY.NS",
        signal_type=SignalType.PULLBACK,
        strength=SignalStrength.VALID,
        total_score=75.0,
        breakdown=ScoreBreakdown(),
        risk_reward=RiskRewardPlan(
            symbol="INFY.NS",
            entry_price=2000.0,
            stop_loss=1900.0,
            target_1=2200.0,
            target_2=2350.0,
            risk_amount=100.0,
            reward_amount=200.0,
            risk_percentage=5.0,
            reward_percentage=10.0,
            rr_ratio=2.0,
            is_acceptable=True,
        ),
        confidence="MEDIUM",
        sector="IT",
        sector_rank=1,
        market_regime="BULLISH",
        timestamp="2026-08-21T10:00:00Z",
    )
    sig_id2 = await sig_repo.save_signal(sig2)
    await ledger_repo.resolve_signal(sig_id2, "STOPPED_OUT", -5.0)

    # Check stats
    stats = await ledger_repo.get_ledger_stats()
    assert stats.total_signals == 2
    assert stats.winning_signals == 1
    assert stats.losing_signals == 1
    assert stats.win_rate_pct == 50.0
    assert stats.total_r_multiple == 1.0  # +2.0R - 1.0R = +1.0R
    assert stats.profit_factor == 2.0     # 2.0 / 1.0 = 2.0


@pytest.mark.asyncio
async def test_signal_ledger_live_evaluation(test_db):
    sig_repo = SignalRepository(test_db)
    ledger_repo = SignalLedgerRepository(test_db)

    # Create an OPEN signal (Entry 500, SL 480, T1 540)
    sig = ScoredSignal(
        symbol="SBIN.NS",
        signal_type=SignalType.BREAKOUT,
        strength=SignalStrength.STRONG,
        total_score=82.0,
        breakdown=ScoreBreakdown(),
        risk_reward=RiskRewardPlan(
            symbol="SBIN.NS",
            entry_price=500.0,
            stop_loss=480.0,
            target_1=540.0,
            target_2=570.0,
            risk_amount=20.0,
            reward_amount=40.0,
            risk_percentage=4.0,
            reward_percentage=8.0,
            rr_ratio=2.0,
            is_acceptable=True,
        ),
        confidence="HIGH",
        sector="Bank",
        sector_rank=2,
        market_regime="BULLISH",
        timestamp="2026-08-21T10:00:00Z",
    )
    await sig_repo.save_signal(sig)

    active_before = await ledger_repo.get_active_signals()
    assert len(active_before) == 1

    # Simulate price rally to ₹545 (Hits Target 1)
    resolved = await ledger_repo.evaluate_active_signals({"SBIN": 545.0})
    assert len(resolved) == 1
    assert resolved[0]["status"] == "HIT_T1"

    active_after = await ledger_repo.get_active_signals()
    assert len(active_after) == 0


@pytest.mark.asyncio
async def test_ledger_rest_api_endpoints(test_db):
    app = create_app()
    app.state.db = test_db
    app.state.repos = Repositories(test_db)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        res_stats = await client.get("/api/ledger/stats")
        assert res_stats.status_code == 200
        data_stats = res_stats.json()
        assert "total_signals" in data_stats
        assert "win_rate_pct" in data_stats
        assert "total_r_multiple" in data_stats

        res_active = await client.get("/api/ledger/active")
        assert res_active.status_code == 200
        assert isinstance(res_active.json(), list)

        res_eval = await client.post("/api/ledger/evaluate", json={"RELIANCE": 3100.0})
        assert res_eval.status_code == 200
        assert "resolved_count" in res_eval.json()

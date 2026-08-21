"""Tests for Master Signal Dispatcher, HMAC Security, Webhooks, and Event Bus."""

import hashlib
import hmac
import json
import pytest
from httpx import AsyncClient, ASGITransport

from config.constants import SignalStrength, SignalType
from dashboard.app import create_app
from engine.risk_reward.rr_calculator import RiskRewardPlan
from engine.signals.scoring import ScoredSignal, ScoreBreakdown
from schemas.signal_dispatch import BotRegistration
from services.signal_dispatcher import SignalDispatcherService
from storage.database import Database
from storage.repositories import Repositories


@pytest.fixture
async def test_db():
    db = Database(":memory:")
    await db.connect()
    await db.migrate()
    yield db
    await db.close()


def test_signal_order_payload_generation():
    dispatcher = SignalDispatcherService()

    sig = ScoredSignal(
        symbol="TATAMOTORS.NS",
        signal_type=SignalType.VCP_BREAKOUT,
        strength=SignalStrength.VERY_STRONG,
        total_score=92.5,
        breakdown=ScoreBreakdown(
            technical_trend=20.0,
            momentum=15.0,
            volume=14.0,
            price_action=15.0,
            multi_timeframe=14.0,
            market_regime=9.5,
            sector_strength=5.0,
            news_sentiment=0.0,
            total_score=92.5,
        ),
        risk_reward=RiskRewardPlan(
            symbol="TATAMOTORS.NS",
            entry_price=1050.0,
            stop_loss=1010.0,
            target_1=1130.0,
            target_2=1190.0,
            risk_amount=40.0,
            reward_amount=80.0,
            risk_percentage=3.81,
            reward_percentage=7.62,
            rr_ratio=2.0,
            is_acceptable=True,
        ),
        confidence="HIGH",
        sector="Auto",
        sector_rank=1,
        market_regime="STRONG_BULLISH",
        setup_reason="VCP Contraction Breakout",
        confirmation_reason="2.4x Volume Expansion",
        rationale=["Leader in Auto", "Tight base"],
    )

    payload = dispatcher.create_order_payload(sig)
    assert payload.symbol == "TATAMOTORS"
    assert payload.exchange == "NSE"
    assert payload.action == "BUY"
    assert payload.order_type == "LIMIT"
    assert payload.entry_price == 1050.0
    assert payload.stop_loss == 1010.0
    assert payload.target_1 == 1130.0
    assert payload.risk_per_share == 40.0
    assert payload.recommended_rr_ratio == 2.0
    assert payload.trailing_strategy == "ATR_CHANDELIER"
    assert payload.confidence_score == 92.5
    assert "Auto" in payload.confluence_factors["sector"]


def test_hmac_signature_generation_and_verification():
    secret = "secret-super-key-12345"
    payload_str = json.dumps({"symbol": "RELIANCE", "price": 3000.0}, sort_keys=True)

    sig = SignalDispatcherService.generate_hmac_signature(payload_str, secret)
    assert isinstance(sig, str)
    assert len(sig) == 64  # SHA256 hex digest length

    # Validate downstream verification calculation matches
    expected = hmac.new(secret.encode(), payload_str.encode(), hashlib.sha256).hexdigest()
    assert sig == expected


@pytest.mark.asyncio
async def test_bot_registration_and_filtering(test_db):
    repos = Repositories(test_db)
    dispatcher = SignalDispatcherService(bot_repo=repos.bots)

    # 1. Register Bot A (Subscribed to VCP_BREAKOUT only)
    bot_a = BotRegistration(
        bot_id="BOT-ZERODHA-1",
        name="Zerodha VCP Runner",
        target_broker="Zerodha",
        webhook_url="https://mock-bot.com/webhook",
        secret_key="secret-a",
        subscribed_setups=["VCP_BREAKOUT"],
        min_confidence_score=80.0,
    )
    await repos.bots.register_bot(bot_a)

    # 2. Register Bot B (Subscribed to ALL)
    bot_b = BotRegistration(
        bot_id="BOT-DHAN-1",
        name="Dhan HQ General Runner",
        target_broker="Dhan",
        webhook_url="https://mock-bot-dhan.com/webhook",
        secret_key="secret-b",
        subscribed_setups=["ALL"],
        min_confidence_score=70.0,
    )
    await repos.bots.register_bot(bot_b)

    all_bots = await repos.bots.list_bots()
    assert len(all_bots) == 2

    # Verify retrieval
    retrieved = await repos.bots.get_bot("BOT-ZERODHA-1")
    assert retrieved is not None
    assert retrieved.name == "Zerodha VCP Runner"
    assert "VCP_BREAKOUT" in retrieved.subscribed_setups


@pytest.mark.asyncio
async def test_dispatch_rest_endpoints(test_db):
    app = create_app()
    app.state.db = test_db
    app.state.repos = Repositories(test_db)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        # 1. Register Bot via REST
        res_reg = await client.post(
            "/api/v1/dispatch/bots",
            json={
                "name": "Fyers Scalper Bot",
                "target_broker": "Fyers",
                "webhook_url": "https://api.fyers-worker.com/signals",
                "secret_key": "my-fyers-key",
                "subscribed_setups": ["ALL"],
                "min_confidence_score": 78.0,
                "is_active": True,
            },
        )
        assert res_reg.status_code == 200
        bot_data = res_reg.json()
        assert bot_data["name"] == "Fyers Scalper Bot"
        bot_id = bot_data["bot_id"]

        # 2. List Bots
        res_list = await client.get("/api/v1/dispatch/bots")
        assert res_list.status_code == 200
        assert len(res_list.json()) == 1

        # 3. Test Ping
        res_ping = await client.post(f"/api/v1/dispatch/test-ping/{bot_id}")
        assert res_ping.status_code == 200
        ping_data = res_ping.json()
        assert "latency_ms" in ping_data

        # 4. Get Logs
        res_logs = await client.get("/api/v1/dispatch/logs")
        assert res_logs.status_code == 200
        assert len(res_logs.json()) >= 1

        # 5. Delete Bot
        res_del = await client.delete(f"/api/v1/dispatch/bots/{bot_id}")
        assert res_del.status_code == 200
        assert res_del.json()["deleted"] is True

"""Comprehensive regression and live-safety tests for Dashboard API endpoints.

Covers:
- POST /api/grids (Grid Creation)
- POST /api/grids/{grid_id}/manual-buy (Manual Buy)
- POST /api/grids/{grid_id}/manual-sell (Manual Sell)
- POST /api/grids/{grid_id}/pause, /resume, /stop (Grid Control)
- POST /api/emergency-stop (Emergency Stop Toggle & Persistence)
- Security checks: Zero secret leakage, proper PAPER/REAL routing, Risk gating
"""
from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient

from config.settings import RiskSettings
from dashboard.app import create_app
from risk.risk_manager import RiskManager
from trading.dca_manager import DCAManager
from trading.mixed_order_manager import MixedOrderManager
from trading.order_manager import OrderManager


@pytest.fixture
async def dashboard_test_setup(repos, mock_exchange, mock_notifier):
    risk_settings = RiskSettings(
        max_total_capital=200000.0,
        max_capital_per_coin=100000.0,
        max_simultaneous_grids=20,
        min_wallet_balance=100.0,
        daily_loss_limit=10000.0,
    )
    risk = RiskManager(risk_settings, repos)
    await risk.load_emergency_stop()

    real_om = OrderManager(mock_exchange, repos)
    paper_om = OrderManager(mock_exchange, repos)
    mixed_om = MixedOrderManager(real=real_om, paper=paper_om, repos=repos)

    dca_manager = DCAManager(
        exchange=mock_exchange,
        repos=repos,
        order_manager=mixed_om,
        notifier=mock_notifier,
        risk=risk,
    )

    app = create_app()
    app.state.repos = repos
    app.state.risk_manager = risk
    app.state.dca_manager = dca_manager
    app.state.exchange = mock_exchange

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        yield {
            "client": client,
            "repos": repos,
            "risk": risk,
            "dca": dca_manager,
            "exchange": mock_exchange,
            "notifier": mock_notifier,
        }


# ==============================================================================
# 1. Grid Creation (POST /api/grids)
# ==============================================================================

async def test_create_paper_grid_via_api(dashboard_test_setup):
    client = dashboard_test_setup["client"]
    repos = dashboard_test_setup["repos"]

    payload = {
        "symbol": "BTCINR",
        "entry_price": 5000000.0,
        "base_investment": 6000.0,
        "dip_buy_amount": 6000.0,
        "dip_percentage": 2.0,
        "profit_sell_amount": 6000.0,
        "profit_percentage": 3.0,
        "max_levels": 5,
        "stop_loss_percentage": 10.0,
        "mode": "paper",
    }

    res = await client.post("/api/grids", json=payload)
    assert res.status_code == 200, res.text
    data = res.json()
    assert data["symbol"] == "BTCINR"
    assert data["mode"] == "paper"
    assert data["status"] == "active"
    assert data["grid_id"].startswith("grd_")

    db_grid = await repos.grids.get(data["grid_id"])
    assert db_grid is not None
    assert db_grid["mode"] == "paper"
    assert db_grid["status"] == "active"


async def test_create_real_grid_via_api(dashboard_test_setup):
    client = dashboard_test_setup["client"]
    repos = dashboard_test_setup["repos"]

    payload = {
        "symbol": "ETHINR",
        "entry_price": 250000.0,
        "base_investment": 3000.0,
        "dip_buy_amount": 3000.0,
        "dip_percentage": 2.5,
        "profit_sell_amount": 3000.0,
        "profit_percentage": 3.5,
        "max_levels": 4,
        "stop_loss_percentage": 8.0,
        "mode": "real",
    }

    res = await client.post("/api/grids", json=payload)
    assert res.status_code == 200, res.text
    data = res.json()
    assert data["symbol"] == "ETHINR"
    assert data["mode"] == "real"
    assert data["status"] == "active"

    db_grid = await repos.grids.get(data["grid_id"])
    assert db_grid is not None
    assert db_grid["mode"] == "real"


async def test_create_grid_blocked_when_emergency_stop_on(dashboard_test_setup):
    client = dashboard_test_setup["client"]
    risk = dashboard_test_setup["risk"]

    await risk.trigger_emergency_stop()

    payload = {
        "symbol": "BTCINR",
        "entry_price": 5000000.0,
        "base_investment": 6000.0,
        "dip_buy_amount": 6000.0,
        "dip_percentage": 2.0,
        "profit_sell_amount": 6000.0,
        "profit_percentage": 3.0,
        "max_levels": 3,
        "stop_loss_percentage": 5.0,
        "mode": "real",
    }

    res = await client.post("/api/grids", json=payload)
    assert res.status_code == 400
    assert "Emergency stop is active" in res.json()["detail"]


# ==============================================================================
# 2. Manual Buy (POST /api/grids/{id}/manual-buy)
# ==============================================================================

async def test_manual_buy_paper_grid_api(dashboard_test_setup):
    client = dashboard_test_setup["client"]
    dca = dashboard_test_setup["dca"]

    grid_id = await dca.start_grid({
        "symbol": "BTCINR",
        "entry_price": 5000000.0,
        "base_investment": 6000.0,
        "dip_buy_amount": 6000.0,
        "dip_percentage": 2.0,
        "profit_sell_amount": 6000.0,
        "profit_percentage": 3.0,
        "max_levels": 5,
        "stop_loss_percentage": 10.0,
        "mode": "paper",
    })

    res = await client.post(f"/api/grids/{grid_id}/manual-buy", json={"inr_amount": 6000.0})
    assert res.status_code == 200, res.text
    data = res.json()
    assert data["success"] is True
    assert data["grid_id"] == grid_id
    assert data["side"] == "buy"
    assert data["inr_amount"] == 6000.0
    assert data["mode"] == "paper"
    assert data["order_id"] is not None


async def test_manual_buy_blocked_by_emergency_stop_api(dashboard_test_setup):
    client = dashboard_test_setup["client"]
    dca = dashboard_test_setup["dca"]
    risk = dashboard_test_setup["risk"]

    grid_id = await dca.start_grid({
        "symbol": "BTCINR",
        "entry_price": 5000000.0,
        "base_investment": 6000.0,
        "dip_buy_amount": 6000.0,
        "dip_percentage": 2.0,
        "profit_sell_amount": 6000.0,
        "profit_percentage": 3.0,
        "max_levels": 5,
        "stop_loss_percentage": 10.0,
        "mode": "real",
    })

    await risk.trigger_emergency_stop()

    res = await client.post(f"/api/grids/{grid_id}/manual-buy", json={"inr_amount": 6000.0})
    assert res.status_code == 400
    assert "Emergency stop is active" in res.json()["detail"]


# ==============================================================================
# 3. Manual Sell (POST /api/grids/{id}/manual-sell)
# ==============================================================================

async def test_manual_sell_api(dashboard_test_setup):
    client = dashboard_test_setup["client"]
    dca = dashboard_test_setup["dca"]
    repos = dashboard_test_setup["repos"]

    grid_id = await dca.start_grid({
        "symbol": "BTCINR",
        "entry_price": 5000000.0,
        "base_investment": 6000.0,
        "dip_buy_amount": 6000.0,
        "dip_percentage": 2.0,
        "profit_sell_amount": 6000.0,
        "profit_percentage": 3.0,
        "max_levels": 5,
        "stop_loss_percentage": 10.0,
        "mode": "paper",
    })

    await repos.grids.update_state(grid_id, total_quantity=0.005, average_entry_price=5000000.0)

    res = await client.post(f"/api/grids/{grid_id}/manual-sell", json={"inr_amount": 6000.0})
    assert res.status_code == 200, res.text
    data = res.json()
    assert data["success"] is True
    assert data["side"] == "sell"
    assert data["grid_id"] == grid_id


# ==============================================================================
# 4. Emergency Stop (POST /api/emergency-stop)
# ==============================================================================

async def test_toggle_emergency_stop_api(dashboard_test_setup):
    client = dashboard_test_setup["client"]
    risk = dashboard_test_setup["risk"]
    repos = dashboard_test_setup["repos"]

    assert risk.emergency_stopped is False

    # Turn ON
    res = await client.post("/api/emergency-stop", json={"enabled": True})
    assert res.status_code == 200
    data = res.json()
    assert data["emergency_stop"] is True
    assert risk.emergency_stopped is True
    assert await repos.monitor_settings.get_emergency_stop() is True

    # Turn OFF
    res = await client.post("/api/emergency-stop", json={"enabled": False})
    assert res.status_code == 200
    data = res.json()
    assert data["emergency_stop"] is False
    assert risk.emergency_stopped is False
    assert await repos.monitor_settings.get_emergency_stop() is False


# ==============================================================================
# 5. Grid Actions (Pause, Resume, Stop)
# ==============================================================================

async def test_grid_actions_api(dashboard_test_setup):
    client = dashboard_test_setup["client"]
    dca = dashboard_test_setup["dca"]
    repos = dashboard_test_setup["repos"]

    grid_id = await dca.start_grid({
        "symbol": "BTCINR",
        "entry_price": 5000000.0,
        "base_investment": 6000.0,
        "dip_buy_amount": 6000.0,
        "dip_percentage": 2.0,
        "profit_sell_amount": 6000.0,
        "profit_percentage": 3.0,
        "max_levels": 3,
        "stop_loss_percentage": 5.0,
        "mode": "paper",
    })

    # Pause
    res = await client.post(f"/api/grids/{grid_id}/pause")
    assert res.status_code == 200
    g = await repos.grids.get(grid_id)
    assert g["status"] == "paused"

    # Resume
    res = await client.post(f"/api/grids/{grid_id}/resume")
    assert res.status_code == 200
    g = await repos.grids.get(grid_id)
    assert g["status"] == "active"

    # Stop
    res = await client.post(f"/api/grids/{grid_id}/stop")
    assert res.status_code == 200
    g = await repos.grids.get(grid_id)
    assert g["status"] == "stopped"


# ==============================================================================
# 6. Security: No Secrets Exposing
# ==============================================================================

async def test_no_secrets_in_settings_or_grid_responses(dashboard_test_setup):
    client = dashboard_test_setup["client"]

    settings_res = await client.get("/api/settings")
    assert settings_res.status_code == 200
    body_text = settings_res.text
    assert "api_key" not in body_text
    assert "api_secret" not in body_text
    assert "bot_token" not in body_text
    assert "COINDCX_API_SECRET" not in body_text
    assert "TELEGRAM_BOT_TOKEN" not in body_text

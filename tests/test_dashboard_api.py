"""Tests for the read-only dashboard FastAPI backend.

Covers every endpoint: success responses against a seeded database, an
empty database, invalid/missing IDs, and basic error handling. Existing
trading-engine tests are untouched by anything here — the dashboard only
reads via the same Repositories class those tests already exercise.
"""
from __future__ import annotations

import asyncio

import pytest
from fastapi.testclient import TestClient

from config.constants import GridStatus
from dashboard.app import create_app
from storage.models import DCAGridRecord, OrderRecord, TradeHistoryRecord
from utils.helpers import new_id, now_iso


def _seed(*coros):
    """Runs one or more repo-seeding coroutines against a fresh event loop,
    for use inside plain (non-async) TestClient-based tests."""
    loop = asyncio.new_event_loop()
    try:
        for coro in coros:
            loop.run_until_complete(coro)
    finally:
        loop.close()



@pytest.fixture
def dashboard_client(tmp_path, monkeypatch):
    """A TestClient wired to a fresh, empty temp database — never :memory:
    (that hangs under this project's WAL PRAGMA, per this session's own
    prior discovery) and never the real data/grid_bot.db."""
    db_path = str(tmp_path / "dashboard_test.db")
    monkeypatch.setenv("DATABASE_PATH", db_path)
    app = create_app()
    with TestClient(app) as client:
        yield client


def _make_grid(**overrides) -> DCAGridRecord:
    now = now_iso()
    base = dict(
        grid_id=new_id("grd"), symbol="BTCINR", status=GridStatus.ACTIVE.value, mode="paper",
        entry_price=5_000_000.0, base_investment=50_000.0, dip_buy_amount=10_000.0,
        dip_percentage=5.0, profit_sell_amount=15_000.0, profit_percentage=5.0,
        max_levels=10, stop_loss_percentage=20.0, current_level=1,
        total_quantity=0.01, total_investment=50_000.0, average_entry_price=5_000_000.0,
        last_buy_price=5_000_000.0, next_buy_price=4_750_000.0, next_sell_price=5_250_000.0,
        realized_profit=0.0, completed_cycles=0, created_at=now, updated_at=now,
    )
    base.update(overrides)
    return DCAGridRecord(**base)


def _make_order(grid_id: str, **overrides) -> OrderRecord:
    now = now_iso()
    base = dict(
        order_id=new_id("ord"), grid_id=grid_id, exchange_order_id="EX1",
        symbol="BTCINR", side="buy", order_type="market_order", price=5_000_000.0,
        quantity=0.01, filled_quantity=0.01, filled_price=5_000_000.0,
        status="filled", fee=5.0, created_at=now, updated_at=now,
    )
    base.update(overrides)
    return OrderRecord(**base)


def _make_trade(grid_id: str, **overrides) -> TradeHistoryRecord:
    base = dict(
        trade_id=new_id("trd"), grid_id=grid_id, order_id="EX1",
        symbol="BTCINR", side="sell", price=5_200_000.0, quantity=0.01,
        investment_inr=52_000.0, fee=5.2, pnl=1_500.0, executed_at=now_iso(),
    )
    base.update(overrides)
    return TradeHistoryRecord(**base)


# ---------------------------------------------------------------------------
# /health
# ---------------------------------------------------------------------------


def test_health_returns_ok_and_connected(dashboard_client):
    resp = dashboard_client.get("/api/health")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "ok"
    assert data["database_connected"] is True


# ---------------------------------------------------------------------------
# /grids
# ---------------------------------------------------------------------------


def test_list_grids_empty_database(dashboard_client):
    resp = dashboard_client.get("/api/grids")
    assert resp.status_code == 200
    assert resp.json() == {"grids": [], "count": 0}


def test_list_grids_returns_seeded_grid(dashboard_client):
    repos = dashboard_client.app.state.repos
    grid = _make_grid()
    _seed(repos.grids.create(grid))

    resp = dashboard_client.get("/api/grids")
    assert resp.status_code == 200
    data = resp.json()
    assert data["count"] == 1
    assert data["grids"][0]["grid_id"] == grid.grid_id
    assert data["grids"][0]["symbol"] == "BTCINR"


def test_get_grid_by_id_success(dashboard_client):
    repos = dashboard_client.app.state.repos
    grid = _make_grid()
    _seed(repos.grids.create(grid))

    resp = dashboard_client.get(f"/api/grids/{grid.grid_id}")
    assert resp.status_code == 200
    assert resp.json()["grid_id"] == grid.grid_id


def test_get_grid_invalid_id_returns_404(dashboard_client):
    resp = dashboard_client.get("/api/grids/nonexistent_grid_id")
    assert resp.status_code == 404
    assert "not found" in resp.json()["detail"].lower()


# ---------------------------------------------------------------------------
# /positions
# ---------------------------------------------------------------------------


def test_positions_empty_database(dashboard_client):
    resp = dashboard_client.get("/api/positions")
    assert resp.status_code == 200
    assert resp.json() == {"positions": [], "count": 0}


def test_positions_excludes_completed_and_stopped_grids(dashboard_client):
    repos = dashboard_client.app.state.repos
    active = _make_grid(symbol="BTCINR")
    completed = _make_grid(symbol="ETHINR", status=GridStatus.COMPLETED.value, total_quantity=0.0)
    _seed(repos.grids.create(active), repos.grids.create(completed))

    resp = dashboard_client.get("/api/positions")
    data = resp.json()
    assert data["count"] == 1
    assert data["positions"][0]["symbol"] == "BTCINR"


def test_positions_without_price_gives_zero_unrealized(dashboard_client):
    repos = dashboard_client.app.state.repos
    grid = _make_grid()
    _seed(repos.grids.create(grid))

    resp = dashboard_client.get("/api/positions")
    pos = resp.json()["positions"][0]
    assert pos["current_price"] is None
    assert pos["unrealized_pnl"] == 0.0


def test_positions_with_price_override_computes_unrealized(dashboard_client):
    repos = dashboard_client.app.state.repos
    grid = _make_grid(average_entry_price=5_000_000.0, total_quantity=0.01)
    _seed(repos.grids.create(grid))

    resp = dashboard_client.get("/api/positions?prices=BTCINR:5200000")
    pos = resp.json()["positions"][0]
    assert pos["current_price"] == 5_200_000.0
    assert pos["unrealized_pnl"] == pytest.approx(2_000.0)


def test_positions_malformed_price_override_ignored_gracefully(dashboard_client):
    repos = dashboard_client.app.state.repos
    grid = _make_grid()
    _seed(repos.grids.create(grid))

    resp = dashboard_client.get("/api/positions?prices=garbage_no_colon,BTCINR:not_a_number")
    assert resp.status_code == 200
    pos = resp.json()["positions"][0]
    assert pos["current_price"] is None  # malformed entries are skipped, not a crash


# ---------------------------------------------------------------------------
# /orders
# ---------------------------------------------------------------------------


def test_orders_empty_database(dashboard_client):
    resp = dashboard_client.get("/api/orders")
    assert resp.status_code == 200
    assert resp.json() == {"orders": [], "count": 0}


def test_orders_returns_seeded_order(dashboard_client):
    repos = dashboard_client.app.state.repos
    grid = _make_grid()
    order = _make_order(grid.grid_id)
    _seed(repos.grids.create(grid), repos.orders.create(order))

    resp = dashboard_client.get("/api/orders")
    data = resp.json()
    assert data["count"] == 1
    assert data["orders"][0]["order_id"] == order.order_id


def test_orders_filtered_by_grid_id(dashboard_client):
    repos = dashboard_client.app.state.repos
    grid1, grid2 = _make_grid(), _make_grid(symbol="ETHINR")
    order1 = _make_order(grid1.grid_id)
    order2 = _make_order(grid2.grid_id)
    _seed(repos.grids.create(grid1), repos.grids.create(grid2),
          repos.orders.create(order1), repos.orders.create(order2))

    resp = dashboard_client.get(f"/api/orders?grid_id={grid1.grid_id}")
    data = resp.json()
    assert data["count"] == 1
    assert data["orders"][0]["order_id"] == order1.order_id


def test_orders_invalid_limit_rejected(dashboard_client):
    resp = dashboard_client.get("/api/orders?limit=0")
    assert resp.status_code == 422  # FastAPI validation error for limit below ge=1


# ---------------------------------------------------------------------------
# /trade-history
# ---------------------------------------------------------------------------


def test_trade_history_empty_database(dashboard_client):
    resp = dashboard_client.get("/api/trade-history")
    assert resp.status_code == 200
    assert resp.json() == {"trades": [], "count": 0}


def test_trade_history_returns_seeded_trade(dashboard_client):
    repos = dashboard_client.app.state.repos
    grid = _make_grid()
    trade = _make_trade(grid.grid_id)
    _seed(repos.grids.create(grid), repos.trade_history.record(trade))

    resp = dashboard_client.get("/api/trade-history")
    data = resp.json()
    assert data["count"] == 1
    assert data["trades"][0]["trade_id"] == trade.trade_id


# ---------------------------------------------------------------------------
# /portfolio
# ---------------------------------------------------------------------------


def test_portfolio_empty_database(dashboard_client):
    resp = dashboard_client.get("/api/portfolio")
    assert resp.status_code == 200
    data = resp.json()
    assert data["total_realized"] == 0.0
    assert data["combined_total"] == 0.0
    assert data["active_grid_count"] == 0


def test_portfolio_aggregates_grid_counts_by_status(dashboard_client):
    repos = dashboard_client.app.state.repos
    _seed(
        repos.grids.create(_make_grid(status=GridStatus.ACTIVE.value)),
        repos.grids.create(_make_grid(symbol="ETHINR", status=GridStatus.PAUSED.value)),
        repos.grids.create(
            _make_grid(symbol="SOLINR", status=GridStatus.COMPLETED.value, total_quantity=0.0, realized_profit=500.0)
        ),
    )

    resp = dashboard_client.get("/api/portfolio")
    data = resp.json()
    assert data["active_grid_count"] == 1
    assert data["paused_grid_count"] == 1
    assert data["completed_grid_count"] == 1
    assert data["total_realized"] == pytest.approx(500.0)


def test_portfolio_with_price_override(dashboard_client):
    repos = dashboard_client.app.state.repos
    grid = _make_grid(average_entry_price=5_000_000.0, total_quantity=0.01, total_investment=50_000.0)
    _seed(repos.grids.create(grid))

    resp = dashboard_client.get("/api/portfolio?prices=BTCINR:5200000")
    data = resp.json()
    assert data["total_unrealized"] == pytest.approx(2_000.0)


# ---------------------------------------------------------------------------
# /analytics
# ---------------------------------------------------------------------------


def test_analytics_empty_database(dashboard_client):
    resp = dashboard_client.get("/api/analytics")
    assert resp.status_code == 200
    data = resp.json()
    assert data["total_buys"] == 0
    assert data["total_sells"] == 0
    assert data["win_rate_pct"] == 0.0
    assert data["profit_factor"] is None


def test_analytics_counts_buys_and_sells(dashboard_client):
    repos = dashboard_client.app.state.repos
    grid = _make_grid()
    _seed(
        repos.grids.create(grid),
        repos.trade_history.record(_make_trade(grid.grid_id, side="buy", pnl=0.0)),
        repos.trade_history.record(_make_trade(grid.grid_id, side="sell", pnl=100.0)),
    )

    resp = dashboard_client.get("/api/analytics")
    data = resp.json()
    assert data["total_buys"] == 1
    assert data["total_sells"] == 1


# ---------------------------------------------------------------------------
# /settings
# ---------------------------------------------------------------------------


def test_settings_returns_risk_and_operational_fields(dashboard_client):
    resp = dashboard_client.get("/api/settings")
    assert resp.status_code == 200
    data = resp.json()
    assert "risk" in data
    assert "max_total_capital" in data["risk"]
    assert data["emergency_stop_active"] is False


def test_settings_never_exposes_secrets(dashboard_client):
    resp = dashboard_client.get("/api/settings")
    body_text = resp.text.lower()
    # None of these field names (or the test secret values from conftest.py's
    # env defaults) should ever appear in the response.
    for forbidden in ("telegram_bot_token", "coindcx_api_key", "coindcx_api_secret", "test-token", "test-secret"):
        assert forbidden not in body_text


# ---------------------------------------------------------------------------
# OpenAPI / Swagger docs (Step 5)
# ---------------------------------------------------------------------------


def test_openapi_schema_available(dashboard_client):
    resp = dashboard_client.get("/openapi.json")
    assert resp.status_code == 200
    schema = resp.json()
    expected_paths = {
        "/api/health", "/api/grids", "/api/grids/{grid_id}", "/api/positions",
        "/api/orders", "/api/trade-history", "/api/portfolio", "/api/analytics", "/api/settings",
    }
    assert expected_paths.issubset(set(schema["paths"].keys()))


def test_swagger_docs_available(dashboard_client):
    resp = dashboard_client.get("/docs")
    assert resp.status_code == 200

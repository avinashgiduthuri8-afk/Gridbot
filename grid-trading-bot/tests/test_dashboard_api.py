"""Tests for the read-only dashboard FastAPI backend.

Covers every endpoint: success responses against a seeded database, an
empty database, invalid/missing IDs, and basic error handling. Existing
trading-engine tests are untouched by anything here — the dashboard only
reads via the same Repositories class those tests already exercise.
"""
from __future__ import annotations

import asyncio
import sqlite3

import pytest
from fastapi.testclient import TestClient

# pyrefly: ignore [missing-import]
from config.constants import GridStatus
from dashboard.app import create_app
from storage.database import Database
from storage.models import DCAGridRecord, OrderRecord, TradeHistoryRecord
from storage.repositories import Repositories
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
    # The bot owns creation/migration. Prepare that database with a regular
    # writer before the dashboard starts, then keep the dashboard itself
    # connected through its read-only Database instance.
    writer_db = Database(db_path)
    _seed(writer_db.connect(), writer_db.migrate())
    monkeypatch.setenv("DATABASE_PATH", db_path)
    app = create_app()
    with TestClient(app) as client:
        app.state.seed_repos = Repositories(writer_db)
        yield client
    _seed(writer_db.close())


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


def test_dashboard_database_connection_is_read_only(dashboard_client):
    dashboard_db = dashboard_client.app.state.db
    assert dashboard_db._read_only is True
    with pytest.raises(sqlite3.OperationalError, match="readonly"):
        _seed(dashboard_db.connection.execute("CREATE TABLE dashboard_write_probe (id INTEGER)"))


def test_dashboard_startup_does_not_migrate_database(tmp_path, monkeypatch):
    """
    Ensures that starting the dashboard against an empty/unmigrated database
    does not create any tables, and leaves the schema entirely empty.
    """
    db_path = str(tmp_path / "dashboard_unmigrated.db")
    open(db_path, "w").close()
    monkeypatch.setenv("DATABASE_PATH", db_path)

    app = create_app()
    with TestClient(app) as client:
        db = app.state.db
        assert db._read_only is True

        # Verify NO tables were created (no migrations ran)
        async def check_tables():
            async with db.connection.execute("SELECT name FROM sqlite_master WHERE type='table'") as cursor:
                rows = await cursor.fetchall()
                # Should be entirely empty
                assert len(rows) == 0, f"Dashboard incorrectly created tables: {rows}"

        _seed(check_tables())


def test_dashboard_handles_missing_database_gracefully(tmp_path, monkeypatch):
    """
    Ensures that if the database file does not exist, the dashboard starts up
    gracefully but endpoints return a 503 error instead of crashing.
    """
    db_path = str(tmp_path / "nonexistent.db")
    monkeypatch.setenv("DATABASE_PATH", db_path)

    app = create_app()
    with TestClient(app) as client:
        # DB should be None in state because it wasn't found
        assert client.app.state.db is None
        
        # Endpoints should return 503
        resp = client.get("/api/grids")
        assert resp.status_code == 503
        assert resp.json() == {"detail": "Database unavailable or unmigrated"}

        resp = client.get("/api/health")
        assert resp.status_code == 200
        assert resp.json()["status"] == "degraded"
        assert resp.json()["database_connected"] is False


def test_dashboard_startup_without_trading_credentials(tmp_path, monkeypatch):
    """
    Proves that the dashboard starts up successfully and connects read-only
    to the configured SQLite database without requiring any Telegram or
    CoinDCX credentials in the environment.
    """
    db_path = str(tmp_path / "dashboard_no_secrets.db")
    writer_db = Database(db_path)
    _seed(writer_db.connect(), writer_db.migrate(), writer_db.close())

    # Ensure no Telegram / CoinDCX secrets exist in environment
    for key in (
        "TELEGRAM_BOT_TOKEN",
        "TELEGRAM_CHAT_ID",
        "TELEGRAM_ALLOWED_USER_IDS",
        "COINDCX_API_KEY",
        "COINDCX_API_SECRET",
    ):
        monkeypatch.delenv(key, raising=False)

    monkeypatch.setenv("DATABASE_PATH", db_path)

    app = create_app()
    with TestClient(app) as client:
        # Dashboard starts successfully
        resp = client.get("/api/health")
        assert resp.status_code == 200
        assert resp.json()["status"] == "ok"
        assert resp.json()["database_connected"] is True

        # Database path is correctly loaded
        assert app.state.dashboard_settings.database_path == db_path
        assert app.state.db is not None
        assert app.state.db._db_path == db_path

        # Database remains read-only
        assert app.state.db._read_only is True
        with pytest.raises(sqlite3.OperationalError, match="readonly"):
            _seed(app.state.db.connection.execute("CREATE TABLE write_fail (id INT)"))

    _seed(writer_db.close())


def test_dashboard_serves_frontend_when_present(tmp_path, monkeypatch):
    """
    Proves that the dashboard serves index.html on root and SPA routes,
    and mounts static assets when the configured static directory exists.
    """
    static_dir = tmp_path / "static"
    static_dir.mkdir()
    index_file = static_dir / "index.html"
    index_file.write_text("<html><body>Dashboard UI</body></html>", encoding="utf-8")
    assets_dir = static_dir / "assets"
    assets_dir.mkdir()
    asset_file = assets_dir / "app.js"
    asset_file.write_text("console.log('ui');", encoding="utf-8")

    db_path = str(tmp_path / "db.db")
    writer_db = Database(db_path)
    _seed(writer_db.connect(), writer_db.migrate())

    monkeypatch.setenv("DATABASE_PATH", db_path)
    monkeypatch.setenv("DASHBOARD_STATIC_DIR", str(static_dir))

    for key in ("TELEGRAM_BOT_TOKEN", "TELEGRAM_CHAT_ID", "COINDCX_API_KEY", "COINDCX_API_SECRET"):
        monkeypatch.delenv(key, raising=False)

    app = create_app()
    with TestClient(app) as client:
        # Root serves index.html
        resp = client.get("/")
        assert resp.status_code == 200
        assert "Dashboard UI" in resp.text

        # Client-side SPA routes fallback to index.html
        resp = client.get("/grids/view")
        assert resp.status_code == 200
        assert "Dashboard UI" in resp.text

        # Assets are served
        resp = client.get("/assets/app.js")
        assert resp.status_code == 200
        assert "console.log('ui')" in resp.text

    _seed(writer_db.close())


# ---------------------------------------------------------------------------
# /grids
# ---------------------------------------------------------------------------


def test_list_grids_empty_database(dashboard_client):
    resp = dashboard_client.get("/api/grids")
    assert resp.status_code == 200
    assert resp.json() == {"grids": [], "count": 0}


def test_list_grids_returns_seeded_grid(dashboard_client):
    repos = dashboard_client.app.state.seed_repos
    grid = _make_grid()
    _seed(repos.grids.create(grid))

    resp = dashboard_client.get("/api/grids")
    assert resp.status_code == 200
    data = resp.json()
    assert data["count"] == 1
    assert data["grids"][0]["grid_id"] == grid.grid_id
    assert data["grids"][0]["symbol"] == "BTCINR"


def test_list_grids_returns_all_statuses(dashboard_client):
    repos = dashboard_client.app.state.seed_repos
    _seed(
        repos.grids.create(_make_grid(symbol="BTCINR", status=GridStatus.ACTIVE.value)),
        repos.grids.create(_make_grid(symbol="ETHINR", status=GridStatus.PAUSED.value)),
        repos.grids.create(_make_grid(symbol="SOLINR", status=GridStatus.STOPPED.value)),
        repos.grids.create(_make_grid(symbol="DOGEINR", status=GridStatus.COMPLETED.value)),
    )

    resp = dashboard_client.get("/api/grids")
    assert resp.status_code == 200
    data = resp.json()
    assert data["count"] == 4
    statuses = {g["status"] for g in data["grids"]}
    assert statuses == {"active", "paused", "stopped", "completed"}


def test_get_grid_by_id_success(dashboard_client):
    repos = dashboard_client.app.state.seed_repos
    grid = _make_grid(
        symbol="BTCINR",
        entry_price=5_000_000.0,
        base_investment=50_000.0,
        trailing_enabled=True,
        trailing_percentage=2.5,
        trailing_peak_price=5_200_000.0,
    )
    _seed(repos.grids.create(grid))

    resp = dashboard_client.get(f"/api/grids/{grid.grid_id}")
    assert resp.status_code == 200
    g = resp.json()
    assert g["grid_id"] == grid.grid_id
    assert g["symbol"] == "BTCINR"
    assert g["entry_price"] == 5_000_000.0
    assert g["base_investment"] == 50_000.0
    assert g["trailing_enabled"] is True
    assert g["trailing_percentage"] == 2.5
    assert g["trailing_peak_price"] == 5_200_000.0


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
    repos = dashboard_client.app.state.seed_repos
    active = _make_grid(symbol="BTCINR")
    completed = _make_grid(symbol="ETHINR", status=GridStatus.COMPLETED.value, total_quantity=0.0)
    _seed(repos.grids.create(active), repos.grids.create(completed))

    resp = dashboard_client.get("/api/positions")
    data = resp.json()
    assert data["count"] == 1
    assert data["positions"][0]["symbol"] == "BTCINR"


def test_positions_returns_active_and_paused_grids(dashboard_client):
    repos = dashboard_client.app.state.seed_repos
    active_grid = _make_grid(symbol="BTCINR", status=GridStatus.ACTIVE.value)
    paused_grid = _make_grid(symbol="ETHINR", status=GridStatus.PAUSED.value)
    stopped_grid = _make_grid(symbol="SOLINR", status=GridStatus.STOPPED.value)
    _seed(
        repos.grids.create(active_grid),
        repos.grids.create(paused_grid),
        repos.grids.create(stopped_grid),
    )

    resp = dashboard_client.get("/api/positions")
    assert resp.status_code == 200
    data = resp.json()
    assert data["count"] == 2
    symbols = {p["symbol"] for p in data["positions"]}
    assert symbols == {"BTCINR", "ETHINR"}
    statuses = {p["status"] for p in data["positions"]}
    assert statuses == {"active", "paused"}


def test_positions_without_price_gives_zero_unrealized(dashboard_client):
    repos = dashboard_client.app.state.seed_repos
    grid = _make_grid()
    _seed(repos.grids.create(grid))

    resp = dashboard_client.get("/api/positions")
    pos = resp.json()["positions"][0]
    assert pos["current_price"] is None
    assert pos["unrealized_pnl"] == 0.0


def test_positions_with_price_override_computes_unrealized(dashboard_client):
    repos = dashboard_client.app.state.seed_repos
    grid = _make_grid(average_entry_price=5_000_000.0, total_quantity=0.01)
    _seed(repos.grids.create(grid))

    resp = dashboard_client.get("/api/positions?prices=BTCINR:5200000")
    pos = resp.json()["positions"][0]
    assert pos["current_price"] == 5_200_000.0
    assert pos["unrealized_pnl"] == pytest.approx(2_000.0)


def test_positions_malformed_price_override_ignored_gracefully(dashboard_client):
    repos = dashboard_client.app.state.seed_repos
    grid = _make_grid()
    _seed(repos.grids.create(grid))

    resp = dashboard_client.get("/api/positions?prices=garbage_no_colon,BTCINR:not_a_number")
    assert resp.status_code == 200
    pos = resp.json()["positions"][0]
    assert pos["current_price"] is None  # malformed entries are skipped, not a crash


def test_positions_field_values_and_json_safety(dashboard_client):
    repos = dashboard_client.app.state.seed_repos
    grid = _make_grid(
        symbol="BTCINR",
        status=GridStatus.ACTIVE.value,
        mode="paper",
        total_quantity=0.05,
        average_entry_price=4_500_000.0,
        total_investment=225_000.0,
        realized_profit=1_250.0,
        current_level=2,
        max_levels=8,
        trailing_enabled=True,
        trailing_peak_price=4_800_000.0,
    )
    _seed(repos.grids.create(grid))

    resp = dashboard_client.get("/api/positions?prices=BTCINR:4700000")
    assert resp.status_code == 200
    data = resp.json()
    assert data["count"] == 1
    pos = data["positions"][0]
    assert pos["grid_id"] == grid.grid_id
    assert pos["symbol"] == "BTCINR"
    assert pos["status"] == "active"
    assert pos["mode"] == "paper"
    assert pos["quantity"] == 0.05
    assert pos["average_entry_price"] == 4_500_000.0
    assert pos["invested"] == 225_000.0
    assert pos["current_price"] == 4_700_000.0
    assert pos["realized_pnl"] == 1_250.0
    assert pos["unrealized_pnl"] == pytest.approx(10_000.0)
    assert pos["combined_pnl"] == pytest.approx(11_250.0)
    assert pos["current_level"] == 2
    assert pos["max_levels"] == 8
    assert pos["trailing_enabled"] is True
    assert pos["trailing_peak_price"] == 4_800_000.0


# ---------------------------------------------------------------------------
# /orders
# ---------------------------------------------------------------------------


def test_orders_empty_database(dashboard_client):
    resp = dashboard_client.get("/api/orders")
    assert resp.status_code == 200
    assert resp.json() == {"orders": [], "count": 0}


def test_orders_returns_seeded_order(dashboard_client):
    repos = dashboard_client.app.state.seed_repos
    grid = _make_grid()
    order = _make_order(grid.grid_id)
    _seed(repos.grids.create(grid), repos.orders.create(order))

    resp = dashboard_client.get("/api/orders")
    data = resp.json()
    assert data["count"] == 1
    assert data["orders"][0]["order_id"] == order.order_id


def test_orders_filtered_by_grid_id(dashboard_client):
    repos = dashboard_client.app.state.seed_repos
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
    repos = dashboard_client.app.state.seed_repos
    grid = _make_grid()
    trade = _make_trade(grid.grid_id)
    _seed(repos.grids.create(grid), repos.trade_history.record(trade))

    resp = dashboard_client.get("/api/trade-history")
    data = resp.json()
    assert data["count"] == 1
    assert data["trades"][0]["trade_id"] == trade.trade_id


def test_trade_history_multiple_records_all_returned(dashboard_client):
    repos = dashboard_client.app.state.seed_repos
    grid = _make_grid()
    trades = [_make_trade(grid.grid_id, side="sell", pnl=float(i * 100)) for i in range(5)]
    _seed(repos.grids.create(grid), *[repos.trade_history.record(t) for t in trades])

    resp = dashboard_client.get("/api/trade-history")
    assert resp.status_code == 200
    data = resp.json()
    assert data["count"] == 5
    returned_ids = {t["trade_id"] for t in data["trades"]}
    assert returned_ids == {t.trade_id for t in trades}


def test_trade_history_field_values_and_json_safety(dashboard_client):
    repos = dashboard_client.app.state.seed_repos
    grid = _make_grid()
    trade = _make_trade(
        grid.grid_id,
        symbol="BTCINR",
        side="sell",
        price=5_200_000.0,
        quantity=0.01,
        investment_inr=52_000.0,
        fee=5.2,
        pnl=1_500.0,
    )
    _seed(repos.grids.create(grid), repos.trade_history.record(trade))

    resp = dashboard_client.get("/api/trade-history")
    assert resp.status_code == 200
    t = resp.json()["trades"][0]
    assert t["trade_id"] == trade.trade_id
    assert t["grid_id"] == grid.grid_id
    assert t["symbol"] == "BTCINR"
    assert t["side"] == "sell"
    assert t["price"] == 5_200_000.0
    assert t["quantity"] == 0.01
    assert t["investment_inr"] == 52_000.0
    assert t["fee"] == 5.2
    assert t["pnl"] == 1_500.0


def test_trade_history_old_records_not_filtered(dashboard_client):
    """Simulates records created at an old timestamp — must still appear."""
    repos = dashboard_client.app.state.seed_repos
    grid = _make_grid()
    old_trade = _make_trade(grid.grid_id, executed_at="2024-01-01T00:00:00")
    new_trade = _make_trade(grid.grid_id, executed_at="2026-08-01T12:00:00")
    _seed(repos.grids.create(grid), repos.trade_history.record(old_trade), repos.trade_history.record(new_trade))

    resp = dashboard_client.get("/api/trade-history")
    assert resp.status_code == 200
    data = resp.json()
    assert data["count"] == 2
    returned_ids = {t["trade_id"] for t in data["trades"]}
    assert old_trade.trade_id in returned_ids
    assert new_trade.trade_id in returned_ids


# ---------------------------------------------------------------------------
# /orders — Group 3 extended
# ---------------------------------------------------------------------------


def test_orders_multiple_statuses_all_returned(dashboard_client):
    repos = dashboard_client.app.state.seed_repos
    grid = _make_grid()
    statuses = ["pending", "filled", "cancelled", "failed"]
    orders = [_make_order(grid.grid_id, status=s) for s in statuses]
    _seed(repos.grids.create(grid), *[repos.orders.create(o) for o in orders])

    resp = dashboard_client.get("/api/orders")
    assert resp.status_code == 200
    data = resp.json()
    assert data["count"] == 4
    returned_statuses = {o["status"] for o in data["orders"]}
    assert returned_statuses == {"pending", "filled", "cancelled", "failed"}


def test_orders_field_values_and_json_safety(dashboard_client):
    repos = dashboard_client.app.state.seed_repos
    grid = _make_grid()
    order = _make_order(
        grid.grid_id,
        symbol="BTCINR",
        side="buy",
        order_type="market_order",
        price=5_000_000.0,
        quantity=0.01,
        filled_quantity=0.01,
        filled_price=5_000_000.0,
        status="filled",
        fee=5.0,
    )
    _seed(repos.grids.create(grid), repos.orders.create(order))

    resp = dashboard_client.get("/api/orders")
    assert resp.status_code == 200
    o = resp.json()["orders"][0]
    assert o["order_id"] == order.order_id
    assert o["grid_id"] == grid.grid_id
    assert o["symbol"] == "BTCINR"
    assert o["side"] == "buy"
    assert o["order_type"] == "market_order"
    assert o["price"] == 5_000_000.0
    assert o["quantity"] == 0.01
    assert o["filled_quantity"] == 0.01
    assert o["filled_price"] == 5_000_000.0
    assert o["status"] == "filled"
    assert o["fee"] == 5.0
    assert o["reconciliation_status"] == "not_needed"


def test_orders_old_records_not_filtered(dashboard_client):
    """Records with old created_at timestamps must still be returned."""
    repos = dashboard_client.app.state.seed_repos
    grid = _make_grid()
    old_order = _make_order(grid.grid_id, status="filled", created_at="2024-01-01T00:00:00", updated_at="2024-01-01T00:00:00")
    new_order = _make_order(grid.grid_id, status="filled", created_at="2026-08-01T12:00:00", updated_at="2026-08-01T12:00:00")
    _seed(repos.grids.create(grid), repos.orders.create(old_order), repos.orders.create(new_order))

    resp = dashboard_client.get("/api/orders")
    assert resp.status_code == 200
    data = resp.json()
    assert data["count"] == 2
    returned_ids = {o["order_id"] for o in data["orders"]}
    assert old_order.order_id in returned_ids
    assert new_order.order_id in returned_ids


def test_orders_and_trades_visible_after_restart(tmp_path, monkeypatch):
    """Records written in session A must still be readable in session B (restart simulation)."""
    db_path = str(tmp_path / "persist_test.db")

    # Session A: write then close
    writer_db = Database(db_path)
    _seed(writer_db.connect(), writer_db.migrate())
    writer_repos = Repositories(writer_db)
    grid = _make_grid()
    order = _make_order(grid.grid_id)
    trade = _make_trade(grid.grid_id)
    _seed(
        writer_repos.grids.create(grid),
        writer_repos.orders.create(order),
        writer_repos.trade_history.record(trade),
    )
    _seed(writer_db.close())

    # Session B: fresh dashboard connects in read-only mode
    monkeypatch.setenv("DATABASE_PATH", db_path)
    from dashboard.app import create_app
    app = create_app()
    from fastapi.testclient import TestClient
    with TestClient(app) as client:
        o_resp = client.get("/api/orders")
        assert o_resp.status_code == 200
        assert o_resp.json()["count"] == 1
        assert o_resp.json()["orders"][0]["order_id"] == order.order_id

        t_resp = client.get("/api/trade-history")
        assert t_resp.status_code == 200
        assert t_resp.json()["count"] == 1
        assert t_resp.json()["trades"][0]["trade_id"] == trade.trade_id


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
    repos = dashboard_client.app.state.seed_repos
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
    repos = dashboard_client.app.state.seed_repos
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
    repos = dashboard_client.app.state.seed_repos
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


def test_analytics_total_realized_profit_sums_all_grids(dashboard_client):
    repos = dashboard_client.app.state.seed_repos
    _seed(
        repos.grids.create(_make_grid(symbol="BTCINR", realized_profit=1_000.0, status=GridStatus.ACTIVE.value)),
        repos.grids.create(_make_grid(symbol="ETHINR", realized_profit=2_500.0, status=GridStatus.COMPLETED.value, total_quantity=0.0)),
        repos.grids.create(_make_grid(symbol="SOLINR", realized_profit=500.0, status=GridStatus.STOPPED.value, total_quantity=0.0)),
    )

    resp = dashboard_client.get("/api/analytics")
    assert resp.status_code == 200
    data = resp.json()
    assert data["total_realized_profit"] == pytest.approx(4_000.0)


def test_analytics_win_rate_calculation(dashboard_client):
    repos = dashboard_client.app.state.seed_repos
    grid = _make_grid()
    _seed(
        repos.grids.create(grid),
        repos.trade_history.record(_make_trade(grid.grid_id, side="sell", pnl=200.0)),
        repos.trade_history.record(_make_trade(grid.grid_id, side="sell", pnl=-50.0)),
        repos.trade_history.record(_make_trade(grid.grid_id, side="sell", pnl=100.0)),
    )

    resp = dashboard_client.get("/api/analytics")
    assert resp.status_code == 200
    data = resp.json()
    assert data["total_sells"] == 3
    assert data["win_rate_pct"] == pytest.approx(200.0 / 3, rel=1e-3)  # 2 wins out of 3
    assert data["profit_factor"] == pytest.approx(300.0 / 50.0, rel=1e-3)


def test_analytics_old_trades_not_filtered(dashboard_client):
    """Trades from far past timestamps must still appear in analytics."""
    repos = dashboard_client.app.state.seed_repos
    grid = _make_grid()
    _seed(
        repos.grids.create(grid),
        repos.trade_history.record(_make_trade(grid.grid_id, side="sell", pnl=300.0, executed_at="2023-05-01T00:00:00")),
        repos.trade_history.record(_make_trade(grid.grid_id, side="sell", pnl=150.0, executed_at="2025-01-15T00:00:00")),
    )

    resp = dashboard_client.get("/api/analytics")
    assert resp.status_code == 200
    data = resp.json()
    assert data["total_sells"] == 2
    assert data["win_rate_pct"] == pytest.approx(100.0)


def test_analytics_completed_cycles_sums_all_grids(dashboard_client):
    repos = dashboard_client.app.state.seed_repos
    _seed(
        repos.grids.create(_make_grid(symbol="BTCINR", completed_cycles=5, status=GridStatus.ACTIVE.value)),
        repos.grids.create(_make_grid(symbol="ETHINR", completed_cycles=3, status=GridStatus.COMPLETED.value, total_quantity=0.0)),
    )

    resp = dashboard_client.get("/api/analytics")
    assert resp.status_code == 200
    assert resp.json()["completed_cycles"] == 8


def test_portfolio_total_realized_includes_completed_grids(dashboard_client):
    repos = dashboard_client.app.state.seed_repos
    _seed(
        repos.grids.create(_make_grid(
            symbol="BTCINR", status=GridStatus.ACTIVE.value,
            realized_profit=1_000.0, total_quantity=0.01, total_investment=50_000.0,
        )),
        repos.grids.create(_make_grid(
            symbol="ETHINR", status=GridStatus.COMPLETED.value,
            realized_profit=3_000.0, total_quantity=0.0, total_investment=30_000.0,
        )),
    )

    resp = dashboard_client.get("/api/portfolio")
    assert resp.status_code == 200
    data = resp.json()
    assert data["total_realized"] == pytest.approx(4_000.0)
    assert data["completed_grid_count"] == 1
    assert data["active_grid_count"] == 1


def test_portfolio_combined_pnl_correctness(dashboard_client):
    repos = dashboard_client.app.state.seed_repos
    grid = _make_grid(
        symbol="BTCINR", status=GridStatus.ACTIVE.value,
        realized_profit=500.0,
        average_entry_price=5_000_000.0, total_quantity=0.01, total_investment=50_000.0,
    )
    _seed(repos.grids.create(grid))

    resp = dashboard_client.get("/api/portfolio?prices=BTCINR:5100000")
    assert resp.status_code == 200
    data = resp.json()
    # unrealized = (5_100_000 - 5_000_000) * 0.01 = 1_000.0
    assert data["total_unrealized"] == pytest.approx(1_000.0)
    # combined = 500 + 1000
    assert data["combined_total"] == pytest.approx(1_500.0)


def test_portfolio_return_pct_correctness(dashboard_client):
    repos = dashboard_client.app.state.seed_repos
    grid = _make_grid(
        symbol="BTCINR", status=GridStatus.ACTIVE.value,
        realized_profit=2_500.0, total_quantity=0.0, total_investment=50_000.0,
    )
    _seed(repos.grids.create(grid))

    resp = dashboard_client.get("/api/portfolio")
    data = resp.json()
    # return_pct = (2500 / 50000) * 100 = 5.0%
    assert data["portfolio_return_pct"] == pytest.approx(5.0)


def test_portfolio_json_safe_all_fields_present(dashboard_client):
    resp = dashboard_client.get("/api/portfolio")
    assert resp.status_code == 200
    data = resp.json()
    for field in ("total_realized", "total_unrealized", "total_invested", "combined_total",
                  "portfolio_return_pct", "active_grid_count", "paused_grid_count",
                  "completed_grid_count", "stopped_grid_count"):
        assert field in data, f"Missing field: {field}"
        assert data[field] is not None


def test_portfolio_and_analytics_visible_after_restart(tmp_path, monkeypatch):
    """Portfolio/analytics data written in session A must be readable in session B."""
    db_path = str(tmp_path / "persist_portfolio.db")

    writer_db = Database(db_path)
    _seed(writer_db.connect(), writer_db.migrate())
    writer_repos = Repositories(writer_db)
    grid = _make_grid(realized_profit=1_200.0, completed_cycles=4)
    trade = _make_trade(grid.grid_id, side="sell", pnl=300.0)
    _seed(writer_repos.grids.create(grid), writer_repos.trade_history.record(trade))
    _seed(writer_db.close())

    monkeypatch.setenv("DATABASE_PATH", db_path)
    from dashboard.app import create_app
    app = create_app()
    from fastapi.testclient import TestClient
    with TestClient(app) as client:
        p_resp = client.get("/api/portfolio")
        assert p_resp.status_code == 200
        assert p_resp.json()["total_realized"] == pytest.approx(1_200.0)

        a_resp = client.get("/api/analytics")
        assert a_resp.status_code == 200
        assert a_resp.json()["total_sells"] == 1
        assert a_resp.json()["completed_cycles"] == 4


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


# ---------------------------------------------------------------------------
# Group 6 — Frontend UI <-> Backend API Integration Contract Verification
# ---------------------------------------------------------------------------


def test_frontend_api_spec_openapi_yaml_schema_alignment(dashboard_client):
    """
    Verifies that the generated openapi.json from the live FastAPI application
    matches every path and schema defined in lib/api-spec/openapi.yaml (used by
    Orval to generate @workspace/api-client-react and @workspace/api-zod).
    """
    import yaml
    from pathlib import Path

    # Find openapi.yaml in lib/api-spec/
    yaml_path = Path(__file__).parents[2] / "lib" / "api-spec" / "openapi.yaml"
    assert yaml_path.is_file(), f"openapi.yaml missing at {yaml_path}"

    with open(yaml_path, "r", encoding="utf-8") as f:
        spec = yaml.safe_load(f)

    # Fetch live OpenAPI spec from FastAPI app
    resp = dashboard_client.get("/openapi.json")
    assert resp.status_code == 200
    live_schema = resp.json()

    # 1. Verify every path in openapi.yaml exists in live_schema with /api prefix
    yaml_paths = set(spec.get("paths", {}).keys())
    live_paths = set(live_schema.get("paths", {}).keys())

    for yp in yaml_paths:
        expected_live_path = f"/api{yp}"
        assert expected_live_path in live_paths, f"Path {yp} in openapi.yaml not found as {expected_live_path} in live OpenAPI"

    # 2. Verify all core component schemas are defined in live schema
    expected_schemas = {
        "GridResponse", "GridListResponse", "PositionResponse", "PositionListResponse",
        "OrderResponse", "OrderListResponse", "TradeResponse", "TradeHistoryResponse",
        "PortfolioResponse", "AnalyticsResponse", "SettingsResponse", "RiskSettingsResponse",
        "HealthResponse", "HTTPValidationError",
    }
    live_schemas = set(live_schema.get("components", {}).get("schemas", {}).keys())
    missing_schemas = expected_schemas - live_schemas
    assert not missing_schemas, f"Missing schemas in live OpenAPI: {missing_schemas}"


def test_frontend_custom_fetch_error_compatibility(dashboard_client):
    """
    Verifies that API error responses (404, 422, 503) return a JSON object with a
    'detail' field, matching customFetch's getStringField(data, 'detail') error parser.
    """
    # 404
    r404 = dashboard_client.get("/api/grids/nonexistent_id")
    assert r404.status_code == 404
    assert "detail" in r404.json()

    # 422
    r422 = dashboard_client.get("/api/orders?limit=-1")
    assert r422.status_code == 422
    assert "detail" in r422.json()

    # 503 (simulated via missing DB)
    from dashboard.app import create_app
    app_no_db = create_app()
    with TestClient(app_no_db) as client_no_db:
        client_no_db.app.state.repos = None
        r503 = client_no_db.get("/api/grids")
        assert r503.status_code == 503
        assert "detail" in r503.json()
        assert r503.json()["detail"] == "Database unavailable or unmigrated"


def test_frontend_cors_headers_supported(dashboard_client):
    """
    Verifies that the FastAPI backend sends appropriate CORS headers for
    cross-origin frontend requests.
    """
    resp = dashboard_client.options(
        "/api/health",
        headers={
            "Origin": "http://localhost:5173",
            "Access-Control-Request-Method": "GET",
        },
    )
    assert resp.status_code == 200
    assert resp.headers.get("access-control-allow-origin") in ("*", "http://localhost:5173")


# ---------------------------------------------------------------------------
# Group 7 — Dashboard Functional & UI Quality Contract Tests
# ---------------------------------------------------------------------------


def test_ui_currency_inr_and_percentage_formatting_precision(dashboard_client):
    """
    Verifies that all financial amounts (INR) and percentage fields return
    Python float numbers suitable for frontend formatting (₹ / %).
    """
    repos = dashboard_client.app.state.seed_repos
    grid = _make_grid(
        entry_price=5_000_000.0,
        base_investment=50_000.0,
        realized_profit=1_250.50,
        dip_percentage=5.0,
        profit_percentage=4.5,
        stop_loss_percentage=15.0,
    )
    _seed(repos.grids.create(grid))

    # Portfolio currency/percentage precision
    p_resp = dashboard_client.get("/api/portfolio")
    assert p_resp.status_code == 200
    p_data = p_resp.json()
    assert isinstance(p_data["total_realized"], (int, float))
    assert isinstance(p_data["portfolio_return_pct"], (int, float))

    # Analytics percentage precision
    a_resp = dashboard_client.get("/api/analytics")
    assert a_resp.status_code == 200
    a_data = a_resp.json()
    assert isinstance(a_data["win_rate_pct"], (int, float))
    assert isinstance(a_data["max_drawdown_pct"], (int, float))


def test_ui_nullable_fields_render_safely_as_null(dashboard_client):
    """
    Verifies that all optional/nullable fields return explicit `null` (None in JSON)
    rather than missing keys or invalid default strings that would crash UI components.
    """
    repos = dashboard_client.app.state.seed_repos
    grid = _make_grid(trailing_enabled=False)
    order = _make_order(grid.grid_id, exchange_order_id=None)
    _seed(repos.grids.create(grid), repos.orders.create(order))

    # Grid trailing nulls
    g_resp = dashboard_client.get(f"/api/grids/{grid.grid_id}")
    assert g_resp.status_code == 200
    g_data = g_resp.json()
    assert g_data["trailing_percentage"] is None
    assert g_data["trailing_peak_price"] is None

    # Order exchange_order_id null
    o_resp = dashboard_client.get(f"/api/orders?grid_id={grid.grid_id}")
    assert o_resp.status_code == 200
    o_data = o_resp.json()
    assert o_data["orders"][0]["exchange_order_id"] is None

    # Analytics profit_factor null on 0 losing trades
    an_resp = dashboard_client.get("/api/analytics")
    assert an_resp.status_code == 200
    assert an_resp.json()["profit_factor"] is None


def test_ui_empty_states_payload_completeness(dashboard_client):
    """
    Verifies that empty state responses return valid structured objects with 0 counts/empty arrays
    so UI pages render empty state UI without undefined access errors.
    """
    assert dashboard_client.get("/api/grids").json() == {"grids": [], "count": 0}
    assert dashboard_client.get("/api/positions").json() == {"positions": [], "count": 0}
    assert dashboard_client.get("/api/orders").json() == {"orders": [], "count": 0}
    assert dashboard_client.get("/api/trade-history").json() == {"trades": [], "count": 0}




def test_strict_get_only_route_policy(dashboard_client):
    forbidden_methods = {"POST", "PUT", "PATCH", "DELETE"}
    app_routes = dashboard_client.app.routes
    for route in app_routes:
        methods = getattr(route, "methods", set()) or set()
        violations = methods.intersection(forbidden_methods)
        assert not violations, f"Route {getattr(route, 'path', route)} exposes forbidden mutation methods: {violations}"


def test_read_only_database_all_write_operations_blocked(dashboard_client):
    conn = dashboard_client.app.state.db.connection

    failing_queries = [
        "CREATE TABLE test_tbl (id INT)",
        "INSERT INTO schema_migrations (version) VALUES (999)",
        "UPDATE dca_grids SET status = 'stopped'",
        "DELETE FROM dca_grids",
        "DROP TABLE IF EXISTS dca_grids",
    ]

    for q in failing_queries:
        with pytest.raises(sqlite3.OperationalError):
            _seed(conn.execute(q))


def test_dashboard_contract_all_endpoints_schema_field_presence(dashboard_client):
    repos = dashboard_client.app.state.seed_repos
    grid = _make_grid()
    order = _make_order(grid.grid_id)
    trade = _make_trade(grid.grid_id, order_id=order.order_id)
    _seed(repos.grids.create(grid), repos.orders.create(order), repos.trade_history.record(trade))

    h = dashboard_client.get("/api/health").json()
    assert {"status", "database_connected"}.issubset(h.keys())

    p = dashboard_client.get("/api/portfolio").json()
    assert {"total_realized", "total_unrealized", "total_invested", "portfolio_return_pct", "active_grid_count", "paused_grid_count", "completed_grid_count", "stopped_grid_count"}.issubset(p.keys())

    g = dashboard_client.get("/api/grids").json()
    assert {"grids", "count"}.issubset(g.keys())
    assert {"grid_id", "symbol", "status", "mode", "entry_price", "base_investment", "current_level", "max_levels", "total_investment", "realized_profit", "completed_cycles", "trailing_enabled"}.issubset(g["grids"][0].keys())

    gd = dashboard_client.get(f"/api/grids/{grid.grid_id}").json()
    assert {"grid_id", "symbol", "status", "mode", "created_at", "updated_at"}.issubset(gd.keys())

    pos = dashboard_client.get("/api/positions").json()
    assert {"positions", "count"}.issubset(pos.keys())
    assert {"grid_id", "symbol", "status", "quantity", "average_entry_price", "invested", "realized_pnl", "unrealized_pnl", "combined_pnl"}.issubset(pos["positions"][0].keys())

    ords = dashboard_client.get("/api/orders").json()
    assert {"orders", "count"}.issubset(ords.keys())
    assert {"order_id", "grid_id", "symbol", "side", "order_type", "price", "quantity", "status", "fee", "created_at"}.issubset(ords["orders"][0].keys())

    trds = dashboard_client.get("/api/trade-history").json()
    assert {"trades", "count"}.issubset(trds.keys())
    assert {"trade_id", "grid_id", "order_id", "symbol", "side", "price", "quantity", "investment_inr", "fee", "pnl", "executed_at"}.issubset(trds["trades"][0].keys())

    an = dashboard_client.get("/api/analytics").json()
    assert {"total_buys", "total_sells", "total_dust_writeoffs", "total_realized_profit", "win_rate_pct", "max_drawdown_pct", "profit_factor", "completed_cycles"}.issubset(an.keys())

    st = dashboard_client.get("/api/settings").json()
    assert {"risk", "order_poll_interval_seconds", "price_poll_interval_seconds", "emergency_stop_active", "backup_enabled", "webhook_enabled"}.issubset(st.keys())


def test_dashboard_data_consistency_invariants(dashboard_client):
    repos = dashboard_client.app.state.seed_repos
    grid1 = _make_grid(symbol="BTCINR", realized_profit=300.0)
    grid2 = _make_grid(symbol="ETHINR", realized_profit=150.0)
    _seed(repos.grids.create(grid1), repos.grids.create(grid2))

    portfolio = dashboard_client.get("/api/portfolio").json()
    analytics = dashboard_client.get("/api/analytics").json()
    grids = dashboard_client.get("/api/grids").json()

    grid_profit_sum = sum(g["realized_profit"] for g in grids["grids"])
    assert portfolio["total_realized"] == grid_profit_sum == 450.0
    assert analytics["total_realized_profit"] == grid_profit_sum == 450.0
    assert portfolio["active_grid_count"] == len([g for g in grids["grids"] if g["status"] == "active"]) == 2


def test_dashboard_error_isolation_and_resilience(dashboard_client):
    res_unknown = dashboard_client.get("/api/unknown_route_999")
    assert res_unknown.status_code == 404

    res_grid_404 = dashboard_client.get("/api/grids/nonexistent_grid_123")
    assert res_grid_404.status_code == 404
    assert "not found" in res_grid_404.json()["detail"].lower()

    res_health = dashboard_client.get("/api/health")
    assert res_health.status_code == 200

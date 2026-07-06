"""Integration tests exercising the SQLite repositories end-to-end
(grid create -> level bulk create -> mark filled -> order lifecycle)."""

from __future__ import annotations

import pytest

from storage.database import Database
from storage.models import GridLevelRecord, GridRecord, OrderRecord
from storage.repositories import Repositories
from utils.helpers import now_iso


@pytest.fixture
async def repos(tmp_path):
    db_path = tmp_path / "test.db"
    db = Database(str(db_path))
    await db.connect()
    await db.migrate()
    yield Repositories(db)
    await db.close()


async def test_grid_create_and_fetch(repos):
    grid = GridRecord(
        grid_id="grid_x", symbol="BTCINR", grid_type="arithmetic", status="active",
        upper_price=100, lower_price=50, grid_levels=5, investment_per_grid=100,
        created_at=now_iso(), updated_at=now_iso(),
    )
    await repos.grids.create(grid)
    fetched = await repos.grids.get("grid_x")
    assert fetched is not None
    assert fetched["symbol"] == "BTCINR"
    assert fetched["status"] == "active"


async def test_grid_levels_bulk_create_and_mark_filled(repos):
    grid = GridRecord(
        grid_id="grid_y", symbol="ETHINR", grid_type="arithmetic", status="active",
        upper_price=100, lower_price=50, grid_levels=3, investment_per_grid=100,
        created_at=now_iso(), updated_at=now_iso(),
    )
    await repos.grids.create(grid)
    levels = [
        GridLevelRecord(id=None, grid_id="grid_y", level_index=i, price=50 + i * 25, side="buy", is_filled=False)
        for i in range(3)
    ]
    await repos.grid_levels.bulk_create(levels)

    fetched_levels = await repos.grid_levels.list_for_grid("grid_y")
    assert len(fetched_levels) == 3
    assert all(not lv["is_filled"] for lv in fetched_levels)

    await repos.grid_levels.mark_filled("grid_y", 0, "buy", "ord_1")
    fetched_levels = await repos.grid_levels.list_for_grid("grid_y")
    filled = next(lv for lv in fetched_levels if lv["level_index"] == 0)
    assert filled["is_filled"] == 1
    assert filled["order_id"] == "ord_1"


async def test_order_create_and_update_status(repos):
    grid = GridRecord(
        grid_id="grid_z", symbol="BTCINR", grid_type="arithmetic", status="active",
        upper_price=100, lower_price=50, grid_levels=5, investment_per_grid=100,
        created_at=now_iso(), updated_at=now_iso(),
    )
    await repos.grids.create(grid)
    order = OrderRecord(
        order_id="ord_z", grid_id="grid_z", exchange_order_id=None, symbol="BTCINR",
        side="buy", price=100, quantity=1, status="pending", level_index=0,
        created_at=now_iso(), updated_at=now_iso(),
    )
    await repos.orders.create(order)
    await repos.orders.update_status("ord_z", "filled", filled_quantity=1, filled_price=100)
    fetched = await repos.orders.get("ord_z")
    assert fetched["status"] == "filled"
    assert fetched["filled_quantity"] == 1


async def test_daily_stats_accumulate(repos):
    await repos.daily_stats.add_trade("2026-07-06", 100.0)
    await repos.daily_stats.add_trade("2026-07-06", -30.0)
    stats = await repos.daily_stats.get("2026-07-06")
    assert stats["realized_pnl"] == 70.0
    assert stats["trades_count"] == 2


async def test_coin_config_upsert(repos):
    await repos.coin_configs.upsert(
        symbol="BTCINR", grid_levels=10, investment_per_grid=100,
        upper_price=200, lower_price=100, grid_type="arithmetic",
    )
    config = await repos.coin_configs.get("BTCINR")
    assert config["grid_levels"] == 10

    await repos.coin_configs.upsert(
        symbol="BTCINR", grid_levels=15, investment_per_grid=150,
        upper_price=200, lower_price=100, grid_type="arithmetic",
    )
    config = await repos.coin_configs.get("BTCINR")
    assert config["grid_levels"] == 15
    assert config["investment_per_grid"] == 150

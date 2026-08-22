"""Comprehensive regression tests for Group 9.5: Database, Persistence & Recovery Integrity.

Validates all persistence, transaction, and restart invariants:
 1. Active grid full state (levels, quantities, investment, avg entry, trailing) persists across restart
 2. Paused grid persists across restart
 3. Stopped grid persists across restart
 4. Completed grid persists across restart
 5. Order lifecycle statuses (PENDING, SUBMITTED, UNKNOWN, OPEN, PARTIALLY_FILLED, FILLED, FAILED, CANCELLED) persist
 6. Order reconciliation fields (client_order_id, reconciliation_status, retry_count) persist
 7. Trade history persists and correctly aggregates realized P&L across restart
 8. Trade history idempotency guard persists across restart
 9. Daily stats persist and accumulate across restart
10. Daily stats multi-date isolation persists across restart
11. Emergency stop flag persists across restart
12. Price monitor interval setting persists across restart
13. Grid defaults persist across restart
14. Foreign key integrity between orders and dca_grids enforced
15. Concurrent database writes under WAL mode execute safely
16. Database schema migrations are idempotent across repeated connects
"""

from __future__ import annotations

import asyncio
import os
import tempfile
import pytest

from config.constants import GridStatus, OrderStatus
from storage.database import Database
from storage.models import DCAGridRecord, OrderRecord, TradeHistoryRecord
from storage.repositories import Repositories
from utils.helpers import new_id, now_iso

pytestmark = pytest.mark.anyio


@pytest.fixture
def temp_db_path():
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    yield path
    if os.path.exists(path):
        try:
            os.remove(path)
        except OSError:
            pass


async def _open_and_migrate(path: str) -> tuple[Database, Repositories]:
    db = Database(path)
    await db.connect()
    await db.migrate()
    return db, Repositories(db)


def _make_grid(
    grid_id: str | None = None,
    symbol: str = "BTCINR",
    status: str = GridStatus.ACTIVE.value,
    mode: str = "real",
    current_level: int = 1,
    max_levels: int = 5,
    total_quantity: float = 0.00925,
    total_investment: float = 499.5,
    average_entry_price: float = 54000.0,
    last_buy_price: float = 54000.0,
    next_buy_price: float = 51300.0,
    next_sell_price: float = 57780.0,
    realized_profit: float = 0.0,
    completed_cycles: int = 0,
    trailing_enabled: bool = False,
    trailing_percentage: float | None = None,
    trailing_peak_price: float | None = None,
) -> DCAGridRecord:
    now = now_iso()
    return DCAGridRecord(
        grid_id=grid_id or new_id("grd"),
        symbol=symbol,
        status=status,
        mode=mode,
        entry_price=54000.0,
        base_investment=500.0,
        dip_buy_amount=100.0,
        dip_percentage=5.0,
        profit_sell_amount=150.0,
        profit_percentage=7.0,
        max_levels=max_levels,
        stop_loss_percentage=50.0,
        current_level=current_level,
        total_quantity=total_quantity,
        total_investment=total_investment,
        average_entry_price=average_entry_price,
        last_buy_price=last_buy_price,
        next_buy_price=next_buy_price,
        next_sell_price=next_sell_price,
        realized_profit=realized_profit,
        completed_cycles=completed_cycles,
        trailing_enabled=trailing_enabled,
        trailing_percentage=trailing_percentage,
        trailing_peak_price=trailing_peak_price,
        created_at=now,
        updated_at=now,
    )


def _make_order(
    grid_id: str,
    side: str = "buy",
    status: str = OrderStatus.OPEN.value,
    exchange_order_id: str | None = "EX0001",
    client_order_id: str | None = None,
    quantity: float = 0.01,
    filled_quantity: float = 0.0,
    filled_price: float = 0.0,
    price: float = 54000.0,
    reconciliation_status: str = "not_needed",
    reconciliation_retry_count: int = 0,
) -> OrderRecord:
    now = now_iso()
    oid = new_id("ord")
    return OrderRecord(
        order_id=oid,
        grid_id=grid_id,
        exchange_order_id=exchange_order_id,
        symbol="BTCINR",
        side=side,
        order_type="market_order",
        price=price,
        quantity=quantity,
        filled_quantity=filled_quantity,
        filled_price=filled_price,
        status=status,
        client_order_id=client_order_id or oid,
        reconciliation_status=reconciliation_status,
        reconciliation_retry_count=reconciliation_retry_count,
        created_at=now,
        updated_at=now,
    )


# 1. Active grid full state persists across restart
async def test_grid_full_state_persists_across_restart(temp_db_path):
    db1, repos1 = await _open_and_migrate(temp_db_path)
    grid_id = new_id("grd")
    grid = _make_grid(
        grid_id=grid_id,
        current_level=3,
        total_quantity=0.015,
        total_investment=799.5,
        average_entry_price=53300.0,
        trailing_enabled=True,
        trailing_percentage=3.0,
        trailing_peak_price=58500.0,
        realized_profit=45.2,
        completed_cycles=2,
    )
    await repos1.grids.create(grid)
    await db1.close()

    # Restart simulated: reconnect fresh Database instance
    db2, repos2 = await _open_and_migrate(temp_db_path)
    loaded = await repos2.grids.get(grid_id)
    await db2.close()

    assert loaded is not None
    assert loaded["grid_id"] == grid_id
    assert loaded["symbol"] == "BTCINR"
    assert loaded["status"] == GridStatus.ACTIVE.value
    assert loaded["mode"] == "real"
    assert loaded["current_level"] == 3
    assert loaded["total_quantity"] == pytest.approx(0.015)
    assert loaded["total_investment"] == pytest.approx(799.5)
    assert loaded["average_entry_price"] == pytest.approx(53300.0)
    assert loaded["trailing_enabled"] == 1
    assert loaded["trailing_peak_price"] == pytest.approx(58500.0)
    assert loaded["realized_profit"] == pytest.approx(45.2)
    assert loaded["completed_cycles"] == 2


# 2. Paused grid persists across restart
async def test_paused_grid_persists_across_restart(temp_db_path):
    db1, repos1 = await _open_and_migrate(temp_db_path)
    grid_id = new_id("grd")
    grid = _make_grid(grid_id=grid_id, symbol="ETHINR", status=GridStatus.PAUSED.value)
    await repos1.grids.create(grid)
    await db1.close()

    db2, repos2 = await _open_and_migrate(temp_db_path)
    loaded = await repos2.grids.get(grid_id)
    await db2.close()

    assert loaded["status"] == GridStatus.PAUSED.value


# 3. Stopped grid persists across restart
async def test_stopped_grid_persists_across_restart(temp_db_path):
    db1, repos1 = await _open_and_migrate(temp_db_path)
    grid_id = new_id("grd")
    grid = _make_grid(grid_id=grid_id, symbol="SOLINR", status=GridStatus.STOPPED.value)
    await repos1.grids.create(grid)
    await db1.close()

    db2, repos2 = await _open_and_migrate(temp_db_path)
    loaded = await repos2.grids.get(grid_id)
    await db2.close()

    assert loaded["status"] == GridStatus.STOPPED.value


# 4. Completed grid persists across restart
async def test_completed_grid_persists_across_restart(temp_db_path):
    db1, repos1 = await _open_and_migrate(temp_db_path)
    grid_id = new_id("grd")
    grid = _make_grid(
        grid_id=grid_id,
        symbol="DOGEINR",
        status=GridStatus.COMPLETED.value,
        total_quantity=0.0,
        completed_cycles=5,
        realized_profit=120.0,
    )
    await repos1.grids.create(grid)
    await db1.close()

    db2, repos2 = await _open_and_migrate(temp_db_path)
    loaded = await repos2.grids.get(grid_id)
    await db2.close()

    assert loaded["status"] == GridStatus.COMPLETED.value
    assert loaded["total_quantity"] == pytest.approx(0.0)
    assert loaded["completed_cycles"] == 5


# 5. Order lifecycle statuses persist
async def test_order_lifecycle_statuses_persist(temp_db_path):
    db1, repos1 = await _open_and_migrate(temp_db_path)
    grid = _make_grid()
    await repos1.grids.create(grid)

    statuses = [
        OrderStatus.PENDING.value,
        OrderStatus.SUBMITTED.value,
        OrderStatus.UNKNOWN.value,
        OrderStatus.OPEN.value,
        OrderStatus.PARTIALLY_FILLED.value,
        OrderStatus.FILLED.value,
        OrderStatus.FAILED.value,
        OrderStatus.CANCELLED.value,
    ]
    order_ids = []
    for st in statuses:
        order = _make_order(
            grid_id=grid.grid_id,
            status=st,
            filled_quantity=0.005 if st == "partially_filled" else (0.01 if st == "filled" else 0.0),
            filled_price=54000.0 if st in ("partially_filled", "filled") else 0.0,
        )
        order_ids.append((order.order_id, st))
        await repos1.orders.create(order)
    await db1.close()

    db2, repos2 = await _open_and_migrate(temp_db_path)
    for oid, expected_status in order_ids:
        row = await repos2.orders.get(oid)
        assert row is not None
        assert row["status"] == expected_status
    await db2.close()


# 6. Order reconciliation fields persist
async def test_order_reconciliation_fields_persist(temp_db_path):
    db1, repos1 = await _open_and_migrate(temp_db_path)
    grid = _make_grid()
    await repos1.grids.create(grid)

    order = _make_order(
        grid_id=grid.grid_id,
        status=OrderStatus.SUBMITTED.value,
        exchange_order_id=None,
        reconciliation_status="submitted",
        reconciliation_retry_count=2,
    )
    await repos1.orders.create(order)
    await db1.close()

    db2, repos2 = await _open_and_migrate(temp_db_path)
    row = await repos2.orders.get(order.order_id)
    await db2.close()

    assert row["client_order_id"] == order.order_id
    assert row["reconciliation_status"] == "submitted"
    assert row["reconciliation_retry_count"] == 2


# 7. Trade history persists and aggregates across restart
async def test_trade_history_persists_and_aggregates(temp_db_path):
    db1, repos1 = await _open_and_migrate(temp_db_path)
    grid_id = new_id("grd")
    now = now_iso()
    await repos1.trade_history.record(
        TradeHistoryRecord(
            trade_id=new_id("trd"), grid_id=grid_id, order_id=new_id("ord"),
            symbol="BTCINR", side="buy", price=50000.0, quantity=0.01,
            investment_inr=500.5, fee=0.5, pnl=0.0, executed_at=now,
        )
    )
    await repos1.trade_history.record(
        TradeHistoryRecord(
            trade_id=new_id("trd"), grid_id=grid_id, order_id=new_id("ord"),
            symbol="BTCINR", side="sell", price=55000.0, quantity=0.01,
            investment_inr=549.5, fee=0.5, pnl=49.0, executed_at=now,
        )
    )
    await db1.close()

    db2, repos2 = await _open_and_migrate(temp_db_path)
    total_pnl = await repos2.trade_history.total_realized_pnl()
    trades = await repos2.trade_history.list_all()
    await db2.close()

    assert total_pnl == pytest.approx(49.0)
    assert len(trades) == 2


# 8. Trade history idempotency guard persists across restart
async def test_trade_history_idempotency_guard_persists(temp_db_path):
    db1, repos1 = await _open_and_migrate(temp_db_path)
    oid = new_id("ord")
    await repos1.trade_history.record(
        TradeHistoryRecord(
            trade_id=new_id("trd"), grid_id="grd_1", order_id=oid,
            symbol="BTCINR", side="buy", price=50000.0, quantity=0.01,
            investment_inr=500.0, fee=0.0, pnl=0.0, executed_at=now_iso(),
        )
    )
    await db1.close()

    db2, repos2 = await _open_and_migrate(temp_db_path)
    existing = await repos2.trade_history.get_by_order_id(oid)
    await db2.close()

    assert existing is not None
    assert existing["order_id"] == oid


# 9. Daily stats persist and accumulate across restart
async def test_daily_stats_persist_and_accumulate(temp_db_path):
    db1, repos1 = await _open_and_migrate(temp_db_path)
    today = "2026-08-17"
    await repos1.daily_stats.add_trade(today, 150.0)
    await repos1.daily_stats.add_trade(today, -50.0)
    await db1.close()

    db2, repos2 = await _open_and_migrate(temp_db_path)
    stats = await repos2.daily_stats.get(today)
    await db2.close()

    assert stats is not None
    assert stats["realized_pnl"] == pytest.approx(100.0)
    assert stats["trades_count"] == 2


# 10. Daily stats multi-date isolation persists
async def test_daily_stats_multi_date_isolation(temp_db_path):
    db1, repos1 = await _open_and_migrate(temp_db_path)
    await repos1.daily_stats.add_trade("2026-08-16", 200.0)
    await repos1.daily_stats.add_trade("2026-08-17", -75.0)
    await db1.close()

    db2, repos2 = await _open_and_migrate(temp_db_path)
    s1 = await repos2.daily_stats.get("2026-08-16")
    s2 = await repos2.daily_stats.get("2026-08-17")
    await db2.close()

    assert s1["realized_pnl"] == pytest.approx(200.0)
    assert s2["realized_pnl"] == pytest.approx(-75.0)


# 11. Emergency stop flag persists across restart
async def test_emergency_stop_flag_persists(temp_db_path):
    db1, repos1 = await _open_and_migrate(temp_db_path)
    await repos1.monitor_settings.set_emergency_stop(True)
    await db1.close()

    db2, repos2 = await _open_and_migrate(temp_db_path)
    is_stopped = await repos2.monitor_settings.get_emergency_stop()
    await db2.close()

    assert is_stopped is True


# 12. Price monitor interval setting persists
async def test_price_monitor_interval_setting_persists(temp_db_path):
    db1, repos1 = await _open_and_migrate(temp_db_path)
    await repos1.monitor_settings.set_interval(15)
    await db1.close()

    db2, repos2 = await _open_and_migrate(temp_db_path)
    interval = await repos2.monitor_settings.get_interval()
    await db2.close()

    assert interval == 15


# 13. Grid defaults persist across restart
async def test_grid_defaults_persist(temp_db_path):
    db1, repos1 = await _open_and_migrate(temp_db_path)
    seed = {
        "base_investment": 750.0,
        "dip_buy_amount": 150.0,
        "dip_percentage": 4.5,
        "profit_sell_amount": 250.0,
        "profit_percentage": 6.5,
        "max_levels": 8,
        "stop_loss_percentage": 40.0,
        "last_mode": "paper",
    }
    await repos1.grid_defaults.get_or_seed(seed)
    await db1.close()

    db2, repos2 = await _open_and_migrate(temp_db_path)
    defaults = await repos2.grid_defaults.get()
    await db2.close()

    assert defaults is not None
    assert defaults["base_investment"] == pytest.approx(750.0)
    assert defaults["dip_buy_amount"] == pytest.approx(150.0)
    assert defaults["dip_percentage"] == pytest.approx(4.5)
    assert defaults["last_mode"] == "paper"


# 14. Foreign key integrity enforced
async def test_foreign_key_integrity_enforced(temp_db_path):
    db, repos = await _open_and_migrate(temp_db_path)
    # Creating an order for a non-existent grid_id must raise an integrity error
    with pytest.raises(Exception):
        await repos.orders.create(
            _make_order(
                grid_id="non_existent_grid",
                side="buy",
                price=54000.0,
                quantity=0.01,
            )
        )
    await db.close()


# 15. Concurrent database writes under WAL mode
async def test_concurrent_database_writes(temp_db_path):
    db, repos = await _open_and_migrate(temp_db_path)

    async def _write_trade(i: int):
        await repos.trade_history.record(
            TradeHistoryRecord(
                trade_id=f"trd_{i}",
                grid_id="grd_concurrent",
                order_id=f"ord_{i}",
                symbol="BTCINR",
                side="buy",
                price=50000.0 + i,
                quantity=0.001,
                investment_inr=50.0,
                fee=0.1,
                pnl=0.0,
                executed_at=now_iso(),
            )
        )

    await asyncio.gather(*[_write_trade(i) for i in range(20)])
    trades = await repos.trade_history.list_all(limit=50)
    await db.close()

    assert len(trades) == 20


# 16. Schema migrations are idempotent across repeated connects
async def test_schema_migrations_idempotent(temp_db_path):
    db, _ = await _open_and_migrate(temp_db_path)
    # Run migrate second time on open db
    await db.migrate()
    # Run migrate third time
    await db.migrate()
    await db.close()

    # Reconnect and migrate again
    db2, repos2 = await _open_and_migrate(temp_db_path)
    grids = await repos2.grids.list_all()
    await db2.close()

    assert grids == []

import pytest

from config.constants import GridStatus
from storage.database import Database
from storage.models import DCAGridRecord, TradeHistoryRecord
from storage.repositories import Repositories
from replay.validation import ReplayValidator
from utils.helpers import new_id, now_iso

pytestmark = pytest.mark.anyio


async def _repos(tmp_path, name="v.sqlite3"):
    db = Database(str(tmp_path / name))
    await db.connect()
    await db.migrate()
    return db, Repositories(db)


def _grid(**overrides):
    now = now_iso()
    base = dict(
        grid_id=new_id("grd"), symbol="BTCINR", status=GridStatus.ACTIVE.value,
        entry_price=100.0, base_investment=500.0, dip_buy_amount=100.0,
        dip_percentage=5.0, profit_sell_amount=150.0, profit_percentage=5.0,
        max_levels=10, stop_loss_percentage=20.0, current_level=1,
        total_quantity=1.0, total_investment=100.0, average_entry_price=100.0,
        last_buy_price=100.0, next_buy_price=95.0, next_sell_price=105.0,
        realized_profit=0.0, completed_cycles=0, created_at=now, updated_at=now,
    )
    base.update(overrides)
    return DCAGridRecord(**base)


async def test_clean_db_passes_everything(tmp_path):
    db, repos = await _repos(tmp_path)
    await repos.grids.create(_grid())

    report = await ReplayValidator(repos).validate()
    assert report.all_passed
    await db.close()


async def test_active_grid_with_zero_quantity_fails(tmp_path):
    db, repos = await _repos(tmp_path)
    await repos.grids.create(_grid(total_quantity=0.0))

    report = await ReplayValidator(repos).validate()
    assert not report.all_passed
    failed_names = {c.name for c in report.failed}
    assert "no_active_grid_with_zero_quantity" in failed_names
    await db.close()


async def test_negative_quantity_fails(tmp_path):
    db, repos = await _repos(tmp_path)
    grid = _grid(status=GridStatus.STOPPED.value, total_quantity=-1.0)
    await repos.grids.create(grid)

    report = await ReplayValidator(repos).validate()
    failed_names = {c.name for c in report.failed}
    assert "no_negative_quantity" in failed_names
    assert "stopped_grids_no_negative_remainder" in failed_names
    await db.close()


async def test_negative_investment_fails(tmp_path):
    db, repos = await _repos(tmp_path)
    await repos.grids.create(_grid(total_investment=-50.0))

    report = await ReplayValidator(repos).validate()
    failed_names = {c.name for c in report.failed}
    assert "no_negative_investment" in failed_names
    await db.close()


async def test_orphan_order_fails(tmp_path):
    db, repos = await _repos(tmp_path)
    # orders.grid_id has a FK constraint, so a genuine orphan can never be
    # created through the normal repository layer — this validator check
    # is defense-in-depth for the (should-be-impossible) case where FK
    # enforcement is off or bypassed. Insert directly via raw SQL with FK
    # checks disabled for this connection to exercise that defense.
    conn = db.connection
    await conn.execute("PRAGMA foreign_keys=OFF;")
    await conn.execute(
        "INSERT INTO orders (order_id, grid_id, exchange_order_id, symbol, side, "
        "order_type, price, quantity, filled_quantity, filled_price, status, "
        "fee, created_at, updated_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (new_id("ord"), "nonexistent_grid", "EX1", "BTCINR", "buy", "market_order",
         100.0, 1.0, 0.0, 0.0, "open", 0.0, now_iso(), now_iso()),
    )
    await conn.commit()

    report = await ReplayValidator(repos).validate()
    failed_names = {c.name for c in report.failed}
    assert "no_orphan_orders" in failed_names
    await db.close()


async def test_trade_history_referencing_missing_grid_fails(tmp_path):
    db, repos = await _repos(tmp_path)
    await repos.trade_history.record(TradeHistoryRecord(
        trade_id=new_id("trd"), grid_id="nonexistent_grid", order_id="(dust-writeoff)",
        symbol="BTCINR", side="sell", price=100.0, quantity=1.0,
        investment_inr=0.0, fee=0.0, pnl=0.0, executed_at=now_iso(),
    ))

    report = await ReplayValidator(repos).validate()
    failed_names = {c.name for c in report.failed}
    assert "trade_history_references_valid_grids" in failed_names
    await db.close()


async def test_completed_cycles_exceeding_sell_history_fails(tmp_path):
    db, repos = await _repos(tmp_path)
    grid = _grid(completed_cycles=3)
    await repos.grids.create(grid)
    # Only one sell recorded, but the grid claims 3 completed cycles.
    await repos.trade_history.record(TradeHistoryRecord(
        trade_id=new_id("trd"), grid_id=grid.grid_id, order_id="EX1",
        symbol="BTCINR", side="sell", price=100.0, quantity=1.0,
        investment_inr=100.0, fee=0.1, pnl=5.0, executed_at=now_iso(),
    ))

    report = await ReplayValidator(repos).validate()
    failed_names = {c.name for c in report.failed}
    assert "completed_cycles_backed_by_sell_history" in failed_names
    await db.close()


async def test_completed_cycles_matching_sell_history_passes(tmp_path):
    db, repos = await _repos(tmp_path)
    grid = _grid(completed_cycles=1)
    await repos.grids.create(grid)
    await repos.trade_history.record(TradeHistoryRecord(
        trade_id=new_id("trd"), grid_id=grid.grid_id, order_id="EX1",
        symbol="BTCINR", side="sell", price=100.0, quantity=1.0,
        investment_inr=100.0, fee=0.1, pnl=5.0, executed_at=now_iso(),
    ))

    report = await ReplayValidator(repos).validate()
    assert report.all_passed
    await db.close()


async def test_zombie_grid_active_zero_level_no_orders_fails(tmp_path):
    """Mirrors RecoveryManager._detect_zombie_grids()'s exact condition: an
    ACTIVE grid with current_level=0 and no order rows at all — a
    crash-window artifact where grid creation succeeded but the initial
    order was never written."""
    db, repos = await _repos(tmp_path)
    zombie = _grid(current_level=0, total_quantity=0.0, total_investment=0.0)
    await repos.grids.create(zombie)

    report = await ReplayValidator(repos).validate()
    failed_names = {c.name for c in report.failed}
    assert "no_zombie_grids" in failed_names
    zombie_check = next(c for c in report.checks if c.name == "no_zombie_grids")
    assert zombie.grid_id in zombie_check.detail
    await db.close()


async def test_active_grid_with_current_level_zero_but_real_orders_is_not_a_zombie(tmp_path):
    """current_level=0 alone isn't a zombie — only current_level=0 AND no
    order rows at all is. A grid can legitimately be freshly created with
    current_level=0 for one instant before its first order is written; the
    presence of ANY order row means it isn't stuck."""
    from storage.models import OrderRecord
    db, repos = await _repos(tmp_path)
    grid = _grid(current_level=0)  # total_quantity=1.0 (fixture default) — a real position, not dust
    await repos.grids.create(grid)
    await repos.orders.create(OrderRecord(
        order_id=new_id("ord"), grid_id=grid.grid_id, exchange_order_id="EX1",
        symbol="BTCINR", side="buy", order_type="market_order", price=100.0,
        quantity=1.0, status="open", filled_quantity=0.0, filled_price=0.0,
        fee=0.0, created_at=now_iso(), updated_at=now_iso(),
    ))

    report = await ReplayValidator(repos).validate()
    assert report.all_passed
    await db.close()


async def test_active_grid_with_orders_and_nonzero_level_is_not_a_zombie(tmp_path):
    """The normal, healthy case — current_level > 0 — must never be
    flagged regardless of order history."""
    db, repos = await _repos(tmp_path)
    grid = _grid(current_level=2)
    await repos.grids.create(grid)

    report = await ReplayValidator(repos).validate()
    assert report.all_passed
    await db.close()


async def test_stopped_grid_with_zero_level_is_not_a_zombie(tmp_path):
    """Only ACTIVE grids can be zombies — a STOPPED grid with
    current_level=0 (e.g. a dust write-off before any level advanced) is
    normal, not stuck."""
    db, repos = await _repos(tmp_path)
    grid = _grid(status=GridStatus.STOPPED.value, current_level=0,
                  total_quantity=0.0, total_investment=0.0)
    await repos.grids.create(grid)

    report = await ReplayValidator(repos).validate()
    assert report.all_passed
    await db.close()

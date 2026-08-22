import pytest

from config.constants import GridStatus
from replay.engine import ReplayStats
from replay.report import build_report, build_trading_summary
from replay.validation import ReplayValidator
from storage.database import Database
from storage.models import DCAGridRecord, TradeHistoryRecord
from storage.repositories import Repositories
from utils.helpers import new_id, now_iso

pytestmark = pytest.mark.anyio


async def _repos(tmp_path, name="r.sqlite3"):
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
        realized_profit=10.0, completed_cycles=2, created_at=now, updated_at=now,
    )
    base.update(overrides)
    return DCAGridRecord(**base)


def _trade(grid_id, side, pnl, order_id="EX1"):
    return TradeHistoryRecord(
        trade_id=new_id("trd"), grid_id=grid_id, order_id=order_id,
        symbol="BTCINR", side=side, price=100.0, quantity=1.0,
        investment_inr=100.0, fee=0.1, pnl=pnl, executed_at=now_iso(),
    )


async def test_trading_summary_counts_buys_and_sells(tmp_path):
    db, repos = await _repos(tmp_path)
    grid = _grid()
    await repos.grids.create(grid)
    await repos.trade_history.record(_trade(grid.grid_id, "buy", 0.0))
    await repos.trade_history.record(_trade(grid.grid_id, "sell", 5.0))
    await repos.trade_history.record(_trade(grid.grid_id, "sell", -2.0))

    summary = await build_trading_summary(repos)
    assert summary.total_buys == 1
    assert summary.total_sells == 2
    assert summary.win_rate_pct == pytest.approx(50.0)
    await db.close()


async def test_trading_summary_excludes_dust_writeoffs_from_sell_count(tmp_path):
    db, repos = await _repos(tmp_path)
    grid = _grid()
    await repos.grids.create(grid)
    await repos.trade_history.record(_trade(grid.grid_id, "sell", 3.0))
    await repos.trade_history.record(_trade(grid.grid_id, "sell", 0.0, order_id="(dust-writeoff)"))

    summary = await build_trading_summary(repos)
    assert summary.total_sells == 1
    assert summary.total_dust_writeoffs == 1
    await db.close()


async def test_trading_summary_profit_factor_none_when_no_losses(tmp_path):
    db, repos = await _repos(tmp_path)
    grid = _grid()
    await repos.grids.create(grid)
    await repos.trade_history.record(_trade(grid.grid_id, "sell", 5.0))

    summary = await build_trading_summary(repos)
    assert summary.profit_factor is None
    await db.close()


async def test_trading_summary_profit_factor_computed_with_losses(tmp_path):
    db, repos = await _repos(tmp_path)
    grid = _grid()
    await repos.grids.create(grid)
    await repos.trade_history.record(_trade(grid.grid_id, "sell", 10.0))
    await repos.trade_history.record(_trade(grid.grid_id, "sell", -5.0))

    summary = await build_trading_summary(repos)
    assert summary.profit_factor == pytest.approx(2.0)
    await db.close()


async def test_build_report_renders_text_and_json(tmp_path):
    db, repos = await _repos(tmp_path)
    grid = _grid(completed_cycles=1)
    await repos.grids.create(grid)
    await repos.trade_history.record(_trade(grid.grid_id, "sell", 5.0))

    stats = ReplayStats(candles_processed=10, sub_ticks_processed=40, trigger_evaluations=40,
                         symbols_seen={"BTCINR"}, start_timestamp=0.0, end_timestamp=600.0)
    validation = await ReplayValidator(repos).validate()

    report = await build_report(
        repos=repos, stats=stats, validation=validation,
        replay_duration_seconds=1.23, speed=None,
    )
    assert report.passed
    text = report.render_text()
    assert "REPLAY REPORT" in text
    assert "OVERALL: PASS" in text

    as_json = report.render_json()
    assert '"all_passed": true' in as_json
    await db.close()


async def test_build_report_fails_when_validation_fails(tmp_path):
    db, repos = await _repos(tmp_path)
    await repos.grids.create(_grid(total_quantity=0.0))  # active + zero qty -> validation fail

    stats = ReplayStats()
    validation = await ReplayValidator(repos).validate()
    report = await build_report(
        repos=repos, stats=stats, validation=validation,
        replay_duration_seconds=0.1, speed=None,
    )
    assert not report.passed
    assert "OVERALL: FAIL" in report.render_text()
    await db.close()

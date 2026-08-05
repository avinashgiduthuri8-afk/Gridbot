"""Regression tests: automated dust write-offs (profit-sell / stop-loss)
must produce the SAME audit trail as manual_sell()'s dust write-off —
trade_history entry, untouched realized_profit, zeroed quantity/investment,
STOPPED status, and the dust_position_written_off notification.
"""
from __future__ import annotations

import pytest

from config.constants import GridStatus
from risk.risk_manager import RiskManager
from storage.models import DCAGridRecord
from trading.dca_manager import DCAManager
from trading.order_manager import OrderManager
from utils.helpers import new_id, now_iso

pytestmark = pytest.mark.anyio


def _make_grid(
    *,
    symbol: str = "BTCINR",
    total_quantity: float,
    total_investment: float,
    average_entry_price: float = 54_000.0,
    next_sell_price: float = 57_780.0,
    stop_loss_percentage: float = 50.0,
    profit_sell_amount: float = 150.0,
    realized_profit: float = 0.0,
) -> DCAGridRecord:
    now = now_iso()
    return DCAGridRecord(
        grid_id=new_id("grd"), symbol=symbol, status=GridStatus.ACTIVE.value,
        entry_price=average_entry_price, base_investment=500.0,
        dip_buy_amount=100.0, dip_percentage=5.0,
        profit_sell_amount=profit_sell_amount, profit_percentage=7.0,
        max_levels=10, stop_loss_percentage=stop_loss_percentage,
        current_level=1, total_quantity=total_quantity,
        total_investment=total_investment, average_entry_price=average_entry_price,
        last_buy_price=average_entry_price, next_buy_price=average_entry_price * 0.95,
        next_sell_price=next_sell_price, realized_profit=realized_profit,
        completed_cycles=0, created_at=now, updated_at=now,
    )


@pytest.fixture
def order_manager(mock_exchange, repos):
    return OrderManager(mock_exchange, repos)


@pytest.fixture
def dca(mock_exchange, repos, order_manager, mock_notifier, permissive_risk_settings):
    return DCAManager(
        exchange=mock_exchange, repos=repos, order_manager=order_manager,
        notifier=mock_notifier, risk=RiskManager(permissive_risk_settings, repos),
    )


# ---------------------------------------------------------------------------
# Automated profit-sell dust write-off
# ---------------------------------------------------------------------------

async def test_auto_profit_dust_history_entry_exists(dca, repos, mock_exchange):
    grid = _make_grid(
        total_quantity=0.0005, total_investment=27.0, realized_profit=42.0,
    )
    await repos.grids.create(grid)

    await dca.check_grid_triggers(grid.grid_id, current_price=58_000.0)

    trades = await repos.trade_history.list_for_grid(grid.grid_id)
    assert len(trades) == 1
    assert trades[0]["side"] == "sell"
    assert trades[0]["quantity"] == pytest.approx(0.0005)
    assert trades[0]["pnl"] == pytest.approx(0.0)


async def test_auto_profit_dust_realized_profit_unchanged(dca, repos):
    grid = _make_grid(
        total_quantity=0.0005, total_investment=27.0, realized_profit=42.0,
    )
    await repos.grids.create(grid)

    await dca.check_grid_triggers(grid.grid_id, current_price=58_000.0)

    row = await repos.grids.get(grid.grid_id)
    assert row["realized_profit"] == pytest.approx(42.0)
    assert row["status"] == GridStatus.STOPPED.value
    assert row["total_quantity"] == pytest.approx(0.0)
    assert row["total_investment"] == pytest.approx(0.0)


# ---------------------------------------------------------------------------
# Automated stop-loss dust write-off
# ---------------------------------------------------------------------------

async def test_auto_stop_loss_dust_history_entry_exists(dca, repos):
    grid = _make_grid(
        total_quantity=0.0005, total_investment=27.0, realized_profit=15.0,
    )
    await repos.grids.create(grid)

    await dca.check_grid_triggers(grid.grid_id, current_price=26_000.0)

    trades = await repos.trade_history.list_for_grid(grid.grid_id)
    assert len(trades) == 1
    assert trades[0]["side"] == "sell"
    assert trades[0]["quantity"] == pytest.approx(0.0005)
    assert trades[0]["pnl"] == pytest.approx(0.0)


async def test_auto_stop_loss_dust_realized_profit_unchanged(dca, repos):
    grid = _make_grid(
        total_quantity=0.0005, total_investment=27.0, realized_profit=15.0,
    )
    await repos.grids.create(grid)

    await dca.check_grid_triggers(grid.grid_id, current_price=26_000.0)

    row = await repos.grids.get(grid.grid_id)
    assert row["realized_profit"] == pytest.approx(15.0)
    assert row["status"] == GridStatus.STOPPED.value
    assert row["total_quantity"] == pytest.approx(0.0)
    assert row["total_investment"] == pytest.approx(0.0)


# ---------------------------------------------------------------------------
# Portfolio totals / active-grid count across both automated paths
# ---------------------------------------------------------------------------

async def test_portfolio_totals_and_active_count_after_auto_profit_dust(dca, repos):
    dust_grid = _make_grid(
        symbol="BTCINR", total_quantity=0.0005, total_investment=27.0,
    )
    healthy_grid = _make_grid(
        symbol="ETHINR", total_quantity=0.00925, total_investment=499.5,
    )
    await repos.grids.create(dust_grid)
    await repos.grids.create(healthy_grid)

    await dca.check_grid_triggers(dust_grid.grid_id, current_price=58_000.0)

    all_grids = await repos.grids.list_all()
    assert sum(g["total_investment"] for g in all_grids) == pytest.approx(499.5)
    assert sum(g["total_quantity"] for g in all_grids) == pytest.approx(0.00925)

    active = [g for g in all_grids if g["status"] == GridStatus.ACTIVE.value]
    assert len(active) == 1
    assert active[0]["symbol"] == "ETHINR"


async def test_portfolio_totals_and_active_count_after_auto_stop_loss_dust(dca, repos):
    dust_grid = _make_grid(
        symbol="BTCINR", total_quantity=0.0005, total_investment=27.0,
    )
    healthy_grid = _make_grid(
        symbol="ETHINR", total_quantity=0.00925, total_investment=499.5,
    )
    await repos.grids.create(dust_grid)
    await repos.grids.create(healthy_grid)

    await dca.check_grid_triggers(dust_grid.grid_id, current_price=26_000.0)

    all_grids = await repos.grids.list_all()
    assert sum(g["total_investment"] for g in all_grids) == pytest.approx(499.5)
    assert sum(g["total_quantity"] for g in all_grids) == pytest.approx(0.00925)

    active = [g for g in all_grids if g["status"] == GridStatus.ACTIVE.value]
    assert len(active) == 1
    assert active[0]["symbol"] == "ETHINR"


# ---------------------------------------------------------------------------
# Both automated paths use the same order_id convention and notification
# as manual_sell(), for a consistent audit trail across all three call sites.
# ---------------------------------------------------------------------------

async def test_auto_profit_dust_uses_same_order_id_convention_as_manual(dca, repos):
    grid = _make_grid(total_quantity=0.0005, total_investment=27.0)
    await repos.grids.create(grid)

    await dca.check_grid_triggers(grid.grid_id, current_price=58_000.0)

    trades = await repos.trade_history.list_for_grid(grid.grid_id)
    assert trades[0]["order_id"] == "(dust-writeoff)"


async def test_auto_stop_loss_dust_notifier_called(dca, repos, mock_notifier):
    grid = _make_grid(total_quantity=0.0005, total_investment=27.0)
    await repos.grids.create(grid)

    await dca.check_grid_triggers(grid.grid_id, current_price=26_000.0)

    assert mock_notifier.was_called("dust_position_written_off")

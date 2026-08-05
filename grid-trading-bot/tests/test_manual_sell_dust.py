"""Regression tests for manual_sell() dust / minimum-quantity handling.

Covers the gap fixed here: when the ENTIRE remaining position clamps below
the exchange's minimum sellable quantity, manual_sell() now writes it off
as dust and closes the grid (mirroring the already-correct automated
profit-sell / stop-loss dust write-off) instead of raising a raw
"Sell quantity 0.00000000 ..." error and leaving the grid stuck ACTIVE.
A genuine partial-sell request that's merely too small is still rejected
with a ValueError, but with a clearer held/minimum-sellable message, and
does NOT touch the grid.
"""
from __future__ import annotations

import pytest

from config.constants import GridStatus
from storage.models import DCAGridRecord
from trading.dca_manager import ManualSellResult
from utils.helpers import new_id, now_iso

pytestmark = pytest.mark.anyio


def _make_grid(
    *,
    total_investment: float,
    total_quantity: float,
    average_entry_price: float,
    realized_profit: float = 12.5,
    symbol: str = "BTCINR",
) -> DCAGridRecord:
    now = now_iso()
    return DCAGridRecord(
        grid_id=new_id("grd"),
        symbol=symbol,
        status=GridStatus.ACTIVE.value,
        entry_price=54000.0,
        base_investment=500.0,
        dip_buy_amount=100.0,
        dip_percentage=5.0,
        profit_sell_amount=150.0,
        profit_percentage=7.0,
        max_levels=10,
        stop_loss_percentage=50.0,
        current_level=1,
        total_quantity=total_quantity,
        total_investment=total_investment,
        average_entry_price=average_entry_price,
        last_buy_price=54000.0,
        next_buy_price=51300.0,
        next_sell_price=57780.0,
        realized_profit=realized_profit,
        completed_cycles=0,
        created_at=now,
        updated_at=now,
    )


# mock_exchange's BTCINR market_info (see conftest.py): min_quantity=0.001,
# min_amount=10.0, step_size=1e-5, last_price=54000.0-ish via get_ticker.


# ---------------------------------------------------------------------------
# 1 & 7 & 9 — Full-position dust closes the grid, status STOPPED, totals zeroed
# ---------------------------------------------------------------------------

async def test_full_position_dust_closes_grid(app_context, repos):
    grid = _make_grid(
        total_investment=0.5, total_quantity=0.00000001, average_entry_price=54000.0,
    )
    await repos.grids.create(grid)

    result = await app_context.dca_manager.manual_sell(grid.grid_id, None)

    assert isinstance(result, ManualSellResult)
    assert result.dust_written_off is True
    assert result.order is None
    assert "written off as exchange dust" in result.message
    assert "Grid closed successfully" in result.message

    row = await repos.grids.get(grid.grid_id)
    assert row["status"] == GridStatus.STOPPED.value
    assert row["total_quantity"] == 0.0
    assert row["total_investment"] == 0.0


# ---------------------------------------------------------------------------
# 2 — Partial dust returns a friendly message and does NOT close the grid
# ---------------------------------------------------------------------------

async def test_partial_dust_returns_friendly_message_grid_stays_active(app_context, repos):
    # Held well above the minimum, but the requested INR amount is tiny —
    # a genuine "ask for more" case, not an unsellable remainder.
    grid = _make_grid(
        total_investment=500.0, total_quantity=0.02, average_entry_price=50000.0,
    )
    await repos.grids.create(grid)

    with pytest.raises(ValueError) as exc_info:
        await app_context.dca_manager.manual_sell(grid.grid_id, 1.0)

    message = str(exc_info.value)
    assert "below the exchange's minimum trade size" in message
    assert "Held:" in message
    assert "Minimum sellable:" in message
    assert "0.00000000" not in message  # the old confusing text must be gone

    row = await repos.grids.get(grid.grid_id)
    assert row["status"] == GridStatus.ACTIVE.value
    assert row["total_quantity"] == 0.02  # untouched


# ---------------------------------------------------------------------------
# 3 — Normal full sell (entire position, well above minimum) is unchanged
# ---------------------------------------------------------------------------

async def test_normal_full_sell_unchanged(app_context, repos):
    grid = _make_grid(
        total_investment=1000.0, total_quantity=0.02, average_entry_price=50000.0,
    )
    await repos.grids.create(grid)

    result = await app_context.dca_manager.manual_sell(grid.grid_id, None)

    assert result.dust_written_off is False
    assert result.order is not None
    assert "Manual sell placed" in result.message

    row = await repos.grids.get(grid.grid_id)
    # A real order was placed, not a dust write-off — grid stays ACTIVE
    # until the fill is processed by handle_order_filled elsewhere.
    assert row["status"] == GridStatus.ACTIVE.value


# ---------------------------------------------------------------------------
# 4 — Normal partial sell (valid INR amount) is unchanged
# ---------------------------------------------------------------------------

async def test_normal_partial_sell_unchanged(app_context, repos):
    grid = _make_grid(
        total_investment=1000.0, total_quantity=0.02, average_entry_price=50000.0,
    )
    await repos.grids.create(grid)

    result = await app_context.dca_manager.manual_sell(grid.grid_id, 300.0)

    assert result.dust_written_off is False
    assert result.order is not None
    assert "Manual sell placed" in result.message


# ---------------------------------------------------------------------------
# 5 & 8 — Dust write-off is recorded in trade_history
# ---------------------------------------------------------------------------

async def test_dust_writeoff_recorded_in_trade_history(app_context, repos):
    grid = _make_grid(
        total_investment=0.5, total_quantity=0.00000001, average_entry_price=54000.0,
    )
    await repos.grids.create(grid)

    trades_before = await repos.trade_history.list_for_grid(grid.grid_id)
    assert len(trades_before) == 0

    await app_context.dca_manager.manual_sell(grid.grid_id, None)

    trades = await repos.trade_history.list_for_grid(grid.grid_id)
    assert len(trades) == 1
    trade = trades[0]
    assert trade["side"] == "sell"
    assert trade["quantity"] == pytest.approx(0.00000001)
    assert trade["grid_id"] == grid.grid_id
    assert trade["symbol"] == "BTCINR"


# ---------------------------------------------------------------------------
# 6 — Realized P&L is left untouched by the write-off (nothing was sold)
# ---------------------------------------------------------------------------

async def test_dust_writeoff_does_not_change_realized_profit(app_context, repos):
    grid = _make_grid(
        total_investment=0.5, total_quantity=0.00000001, average_entry_price=54000.0,
        realized_profit=77.25,
    )
    await repos.grids.create(grid)

    await app_context.dca_manager.manual_sell(grid.grid_id, None)

    row = await repos.grids.get(grid.grid_id)
    assert row["realized_profit"] == pytest.approx(77.25)


# ---------------------------------------------------------------------------
# 9 (continued) — Portfolio totals: a written-off grid contributes nothing
# ---------------------------------------------------------------------------

async def test_portfolio_totals_correct_after_dust_writeoff(app_context, repos):
    dust_grid = _make_grid(
        total_investment=0.5, total_quantity=0.00000001, average_entry_price=54000.0,
        symbol="BTCINR",
    )
    healthy_grid = _make_grid(
        total_investment=1000.0, total_quantity=0.02, average_entry_price=50000.0,
        symbol="ETHINR",
    )
    await repos.grids.create(dust_grid)
    await repos.grids.create(healthy_grid)

    await app_context.dca_manager.manual_sell(dust_grid.grid_id, None)

    all_grids = await repos.grids.list_all()
    total_investment_sum = sum(g["total_investment"] for g in all_grids)
    total_quantity_sum = sum(g["total_quantity"] for g in all_grids)

    # Only the healthy grid's capital should remain counted.
    assert total_investment_sum == pytest.approx(1000.0)
    assert total_quantity_sum == pytest.approx(0.02)

    active_grids = [g for g in all_grids if g["status"] == GridStatus.ACTIVE.value]
    assert len(active_grids) == 1
    assert active_grids[0]["symbol"] == "ETHINR"

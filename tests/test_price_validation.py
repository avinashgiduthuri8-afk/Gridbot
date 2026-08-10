"""Regression tests for the price-sanity validation fix.

Covers both layers:
  1. utils.helpers.is_valid_price — the shared validity check itself.
  2. DCAManager.check_grid_triggers's own defensive validation, which
     protects any DIRECT caller (replay engine, tests, future
     integrations) that bypasses PriceMonitor's own guard entirely.

PriceMonitor's layer (which uses the same helper) is covered separately
in tests/test_price_monitor.py.
"""
from __future__ import annotations

import pytest

from config.constants import GridStatus
from storage.models import DCAGridRecord
from utils.helpers import is_valid_price, new_id, now_iso

pytestmark = pytest.mark.anyio


# ---------------------------------------------------------------------------
# Layer 0: is_valid_price itself
# ---------------------------------------------------------------------------


class TestIsValidPrice:
    def test_positive_price_is_valid(self):
        assert is_valid_price(100.0) is True
        assert is_valid_price(0.00001) is True
        assert is_valid_price(5_000_000.0) is True

    def test_zero_is_invalid(self):
        assert is_valid_price(0.0) is False
        assert is_valid_price(0) is False

    def test_negative_is_invalid(self):
        assert is_valid_price(-1.0) is False
        assert is_valid_price(-5_000_000.0) is False

    def test_nan_is_invalid(self):
        assert is_valid_price(float("nan")) is False

    def test_positive_infinity_is_invalid(self):
        assert is_valid_price(float("inf")) is False

    def test_negative_infinity_is_invalid(self):
        assert is_valid_price(float("-inf")) is False

    def test_non_numeric_is_invalid(self):
        assert is_valid_price("100") is False
        assert is_valid_price(None) is False
        assert is_valid_price([100.0]) is False


# ---------------------------------------------------------------------------
# Layer 2: DCAManager.check_grid_triggers's own defensive validation
# ---------------------------------------------------------------------------


def _active_grid(**overrides) -> DCAGridRecord:
    now = now_iso()
    base = dict(
        grid_id=new_id("grd"), symbol="BTCINR", status=GridStatus.ACTIVE.value,
        entry_price=100000.0, base_investment=500000.0, dip_buy_amount=100000.0,
        dip_percentage=5.0, profit_sell_amount=150000.0, profit_percentage=5.0,
        max_levels=10, stop_loss_percentage=20.0, current_level=1,
        total_quantity=5.0, total_investment=500000.0, average_entry_price=100000.0,
        last_buy_price=100000.0, next_buy_price=95000.0, next_sell_price=105000.0,
        realized_profit=0.0, completed_cycles=0, created_at=now, updated_at=now,
    )
    base.update(overrides)
    return DCAGridRecord(**base)


@pytest.mark.parametrize("bad_price", [0.0, -1.0, -100000.0, float("nan"), float("inf"), float("-inf")])
async def test_check_grid_triggers_rejects_invalid_price_directly(app_context, repos, bad_price):
    """A direct caller of check_grid_triggers() (replay engine, a test, a
    future integration) gets the same protection PriceMonitor has, even
    though nothing routed this price through PriceMonitor's own guard."""
    grid = _active_grid()
    await repos.grids.create(grid)

    await app_context.dca_manager.check_grid_triggers(grid.grid_id, bad_price)

    orders = await repos.orders.list_for_grid(grid.grid_id)
    assert orders == [], f"no order should be placed for an invalid price {bad_price!r}"

    row = await repos.grids.get(grid.grid_id)
    assert row["status"] == GridStatus.ACTIVE.value, "an invalid price must not trigger stop-loss or any state change"
    assert row["total_quantity"] == grid.total_quantity, "grid state must be completely untouched"


async def test_check_grid_triggers_still_works_normally_for_a_valid_price(app_context, repos):
    """Control case: the fix must not affect any genuinely valid price —
    a real stop-loss-triggering price must still fire normally."""
    grid = _active_grid()
    await repos.grids.create(grid)

    # 20% stop-loss from avg entry 100000 triggers at/below 80000.
    await app_context.dca_manager.check_grid_triggers(grid.grid_id, 79000.0)

    row = await repos.grids.get(grid.grid_id)
    assert row["status"] == GridStatus.STOPPED.value, "a genuinely valid, stop-loss-triggering price must still work"


async def test_a_zero_price_specifically_does_not_falsely_trigger_stop_loss(app_context, repos):
    """The exact scenario the audit flagged: current_price=0 would satisfy
    is_stop_loss_triggered() for ANY positive stop price, since
    0 <= stop_price is always true. Confirms this no longer fires."""
    grid = _active_grid(stop_loss_percentage=20.0, average_entry_price=100000.0)
    await repos.grids.create(grid)

    await app_context.dca_manager.check_grid_triggers(grid.grid_id, 0.0)

    row = await repos.grids.get(grid.grid_id)
    assert row["status"] == GridStatus.ACTIVE.value, "price=0 must not trigger a false stop-loss liquidation"
    assert row["total_quantity"] == grid.total_quantity


async def test_nan_price_does_not_falsely_trigger_dip_buy(app_context, repos):
    """NaN comparisons are always False in Python, so a naive
    current_price <= next_buy_price check wouldn't false-trigger on NaN by
    accident — but this confirms the explicit guard also correctly blocks
    it, rather than relying on that comparison quirk."""
    grid = _active_grid()
    await repos.grids.create(grid)

    await app_context.dca_manager.check_grid_triggers(grid.grid_id, float("nan"))

    orders = await repos.orders.list_for_grid(grid.grid_id)
    assert orders == []
    row = await repos.grids.get(grid.grid_id)
    assert row["current_level"] == grid.current_level

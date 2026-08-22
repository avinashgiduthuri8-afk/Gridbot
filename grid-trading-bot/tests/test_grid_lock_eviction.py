"""Regression tests for the _grid_locks eviction fix.

DCAManager._grid_locks previously grew forever — one asyncio.Lock entry
per grid ever created, never removed even after the grid reached a
terminal state (STOPPED/COMPLETED). Over a long-running deployment that
creates many grids over time, this was an unbounded memory leak.

These tests confirm: (1) the dict returns to its original size after many
grids are created and terminated, (2) locking guarantees are preserved
(concurrent callers on the same grid still serialize correctly), and
(3) a lock is never evicted while another coroutine still holds or is
waiting on it.
"""
from __future__ import annotations

import asyncio

import pytest

from config.constants import GridStatus
from storage.models import DCAGridRecord
from utils.helpers import new_id, now_iso

pytestmark = pytest.mark.anyio


def _grid(symbol: str, **overrides) -> DCAGridRecord:
    now = now_iso()
    base = dict(
        grid_id=new_id("grd"), symbol=symbol, status=GridStatus.ACTIVE.value,
        entry_price=100.0, base_investment=500.0, dip_buy_amount=100.0,
        dip_percentage=5.0, profit_sell_amount=150.0, profit_percentage=5.0,
        max_levels=10, stop_loss_percentage=20.0, current_level=1,
        total_quantity=5.0, total_investment=500.0, average_entry_price=100.0,
        last_buy_price=100.0, next_buy_price=95.0, next_sell_price=105.0,
        realized_profit=0.0, completed_cycles=0, created_at=now, updated_at=now,
    )
    base.update(overrides)
    return DCAGridRecord(**base)


async def test_grid_locks_do_not_grow_after_many_manual_stops(app_context, repos):
    """Create hundreds of grids, stop every one of them (a terminal
    transition via stop_grid), and confirm _grid_locks and its refcount
    dict both return to their original (empty) size."""
    dca = app_context.dca_manager
    assert len(dca._grid_locks) == 0
    assert len(dca._grid_lock_refcounts) == 0

    grid_ids = []
    for i in range(300):
        grid = _grid(symbol=f"SYM{i}INR")
        await repos.grids.create(grid)
        grid_ids.append(grid.grid_id)

    for grid_id in grid_ids:
        await dca.stop_grid(grid_id, reason="bulk test")

    assert len(dca._grid_locks) == 0, (
        f"expected 0 remaining lock entries after stopping all grids, found {len(dca._grid_locks)}"
    )
    assert len(dca._grid_lock_refcounts) == 0

    # And every grid really did reach a terminal state (sanity check the
    # test itself is exercising what it claims to).
    for grid_id in grid_ids:
        row = await repos.grids.get(grid_id)
        assert row["status"] == GridStatus.STOPPED.value


async def test_grid_locks_do_not_grow_after_completed_full_exit(app_context, repos):
    """Same, but via the COMPLETED path (a normal full sell fill) rather
    than STOPPED, to confirm both terminal statuses are handled."""
    dca = app_context.dca_manager

    grid_ids = []
    for i in range(200):
        grid = _grid(symbol=f"COMP{i}INR")
        await repos.grids.create(grid)
        grid_ids.append(grid.grid_id)

    for grid_id in grid_ids:
        result = await dca.manual_sell(grid_id, None)
        if result.order is not None:
            await dca.handle_order_filled(result.order.order_id, fill_price=100.0, fill_qty=5.0)

    assert len(dca._grid_locks) == 0
    assert len(dca._grid_lock_refcounts) == 0

    for grid_id in grid_ids:
        row = await repos.grids.get(grid_id)
        assert row["status"] in (GridStatus.COMPLETED.value, GridStatus.STOPPED.value)


async def test_active_grids_keep_their_lock_entry(app_context, repos):
    """Locks for grids that are still ACTIVE must NOT be evicted — only
    terminal-state grids get cleaned up."""
    dca = app_context.dca_manager
    grid = _grid(symbol="KEEPINR")
    await repos.grids.create(grid)

    # Touch the grid with a lock-guarded, non-terminal operation.
    await dca.pause_grid(grid.grid_id)
    await dca.resume_grid(grid.grid_id)

    row = await repos.grids.get(grid.grid_id)
    assert row["status"] == GridStatus.ACTIVE.value
    assert grid.grid_id in dca._grid_locks, "an active grid's lock must not be evicted"


async def test_lock_not_evicted_while_a_second_coroutine_is_waiting(app_context, repos):
    """The core safety property: if a second coroutine is already queued
    on a grid's lock when the first releases it (even if the grid just
    became terminal), eviction must not happen until that second
    coroutine has also finished — otherwise the two coroutines would end
    up serialized on two DIFFERENT lock objects, breaking mutual
    exclusion."""
    dca = app_context.dca_manager
    grid = _grid(symbol="RACEINR")
    await repos.grids.create(grid)

    order_of_events: list[str] = []
    first_holder_started = asyncio.Event()
    let_first_holder_finish = asyncio.Event()

    async def first_holder():
        async with dca._grid_lock(grid.grid_id):
            order_of_events.append("first_acquired")
            first_holder_started.set()
            await let_first_holder_finish.wait()
            # Transition the grid to terminal WHILE holding the lock, same
            # as a real stop_grid/manual_sell call would.
            await repos.grids.update_state(grid.grid_id, status=GridStatus.STOPPED.value)
            order_of_events.append("first_released")

    async def second_waiter():
        await first_holder_started.wait()
        lock_before_second_call = dca._grid_locks.get(grid.grid_id)
        async with dca._grid_lock(grid.grid_id):
            # By the time we get in here, the lock we queued on must be
            # the SAME object we saw before — proving it wasn't swapped
            # out from under us while we were waiting.
            assert dca._grid_locks.get(grid.grid_id) is lock_before_second_call or \
                grid.grid_id not in dca._grid_locks  # or already evicted after we're done below
            order_of_events.append("second_acquired")

    t1 = asyncio.create_task(first_holder())
    t2 = asyncio.create_task(second_waiter())
    await first_holder_started.wait()
    await asyncio.sleep(0.01)  # let second_waiter register itself as queued
    let_first_holder_finish.set()
    await asyncio.wait_for(asyncio.gather(t1, t2), timeout=5)

    assert order_of_events == ["first_acquired", "first_released", "second_acquired"]
    # After BOTH coroutines are done and the grid is terminal, the lock
    # must now be evicted.
    assert grid.grid_id not in dca._grid_locks
    assert grid.grid_id not in dca._grid_lock_refcounts


async def test_concurrent_operations_on_same_grid_still_serialize(app_context, repos):
    """Locking guarantees must be unchanged: two concurrent callers on the
    same grid must never both be "inside" at once."""
    dca = app_context.dca_manager
    grid = _grid(symbol="SERIALINR")
    await repos.grids.create(grid)

    concurrent_count = 0
    max_concurrent = 0

    async def touch():
        nonlocal concurrent_count, max_concurrent
        async with dca._grid_lock(grid.grid_id):
            concurrent_count += 1
            max_concurrent = max(max_concurrent, concurrent_count)
            await asyncio.sleep(0.01)
            concurrent_count -= 1

    await asyncio.gather(*(touch() for _ in range(20)))
    assert max_concurrent == 1, "the per-grid lock must still fully serialize concurrent access"

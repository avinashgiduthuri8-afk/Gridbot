"""Tests for the Quick Default Grid Mode: GridDefaultsRepository persistence
and the /defaults command."""

from __future__ import annotations

import pytest

from config.constants import QUICK_GRID_DEFAULTS_SEED

pytestmark = pytest.mark.anyio


async def test_get_returns_none_before_seeding(repos):
    assert await repos.grid_defaults.get() is None


async def test_get_or_seed_creates_row_with_seed_values(repos):
    d = await repos.grid_defaults.get_or_seed(QUICK_GRID_DEFAULTS_SEED)
    assert d["base_investment"] == 500.0
    assert d["dip_buy_amount"] == 100.0
    assert d["dip_percentage"] == 5.0
    assert d["profit_sell_amount"] == 120.0
    assert d["profit_percentage"] == 7.0
    assert d["max_levels"] == 5
    assert d["stop_loss_percentage"] == 50.0
    assert d["last_mode"] is None


async def test_get_or_seed_does_not_overwrite_existing_row(repos):
    await repos.grid_defaults.get_or_seed(QUICK_GRID_DEFAULTS_SEED)
    await repos.grid_defaults.update(base_investment=999.0)

    d = await repos.grid_defaults.get_or_seed(QUICK_GRID_DEFAULTS_SEED)
    assert d["base_investment"] == 999.0, "second get_or_seed call must not reset an edited value"


async def test_update_merges_partial_fields(repos):
    await repos.grid_defaults.get_or_seed(QUICK_GRID_DEFAULTS_SEED)
    updated = await repos.grid_defaults.update(base_investment=750.0, max_levels=7)
    assert updated["base_investment"] == 750.0
    assert updated["max_levels"] == 7
    # Untouched fields preserved
    assert updated["dip_percentage"] == 5.0
    assert updated["profit_percentage"] == 7.0


async def test_update_rejects_unknown_field(repos):
    await repos.grid_defaults.get_or_seed(QUICK_GRID_DEFAULTS_SEED)
    with pytest.raises(ValueError):
        await repos.grid_defaults.update(not_a_real_field=123)


async def test_update_before_seed_raises(repos):
    with pytest.raises(RuntimeError):
        await repos.grid_defaults.update(base_investment=100.0)


async def test_defaults_persist_across_simulated_restart(repos, db):
    from storage.repositories import Repositories

    await repos.grid_defaults.get_or_seed(QUICK_GRID_DEFAULTS_SEED)
    await repos.grid_defaults.update(base_investment=888.0, last_mode="paper")

    # Simulate a restart: a brand-new Repositories instance over the same DB.
    restarted_repos = Repositories(db)
    d = await restarted_repos.grid_defaults.get()
    assert d is not None
    assert d["base_investment"] == 888.0
    assert d["last_mode"] == "paper"


async def test_last_mode_can_be_cleared_back_to_ask(repos):
    await repos.grid_defaults.get_or_seed(QUICK_GRID_DEFAULTS_SEED)
    await repos.grid_defaults.update(last_mode="real")
    d = await repos.grid_defaults.update(last_mode=None)
    assert d["last_mode"] is None

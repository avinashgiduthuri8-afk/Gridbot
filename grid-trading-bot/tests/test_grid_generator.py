"""Unit tests for grid price generation (arithmetic and geometric)."""

from __future__ import annotations

import pytest

from config.constants import GridType
from grid.generator import (
    GridValidationError,
    build_grid_plan,
    find_nearest_level_below,
    generate_arithmetic_levels,
    generate_geometric_levels,
    validate_grid_params,
)


def test_arithmetic_levels_equal_spacing():
    levels = generate_arithmetic_levels(upper_price=1100, lower_price=1000, grid_levels=6)
    assert len(levels) == 6
    prices = [lv.price for lv in levels]
    diffs = [round(prices[i + 1] - prices[i], 6) for i in range(len(prices) - 1)]
    assert all(d == diffs[0] for d in diffs)
    assert prices[0] == 1000
    assert prices[-1] == 1100


def test_geometric_levels_equal_ratio_spacing():
    levels = generate_geometric_levels(upper_price=2000, lower_price=1000, grid_levels=5)
    prices = [lv.price for lv in levels]
    ratios = [round(prices[i + 1] / prices[i], 6) for i in range(len(prices) - 1)]
    assert all(r == ratios[0] for r in ratios)
    assert prices[0] == 1000
    assert prices[-1] == 2000


def test_validate_grid_params_rejects_inverted_range():
    with pytest.raises(GridValidationError):
        validate_grid_params(upper_price=100, lower_price=200, grid_levels=5, investment_per_grid=100)


def test_validate_grid_params_rejects_too_few_levels():
    with pytest.raises(GridValidationError):
        validate_grid_params(upper_price=200, lower_price=100, grid_levels=1, investment_per_grid=100)


def test_validate_grid_params_rejects_too_many_levels():
    with pytest.raises(GridValidationError):
        validate_grid_params(upper_price=200, lower_price=100, grid_levels=500, investment_per_grid=100)


def test_validate_grid_params_rejects_zero_investment():
    with pytest.raises(GridValidationError):
        validate_grid_params(upper_price=200, lower_price=100, grid_levels=5, investment_per_grid=0)


def test_build_grid_plan_arithmetic_total_investment():
    plan = build_grid_plan(
        symbol="BTCINR", grid_type=GridType.ARITHMETIC,
        upper_price=1100, lower_price=1000, grid_levels=6, investment_per_grid=100,
    )
    assert plan.total_investment == 500  # 5 buy levels (levels - 1)
    assert len(plan.levels) == 6


def test_build_grid_plan_geometric():
    plan = build_grid_plan(
        symbol="ETHINR", grid_type=GridType.GEOMETRIC,
        upper_price=2000, lower_price=1000, grid_levels=5, investment_per_grid=50,
    )
    assert plan.grid_type == GridType.GEOMETRIC
    assert plan.levels[0].price == 1000
    assert plan.levels[-1].price == 2000


def test_find_nearest_level_below():
    levels = generate_arithmetic_levels(upper_price=1100, lower_price=1000, grid_levels=6)
    nearest = find_nearest_level_below(levels, current_price=1045)
    assert nearest is not None
    assert nearest.price <= 1045


def test_find_nearest_level_below_returns_none_when_price_below_all_levels():
    levels = generate_arithmetic_levels(upper_price=1100, lower_price=1000, grid_levels=6)
    nearest = find_nearest_level_below(levels, current_price=900)
    assert nearest is None

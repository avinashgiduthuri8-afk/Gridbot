"""Unit tests for pure grid lifecycle/profit calculations."""

from __future__ import annotations

from grid.lifecycle import (
    compute_sell_price_for_level,
    compute_step_profit,
    grid_completion_ratio,
    is_price_out_of_range,
)


def test_compute_sell_price_for_level_returns_next_level_price():
    assert compute_sell_price_for_level(100, 110) == 110


def test_compute_step_profit_positive():
    result = compute_step_profit(buy_price=100, sell_price=110, quantity=1, fee_rate=0.001)
    assert result.gross_profit == 10
    assert result.fee == round((100 + 110) * 1 * 0.001, 10)
    assert result.net_profit == result.gross_profit - result.fee
    assert result.net_profit > 0


def test_compute_step_profit_accounts_for_fees_reducing_profit():
    result = compute_step_profit(buy_price=1000, sell_price=1001, quantity=1, fee_rate=0.01)
    # Fee is large relative to the tiny price move, so net profit should be negative.
    assert result.net_profit < result.gross_profit


def test_is_price_out_of_range_above():
    assert is_price_out_of_range(150, upper_price=120, lower_price=80) == "above"


def test_is_price_out_of_range_below():
    assert is_price_out_of_range(50, upper_price=120, lower_price=80) == "below"


def test_is_price_out_of_range_within_bounds():
    assert is_price_out_of_range(100, upper_price=120, lower_price=80) is None


def test_grid_completion_ratio():
    assert grid_completion_ratio(completed_cycles=5, grid_levels=10) == 0.5
    assert grid_completion_ratio(completed_cycles=0, grid_levels=0) == 0.0

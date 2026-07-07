"""Unit tests for the pure DCA engine calculation functions."""

from __future__ import annotations

import pytest

from grid.dca_engine import (
    calculate_average_entry_price,
    calculate_next_buy_price,
    calculate_profit_target,
    calculate_quantity_for_inr,
    calculate_stop_loss_price,
    clamp_sell_quantity,
    is_dip_triggered,
    is_profit_triggered,
    is_stop_loss_triggered,
    update_position_after_buy,
    update_position_after_sell,
)


# ---------------------------------------------------------------------------
# Price threshold calculations
# ---------------------------------------------------------------------------


def test_average_entry_zero_quantity():
    assert calculate_average_entry_price(1000, 0) == 0.0


def test_average_entry_single_buy():
    # 50000 INR / 1 BTC = 50000
    assert calculate_average_entry_price(50000, 1.0) == pytest.approx(50000.0)


def test_average_entry_weighted():
    # 50000 INR for 0.5 BTC + 40000 INR for 0.5 BTC = 90000 / 1.0 = 90000
    avg = calculate_average_entry_price(90000.0, 1.0)
    assert avg == pytest.approx(90000.0)


def test_next_buy_price_5pct():
    # 54000 * (1 - 0.05) = 51300
    result = calculate_next_buy_price(54000.0, 5.0)
    assert result == pytest.approx(51300.0)


def test_profit_target_7pct():
    # 52000 * 1.07 = 55640
    result = calculate_profit_target(52000.0, 7.0)
    assert result == pytest.approx(55640.0)


def test_stop_loss_price_50pct():
    # 52000 * (1 - 0.50) = 26000
    result = calculate_stop_loss_price(52000.0, 50.0)
    assert result == pytest.approx(26000.0)


# ---------------------------------------------------------------------------
# Quantity helpers
# ---------------------------------------------------------------------------


def test_quantity_for_inr_basic():
    # 500 INR at 50000 = 0.01 BTC, step 0.001 → floors to 0.010
    qty = calculate_quantity_for_inr(500.0, 50000.0, step_size=0.001, min_quantity=0.001)
    assert qty == pytest.approx(0.01)


def test_quantity_for_inr_floors_to_step():
    # 100 INR at 50001 = 0.001999... → floors to 0.001
    qty = calculate_quantity_for_inr(100.0, 50001.0, step_size=0.001, min_quantity=0.001)
    assert qty == pytest.approx(0.001)


def test_quantity_for_inr_below_minimum_raises():
    with pytest.raises(ValueError, match="below the exchange minimum"):
        calculate_quantity_for_inr(1.0, 1_000_000.0, step_size=0.00001, min_quantity=0.001)


def test_quantity_for_inr_zero_price_raises():
    with pytest.raises(ValueError):
        calculate_quantity_for_inr(500.0, 0.0, step_size=0.001, min_quantity=0.001)


def test_clamp_sell_quantity_clamps_to_available():
    # Want 0.5, have 0.3 → clamp to 0.3
    result = clamp_sell_quantity(0.5, 0.3, step_size=0.001)
    assert result == pytest.approx(0.3)


def test_clamp_sell_quantity_floors_to_step():
    # 0.0019 with step 0.001 → floors to 0.001
    result = clamp_sell_quantity(0.0019, 1.0, step_size=0.001)
    assert result == pytest.approx(0.001)


def test_clamp_sell_quantity_below_step_returns_zero():
    result = clamp_sell_quantity(0.0009, 1.0, step_size=0.001)
    assert result == 0.0


# ---------------------------------------------------------------------------
# Position state transitions
# ---------------------------------------------------------------------------


def test_update_position_after_buy_first_purchase():
    new_inv, new_qty, avg = update_position_after_buy(0.0, 0.0, 500.0, 0.01)
    assert new_inv == pytest.approx(500.0)
    assert new_qty == pytest.approx(0.01)
    assert avg == pytest.approx(50000.0)


def test_update_position_after_buy_dip_buy():
    # 500 INR for 0.01 BTC + 100 INR for 0.002 BTC (at 50000) = 600/0.012 = 50000
    new_inv, new_qty, avg = update_position_after_buy(500.0, 0.01, 100.0, 0.002)
    assert new_inv == pytest.approx(600.0)
    assert new_qty == pytest.approx(0.012)
    assert avg == pytest.approx(50000.0)


def test_update_position_after_sell_partial():
    # Sell 0.005 at 55000 from position of 0.01 @ avg 50000
    # cost_basis = 0.005 * 50000 = 250, proceeds = 0.005 * 55000 = 275, pnl = 25
    new_inv, new_qty, pnl, avg = update_position_after_sell(500.0, 0.01, 50000.0, 0.005, 55000.0)
    assert new_inv == pytest.approx(250.0)
    assert new_qty == pytest.approx(0.005)
    assert pnl == pytest.approx(25.0)
    assert avg == pytest.approx(50000.0)


def test_update_position_after_sell_full_position():
    new_inv, new_qty, pnl, avg = update_position_after_sell(500.0, 0.01, 50000.0, 0.01, 55000.0)
    assert new_inv == pytest.approx(0.0)
    assert new_qty == pytest.approx(0.0)
    assert pnl == pytest.approx(50.0)


def test_update_position_after_sell_loss():
    # Sell at below avg entry → negative pnl
    _, _, pnl, _ = update_position_after_sell(500.0, 0.01, 50000.0, 0.01, 45000.0)
    assert pnl == pytest.approx(-50.0)


# ---------------------------------------------------------------------------
# Trigger checks
# ---------------------------------------------------------------------------


def test_dip_triggered_when_below():
    assert is_dip_triggered(current_price=51000.0, next_buy_price=51300.0) is True


def test_dip_not_triggered_when_above():
    assert is_dip_triggered(current_price=52000.0, next_buy_price=51300.0) is False


def test_dip_not_triggered_when_next_buy_is_zero():
    assert is_dip_triggered(current_price=0.0, next_buy_price=0.0) is False


def test_profit_triggered_when_above():
    assert is_profit_triggered(current_price=56000.0, next_sell_price=55640.0) is True


def test_profit_not_triggered_when_below():
    assert is_profit_triggered(current_price=54000.0, next_sell_price=55640.0) is False


def test_stop_loss_triggered_when_below_threshold():
    # avg_entry=52000, stop_loss=50% → threshold=26000; price=25000 → triggered
    assert is_stop_loss_triggered(25000.0, 52000.0, 50.0) is True


def test_stop_loss_not_triggered_when_above():
    assert is_stop_loss_triggered(50000.0, 52000.0, 50.0) is False


def test_stop_loss_not_triggered_when_avg_entry_zero():
    assert is_stop_loss_triggered(0.0, 0.0, 50.0) is False

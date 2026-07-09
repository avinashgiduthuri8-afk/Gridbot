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
    validate_order,
    validate_quantity,
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


# ---------------------------------------------------------------------------
# Shared exchange-rule validation: validate_order / calculate_quantity_for_inr
#
# This is the SAME function CoinValidator.validate_investment delegates to
# (see trading/coin_validator.py), so these tests double as the guarantee
# that the Trading Engine and CoinValidator can never disagree again.
# ---------------------------------------------------------------------------


class TestValidateOrderSharedLogic:
    def test_valid_order_passes_every_rule(self):
        # 500 INR @ 30000, step 0.0001, min_qty 0.0001, min_notional 100
        # raw = 0.016666..., rounded = 0.0166, notional = 498 >= 100
        result = validate_order(
            500.0, 30000.0, step_size=0.0001, min_quantity=0.0001,
            min_notional=100.0, quantity_precision=4,
        )
        assert result.valid is True
        assert result.reason == ""
        assert result.quantity == pytest.approx(0.0166)
        assert result.notional == pytest.approx(0.0166 * 30000.0)

    def test_below_minimum_quantity_rejected_with_reason_and_min_investment(self):
        # price so high that 1 INR doesn't even reach min_quantity
        result = validate_order(
            1.0, 30_000_000.0, step_size=0.00001, min_quantity=0.001,
        )
        assert result.valid is False
        assert "minimum quantity" in result.reason.lower()
        assert "Minimum investment required" in result.reason
        assert result.min_investment_inr == pytest.approx(0.001 * 30_000_000.0)

    def test_below_minimum_notional_rejected_even_though_quantity_ok(self):
        # This is the exact production gap the audit found: quantity clears
        # min_quantity, but the resulting order value is below min_notional.
        result = validate_order(
            100.0, 9_500_000.0, step_size=0.00001, min_quantity=0.00001,
            min_notional=100.0,
        )
        assert result.quantity >= 0.00001  # min_quantity rule alone would pass
        assert result.valid is False
        assert "minimum order value" in result.reason.lower()
        # min_investment_inr must be step-aligned so it ACTUALLY works when
        # reinvested — 100 INR would floor to a quantity worth only ₹95,
        # so the true minimum here is 2 steps (₹190), not ₹100.
        assert result.min_investment_inr == pytest.approx(190.0)

    def test_quantity_rounding_floors_never_rounds_up(self):
        result = validate_order(999.0, 1000.0, step_size=0.01, min_quantity=0.0)
        assert result.valid is True
        assert result.quantity == pytest.approx(0.99, abs=1e-10)
        assert result.raw_quantity == pytest.approx(0.999, abs=1e-10)

    def test_high_priced_asset_matches_reported_bug_scenario(self):
        # Reproduces the original ₹500 @ ₹6,234,915.90 bug report end-to-end
        # through the shared function.
        result = validate_order(
            500.0, 6_234_915.90, step_size=0.00001, min_quantity=0.00001,
            min_notional=0.0, quantity_precision=5,
        )
        assert result.valid is True
        assert result.quantity > 0
        assert result.step_size == pytest.approx(0.00001)
        assert result.min_investment_inr == pytest.approx(62.349159, rel=1e-4)

    def test_low_priced_whole_unit_asset(self):
        # DOGE-like: price 15, step 1 (whole units only), min_qty 1
        result = validate_order(
            500.0, 15.0, step_size=1.0, min_quantity=1.0, min_notional=50.0,
            quantity_precision=0,
        )
        assert result.valid is True
        assert result.quantity == pytest.approx(33.0)
        assert result.notional == pytest.approx(495.0)

    def test_exact_boundary_min_investment_is_itself_valid(self):
        # The min_investment_inr this function reports must, when re-invested,
        # itself produce a valid order — the whole point of reporting it.
        first = validate_order(
            10.0, 9_500_000.0, step_size=0.00001, min_quantity=0.00001,
            min_notional=100.0,
        )
        assert first.valid is False
        retry = validate_order(
            first.min_investment_inr, 9_500_000.0,
            step_size=0.00001, min_quantity=0.00001, min_notional=100.0,
        )
        assert retry.valid is True

    def test_exact_boundary_quantity_equal_to_min_quantity_passes(self):
        # raw_quantity lands EXACTLY on min_quantity after step rounding
        result = validate_order(
            10.0, 1000.0, step_size=0.001, min_quantity=0.01, min_notional=0.0,
        )
        assert result.quantity == pytest.approx(0.01)
        assert result.valid is True

    def test_quantity_precision_mismatch_is_rejected(self):
        # step_size implies far more decimal places than quantity_precision
        # allows — this is an exchange-metadata inconsistency, not a valid order.
        result = validate_order(
            100.0, 3.0, step_size=0.00001, min_quantity=0.0,
            min_notional=0.0, quantity_precision=2,
        )
        assert result.valid is False
        assert "precision" in result.reason.lower()

    def test_quantity_precision_sufficient_is_accepted(self):
        result = validate_order(
            100.0, 3.0, step_size=0.00001, min_quantity=0.0,
            min_notional=0.0, quantity_precision=8,
        )
        assert result.valid is True

    def test_zero_price_rejected(self):
        result = validate_order(500.0, 0.0, step_size=0.001, min_quantity=0.0)
        assert result.valid is False
        assert "positive" in result.reason.lower()

    def test_calculate_quantity_for_inr_raises_on_min_notional_failure(self):
        # The Trading Engine's own entry point must now enforce min_notional too.
        with pytest.raises(ValueError, match="minimum order value"):
            calculate_quantity_for_inr(
                100.0, 9_500_000.0, step_size=0.00001, min_quantity=0.00001,
                min_notional=100.0,
            )

    def test_calculate_quantity_for_inr_matches_validate_order(self):
        # calculate_quantity_for_inr must be a pure pass-through wrapper.
        qty = calculate_quantity_for_inr(
            500.0, 30000.0, step_size=0.0001, min_quantity=0.0001,
            min_notional=100.0, quantity_precision=4,
        )
        direct = validate_order(
            500.0, 30000.0, step_size=0.0001, min_quantity=0.0001,
            min_notional=100.0, quantity_precision=4,
        )
        assert qty == pytest.approx(direct.quantity)

    def test_different_quantity_precisions_all_validate_correctly(self):
        cases = [
            # (price, step, min_qty, min_notional, qty_prec, inr, expected_valid)
            (50000.0, 1.0, 1.0, 0.0, 0, 60000.0, True),          # whole-unit coin
            (200.0, 0.01, 0.01, 0.0, 2, 5.0, True),               # 2-decimal coin
            (6_234_915.90, 0.00001, 0.00001, 0.0, 5, 500.0, True),  # very high priced
            (9_500_000.0, 1e-8, 1e-8, 0.0, 8, 100.0, True),       # BTC-like precision
        ]
        for price, step, min_qty, min_notional, qty_prec, inr, expected in cases:
            result = validate_order(
                inr, price, step_size=step, min_quantity=min_qty,
                min_notional=min_notional, quantity_precision=qty_prec,
            )
            assert result.valid is expected, (
                f"price={price} step={step} inr={inr}: expected {expected}, "
                f"got {result.valid} ({result.reason})"
            )


# ---------------------------------------------------------------------------
# validate_quantity: the sell-side counterpart used after clamp_sell_quantity
#
# These close the gap the audit found: clamp_sell_quantity() only floors to
# step_size, it never re-checks min_quantity/min_notional. Production code
# (trading/dca_manager.py) now calls validate_quantity() on the CLAMPED
# result before placing a sell order — these tests lock in that contract.
# ---------------------------------------------------------------------------


class TestValidateQuantitySharedLogic:
    def test_valid_quantity_passes_every_rule(self):
        result = validate_quantity(
            0.01, 30000.0, min_quantity=0.001, step_size=0.0001,
            min_notional=100.0, quantity_precision=4,
        )
        assert result.valid is True
        assert result.reason == ""
        assert result.notional == pytest.approx(300.0)

    def test_below_minimum_quantity_rejected(self):
        result = validate_quantity(
            0.0001, 9_500_000.0, min_quantity=0.001, step_size=0.00001,
        )
        assert result.valid is False
        assert "minimum quantity" in result.reason.lower()
        assert "Minimum investment required" in result.reason

    def test_below_minimum_notional_rejected_even_though_quantity_ok(self):
        # Mirrors the buy-side audit finding, but on the sell path: a
        # quantity that clears min_quantity can still be below min_notional.
        result = validate_quantity(
            0.00002, 9_500_000.0, min_quantity=0.00001, step_size=0.00001,
            min_notional=1000.0,
        )
        assert result.quantity >= 0.00001
        assert result.valid is False
        assert "minimum order value" in result.reason.lower()

    def test_zero_price_rejected(self):
        result = validate_quantity(1.0, 0.0, min_quantity=0.0)
        assert result.valid is False
        assert "positive" in result.reason.lower()

    def test_quantity_and_order_agree_on_the_same_valid_input(self):
        # validate_order (buy) and validate_quantity (sell) must reach the
        # SAME verdict for the same effective quantity/price/rules — they
        # share one rule engine, so they cannot drift apart.
        order_result = validate_order(
            500.0, 30000.0, step_size=0.0001, min_quantity=0.0001,
            min_notional=100.0, quantity_precision=4,
        )
        qty_result = validate_quantity(
            order_result.quantity, 30000.0, min_quantity=0.0001, step_size=0.0001,
            min_notional=100.0, quantity_precision=4,
        )
        assert order_result.valid is True
        assert qty_result.valid is True


class TestClampThenValidateSellFlow:
    """End-to-end: clamp_sell_quantity() followed by validate_quantity(),
    exactly as trading/dca_manager.py now does before every sell order.
    """

    def test_clamped_quantity_above_minimum_is_valid(self):
        # Partial sell: desired qty is well within the held balance.
        desired = 0.05
        available = 1.0
        step = 0.0001
        clamped = clamp_sell_quantity(desired, available, step)
        result = validate_quantity(
            clamped, 30000.0, min_quantity=0.001, step_size=step, min_notional=100.0,
        )
        assert clamped == pytest.approx(0.05)
        assert result.valid is True

    def test_clamped_quantity_below_min_quantity_is_rejected(self):
        # Desired qty clamps down to a sliver of the (small) available balance.
        desired = 0.5
        available = 0.00005  # far below min_quantity once clamped
        step = 0.00001
        clamped = clamp_sell_quantity(desired, available, step)
        result = validate_quantity(
            clamped, 9_500_000.0, min_quantity=0.001, step_size=step, min_notional=0.0,
        )
        assert clamped < 0.001
        assert result.valid is False
        assert "minimum quantity" in result.reason.lower()

    def test_clamped_quantity_below_min_notional_is_rejected(self):
        # Clamped quantity clears min_quantity but the order value doesn't
        # clear min_notional — the exact shape of the original audit bug,
        # now proven on the sell side too.
        desired = 1.0
        available = 0.00002  # 2 steps of 0.00001
        step = 0.00001
        clamped = clamp_sell_quantity(desired, available, step)
        result = validate_quantity(
            clamped, 9_500_000.0, min_quantity=0.00001, step_size=step, min_notional=1000.0,
        )
        assert clamped >= 0.00001
        assert result.valid is False
        assert "minimum order value" in result.reason.lower()

    def test_partial_sell_leaves_a_valid_remainder(self):
        # Selling part of a large position: both the sold amount and what's
        # left behind should be well-formed (this test only asserts the
        # sold portion; the remainder's own validity is DCAManager's
        # concern via total_quantity bookkeeping, not clamp/validate here).
        desired = 0.1
        available = 1.0
        step = 0.0001
        clamped = clamp_sell_quantity(desired, available, step)
        result = validate_quantity(clamped, 50000.0, min_quantity=0.001, step_size=step)
        assert result.valid is True
        remainder = available - clamped
        assert remainder == pytest.approx(0.9, abs=1e-9)

    def test_full_sell_of_entire_position_is_valid(self):
        # Stop-loss / full-exit path: desired == available == total_quantity.
        total_qty = 0.25
        step = 0.0001
        clamped = clamp_sell_quantity(total_qty, total_qty, step)
        result = validate_quantity(clamped, 40000.0, min_quantity=0.0001, step_size=step)
        assert clamped == pytest.approx(0.25)
        assert result.valid is True

    def test_tiny_dust_remainder_fails_validation_after_clamp(self):
        # The exact scenario the audit flagged as a latent gap: a dust-sized
        # remaining position clamps down to (or below) zero and must be
        # caught by validate_quantity, not silently sent to OrderManager.
        total_qty = 0.0000003  # smaller than one step
        step = 0.00001
        clamped = clamp_sell_quantity(total_qty, total_qty, step)
        assert clamped == 0.0
        result = validate_quantity(
            clamped, 9_500_000.0, min_quantity=0.00001, step_size=step, min_notional=100.0,
        )
        assert result.valid is False
        assert "minimum quantity" in result.reason.lower()

    def test_dust_remainder_reports_a_reinvestable_minimum(self):
        # Even in the dust-rejection case, min_investment_inr must be
        # actionable (i.e. itself produces a valid order if reinvested).
        total_qty = 0.000002
        step = 0.00001
        price = 9_500_000.0
        clamped = clamp_sell_quantity(total_qty, total_qty, step)
        result = validate_quantity(
            clamped, price, min_quantity=0.00001, step_size=step, min_notional=100.0,
        )
        assert result.valid is False
        retry_order = validate_order(
            result.min_investment_inr, price, step_size=step,
            min_quantity=0.00001, min_notional=100.0,
        )
        assert retry_order.valid is True

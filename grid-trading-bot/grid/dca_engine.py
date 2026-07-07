"""DCA (Dollar Cost Averaging) Grid Engine.

Pure calculation functions — no I/O, no side effects, fully unit-testable.

DCA grid logic:
  1. User places an initial buy at the entry price.
  2. Every time the price falls by dip_percentage from the previous buy price,
     the bot places another buy using dip_buy_amount INR.
  3. After each buy the weighted average entry price is recalculated.
  4. Whenever the price rises to (average_entry * (1 + profit_pct)),
     the bot sells approximately profit_sell_amount INR worth of coin.
  5. If the price ever falls to (average_entry * (1 - stop_loss_pct)),
     the bot sells the entire remaining position and stops the grid.
"""

from __future__ import annotations

import math
from decimal import Decimal, ROUND_DOWN

from utils.logger import get_logger

log = get_logger("trading")


# ---------------------------------------------------------------------------
# Price threshold calculations
# ---------------------------------------------------------------------------


def calculate_average_entry_price(total_investment: float, total_quantity: float) -> float:
    """Weighted average entry price across all accumulated buys."""
    if total_quantity <= 0:
        return 0.0
    return total_investment / total_quantity


def calculate_next_buy_price(last_buy_price: float, dip_percentage: float) -> float:
    """Price at which the next dip buy should be triggered.

    The dip is measured from the last executed buy price, not from the
    average entry.  Example: last_buy=54000, dip=5% → next_buy=51300.
    """
    return last_buy_price * (1.0 - dip_percentage / 100.0)


def calculate_profit_target(average_entry_price: float, profit_percentage: float) -> float:
    """Sell target price based on the current average entry price.

    Recalculated after every buy so that the target always reflects the
    most recent average cost.  Example: avg=52000, profit=7% → target=55640.
    """
    return average_entry_price * (1.0 + profit_percentage / 100.0)


def calculate_stop_loss_price(average_entry_price: float, stop_loss_percentage: float) -> float:
    """Price below which the stop-loss triggers.

    Example: avg=52000, stop_loss=50% → trigger=26000.
    """
    return average_entry_price * (1.0 - stop_loss_percentage / 100.0)


# ---------------------------------------------------------------------------
# Quantity helpers (exchange precision)
# ---------------------------------------------------------------------------


def calculate_quantity_for_inr(
    inr_amount: float,
    price: float,
    step_size: float,
    min_quantity: float,
) -> float:
    """Convert an INR investment amount into a tradeable coin quantity.

    Uses Decimal arithmetic to avoid floating-point rounding surprises when
    dividing and snapping to a step_size.  Rounds DOWN (toward zero) to the
    nearest valid step so the order is always within the user's budget.
    Raises ValueError if the resulting quantity is below the exchange minimum.

    Audit log emitted at DEBUG level every call:
      price, investment, raw_quantity, rounded_quantity, min_quantity, result.

    Args:
        inr_amount:   INR amount the user wants to invest.
        price:        Current or limit price in INR.
        step_size:    Minimum quantity increment (e.g. 0.001 for BTC).
        min_quantity: Exchange-enforced minimum order quantity.
    """
    if price <= 0:
        raise ValueError(f"Price must be positive, got {price}")

    d_inr = Decimal(str(inr_amount))
    d_price = Decimal(str(price))
    d_step = Decimal(str(step_size)) if step_size > 0 else Decimal(0)

    raw_quantity = d_inr / d_price

    if d_step > 0:
        # Integer number of steps, then scale back — no floating-point noise
        n_steps = int(raw_quantity / d_step)  # equivalent to floor for positives
        quantity = Decimal(n_steps) * d_step
    else:
        quantity = raw_quantity

    quantity_float = float(quantity)
    raw_float = float(raw_quantity)

    log.debug(
        "qty_calc: price=₹%.4f investment=₹%.4f raw=%.8f rounded=%.8f "
        "step=%s min=%.8f result=%s",
        price, inr_amount, raw_float, quantity_float,
        step_size, min_quantity,
        "OK" if quantity_float >= min_quantity else "BELOW_MIN",
    )

    if quantity_float < min_quantity:
        min_investment = float(Decimal(str(min_quantity)) * d_price)
        raise ValueError(
            f"₹{inr_amount:,.2f} at ₹{price:,.2f} yields {quantity_float:.8f} units "
            f"which is below the exchange minimum of {min_quantity}. "
            f"Minimum investment required: ₹{min_investment:,.2f}."
        )
    return quantity_float


def clamp_sell_quantity(
    desired_quantity: float,
    available_quantity: float,
    step_size: float,
) -> float:
    """Ensure sell qty does not exceed what the grid holds, rounded down.

    Returns 0.0 if the clamped result is less than step_size.
    """
    qty = min(desired_quantity, available_quantity)
    if step_size > 0:
        steps = math.floor(qty / step_size)
        qty = round(steps * step_size, 10)
    return max(qty, 0.0)


# ---------------------------------------------------------------------------
# Position state transitions
# ---------------------------------------------------------------------------


def update_position_after_buy(
    total_investment: float,
    total_quantity: float,
    buy_cost: float,
    buy_quantity: float,
) -> tuple[float, float, float]:
    """Accumulate a buy into the running position.

    Returns:
        (new_total_investment, new_total_quantity, new_avg_entry_price)
    """
    new_total_investment = total_investment + buy_cost
    new_total_quantity = total_quantity + buy_quantity
    new_avg_entry = calculate_average_entry_price(new_total_investment, new_total_quantity)
    return new_total_investment, new_total_quantity, new_avg_entry


def update_position_after_sell(
    total_investment: float,
    total_quantity: float,
    average_entry_price: float,
    sell_quantity: float,
    sell_price: float,
) -> tuple[float, float, float, float]:
    """Remove a sell from the running position and compute realised PnL.

    Selling a portion of the position does *not* change the average entry
    price of the remaining units — only the total investment and total
    quantity are reduced proportionally.

    Returns:
        (new_total_investment, new_total_quantity, pnl, average_entry_price)
    """
    actual_qty = min(sell_quantity, total_quantity)
    cost_basis = actual_qty * average_entry_price
    proceeds = actual_qty * sell_price
    pnl = proceeds - cost_basis
    new_total_investment = max(0.0, total_investment - cost_basis)
    new_total_quantity = max(0.0, total_quantity - actual_qty)
    return new_total_investment, new_total_quantity, pnl, average_entry_price


# ---------------------------------------------------------------------------
# Trigger checks
# ---------------------------------------------------------------------------


def is_dip_triggered(current_price: float, next_buy_price: float) -> bool:
    """True when the price has fallen to or below the next scheduled buy."""
    return next_buy_price > 0 and current_price <= next_buy_price


def is_profit_triggered(current_price: float, next_sell_price: float) -> bool:
    """True when the price has risen to or above the profit target."""
    return next_sell_price > 0 and current_price >= next_sell_price


def is_stop_loss_triggered(
    current_price: float,
    average_entry_price: float,
    stop_loss_percentage: float,
) -> bool:
    """True when the price has dropped below the stop-loss threshold."""
    if average_entry_price <= 0:
        return False
    stop_price = calculate_stop_loss_price(average_entry_price, stop_loss_percentage)
    return current_price <= stop_price


def current_loss_percentage(current_price: float, average_entry_price: float) -> float:
    """Percentage loss from average entry at the current price (negative = loss)."""
    if average_entry_price <= 0:
        return 0.0
    return ((current_price - average_entry_price) / average_entry_price) * 100.0

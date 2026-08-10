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

from dataclasses import dataclass
from decimal import Decimal, ROUND_DOWN, ROUND_UP

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


@dataclass
class OrderValidation:
    """Result of validating a prospective order against ALL exchange rules.

    This is the single source of truth for "will CoinDCX accept this
    order?" — shared by the Trading Engine (calculate_quantity_for_inr),
    CoinValidator.validate_investment, /coininfo, and /newgrid pre-flight
    checks. Any one of them changing independently is exactly how the
    Trading Engine and CoinValidator drifted apart before; there must only
    ever be one implementation of this logic.
    """

    valid: bool
    reason: str = ""
    quantity: float = 0.0          # rounded, ready-to-trade quantity
    raw_quantity: float = 0.0      # before step-size rounding
    notional: float = 0.0          # quantity * price — the ACTUAL order value
    min_quantity: float = 0.0
    min_notional: float = 0.0
    min_investment_inr: float = 0.0  # INR needed to satisfy every rule below
    step_size: float = 0.0
    quantity_precision: int | None = None
    price_precision: int | None = None
    market_price: float = 0.0
    investment_inr: float = 0.0


def _minimum_investment_required(
    price: float, step_size: float, min_quantity: float, min_notional: float,
) -> float:
    """The smallest INR amount that would satisfy min_quantity AND min_notional
    at this price, after step-floor rounding — usable from either a
    quantity-in or an INR-in caller, since it depends on neither.
    """
    d_price = Decimal(str(price))
    d_step = Decimal(str(step_size)) if step_size > 0 else Decimal(0)
    d_min_qty = Decimal(str(min_quantity)) if min_quantity > 0 else Decimal(0)
    d_min_notional = Decimal(str(min_notional)) if min_notional > 0 else Decimal(0)

    if d_step > 0:
        steps_for_qty = (
            (d_min_qty / d_step).to_integral_value(rounding=ROUND_UP)
            if d_min_qty > 0 else Decimal(1)
        )
        steps_for_notional = (
            (d_min_notional / d_price / d_step).to_integral_value(rounding=ROUND_UP)
            if d_min_notional > 0 else Decimal(0)
        )
        steps_needed = max(steps_for_qty, steps_for_notional, Decimal(1))
        q_target = steps_needed * d_step
    else:
        q_target = d_min_qty
        if d_min_notional > 0:
            q_target = max(q_target, d_min_notional / d_price)

    return float((q_target * d_price).quantize(Decimal("0.01"), rounding=ROUND_UP))


@dataclass
class _RuleCheck:
    """Outcome of the shared rule engine — which single rule failed, if any."""

    ok: bool
    failed_rule: str = ""  # "min_quantity" | "min_notional" | "quantity_precision" | "price_precision"
    detail: dict | None = None


def _check_exchange_rules(
    quantity: Decimal,
    price: Decimal,
    min_quantity: float,
    min_notional: float,
    quantity_precision: int | None,
    price_precision: int | None,
) -> _RuleCheck:
    """The ONE place every min-quantity / min-notional / precision rule is decided.

    Both ``validate_order`` (INR-in, buy side) and ``validate_quantity``
    (quantity-in, sell side) call this after arriving at a candidate
    quantity, so a buy path and a sell path can never disagree about
    whether an order is exchange-legal — there is exactly one
    implementation of "is this quantity/price combination exchange-legal".
    """
    qty_float = float(quantity)
    price_float = float(price)
    notional = qty_float * price_float

    if qty_float <= 0 or (min_quantity > 0 and qty_float < min_quantity):
        return _RuleCheck(
            False, "min_quantity",
            {"quantity": qty_float, "min_quantity": min_quantity, "notional": notional},
        )

    if min_notional > 0 and notional < min_notional:
        return _RuleCheck(
            False, "min_notional",
            {"quantity": qty_float, "notional": notional, "min_notional": min_notional},
        )

    if quantity_precision is not None:
        exponent = quantity.normalize().as_tuple().exponent if quantity != 0 else 0
        decimals_needed = max(0, -exponent)
        if decimals_needed > quantity_precision:
            return _RuleCheck(
                False, "quantity_precision",
                {"quantity": qty_float, "decimals_needed": decimals_needed,
                 "quantity_precision": quantity_precision},
            )

    if price_precision is not None:
        price_exponent = price.normalize().as_tuple().exponent if price != 0 else 0
        price_decimals_needed = max(0, -price_exponent)
        if price_decimals_needed > price_precision:
            return _RuleCheck(
                False, "price_precision",
                {"price": price_float, "decimals_needed": price_decimals_needed,
                 "price_precision": price_precision},
            )

    return _RuleCheck(True)


def validate_order(
    inr_amount: float,
    price: float,
    step_size: float,
    min_quantity: float,
    min_notional: float = 0.0,
    quantity_precision: int | None = None,
    price_precision: int | None = None,
    unit_label: str = "units",
) -> OrderValidation:
    """Validate an INR investment against every exchange rule for a pair.

    Enforces, in this order, exactly and only:
      1. price must be positive
      2. quantity after step-size rounding must be > 0
      3. quantity must be >= min_quantity
      4. resulting notional (quantity * price) must be >= min_notional
      5. (if quantity_precision given) the rounded quantity must not need
         more decimal places than the exchange allows for this pair —
         catches step_size / quantity_precision metadata that disagree.
      6. (if price_precision given) the market price itself must not need
         more decimal places than the exchange allows for this pair —
         catches a price feed that disagrees with base_currency_precision.

    Rules 3-6 are decided by ``_check_exchange_rules`` — the SAME function
    ``validate_quantity`` (the sell-side counterpart, used after
    ``clamp_sell_quantity``) calls, so buys and sells can never disagree.

    Uses Decimal arithmetic throughout and always rounds DOWN (toward zero)
    to the nearest valid step, so a returned quantity is always affordable
    and always exchange-legal.

    On success, ``min_investment_inr`` is still populated: it is the INR
    amount that would exactly satisfy both min_quantity and min_notional at
    this price, useful for showing "you could invest as little as ₹X".
    """
    result = OrderValidation(
        valid=False,
        market_price=price,
        investment_inr=inr_amount,
        step_size=step_size,
        min_quantity=min_quantity,
        min_notional=min_notional,
        quantity_precision=quantity_precision,
        price_precision=price_precision,
    )

    if price <= 0:
        result.reason = f"Market price must be positive, got {price}."
        return result

    d_inr = Decimal(str(inr_amount))
    d_price = Decimal(str(price))
    d_step = Decimal(str(step_size)) if step_size > 0 else Decimal(0)

    raw_quantity = d_inr / d_price
    if d_step > 0:
        n_steps = int(raw_quantity / d_step)  # equivalent to floor for positives
        quantity = Decimal(n_steps) * d_step
    else:
        quantity = raw_quantity

    qty_float = float(quantity)
    raw_float = float(raw_quantity)
    notional = qty_float * price

    result.quantity = qty_float
    result.raw_quantity = raw_float
    result.notional = notional

    min_investment = _minimum_investment_required(price, step_size, min_quantity, min_notional)
    result.min_investment_inr = min_investment

    log.debug(
        "validate_order: price=₹%.8f investment=₹%.4f raw_quantity=%.10f step_size=%s "
        "rounded_quantity=%.10f notional=₹%.4f min_quantity=%.10f min_notional=₹%.4f "
        "min_investment_inr=₹%.4f",
        price, inr_amount, raw_float, step_size, qty_float, notional,
        min_quantity, min_notional, min_investment,
    )

    check = _check_exchange_rules(
        quantity, d_price, min_quantity, min_notional, quantity_precision, price_precision,
    )
    if not check.ok:
        result.reason = _format_buy_rejection_reason(
            check, inr_amount=inr_amount, price=price, step_size=step_size,
            unit_label=unit_label, min_investment=min_investment,
        )
        return result

    result.valid = True
    return result


def _format_buy_rejection_reason(
    check: _RuleCheck, *, inr_amount: float, price: float, step_size: float,
    unit_label: str, min_investment: float,
) -> str:
    """Human-readable rejection text for the INR-in (buy) path."""
    d = check.detail or {}
    if check.failed_rule == "min_quantity":
        min_quantity = d["min_quantity"]
        shortfall_qty = min_quantity if min_quantity > 0 else step_size
        return (
            f"₹{inr_amount:,.2f} at ₹{price:,.2f} yields {d['quantity']:.8f} {unit_label}, "
            f"below the exchange minimum quantity of {shortfall_qty} {unit_label}. "
            f"Minimum investment required: ₹{min_investment:,.2f}."
        )
    if check.failed_rule == "min_notional":
        return (
            f"₹{inr_amount:,.2f} at ₹{price:,.2f} produces an order worth ₹{d['notional']:,.2f}, "
            f"below the exchange's minimum order value of ₹{d['min_notional']:,.2f}. "
            f"Minimum investment required: ₹{min_investment:,.2f}."
        )
    if check.failed_rule == "quantity_precision":
        return (
            f"Calculated quantity {d['quantity']} requires {d['decimals_needed']} decimal "
            f"place(s), exceeding this pair's quantity precision of "
            f"{d['quantity_precision']} — step_size and quantity_precision metadata "
            f"disagree for this symbol; do not trust this order."
        )
    if check.failed_rule == "price_precision":
        return (
            f"Market price ₹{price} requires {d['decimals_needed']} decimal "
            f"place(s), exceeding this pair's price precision of "
            f"{d['price_precision']} — the price feed and exchange price-precision "
            f"metadata disagree for this symbol; do not trust this order."
        )
    return "Order failed exchange validation."  # pragma: no cover — defensive fallback


def validate_quantity(
    quantity: float,
    price: float,
    min_quantity: float,
    step_size: float = 0.0,
    min_notional: float = 0.0,
    quantity_precision: int | None = None,
    price_precision: int | None = None,
    unit_label: str = "units",
) -> OrderValidation:
    """Validate an ALREADY-DETERMINED quantity against the exact same
    exchange rules as ``validate_order``.

    This is the sell-side counterpart used after ``clamp_sell_quantity``:
    a desired sell quantity is computed via ``calculate_quantity_for_inr``
    (buy-side math), then clamped to the actually-held balance, and the
    clamped result must be revalidated here before it reaches
    ``OrderManager`` — clamping can push a previously-valid quantity back
    below min_quantity or min_notional (e.g. a small "dust" remainder).

    Shares ``_check_exchange_rules`` and ``_minimum_investment_required``
    with ``validate_order`` — there is exactly one rule engine; this
    function only skips the INR->quantity derivation step, since the
    quantity is already known.
    """
    result = OrderValidation(
        valid=False,
        market_price=price,
        investment_inr=0.0,
        step_size=step_size,
        min_quantity=min_quantity,
        min_notional=min_notional,
        quantity_precision=quantity_precision,
        price_precision=price_precision,
    )

    if price <= 0:
        result.reason = f"Market price must be positive, got {price}."
        return result

    d_price = Decimal(str(price))
    d_qty = Decimal(str(quantity))
    qty_float = float(d_qty)
    notional = qty_float * price

    result.quantity = qty_float
    result.raw_quantity = qty_float
    result.notional = notional

    min_investment = _minimum_investment_required(price, step_size, min_quantity, min_notional)
    result.min_investment_inr = min_investment

    log.debug(
        "validate_quantity: price=₹%.8f quantity=%.10f step_size=%s notional=₹%.4f "
        "min_quantity=%.10f min_notional=₹%.4f min_investment_inr=₹%.4f",
        price, qty_float, step_size, notional, min_quantity, min_notional, min_investment,
    )

    check = _check_exchange_rules(
        d_qty, d_price, min_quantity, min_notional, quantity_precision, price_precision,
    )
    if not check.ok:
        result.reason = _format_sell_rejection_reason(
            check, quantity=qty_float, price=price, unit_label=unit_label,
            min_investment=min_investment,
        )
        return result

    result.valid = True
    return result


def _format_sell_rejection_reason(
    check: _RuleCheck, *, quantity: float, price: float, unit_label: str, min_investment: float,
) -> str:
    """Human-readable rejection text for the quantity-in (sell) path."""
    d = check.detail or {}
    if check.failed_rule == "min_quantity":
        return (
            f"Sell quantity {quantity:.8f} {unit_label} at ₹{price:,.2f} is below the "
            f"exchange minimum quantity of {d['min_quantity']} {unit_label}. "
            f"Minimum investment required to rebuild a valid position: ₹{min_investment:,.2f}."
        )
    if check.failed_rule == "min_notional":
        return (
            f"Sell quantity {quantity:.8f} {unit_label} at ₹{price:,.2f} produces an order "
            f"worth ₹{d['notional']:,.2f}, below the exchange's minimum order value of "
            f"₹{d['min_notional']:,.2f}. Minimum investment required: ₹{min_investment:,.2f}."
        )
    if check.failed_rule == "quantity_precision":
        return (
            f"Sell quantity {d['quantity']} requires {d['decimals_needed']} decimal "
            f"place(s), exceeding this pair's quantity precision of "
            f"{d['quantity_precision']} — step_size and quantity_precision metadata "
            f"disagree for this symbol; do not trust this order."
        )
    if check.failed_rule == "price_precision":
        return (
            f"Market price ₹{price} requires {d['decimals_needed']} decimal "
            f"place(s), exceeding this pair's price precision of "
            f"{d['price_precision']} — the price feed and exchange price-precision "
            f"metadata disagree for this symbol; do not trust this order."
        )
    return "Sell quantity failed exchange validation."  # pragma: no cover — defensive fallback


def calculate_quantity_for_inr(
    inr_amount: float,
    price: float,
    step_size: float,
    min_quantity: float,
    min_notional: float = 0.0,
    quantity_precision: int | None = None,
    price_precision: int | None = None,
) -> float:
    """Convert an INR investment amount into a tradeable coin quantity.

    Thin wrapper around ``validate_order`` — the SAME shared validation used
    by CoinValidator, /coininfo, and /newgrid pre-flight checks — so the
    Trading Engine can never generate an order that those checks would have
    rejected. Do not add logic here; add it to ``validate_order`` instead,
    or the two will drift apart again.

    Raises ValueError, with the exact failing rule and the minimum
    investment required, if the order does not meet exchange rules.
    """
    result = validate_order(
        inr_amount, price, step_size, min_quantity,
        min_notional=min_notional, quantity_precision=quantity_precision,
        price_precision=price_precision,
    )
    if not result.valid:
        raise ValueError(result.reason)
    return result.quantity


def clamp_sell_quantity(
    desired_quantity: float,
    available_quantity: float,
    step_size: float,
) -> float:
    """Ensure sell qty does not exceed what the grid holds, rounded down.

    Uses Decimal arithmetic (matching calculate_quantity_for_inr elsewhere
    in this module) rather than raw float division/floor. Binary floating
    point cannot represent most decimal step sizes exactly (e.g. 1e-5), so
    `math.floor(5.0 / 1e-5)` can evaluate to 499999 instead of 500000 —
    silently clamping an EXACT step-boundary quantity (a full-position
    sell that should leave zero remainder) down by one whole step. That
    residual is too small to trade (below the exchange's min_quantity) but
    not exactly zero, so it wasn't caught as a clean "position closed" and
    could leave a grid stuck ACTIVE holding unsellable dust after what
    looked like a fully successful sell.

    Returns 0.0 if the clamped result is less than step_size.
    """
    d_qty = min(Decimal(str(desired_quantity)), Decimal(str(available_quantity)))
    if step_size > 0:
        d_step = Decimal(str(step_size))
        n_steps = int(d_qty / d_step)  # equivalent to floor for non-negative values
        d_qty = Decimal(n_steps) * d_step
    return max(float(d_qty), 0.0)


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

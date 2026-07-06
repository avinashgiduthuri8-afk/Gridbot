"""Pure grid lifecycle/profit calculations — no I/O, no exchange calls.

Kept separate from trading/grid_manager.py (which handles orchestration
and side effects) so the arithmetic here is trivially unit-testable.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class GridStepResult:
    """Result of a buy being matched to its re-entry sell one level up."""

    buy_price: float
    sell_price: float
    quantity: float
    gross_profit: float
    fee: float
    net_profit: float


def compute_sell_price_for_level(level_price: float, next_level_price: float) -> float:
    """A filled buy at `level_price` gets a matching sell order placed at
    the next grid level up (`next_level_price`) — this is the core grid
    "buy low, sell high one rung up" mechanic."""
    return next_level_price


def compute_step_profit(
    buy_price: float, sell_price: float, quantity: float, fee_rate: float = 0.001
) -> GridStepResult:
    """Compute the realized profit for one completed grid cycle
    (buy filled, then matching sell filled)."""
    gross_profit = (sell_price - buy_price) * quantity
    fee = (buy_price + sell_price) * quantity * fee_rate
    net_profit = gross_profit - fee
    return GridStepResult(
        buy_price=buy_price,
        sell_price=sell_price,
        quantity=quantity,
        gross_profit=gross_profit,
        fee=fee,
        net_profit=net_profit,
    )


def is_price_out_of_range(current_price: float, upper_price: float, lower_price: float) -> str | None:
    """Return 'above' / 'below' if price has broken out of the grid range,
    otherwise None. Used to warn/auto-pause a grid that has moved outside
    its designed band."""
    if current_price > upper_price:
        return "above"
    if current_price < lower_price:
        return "below"
    return None


def grid_completion_ratio(completed_cycles: int, grid_levels: int) -> float:
    """Rough measure of how many times the grid has fully cycled relative
    to its level count — used for status/progress reporting only."""
    if grid_levels <= 0:
        return 0.0
    return completed_cycles / grid_levels

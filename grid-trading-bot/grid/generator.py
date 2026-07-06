"""Grid price generation: arithmetic (equal spacing) and geometric
(equal percentage spacing) layouts.
"""

from __future__ import annotations

from config.constants import (
    MAX_GRID_LEVELS,
    MIN_GRID_LEVELS,
    GridType,
)
from grid.models import GridLevelPlan, GridPlan


class GridValidationError(ValueError):
    """Raised when requested grid parameters are invalid."""


def validate_grid_params(
    upper_price: float, lower_price: float, grid_levels: int, investment_per_grid: float
) -> None:
    if upper_price <= lower_price:
        raise GridValidationError("Upper price must be greater than lower price.")
    if lower_price <= 0:
        raise GridValidationError("Lower price must be greater than zero.")
    if not (MIN_GRID_LEVELS <= grid_levels <= MAX_GRID_LEVELS):
        raise GridValidationError(
            f"Grid levels must be between {MIN_GRID_LEVELS} and {MAX_GRID_LEVELS}."
        )
    if investment_per_grid <= 0:
        raise GridValidationError("Investment per grid must be greater than zero.")


def generate_arithmetic_levels(
    upper_price: float, lower_price: float, grid_levels: int
) -> list[GridLevelPlan]:
    """Equal absolute price spacing between levels."""
    step = (upper_price - lower_price) / (grid_levels - 1)
    return [
        GridLevelPlan(level_index=i, price=round(lower_price + step * i, 8))
        for i in range(grid_levels)
    ]


def generate_geometric_levels(
    upper_price: float, lower_price: float, grid_levels: int
) -> list[GridLevelPlan]:
    """Equal percentage (ratio) spacing between levels — tighter grids near
    the lower bound, wider near the upper bound, mirroring compounding
    percentage moves rather than absolute price moves."""
    ratio = (upper_price / lower_price) ** (1 / (grid_levels - 1))
    return [
        GridLevelPlan(level_index=i, price=round(lower_price * (ratio**i), 8))
        for i in range(grid_levels)
    ]


def build_grid_plan(
    symbol: str,
    grid_type: GridType,
    upper_price: float,
    lower_price: float,
    grid_levels: int,
    investment_per_grid: float,
) -> GridPlan:
    """Validate inputs and produce a complete GridPlan."""
    validate_grid_params(upper_price, lower_price, grid_levels, investment_per_grid)

    if grid_type == GridType.GEOMETRIC:
        levels = generate_geometric_levels(upper_price, lower_price, grid_levels)
    else:
        levels = generate_arithmetic_levels(upper_price, lower_price, grid_levels)

    return GridPlan(
        symbol=symbol,
        grid_type=grid_type,
        upper_price=upper_price,
        lower_price=lower_price,
        grid_levels=grid_levels,
        investment_per_grid=investment_per_grid,
        levels=tuple(levels),
    )


def find_nearest_level_below(levels: list[GridLevelPlan], current_price: float) -> GridLevelPlan | None:
    """Find the highest-priced level that sits at or below current_price —
    used to decide where the initial buy ladder should start."""
    candidates = [lv for lv in levels if lv.price <= current_price]
    if not candidates:
        return None
    return max(candidates, key=lambda lv: lv.price)

"""In-memory grid domain models used by the grid generator and engine."""

from __future__ import annotations

from dataclasses import dataclass

from config.constants import GridType


@dataclass(frozen=True)
class GridLevelPlan:
    """A single price rung of the grid before any orders exist."""

    level_index: int
    price: float


@dataclass(frozen=True)
class GridPlan:
    """The full set of levels generated for a new grid, plus the config
    used to produce them. Purely a calculation result — has no idea about
    orders, exchanges, or persistence.
    """

    symbol: str
    grid_type: GridType
    upper_price: float
    lower_price: float
    grid_levels: int
    investment_per_grid: float
    levels: tuple[GridLevelPlan, ...]

    @property
    def total_investment(self) -> float:
        # One buy order sits at every level except the topmost, since the
        # topmost level only ever acts as a sell target.
        buy_levels = max(self.grid_levels - 1, 0)
        return buy_levels * self.investment_per_grid

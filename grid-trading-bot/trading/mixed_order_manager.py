"""MixedOrderManager: routes order calls to real or paper OrderManager
based on the mode stored on the order's parent grid.

This lets DCAManager and OrderMonitor use a single order-manager reference
while transparently supporting both live and paper-trade grids.
"""

from __future__ import annotations

from storage.models import OrderRecord
from storage.repositories import Repositories
from trading.order_manager import OrderManager
from utils.logger import get_logger

log = get_logger("trading")


class MixedOrderManager:
    """Delegates to real or paper OrderManager based on the grid's mode column."""

    def __init__(
        self,
        real: OrderManager,
        paper: OrderManager,
        repos: Repositories,
    ) -> None:
        self._managers: dict[str, OrderManager] = {"real": real, "paper": paper}
        self._repos = repos

    async def _manager_for_grid(self, grid_id: str) -> OrderManager:
        grid = await self._repos.grids.get(grid_id)
        mode = (grid or {}).get("mode", "real")
        return self._managers.get(mode, self._managers["real"])

    async def _manager_for_order(self, order_id: str) -> OrderManager:
        order = await self._repos.orders.get(order_id)
        if not order:
            return self._managers["real"]
        return await self._manager_for_grid(order["grid_id"])

    async def place_dca_order(
        self,
        grid_id: str,
        symbol: str,
        side: str,
        price: float,
        quantity: float,
        order_type: str = "market_order",
    ) -> OrderRecord:
        manager = await self._manager_for_grid(grid_id)
        return await manager.place_dca_order(
            grid_id=grid_id,
            symbol=symbol,
            side=side,
            price=price,
            quantity=quantity,
            order_type=order_type,
        )

    async def cancel_order(self, order_id: str) -> bool:
        manager = await self._manager_for_order(order_id)
        return await manager.cancel_order(order_id)

    async def sync_order_status(self, order_id: str) -> OrderRecord | None:
        manager = await self._manager_for_order(order_id)
        return await manager.sync_order_status(order_id)

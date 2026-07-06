"""Order Monitor: background loop that polls open orders for fills and
routes filled buy/sell events into the GridManager.

This is the only place that discovers fills — CoinDCX has no push/websocket
guarantee used here, so a resilient polling loop is the source of truth.
"""

from __future__ import annotations

import asyncio

from config.constants import OrderStatus
from exchange.exceptions import ExchangeError
from storage.repositories import Repositories
from trading.grid_manager import GridManager
from utils.logger import get_logger

log = get_logger("trading")


class OrderMonitor:
    def __init__(self, repos: Repositories, order_manager, grid_manager: GridManager, poll_interval: int) -> None:
        self._repos = repos
        self._order_manager = order_manager
        self._grid_manager = grid_manager
        self._poll_interval = poll_interval
        self._running = False
        self._task: asyncio.Task | None = None

    def start(self) -> None:
        if self._task is None:
            self._running = True
            self._task = asyncio.create_task(self._run_loop())
            log.info("Order monitor started (poll interval %ss)", self._poll_interval)

    async def stop(self) -> None:
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None

    async def _run_loop(self) -> None:
        while self._running:
            try:
                await self._poll_once()
            except Exception:  # noqa: BLE001 - never let the monitor die
                log.exception("Order monitor cycle failed")
            await asyncio.sleep(self._poll_interval)

    async def _poll_once(self) -> None:
        open_orders = await self._repos.orders.list_open()
        for order in open_orders:
            if not order["exchange_order_id"]:
                continue
            try:
                refreshed = await self._order_manager.sync_order_status(order["order_id"])
            except ExchangeError as exc:
                log.warning("Could not sync order %s: %s", order["order_id"], exc)
                continue

            if refreshed is None:
                continue

            if refreshed.status == OrderStatus.FILLED.value:
                await self._handle_fill(refreshed)

    async def _handle_fill(self, order) -> None:
        order_dict = {
            "order_id": order.order_id,
            "grid_id": order.grid_id,
            "symbol": order.symbol,
            "side": order.side,
            "price": order.filled_price or order.price,
            "quantity": order.quantity,
            "level_index": order.level_index,
        }
        log.info("Order %s filled: %s %s @ %.8f", order.order_id, order.side, order.symbol, order_dict["price"])

        if order.side == "buy":
            levels = await self._repos.grid_levels.list_for_grid(order.grid_id)
            await self._grid_manager.on_buy_filled(order.grid_id, order_dict, levels)
        else:
            await self._grid_manager.on_sell_filled(order.grid_id, order_dict)

"""Order Monitor: background loop that polls open orders for fills and
routes filled buy/sell events to the DCA Manager.

CoinDCX has no push/websocket guarantee in this integration, so a
resilient polling loop is the source of truth for fill events.
"""

from __future__ import annotations

import asyncio

from config.constants import OrderStatus
from exchange.exceptions import ExchangeError
from storage.repositories import Repositories
from trading.dca_manager import DCAManager
from utils.logger import get_logger

log = get_logger("trading")


class OrderMonitor:
    def __init__(
        self,
        repos: Repositories,
        order_manager,
        dca_manager: DCAManager,
        poll_interval: int,
    ) -> None:
        self._repos = repos
        self._order_manager = order_manager
        self._dca_manager = dca_manager
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
            except Exception:  # noqa: BLE001
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
                fill_price = refreshed.filled_price or refreshed.price
                fill_qty = refreshed.filled_quantity or refreshed.quantity
                log.info(
                    "Order %s filled: %s %s @ ₹%.2f qty %.8f",
                    refreshed.order_id, refreshed.side, refreshed.symbol,
                    fill_price, fill_qty,
                )
                try:
                    await self._dca_manager.handle_order_filled(
                        order_id=refreshed.order_id,
                        fill_price=fill_price,
                        fill_qty=fill_qty,
                    )
                except Exception:  # noqa: BLE001
                    log.exception(
                        "handle_order_filled failed for order %s", refreshed.order_id
                    )

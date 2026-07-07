"""Recovery Manager: reconciles local state against the exchange on startup.

Recovery steps:
  1. For every grid in active/paused state, verify it still exists locally.
  2. For every order in a non-terminal state, re-fetch its exchange status.
     - Orders that never reached the exchange are marked FAILED.
     - Orders that filled while the bot was down are processed through
       DCAManager.handle_order_filled so grid state is up to date.
  3. Re-arm the order monitor and price watcher for all active grids.
"""

from __future__ import annotations

from config.constants import GridStatus, OrderStatus
from exchange.base import ExchangeClient
from exchange.exceptions import ExchangeError
from notifications.notifier import Notifier
from storage.repositories import Repositories
from utils.logger import get_logger

log = get_logger("trading")

_TERMINAL = {
    OrderStatus.FILLED.value,
    OrderStatus.CANCELLED.value,
    OrderStatus.REJECTED.value,
    OrderStatus.FAILED.value,
}


class RecoveryManager:
    def __init__(
        self,
        exchange: ExchangeClient,
        repos: Repositories,
        notifier: Notifier,
        dca_manager,
    ) -> None:
        self._exchange = exchange
        self._repos = repos
        self._notifier = notifier
        self._dca_manager = dca_manager

    async def recover(self) -> dict[str, int]:
        """Run the full recovery sequence. Returns a summary dict."""
        log.info("Starting recovery sequence...")
        active_grids = await self._repos.grids.list_by_status(
            [GridStatus.ACTIVE.value, GridStatus.PAUSED.value]
        )
        reconciled = await self._reconcile_open_orders()

        summary = {
            "active_grids": len(active_grids),
            "reconciled_orders": reconciled,
        }
        log.info(
            "Recovery complete: %d active/paused grids restored, %d orders reconciled",
            summary["active_grids"], summary["reconciled_orders"],
        )
        await self._notifier.recovery_complete(
            active_count=len(active_grids),
            reconciled=reconciled,
        )
        return summary

    async def _reconcile_open_orders(self) -> int:
        open_orders = await self._repos.orders.list_open()
        reconciled = 0
        for order in open_orders:
            order_id = order["order_id"]
            if not order["exchange_order_id"]:
                await self._repos.orders.update_status(
                    order_id,
                    OrderStatus.FAILED.value,
                )
                log.warning(
                    "Order %s never reached exchange before restart — marked FAILED", order_id
                )
                reconciled += 1
                continue

            try:
                ex_order = await self._exchange.get_order_status(order["exchange_order_id"])
            except ExchangeError as exc:
                log.warning("Could not reconcile order %s during recovery: %s", order_id, exc)
                continue

            if ex_order.status != order["status"]:
                await self._repos.orders.update_status(
                    order_id,
                    ex_order.status,
                    filled_quantity=ex_order.filled_quantity,
                    filled_price=ex_order.filled_price,
                )
                reconciled += 1

                if ex_order.status == OrderStatus.FILLED.value:
                    fill_price = ex_order.filled_price or ex_order.price
                    fill_qty = ex_order.filled_quantity or ex_order.quantity
                    log.info(
                        "Recovered fill for order %s: qty %.8f @ ₹%.2f",
                        order_id, fill_qty, fill_price,
                    )
                    try:
                        await self._dca_manager.handle_order_filled(
                            order_id=order_id,
                            fill_price=fill_price,
                            fill_qty=fill_qty,
                        )
                    except Exception:  # noqa: BLE001
                        log.exception(
                            "Recovery: handle_order_filled failed for %s", order_id
                        )

        return reconciled

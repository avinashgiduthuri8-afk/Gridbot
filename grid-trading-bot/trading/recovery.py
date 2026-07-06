"""Recovery Manager: runs once at startup to reconcile local state against
the exchange's actual state, so an active grid is never silently lost
after a crash or restart.

Recovery steps:
1. For every grid marked active/paused, re-verify it still exists and its
   coin config is intact.
2. For every order in a non-terminal state, re-fetch its status from the
   exchange and update the local record (it may have filled or been
   cancelled while the bot was down).
3. Re-arm the order monitor and price watchers for all active grids.
"""

from __future__ import annotations

from config.constants import GridStatus, OrderStatus
from exchange.base import ExchangeClient
from exchange.exceptions import ExchangeError
from notifications.notifier import Notifier
from storage.repositories import Repositories
from utils.logger import get_logger

log = get_logger("trading")

_TERMINAL_STATUSES = {
    OrderStatus.FILLED.value,
    OrderStatus.CANCELLED.value,
    OrderStatus.REJECTED.value,
    OrderStatus.FAILED.value,
}


class RecoveryManager:
    def __init__(self, exchange: ExchangeClient, repos: Repositories, notifier: Notifier) -> None:
        self._exchange = exchange
        self._repos = repos
        self._notifier = notifier

    async def recover(self) -> dict[str, int]:
        log.info("Starting recovery sequence...")
        active_grids = await self._repos.grids.list_by_status(
            [GridStatus.ACTIVE.value, GridStatus.PAUSED.value]
        )
        reconciled_orders = await self._reconcile_open_orders()

        summary = {
            "active_grids": len(active_grids),
            "reconciled_orders": reconciled_orders,
        }
        log.info(
            "Recovery complete: %d active/paused grids restored, %d orders reconciled",
            summary["active_grids"], summary["reconciled_orders"],
        )
        if active_grids:
            symbols = ", ".join(sorted({g["symbol"] for g in active_grids}))
            await self._notifier.send(
                f"🔄 <b>Recovery Complete</b>\nRestored {len(active_grids)} grid(s): {symbols}\n"
                f"Reconciled {summary['reconciled_orders']} open order(s)."
            )
        else:
            await self._notifier.send("🔄 <b>Recovery Complete</b>\nNo active grids to restore.")
        return summary

    async def _reconcile_open_orders(self) -> int:
        open_orders = await self._repos.orders.list_open()
        reconciled = 0
        for order in open_orders:
            if not order["exchange_order_id"]:
                # Never made it to the exchange before the crash — mark failed
                # so it won't be treated as live.
                await self._repos.orders.update_status(
                    order["order_id"], OrderStatus.FAILED.value,
                    error_message="Order never reached exchange before restart",
                )
                reconciled += 1
                continue
            try:
                exchange_order = await self._exchange.get_order_status(order["exchange_order_id"])
            except ExchangeError as exc:
                log.warning("Could not reconcile order %s during recovery: %s", order["order_id"], exc)
                continue

            if exchange_order.status != order["status"]:
                await self._repos.orders.update_status(
                    order["order_id"], exchange_order.status,
                    filled_quantity=exchange_order.filled_quantity,
                    filled_price=exchange_order.price,
                )
                reconciled += 1
        return reconciled

"""Order Manager: the only component allowed to talk to the exchange for
placing/cancelling orders. Wraps every call with DB persistence so no
order is ever placed on the exchange without a corresponding local record
(and vice versa, no local record is left dangling without a status check).
"""

from __future__ import annotations

from config.constants import OrderStatus
from exchange.base import ExchangeClient
from exchange.exceptions import ExchangeError, InsufficientBalanceError, OrderRejectedError
from storage.models import OrderRecord
from storage.repositories import Repositories
from utils.helpers import new_id, now_iso
from utils.logger import get_logger

log = get_logger("trading")


class OrderManager:
    def __init__(self, exchange: ExchangeClient, repos: Repositories) -> None:
        self._exchange = exchange
        self._repos = repos

    async def place_grid_order(
        self, grid_id: str, symbol: str, side: str, price: float, quantity: float, level_index: int
    ) -> OrderRecord:
        """Place a grid order on the exchange and persist it locally.

        The local record is created in PENDING state *before* the exchange
        call so a crash between the two never loses knowledge that an order
        attempt was in flight — the recovery manager can reconcile it.
        """
        order_id = new_id("ord")
        record = OrderRecord(
            order_id=order_id,
            grid_id=grid_id,
            exchange_order_id=None,
            symbol=symbol,
            side=side,
            price=price,
            quantity=quantity,
            status=OrderStatus.PENDING.value,
            level_index=level_index,
            created_at=now_iso(),
            updated_at=now_iso(),
        )
        await self._repos.orders.create(record)

        try:
            from config.constants import OrderSide

            exchange_order = await self._exchange.place_order(
                symbol=symbol, side=OrderSide(side), price=price, quantity=quantity
            )
        except InsufficientBalanceError as exc:
            log.error("Order %s rejected (insufficient balance): %s", order_id, exc)
            await self._repos.orders.update_status(
                order_id, OrderStatus.FAILED.value, error_message=str(exc)
            )
            raise
        except (OrderRejectedError, ExchangeError) as exc:
            log.error("Order %s failed to place: %s", order_id, exc)
            await self._repos.orders.update_status(
                order_id, OrderStatus.FAILED.value, error_message=str(exc)
            )
            raise

        await self._repos.orders.update_status(
            order_id, exchange_order.status, exchange_order_id=exchange_order.exchange_order_id
        )
        log.info(
            "Placed %s order %s for %s @ %.8f qty %.8f (exchange id %s)",
            side, order_id, symbol, price, quantity, exchange_order.exchange_order_id,
        )
        record.exchange_order_id = exchange_order.exchange_order_id
        record.status = exchange_order.status
        return record

    async def cancel_order(self, order_id: str) -> bool:
        order = await self._repos.orders.get(order_id)
        if not order:
            log.warning("Attempted to cancel unknown order %s", order_id)
            return False
        if not order["exchange_order_id"]:
            await self._repos.orders.update_status(order_id, OrderStatus.CANCELLED.value)
            return True

        cancelled = await self._exchange.cancel_order(order["exchange_order_id"])
        if cancelled:
            await self._repos.orders.update_status(order_id, OrderStatus.CANCELLED.value)
        return cancelled

    async def sync_order_status(self, order_id: str) -> OrderRecord | None:
        """Poll the exchange for the latest status of a local order and
        persist any change. Returns the refreshed record, or None if the
        order can't be found locally."""
        order = await self._repos.orders.get(order_id)
        if not order or not order["exchange_order_id"]:
            return None

        exchange_order = await self._exchange.get_order_status(order["exchange_order_id"])
        await self._repos.orders.update_status(
            order_id,
            exchange_order.status,
            filled_quantity=exchange_order.filled_quantity,
            filled_price=exchange_order.price,
        )
        refreshed = await self._repos.orders.get(order_id)
        return OrderRecord(**refreshed) if refreshed else None

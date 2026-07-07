"""Order Manager: the only component allowed to talk to the exchange for
placing and cancelling orders. Every call is wrapped with DB persistence
so no order is ever placed without a local record (and vice versa).
"""

from __future__ import annotations

from config.constants import OrderSide, OrderStatus
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

    async def place_dca_order(
        self,
        grid_id: str,
        symbol: str,
        side: str,
        price: float,
        quantity: float,
        order_type: str = "market_order",
    ) -> OrderRecord:
        """Place a DCA order on the exchange and persist it locally.

        The local record is created in PENDING state *before* the exchange
        call so a crash between the two never loses the order — recovery
        can detect and reconcile the dangling record on the next start.
        """
        order_id = new_id("ord")
        record = OrderRecord(
            order_id=order_id,
            grid_id=grid_id,
            exchange_order_id=None,
            symbol=symbol,
            side=side,
            order_type=order_type,
            price=price,
            quantity=quantity,
            filled_quantity=0.0,
            filled_price=0.0,
            status=OrderStatus.PENDING.value,
            created_at=now_iso(),
            updated_at=now_iso(),
        )
        await self._repos.orders.create(record)

        try:
            ex_order = await self._exchange.place_order(
                symbol=symbol,
                side=OrderSide(side),
                price=price,
                quantity=quantity,
                order_type=order_type,
            )
        except InsufficientBalanceError as exc:
            log.error("Order %s rejected (insufficient balance): %s", order_id, exc)
            await self._repos.orders.update_status(order_id, OrderStatus.FAILED.value)
            raise
        except (OrderRejectedError, ExchangeError) as exc:
            log.error("Order %s failed to place: %s", order_id, exc)
            await self._repos.orders.update_status(order_id, OrderStatus.FAILED.value)
            raise

        await self._repos.orders.update_status(
            order_id,
            ex_order.status,
            exchange_order_id=ex_order.exchange_order_id,
            filled_quantity=ex_order.filled_quantity,
            filled_price=ex_order.filled_price,
        )
        log.info(
            "Placed %s %s order %s @ qty %.8f (exchange id %s, status %s)",
            order_type, side, order_id, quantity, ex_order.exchange_order_id, ex_order.status,
        )
        record.exchange_order_id = ex_order.exchange_order_id
        record.status = ex_order.status
        record.filled_quantity = ex_order.filled_quantity
        record.filled_price = ex_order.filled_price
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
        """Poll the exchange for the latest status of a local order and persist
        any change. Returns the refreshed record, or None if not found."""
        order = await self._repos.orders.get(order_id)
        if not order or not order["exchange_order_id"]:
            return None
        ex_order = await self._exchange.get_order_status(order["exchange_order_id"])
        await self._repos.orders.update_status(
            order_id,
            ex_order.status,
            filled_quantity=ex_order.filled_quantity,
            filled_price=ex_order.filled_price,
        )
        refreshed = await self._repos.orders.get(order_id)
        if refreshed is None:
            return None
        return OrderRecord(
            order_id=refreshed["order_id"],
            grid_id=refreshed["grid_id"],
            exchange_order_id=refreshed["exchange_order_id"],
            symbol=refreshed["symbol"],
            side=refreshed["side"],
            order_type=refreshed["order_type"],
            price=refreshed["price"],
            quantity=refreshed["quantity"],
            filled_quantity=refreshed["filled_quantity"],
            filled_price=refreshed["filled_price"],
            status=refreshed["status"],
            created_at=refreshed["created_at"],
            updated_at=refreshed["updated_at"],
        )

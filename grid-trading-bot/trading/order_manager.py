"""Order Manager: the only component allowed to talk to the exchange for
placing and cancelling orders.

Every order follows a strict state machine:
  PENDING → SUBMITTED → OPEN → PARTIALLY_FILLED → FILLED
                              → CANCELLED / REJECTED / EXPIRED / FAILED

The local record is created in PENDING state *before* the exchange call.
It transitions to SUBMITTED immediately before the HTTP request fires.
If the process crashes in the SUBMITTED state with no exchange_order_id,
RecoveryManager knows an attempt was made and queries the exchange for a
matching open order before marking it FAILED.
"""

from __future__ import annotations

from config.constants import OrderSide, OrderStatus
from exchange.base import ExchangeClient
from exchange.exceptions import (
    ExchangeConnectionError,
    ExchangeError,
    ExchangeTimeoutError,
    InsufficientBalanceError,
    OrderRejectedError,
)
from storage.models import OrderRecord
from storage.repositories import Repositories
from utils.helpers import new_id, now_iso
from utils.logger import get_logger

log = get_logger("trading")

# Exceptions that indicate "uncertain" delivery (request may have landed)
_UNCERTAIN_ERRORS = (ExchangeTimeoutError, ExchangeConnectionError)


def _build_record(order_id: str, grid_id: str, symbol: str, side: str,
                  order_type: str, price: float, quantity: float) -> OrderRecord:
    now = now_iso()
    return OrderRecord(
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
        created_at=now,
        updated_at=now,
    )


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
        mode: str = "real",
    ) -> OrderRecord:
        """Place a DCA order on the exchange and persist it locally.

        State transitions:
          PENDING  — record created, exchange call not yet attempted
          SUBMITTED — HTTP request in-flight; crash here → check exchange on recovery
          OPEN/FILLED — exchange acknowledged; updated with exchange_order_id
          FAILED  — permanent or transient failure (uncertain delivery logged separately)
        """
        order_id = new_id("ord")
        record = _build_record(order_id, grid_id, symbol, side, order_type, price, quantity)
        await self._repos.orders.create(record)

        log.info(
            "order.pending  order=%s grid=%s symbol=%s side=%s qty=%.8f price=%.4f mode=%s",
            order_id, grid_id, symbol, side, quantity, price, mode,
        )

        # Mark SUBMITTED so recovery can detect in-flight crashes
        await self._repos.orders.update_status(order_id, OrderStatus.SUBMITTED.value)

        try:
            ex_order = await self._exchange.place_order(
                symbol=symbol,
                side=OrderSide(side),
                price=price,
                quantity=quantity,
                order_type=order_type,
            )
        except _UNCERTAIN_ERRORS as exc:
            # Exchange may or may not have received the request.
            # Mark FAILED but log clearly so recovery can investigate.
            await self._repos.orders.update_status(order_id, OrderStatus.FAILED.value)
            log.warning(
                "order.failed   order=%s grid=%s symbol=%s side=%s "
                "reason=transient_uncertain type=%s detail=%s",
                order_id, grid_id, symbol, side, type(exc).__name__, exc,
            )
            raise
        except InsufficientBalanceError as exc:
            await self._repos.orders.update_status(order_id, OrderStatus.FAILED.value)
            log.error(
                "order.failed   order=%s grid=%s symbol=%s side=%s "
                "reason=insufficient_balance detail=%s",
                order_id, grid_id, symbol, side, exc,
            )
            raise
        except OrderRejectedError as exc:
            await self._repos.orders.update_status(order_id, OrderStatus.REJECTED.value)
            log.error(
                "order.rejected order=%s grid=%s symbol=%s side=%s detail=%s",
                order_id, grid_id, symbol, side, exc,
            )
            raise
        except ExchangeError as exc:
            await self._repos.orders.update_status(order_id, OrderStatus.FAILED.value)
            log.error(
                "order.failed   order=%s grid=%s symbol=%s side=%s "
                "reason=exchange_error detail=%s",
                order_id, grid_id, symbol, side, exc,
            )
            raise

        await self._repos.orders.update_status(
            order_id,
            ex_order.status,
            exchange_order_id=ex_order.exchange_order_id,
            filled_quantity=ex_order.filled_quantity,
            filled_price=ex_order.filled_price,
        )

        log.info(
            "order.%-12s order=%s grid=%s symbol=%s side=%s "
            "exchange_id=%s qty=%.8f filled=%.8f mode=%s",
            ex_order.status, order_id, grid_id, symbol, side,
            ex_order.exchange_order_id, quantity,
            ex_order.filled_quantity or 0, mode,
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
        if order["status"] in (
            OrderStatus.FILLED.value,
            OrderStatus.CANCELLED.value,
            OrderStatus.FAILED.value,
            OrderStatus.REJECTED.value,
            OrderStatus.EXPIRED.value,
        ):
            log.debug("Order %s already terminal (%s), skip cancel", order_id, order["status"])
            return False
        if not order["exchange_order_id"]:
            # Never reached exchange — just mark cancelled
            await self._repos.orders.update_status(order_id, OrderStatus.CANCELLED.value)
            log.info(
                "order.cancelled order=%s grid=%s (no exchange_id, local cancel)",
                order_id, order["grid_id"],
            )
            return True
        cancelled = await self._exchange.cancel_order(order["exchange_order_id"])
        if cancelled:
            await self._repos.orders.update_status(order_id, OrderStatus.CANCELLED.value)
            log.info(
                "order.cancelled order=%s grid=%s exchange_id=%s",
                order_id, order["grid_id"], order["exchange_order_id"],
            )
        return cancelled

    async def sync_order_status(self, order_id: str) -> OrderRecord | None:
        """Poll the exchange for the latest status of a local order and persist
        any change. Returns the refreshed record, or None if not found."""
        order = await self._repos.orders.get(order_id)
        if not order or not order["exchange_order_id"]:
            return None
        ex_order = await self._exchange.get_order_status(order["exchange_order_id"])

        new_status = ex_order.status
        old_status = order["status"]

        if new_status != old_status or ex_order.filled_quantity != order["filled_quantity"]:
            await self._repos.orders.update_status(
                order_id,
                new_status,
                filled_quantity=ex_order.filled_quantity,
                filled_price=ex_order.filled_price,
            )
            if new_status != old_status:
                log.info(
                    "order.%-12s order=%s grid=%s symbol=%s side=%s "
                    "exchange_id=%s filled=%.8f (was %s)",
                    new_status, order_id, order["grid_id"], order["symbol"],
                    order["side"], order["exchange_order_id"],
                    ex_order.filled_quantity or 0, old_status,
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

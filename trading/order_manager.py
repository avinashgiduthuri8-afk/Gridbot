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
        fee=0.0,
        client_order_id=order_id,
    )


class OrderManager:
    def __init__(self, exchange: ExchangeClient, repos: Repositories) -> None:
        self._exchange = exchange
        self._repos = repos

    async def _resolve_fee(self, symbol: str, exchange_order_id: str | None, fallback: float = 0.0) -> float:
        if not exchange_order_id:
            return max(0.0, fallback)
        try:
            trades = await self._exchange.get_trade_history(symbol=symbol, limit=500, order_id=exchange_order_id)
        except ExchangeError:
            return max(0.0, fallback)
        fee = sum(float(t.fee or 0.0) for t in trades if t.exchange_order_id == exchange_order_id)
        return fee if fee > 0 else max(0.0, fallback)

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
          UNKNOWN — create result was lost; reconciliation is retried forever
          OPEN/FILLED — exchange acknowledged; updated with exchange_order_id
          FAILED/REJECTED — exchange definitively rejected the request
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
                client_order_id=order_id,
            )
        except _UNCERTAIN_ERRORS as exc:
            # The create endpoint was deliberately attempted exactly once. A
            # timeout/connection loss is an unknown result, not a failure and
            # never permission to create a replacement order.
            await self._repos.orders.mark_unknown(order_id, type(exc).__name__)
            log.warning(
                "order.unknown order=%s grid=%s symbol=%s side=%s type=%s detail=%s",
                order_id, grid_id, symbol, side, type(exc).__name__, exc,
            )
            await self.resolve_uncertain_submitted(order_id)
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

        fee = await self._resolve_fee(symbol, ex_order.exchange_order_id, ex_order.fee)
        await self._repos.orders.update_status(
            order_id,
            ex_order.status,
            exchange_order_id=ex_order.exchange_order_id,
            filled_quantity=ex_order.filled_quantity,
            filled_price=ex_order.filled_price,
            fee=fee,
            reconciliation_status="resolved",
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
        record.fee = fee
        record.reconciliation_status = "resolved"
        return record

    async def resolve_uncertain_submitted(self, order_id: str) -> bool:
        """Reconcile a SUBMITTED/UNKNOWN order by immutable client_order_id.

        Called by the order monitor's sync cycle to un-stick orders that were
        in-flight when a previous poll cycle crashed or timed out (and thus were
        not resolved by the at-startup recovery run).

        No result is ever treated as authority to create a replacement order.
        """
        order = await self._repos.orders.get(order_id)
        if not order or order.get("exchange_order_id"):
            return False  # nothing to do
        if order["status"] not in (OrderStatus.SUBMITTED.value, OrderStatus.UNKNOWN.value):
            return False
        client_order_id = order.get("client_order_id")
        if not client_order_id:
            await self._repos.orders.mark_unknown(order_id, "legacy_missing_client_order_id")
            log.error("Cannot safely reconcile legacy order %s without client_order_id", order_id)
            return False
        try:
            match = await self._exchange.get_order_by_client_order_id(client_order_id)
        except ExchangeError as exc:
            log.warning(
                "resolve_uncertain_submitted: exchange query failed for %s, "
                "leaving as UNKNOWN for retry: %s",
                order_id, exc,
            )
            return False
        if match is not None:
            await self._repos.orders.update_status(
                order_id,
                match.status,
                exchange_order_id=match.exchange_order_id,
                filled_quantity=match.filled_quantity,
                filled_price=match.filled_price,
                fee=match.fee,
                reconciliation_status="resolved",
            )
            log.info(
                "resolve_uncertain_submitted: linked %s → exchange %s (status=%s)",
                order_id, match.exchange_order_id, match.status,
            )
            return True
        await self._repos.orders.mark_unknown(order_id, "not_found_yet")
        log.warning("resolve_uncertain_submitted: no exchange match for %s; retained UNKNOWN", order_id)
        return False

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
            if order["status"] in (OrderStatus.SUBMITTED.value, OrderStatus.UNKNOWN.value):
                # There may be a live order behind this unknown response. Do
                # not falsely report a local cancellation; reconcile first.
                await self.resolve_uncertain_submitted(order_id)
                return False
            await self._repos.orders.update_status(order_id, OrderStatus.CANCELLED.value)
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
            fee = await self._resolve_fee(order["symbol"], order["exchange_order_id"], ex_order.fee)
            await self._repos.orders.update_status(
                order_id,
                new_status,
                filled_quantity=ex_order.filled_quantity,
                filled_price=ex_order.filled_price,
                fee=fee,
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
            client_order_id=refreshed.get("client_order_id"),
            fee=refreshed.get("fee", 0.0),
            reconciliation_status=refreshed.get("reconciliation_status", "not_needed"),
            reconciliation_retry_count=refreshed.get("reconciliation_retry_count", 0),
        )

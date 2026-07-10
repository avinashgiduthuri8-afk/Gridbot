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
            # Immediately check for a matching open order on the exchange so we
            # can link it if it landed, rather than blocking the grid indefinitely
            # in SUBMITTED state or risking a duplicate on the next trigger.
            log.warning(
                "order.uncertain order=%s grid=%s symbol=%s side=%s "
                "type=%s detail=%s — querying exchange for match",
                order_id, grid_id, symbol, side, type(exc).__name__, exc,
            )
            linked = await self._try_link_uncertain_order(
                order_id, symbol, side, quantity, price
            )
            if not linked:
                await self._repos.orders.update_status(order_id, OrderStatus.FAILED.value)
                log.warning(
                    "order.failed   order=%s grid=%s symbol=%s side=%s "
                    "reason=transient_no_exchange_match",
                    order_id, grid_id, symbol, side,
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

    async def _try_link_uncertain_order(
        self,
        order_id: str,
        symbol: str,
        side: str,
        quantity: float,
        price: float,
        qty_tolerance: float = 0.02,
        price_tolerance: float = 0.05,
    ) -> bool:
        """After a transient placement failure, query the exchange for a matching
        open order and link it if exactly one unambiguous match is found.

        Matching criteria: same side, quantity within qty_tolerance, price within
        price_tolerance.  If zero or multiple matches are found we return False
        (the caller should mark the order FAILED and let the grid retry).

        Returns True if the order was successfully linked to an exchange order.
        """
        try:
            open_orders = await self._exchange.get_open_orders(symbol=symbol)
        except Exception:  # noqa: BLE001
            log.warning(
                "_try_link_uncertain_order: get_open_orders(%s) failed, cannot link %s",
                symbol, order_id,
            )
            return False

        def _qty_ok(ex_qty: float) -> bool:
            if quantity <= 0 or ex_qty <= 0:
                return False
            return abs(ex_qty - quantity) / quantity <= qty_tolerance

        def _price_ok(ex_price: float) -> bool:
            if price <= 0 or ex_price <= 0:
                return True  # market orders may have price=0 on both sides
            return abs(ex_price - price) / price <= price_tolerance

        candidates = [
            o for o in open_orders
            if (o.side if isinstance(o.side, str) else o.side.value) == side
            and _qty_ok(float(o.quantity or 0))
            and _price_ok(float(o.price or 0))
        ]

        if len(candidates) == 0:
            log.info(
                "_try_link_uncertain_order: no match for %s %s qty=%.8f — order did not land",
                side, symbol, quantity,
            )
            return False

        if len(candidates) > 1:
            log.warning(
                "_try_link_uncertain_order: %d ambiguous matches for %s %s qty=%.8f "
                "— refusing to link, marking FAILED",
                len(candidates), side, symbol, quantity,
            )
            return False

        match = candidates[0]
        await self._repos.orders.update_status(
            order_id,
            match.status,
            exchange_order_id=match.exchange_order_id,
            filled_quantity=match.filled_quantity,
            filled_price=match.filled_price,
        )
        log.info(
            "_try_link_uncertain_order: linked %s → exchange %s (status=%s qty=%.8f)",
            order_id, match.exchange_order_id, match.status, float(match.quantity or 0),
        )
        return True

    async def resolve_uncertain_submitted(self, order_id: str) -> bool:
        """Try to link a SUBMITTED-without-exchange_id order to an open exchange order.

        Called by the order monitor's sync cycle to un-stick orders that were
        in-flight when a previous poll cycle crashed or timed out (and thus were
        not resolved by the at-startup recovery run).

        Crucially, this method distinguishes between:
        - Exchange query failure  → leave SUBMITTED, retry next cycle (return False)
        - Query succeeded, no match found → mark FAILED (the order didn't land)
        - Query succeeded, one match → link and return True

        This prevents incorrectly failing orders during transient exchange outages.

        Returns True if successfully linked, False otherwise (SUBMITTED left intact
        on exchange errors, FAILED set on definitive no-match).
        """
        order = await self._repos.orders.get(order_id)
        if not order or order.get("exchange_order_id"):
            return False  # nothing to do
        if order["status"] != OrderStatus.SUBMITTED.value:
            return False

        symbol = order["symbol"]
        side = order["side"]
        quantity = float(order["quantity"])
        price = float(order["price"])

        log.info(
            "resolve_uncertain_submitted: attempting to link stuck order %s "
            "(%s %s qty=%.8f)",
            order_id, side, symbol, quantity,
        )

        # Query the exchange — if this fails we defer (leave SUBMITTED) rather
        # than incorrectly marking the order FAILED during a transient outage.
        try:
            open_orders = await self._exchange.get_open_orders(symbol=symbol)
        except ExchangeError as exc:
            log.warning(
                "resolve_uncertain_submitted: exchange query failed for %s, "
                "leaving as SUBMITTED for retry: %s",
                order_id, exc,
            )
            return False

        def _qty_ok(ex_qty: float) -> bool:
            return quantity > 0 and ex_qty > 0 and abs(ex_qty - quantity) / quantity <= 0.02

        def _price_ok(ex_price: float) -> bool:
            if price <= 0 or ex_price <= 0:
                return True
            return abs(ex_price - price) / price <= 0.05

        candidates = [
            o for o in open_orders
            if (o.side if isinstance(o.side, str) else o.side.value) == side
            and _qty_ok(float(o.quantity or 0))
            and _price_ok(float(o.price or 0))
        ]

        if len(candidates) == 1:
            match = candidates[0]
            await self._repos.orders.update_status(
                order_id,
                match.status,
                exchange_order_id=match.exchange_order_id,
                filled_quantity=match.filled_quantity,
                filled_price=match.filled_price,
            )
            log.info(
                "resolve_uncertain_submitted: linked %s → exchange %s (status=%s)",
                order_id, match.exchange_order_id, match.status,
            )
            return True

        # Zero or ambiguous matches: mark FAILED so the grid can re-enter.
        # Note: an order that filled quickly may not appear in open_orders.
        # That case is handled by the regular order-monitor poll cycle, which
        # uses sync_order_status once exchange_order_id is known.
        if len(candidates) > 1:
            log.warning(
                "resolve_uncertain_submitted: %d ambiguous matches for %s — marked FAILED",
                len(candidates), order_id,
            )
        else:
            log.warning(
                "resolve_uncertain_submitted: no exchange match for %s — marked FAILED",
                order_id,
            )
        await self._repos.orders.update_status(order_id, OrderStatus.FAILED.value)
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

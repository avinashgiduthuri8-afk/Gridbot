"""Recovery Manager: reconciles local state against the exchange on startup.

Recovery sequence
-----------------
1. SUBMITTED orders with no exchange_order_id
   These represent orders whose HTTP request was in-flight when the process
   crashed.  We query the exchange for open orders on the same symbol+side
   and link any plausible match.  Unmatched ones are marked FAILED.

2. PENDING orders with no exchange_order_id
   The DB record was written but the exchange call never started → FAILED.

3. Orders that already have an exchange_order_id (OPEN / PARTIALLY_FILLED)
   Re-fetch status.  Any that filled while the bot was down are processed
   through DCAManager.handle_order_filled so grid state is up to date.

4. Orphan detection (optional)
   Fetch all exchange open orders; check for any not present in the local DB.
   These could be orders placed by a previous bot instance that crashed before
   writing the DB record.  They are logged for human review; the bot will not
   trade against them automatically.
"""

from __future__ import annotations

import math

from config.constants import GridStatus, OrderStatus
from exchange.base import ExchangeClient, ExchangeOrder
from exchange.exceptions import ExchangeError
from notifications.notifier import Notifier
from storage.repositories import Repositories
from utils.logger import get_logger

log = get_logger("trading")

_TERMINAL = {
    OrderStatus.FILLED.value,
    OrderStatus.CANCELLED.value,
    OrderStatus.REJECTED.value,
    OrderStatus.EXPIRED.value,
    OrderStatus.FAILED.value,
}

# Match tolerances for linking SUBMITTED orders to exchange open orders
_QTY_MATCH_TOLERANCE = 0.02    # 2% qty difference allowed
_PRICE_MATCH_TOLERANCE = 0.05  # 5% price difference allowed (market orders vary)


def _qty_matches(expected: float, actual: float) -> bool:
    """True if actual is within qty tolerance of expected (and both are > 0)."""
    if expected <= 0 or actual <= 0:
        return False
    return abs(actual - expected) / expected <= _QTY_MATCH_TOLERANCE


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
        log.info("Recovery: found %d active/paused grid(s)", len(active_grids))

        submitted_reconciled = await self._reconcile_submitted_orders()
        reconciled, fills_recovered = await self._reconcile_open_orders()
        orphans_linked = await self._detect_orphan_orders(active_grids)

        total_reconciled = submitted_reconciled + reconciled

        summary = {
            "active_grids": len(active_grids),
            "reconciled_orders": total_reconciled,
            "fills_recovered": fills_recovered,
            "orphans_linked": orphans_linked,
        }
        log.info(
            "Recovery complete: grids=%d reconciled=%d fills=%d orphans=%d",
            summary["active_grids"], summary["reconciled_orders"],
            summary["fills_recovered"], summary["orphans_linked"],
        )
        await self._notifier.recovery_complete(
            active_count=len(active_grids),
            reconciled=total_reconciled,
            orphans_linked=orphans_linked,
            fills_recovered=fills_recovered,
        )
        return summary

    # ------------------------------------------------------------------
    # Step 1: SUBMITTED orders with no exchange_order_id
    # ------------------------------------------------------------------

    async def _reconcile_submitted_orders(self) -> int:
        """Handle orders that were in-flight when the process crashed.

        Matching uses multi-factor criteria: side + qty tolerance + price tolerance.
        Ambiguous results (zero or multiple candidates) are never linked — the order
        is marked FAILED and the grid can re-enter on the next price trigger.
        """
        submitted = await self._repos.orders.list_submitted_no_exchange_id()
        reconciled = 0
        for order in submitted:
            order_id = order["order_id"]
            symbol = order["symbol"]
            side = order["side"]
            qty = float(order["quantity"])
            price = float(order["price"])

            log.info(
                "Recovery: SUBMITTED order %s (%s %s qty=%.8f @ %.4f) — checking exchange",
                order_id, side, symbol, qty, price,
            )

            # Query exchange for open orders on this symbol
            try:
                exchange_open = await self._exchange.get_open_orders(symbol=symbol)
            except ExchangeError as exc:
                log.warning(
                    "Recovery: cannot query exchange for SUBMITTED order %s: %s",
                    order_id, exc,
                )
                continue

            # Multi-factor match: side + qty tolerance + price tolerance
            # Price check is skipped for market orders (price == 0 locally)
            candidates: list[ExchangeOrder] = []
            for ex_o in exchange_open:
                ex_side = ex_o.side if isinstance(ex_o.side, str) else ex_o.side.value
                ex_qty = float(ex_o.quantity or 0)
                ex_price = float(ex_o.price or 0)

                if ex_side != side:
                    continue
                if not _qty_matches(qty, ex_qty):
                    continue
                # Only apply price check when both sides have a non-zero price
                if price > 0 and ex_price > 0:
                    price_diff_pct = abs(ex_price - price) / price
                    if price_diff_pct > _PRICE_MATCH_TOLERANCE:
                        continue
                candidates.append(ex_o)

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
                    "Recovery: linked SUBMITTED order %s → exchange %s (status=%s)",
                    order_id, match.exchange_order_id, match.status,
                )
            elif len(candidates) > 1:
                # Ambiguous: multiple open orders match our criteria.
                # Refuse to link rather than risk mis-attribution.
                await self._repos.orders.update_status(order_id, OrderStatus.FAILED.value)
                log.warning(
                    "Recovery: AMBIGUOUS match for SUBMITTED order %s "
                    "(%s %s qty=%.8f) — %d candidates, marked FAILED",
                    order_id, side, symbol, qty, len(candidates),
                )
            else:
                # No match — order never reached the exchange or filled instantly.
                # Mark FAILED so the grid can re-enter on the next price trigger.
                await self._repos.orders.update_status(order_id, OrderStatus.FAILED.value)
                log.warning(
                    "Recovery: no exchange match for SUBMITTED order %s "
                    "(%s %s qty=%.8f) — marked FAILED",
                    order_id, side, symbol, qty,
                )
            reconciled += 1

        return reconciled

    # ------------------------------------------------------------------
    # Step 2 & 3: PENDING/OPEN/PARTIALLY_FILLED orders
    # ------------------------------------------------------------------

    async def _reconcile_open_orders(self) -> tuple[int, int]:
        """Reconcile all local non-terminal orders that have an exchange_order_id.
        Returns (reconciled_count, fills_recovered_count).
        """
        open_orders = await self._repos.orders.list_open()
        reconciled = 0
        fills_recovered = 0

        for order in open_orders:
            order_id = order["order_id"]

            # PENDING with no exchange_id: the call was never attempted → FAILED
            if not order["exchange_order_id"] and order["status"] == OrderStatus.PENDING.value:
                await self._repos.orders.update_status(order_id, OrderStatus.FAILED.value)
                log.warning(
                    "Recovery: PENDING order %s has no exchange_id — marked FAILED",
                    order_id,
                )
                reconciled += 1
                continue

            # Skip if no exchange_id (already handled as SUBMITTED above, or edge case)
            if not order["exchange_order_id"]:
                continue

            # Skip terminal local status (shouldn't be in list_open, but guard anyway)
            if order["status"] in _TERMINAL:
                continue

            try:
                ex_order = await self._exchange.get_order_status(order["exchange_order_id"])
            except ExchangeError as exc:
                log.warning(
                    "Recovery: cannot fetch exchange status for order %s: %s",
                    order_id, exc,
                )
                continue

            if ex_order.status != order["status"] or \
               ex_order.filled_quantity != order["filled_quantity"]:
                await self._repos.orders.update_status(
                    order_id,
                    ex_order.status,
                    filled_quantity=ex_order.filled_quantity,
                    filled_price=ex_order.filled_price,
                )
                reconciled += 1
                log.info(
                    "Recovery: order %s %s → %s (filled %.8f)",
                    order_id, order["status"], ex_order.status,
                    ex_order.filled_quantity or 0,
                )

            if ex_order.status == OrderStatus.FILLED.value:
                fill_price = ex_order.filled_price or ex_order.price
                fill_qty = ex_order.filled_quantity or ex_order.quantity
                fills_recovered += 1
                log.info(
                    "Recovery: processing offline fill for order %s "
                    "qty=%.8f @ ₹%.2f",
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

        return reconciled, fills_recovered

    # ------------------------------------------------------------------
    # Step 4: Orphan detection
    # ------------------------------------------------------------------

    async def _detect_orphan_orders(self, active_grids: list[dict]) -> int:
        """Fetch all exchange open orders for REAL (non-paper) active grid symbols.
        Any order not present in the local DB is an orphan.

        Orphans are notified via Telegram so the user can decide whether to
        cancel them manually on CoinDCX.  We never auto-cancel because they
        could be legitimate orders placed outside the bot.

        Paper grids route through the paper exchange, which reflects the real
        exchange's open orders; checking the real exchange for paper grid symbols
        would produce false positives from unrelated real orders.

        Returns the count of orphan orders found.
        """
        if not active_grids:
            return 0

        # Only check real exchange for non-paper grids
        symbols = {g["symbol"] for g in active_grids if g.get("mode", "real") != "paper"}
        if not symbols:
            log.debug("Recovery orphan check: all active grids are paper-mode, skipping")
            return 0

        orphan_count = 0
        orphan_details: list[dict] = []

        for symbol in symbols:
            try:
                exchange_open = await self._exchange.get_open_orders(symbol=symbol)
            except ExchangeError as exc:
                log.warning(
                    "Recovery: orphan check failed for %s: %s", symbol, exc
                )
                continue

            for ex_order in exchange_open:
                local = await self._repos.orders.get_by_exchange_order_id(
                    ex_order.exchange_order_id
                )
                if local is None:
                    orphan_count += 1
                    log.warning(
                        "Recovery: ORPHAN exchange order %s (%s %s qty=%.8f @ ₹%.4f) "
                        "has no local record — review and cancel on CoinDCX if needed",
                        ex_order.exchange_order_id, ex_order.side,
                        symbol, float(ex_order.quantity or 0), float(ex_order.price or 0),
                    )
                    orphan_details.append({
                        "exchange_order_id": ex_order.exchange_order_id,
                        "symbol": symbol,
                        "side": ex_order.side if isinstance(ex_order.side, str) else ex_order.side.value,
                        "quantity": float(ex_order.quantity or 0),
                        "price": float(ex_order.price or 0),
                    })

        if orphan_details:
            await self._notifier.orphan_orders_detected(orphan_details)

        return orphan_count

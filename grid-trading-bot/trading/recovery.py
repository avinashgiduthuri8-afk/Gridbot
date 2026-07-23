"""Recovery Manager: reconciles local state against the exchange on startup.

Recovery sequence
-----------------
1. SUBMITTED/UNKNOWN orders with no exchange_order_id
   These are reconciled solely by their immutable client_order_id. Unmatched
   ones remain UNKNOWN and are never submitted again.

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
        zombie_grids = await self._detect_zombie_grids(active_grids)

        total_reconciled = submitted_reconciled + reconciled

        summary = {
            "active_grids": len(active_grids),
            "reconciled_orders": total_reconciled,
            "fills_recovered": fills_recovered,
            "orphans_linked": orphans_linked,
            "zombie_grids": zombie_grids,
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
            zombie_grids=zombie_grids,
        )
        return summary

    # ------------------------------------------------------------------
    # Step 1: SUBMITTED orders with no exchange_order_id
    # ------------------------------------------------------------------

    async def _reconcile_submitted_orders(self) -> int:
        """Handle orders that were in-flight when the process crashed.

        Matching uses CoinDCX's client_order_id, never price/quantity heuristics.
        """
        submitted = await self._repos.orders.list_needing_reconciliation()
        reconciled = 0
        for order in submitted:
            order_id = order["order_id"]
            client_order_id = order.get("client_order_id")
            if not client_order_id:
                # Pre-protocol records cannot be safely attributed by a fuzzy
                # price/quantity match. Preserve them for manual investigation.
                await self._repos.orders.mark_unknown(order_id, "legacy_missing_client_order_id")
                log.error("Recovery: order %s has no client_order_id; retained UNKNOWN", order_id)
                continue
            try:
                match = await self._exchange.get_order_by_client_order_id(client_order_id)
            except ExchangeError as exc:
                log.warning(
                    "Recovery: cannot reconcile UNKNOWN order %s: %s",
                    order_id, exc,
                )
                continue
            if match is not None:
                await self._repos.orders.update_status(
                    order_id,
                    match.status,
                    exchange_order_id=match.exchange_order_id,
                    filled_quantity=match.filled_quantity,
                    filled_price=match.filled_price,
                    reconciliation_status="resolved",
                )
                log.info(
                    "Recovery: linked order %s by client_order_id → exchange %s (status=%s)",
                    order_id, match.exchange_order_id, match.status,
                )
            else:
                await self._repos.orders.mark_unknown(order_id, "not_found_yet")
                log.warning("Recovery: order %s still UNKNOWN; it will be reconciled again", order_id)
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
                # The order id is itself authoritative, so trade history is a
                # safe last-resort recovery source. Never match on symbol/side
                # alone: another manual trade could look identical.
                try:
                    trades = await self._exchange.get_trade_history(order["symbol"], limit=500)
                except ExchangeError:
                    log.warning("Recovery: cannot fetch status or trade history for %s: %s", order_id, exc)
                    continue
                matched = [t for t in trades if t.exchange_order_id == order["exchange_order_id"]]
                if not matched:
                    log.warning("Recovery: exchange status unavailable and no trade history for %s", order_id)
                    continue
                filled_qty = sum(t.quantity for t in matched)
                filled_value = sum(t.quantity * t.price for t in matched)
                ex_order = ExchangeOrder(
                    exchange_order_id=order["exchange_order_id"], symbol=order["symbol"], side=order["side"],
                    price=float(order["price"]), quantity=float(order["quantity"]),
                    filled_quantity=filled_qty,
                    filled_price=(filled_value / filled_qty) if filled_qty else 0.0,
                    status=(OrderStatus.FILLED.value if filled_qty >= float(order["quantity"]) else OrderStatus.PARTIALLY_FILLED.value),
                    raw_status="trade_history_reconciled",
                    client_order_id=order.get("client_order_id") or "",
                )
                log.warning("Recovery: reconstructed order %s from authoritative trade history", order_id)

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

    # ------------------------------------------------------------------
    # Step 5: Zombie grid detection (crash between grid-row insert and
    # initial-order-row insert)
    # ------------------------------------------------------------------

    async def _detect_zombie_grids(self, active_grids: list[dict]) -> int:
        """Flag grids with no order rows at all — a crash between
        ``repos.grids.create()`` and the initial order being written in
        ``start_grid()``.

        This is distinct from orphan detection above: an orphan is a real
        exchange order with no local row; a zombie grid is a local grid row
        with *no order rows whatsoever*, real or otherwise, so
        ``check_grid_triggers`` (which only acts once ``current_level > 0``)
        would otherwise leave it silently stuck forever with no path to
        progress and no error ever surfaced.

        We do not auto-delete these grids: the initial exchange call may or
        may not have gone out before the crash, and if it did, the orphan
        check above is the correct place to surface that fact so the user
        can decide (link it manually, or cancel on CoinDCX). Here we only
        notify so the user knows this grid needs manual attention — likely
        `/stopgrid` followed by a fresh `/newgrid`.
        """
        zombie_count = 0
        for grid in active_grids:
            if grid.get("current_level", 0):
                continue  # already has at least one filled buy
            orders = await self._repos.orders.list_for_grid(grid["grid_id"])
            if orders:
                continue  # has at least one order row (even if failed/pending)
            zombie_count += 1
            log.error(
                "Recovery: ZOMBIE grid %s (%s) has zero order rows — the "
                "initial buy was never recorded, likely due to a crash "
                "between grid creation and order placement. Manual review "
                "needed: check CoinDCX for a stray order, then /stopgrid "
                "this grid and start a fresh one if nothing was placed.",
                grid["grid_id"], grid["symbol"],
            )
            await self._notifier.error(
                context=f"Zombie grid {grid['grid_id']} ({grid['symbol']})",
                message=(
                    "This grid has no order history at all — its initial buy "
                    "was never recorded, likely from a crash during grid "
                    "creation. Check CoinDCX for a stray order manually, then "
                    "/stopgrid this grid and start a fresh one."
                ),
            )
        return zombie_count

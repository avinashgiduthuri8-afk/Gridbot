"""Order Monitor: background loop that polls open orders for fills and
routes filled / partially-filled events to the DCA Manager.

Two poll modes
--------------
Normal cycle (every `poll_interval` seconds):
  Iterates all local non-terminal orders and calls sync_order_status().
  For FILLED orders: routes to DCAManager.handle_order_filled().
  For PARTIALLY_FILLED orders: sends a notification if new qty was filled.

Full exchange sync (every `sync_every_n_cycles` normal cycles):
  Fetches all exchange open orders for cross-check.  Any local open order
  whose exchange_order_id is no longer in the exchange open set is likely
  filled or cancelled silently → sync and process immediately.

Logging fields on every event:
  order_id, grid_id, symbol, side, mode, exchange_id, status, filled_qty
"""

from __future__ import annotations

import asyncio

from config.constants import GridStatus, OrderStatus
from exchange.base import ExchangeClient
from exchange.exceptions import ExchangeError, ExchangeRateLimitError
from notifications.notifier import Notifier
from storage.repositories import Repositories
from trading.dca_manager import DCAManager
from utils.logger import get_logger

log = get_logger("trading")


class OrderMonitor:
    # Backoff schedule when the exchange returns rate-limit errors.
    # Each consecutive hit doubles the extra sleep, capped at _MAX_BACKOFF_SECONDS.
    _BACKOFF_BASE_SECONDS: int = 30
    _MAX_BACKOFF_SECONDS: int = 300  # 5 minutes

    def __init__(
        self,
        repos: Repositories,
        order_manager,
        dca_manager: DCAManager,
        notifier: Notifier,
        exchange: ExchangeClient,
        poll_interval: int,
        sync_every_n_cycles: int = 10,
    ) -> None:
        self._repos = repos
        self._order_manager = order_manager
        self._dca_manager = dca_manager
        self._notifier = notifier
        self._exchange = exchange
        self._poll_interval = poll_interval
        self._sync_every_n_cycles = sync_every_n_cycles
        self._cycle_count = 0
        self._running = False
        self._task: asyncio.Task | None = None
        self._consecutive_rate_limit_hits: int = 0

    def start(self) -> None:
        if self._task is None:
            self._running = True
            self._task = asyncio.create_task(self._run_loop())
            log.info(
                "Order monitor started (poll=%ds, full-sync every %d cycles)",
                self._poll_interval, self._sync_every_n_cycles,
            )

    async def stop(self) -> None:
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None

    # ------------------------------------------------------------------
    # Main loop
    # ------------------------------------------------------------------

    async def _run_loop(self) -> None:
        while self._running:
            self._cycle_count += 1
            try:
                await self._poll_once()
                # Successful cycle — reset any rate-limit backoff.
                self._consecutive_rate_limit_hits = 0
            except ExchangeRateLimitError:
                self._consecutive_rate_limit_hits += 1
                # True exponential doubling: 30s, 60s, 120s, 240s, then capped
                # at _MAX_BACKOFF_SECONDS. The previous formula (base * count)
                # was linear (30, 60, 90, 120...), not exponential as the
                # class docstring claimed — this now matches the stated intent
                # and backs off faster under sustained rate-limiting.
                extra = min(
                    self._BACKOFF_BASE_SECONDS * (2 ** (self._consecutive_rate_limit_hits - 1)),
                    self._MAX_BACKOFF_SECONDS,
                )
                log.warning(
                    "Rate limit hit in order monitor (consecutive=%d); "
                    "sleeping extra %ds before next poll",
                    self._consecutive_rate_limit_hits,
                    extra,
                )
                await asyncio.sleep(extra)
                continue  # skip the sync cycle this round too
            except Exception:  # noqa: BLE001
                log.exception("Order monitor poll cycle failed")

            if self._cycle_count % self._sync_every_n_cycles == 0:
                try:
                    synced, fills = await self._sync_with_exchange()
                    if synced > 0 or fills > 0:
                        log.info(
                            "Exchange sync: synced=%d fills=%d", synced, fills
                        )
                        await self._notifier.sync_completed(synced, fills)
                except Exception:  # noqa: BLE001
                    log.exception("Exchange sync cycle failed")
                    await self._notifier.sync_error(
                        "Order monitor sync", "Exchange sync cycle failed"
                    )

            await asyncio.sleep(self._poll_interval)

    # ------------------------------------------------------------------
    # Per-cycle: poll all local non-terminal orders
    # ------------------------------------------------------------------

    async def _poll_once(self) -> None:
        open_orders = await self._repos.orders.list_open()
        for order in open_orders:
            if not order["exchange_order_id"]:
                continue

            prev_filled_qty: float = float(order.get("filled_quantity") or 0)
            prev_status: str = order["status"]

            try:
                refreshed = await self._order_manager.sync_order_status(
                    order["order_id"]
                )
            except ExchangeRateLimitError:
                # Bubble up so _run_loop can apply backoff and skip remaining orders.
                raise
            except ExchangeError as exc:
                log.warning(
                    "sync_order_status failed for %s: %s", order["order_id"], exc
                )
                continue

            if refreshed is None:
                continue

            if refreshed.status == OrderStatus.FILLED.value:
                fill_price = refreshed.filled_price or refreshed.price
                fill_qty = refreshed.filled_quantity or refreshed.quantity
                log.info(
                    "order.filled   order=%s grid=%s symbol=%s side=%s "
                    "exchange_id=%s qty=%.8f @ ₹%.2f",
                    refreshed.order_id, refreshed.grid_id, refreshed.symbol,
                    refreshed.side, refreshed.exchange_order_id, fill_qty, fill_price,
                )
                try:
                    await self._dca_manager.handle_order_filled(
                        order_id=refreshed.order_id,
                        fill_price=fill_price,
                        fill_qty=fill_qty,
                    )
                except Exception:  # noqa: BLE001
                    log.exception(
                        "handle_order_filled failed for order %s",
                        refreshed.order_id,
                    )

            elif refreshed.status == OrderStatus.PARTIALLY_FILLED.value:
                new_filled_qty = float(refreshed.filled_quantity or 0)
                if new_filled_qty > prev_filled_qty or prev_status != refreshed.status:
                    remaining = float(refreshed.quantity) - new_filled_qty
                    log.info(
                        "order.partial_fill order=%s grid=%s symbol=%s side=%s "
                        "filled=%.8f remaining=%.8f",
                        refreshed.order_id, refreshed.grid_id, refreshed.symbol,
                        refreshed.side, new_filled_qty, remaining,
                    )
                    # Look up mode for notification
                    grid = await self._repos.grids.get(refreshed.grid_id)
                    mode = (grid or {}).get("mode", "real")
                    await self._notifier.partial_fill_received(
                        symbol=refreshed.symbol,
                        grid_id=refreshed.grid_id,
                        order_id=refreshed.order_id,
                        side=refreshed.side,
                        filled_qty=new_filled_qty,
                        total_qty=float(refreshed.quantity),
                        fill_price=float(refreshed.filled_price or refreshed.price),
                        mode=mode,
                    )

            elif refreshed.status in (
                OrderStatus.CANCELLED.value,
                OrderStatus.EXPIRED.value,
            ):
                if prev_status not in (
                    OrderStatus.CANCELLED.value,
                    OrderStatus.EXPIRED.value,
                ):
                    grid = await self._repos.grids.get(refreshed.grid_id)
                    mode = (grid or {}).get("mode", "real")
                    await self._notifier.order_cancelled(
                        symbol=refreshed.symbol,
                        grid_id=refreshed.grid_id,
                        order_id=refreshed.order_id,
                        side=refreshed.side,
                        mode=mode,
                    )
                    # If this was a pending stop-loss attempt, roll the grid back
                    # to ACTIVE so normal processing can resume.
                    try:
                        if grid and grid.get("status") == GridStatus.STOPPING.value:
                            await self._repos.grids.update_status(refreshed.grid_id, GridStatus.ACTIVE.value)
                            await self._notifier.grid_resumed(symbol=refreshed.symbol, grid_id=refreshed.grid_id)
                    except Exception:  # noqa: BLE001
                        log.exception("Failed to roll back STOPPING grid %s after order cancelled", refreshed.grid_id)

    # ------------------------------------------------------------------
    # Periodic full exchange sync
    # ------------------------------------------------------------------

    async def _sync_with_exchange(self) -> tuple[int, int]:
        """Cross-check all local open orders against the exchange.

        Detects orders that filled / got cancelled on the exchange side without
        the normal poll catching them (e.g., brief connectivity loss).

        Returns (synced_count, fills_found).
        """
        local_open = await self._repos.orders.list_open()
        if not local_open:
            return 0, 0

        # Resolve SUBMITTED orders that have no exchange_order_id — these are
        # orders that were in-flight when a previous cycle crashed.  Recovery
        # handles them at startup but the monitor may encounter them mid-session
        # if a timeout error arrived after the HTTP request actually landed.
        for order in local_open:
            if order.get("status") in (OrderStatus.SUBMITTED.value, OrderStatus.UNKNOWN.value) and not order.get("exchange_order_id"):
                log.info(
                    "exchange_sync: resolving stuck SUBMITTED order %s (%s %s)",
                    order["order_id"], order["side"], order["symbol"],
                )
                try:
                    await self._order_manager.resolve_uncertain_submitted(order["order_id"])
                except ExchangeError as exc:
                    log.warning(
                        "exchange_sync: resolve_uncertain_submitted(%s) failed: %s",
                        order["order_id"], exc,
                    )

        # Re-fetch so any newly-linked orders appear with their exchange_order_id
        local_open = await self._repos.orders.list_open()

        # Collect symbols with active local orders
        symbols: set[str] = {
            o["symbol"] for o in local_open if o.get("exchange_order_id")
        }

        # Fetch exchange open orders (batched by symbol)
        exchange_open_ids: set[str] = set()
        for symbol in symbols:
            try:
                ex_orders = await self._exchange.get_open_orders(symbol=symbol)
                for eo in ex_orders:
                    exchange_open_ids.add(eo.exchange_order_id)
            except ExchangeError as exc:
                log.warning("Exchange sync: get_open_orders(%s) failed: %s", symbol, exc)

        synced = 0
        fills_found = 0

        for order in local_open:
            ex_id = order.get("exchange_order_id")
            if not ex_id:
                continue

            # Order is locally open but no longer in exchange open set
            # → it must have moved to a terminal state (filled/cancelled)
            if ex_id not in exchange_open_ids:
                try:
                    refreshed = await self._order_manager.sync_order_status(
                        order["order_id"]
                    )
                except ExchangeError as exc:
                    log.warning(
                        "Exchange sync: cannot fetch %s status: %s",
                        order["order_id"], exc,
                    )
                    continue

                if refreshed is None:
                    continue

                synced += 1
                log.info(
                    "exchange_sync: order=%s exchange_id=%s new_status=%s",
                    refreshed.order_id, ex_id, refreshed.status,
                )

                if refreshed.status == OrderStatus.FILLED.value:
                    fills_found += 1
                    fill_price = refreshed.filled_price or refreshed.price
                    fill_qty = refreshed.filled_quantity or refreshed.quantity
                    try:
                        await self._dca_manager.handle_order_filled(
                            order_id=refreshed.order_id,
                            fill_price=fill_price,
                            fill_qty=fill_qty,
                        )
                    except Exception:  # noqa: BLE001
                        log.exception(
                            "Exchange sync: handle_order_filled failed for %s",
                            refreshed.order_id,
                        )

        return synced, fills_found

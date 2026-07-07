"""Price Monitoring Engine.

Replaces the raw ``run_price_trigger_loop`` in main.py with a dedicated,
self-contained class that:

- Monitors **only** coins that have active grids (queried every cycle).
- Fetches prices in a **single batch** API call per cycle instead of one
  call per symbol.
- Supports a **configurable refresh interval** (2 / 5 / 10 / 15 / 30 s)
  stored in SQLite so it survives restarts.
- Skips paused grids (only status=active is monitored).
- Continues monitoring surviving coins even when one symbol fetch fails.
- Retries failed requests (via the exchange client's built-in tenacity
  retry policy).
- Logs all API failures with detail.
- Exposes a ``get_status()`` snapshot consumed by the /monitor command.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import TYPE_CHECKING

from storage.repositories import VALID_MONITOR_INTERVALS, DEFAULT_MONITOR_INTERVAL
from utils.logger import get_logger

if TYPE_CHECKING:
    from exchange.base import ExchangeClient
    from notifications.notifier import Notifier
    from storage.repositories import Repositories
    from trading.dca_manager import DCAManager

log = get_logger("trading")


# ---------------------------------------------------------------------------
# Status snapshot (returned to the /monitor handler)
# ---------------------------------------------------------------------------


@dataclass
class MonitorStatus:
    interval_seconds: int
    monitored_symbols: list[str]
    last_refresh: datetime | None
    next_refresh: datetime | None
    api_ok: bool
    consecutive_failures: int
    total_cycles: int


# ---------------------------------------------------------------------------
# Engine
# ---------------------------------------------------------------------------


class PriceMonitor:
    """Price monitoring engine — one asyncio task, configurable interval."""

    def __init__(
        self,
        exchange: "ExchangeClient",
        repos: "Repositories",
        dca_manager: "DCAManager",
        notifier: "Notifier",
        default_interval: int = DEFAULT_MONITOR_INTERVAL,
    ) -> None:
        self._exchange = exchange
        self._repos = repos
        self._dca_manager = dca_manager
        self._notifier = notifier
        self._default_interval = default_interval

        # Runtime state
        self._interval: int = default_interval
        self._monitored_symbols: list[str] = []
        self._last_refresh: datetime | None = None
        self._next_refresh: datetime | None = None
        self._api_ok: bool = True
        self._consecutive_failures: int = 0
        self._total_cycles: int = 0
        self._task: asyncio.Task | None = None

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def load_interval(self) -> None:
        """Load the persisted interval from the database.

        Call this once after the database is ready, before start().
        When no value has been explicitly stored (first run), the constructor
        default (which honours PRICE_POLL_INTERVAL_SECONDS from settings) is
        kept unchanged rather than being overridden by the repository constant.
        """
        stored = await self._repos.monitor_settings.get_interval()
        if stored is not None:
            self._interval = stored
            log.info("Price monitor interval loaded from DB: %ds", self._interval)
        else:
            log.info(
                "No persisted monitor interval found — using default: %ds",
                self._interval,
            )

    async def set_interval(self, seconds: int) -> None:
        """Change and persist the refresh interval.

        Raises ValueError if *seconds* is not one of VALID_MONITOR_INTERVALS.
        The change takes effect at the start of the next cycle.
        """
        if seconds not in VALID_MONITOR_INTERVALS:
            raise ValueError(
                f"Invalid interval {seconds}s. "
                f"Allowed values: {', '.join(str(v) for v in VALID_MONITOR_INTERVALS)}s"
            )
        await self._repos.monitor_settings.set_interval(seconds)
        self._interval = seconds
        log.info("Price monitor interval updated to %ds", seconds)

    def get_status(self) -> MonitorStatus:
        """Return a snapshot of the current monitor state."""
        return MonitorStatus(
            interval_seconds=self._interval,
            monitored_symbols=list(self._monitored_symbols),
            last_refresh=self._last_refresh,
            next_refresh=self._next_refresh,
            api_ok=self._api_ok,
            consecutive_failures=self._consecutive_failures,
            total_cycles=self._total_cycles,
        )

    def start(self) -> None:
        """Spawn the monitoring loop as an asyncio background task."""
        self._task = asyncio.create_task(self._run(), name="price_monitor")
        log.info("Price monitor started (interval=%ds)", self._interval)

    async def stop(self) -> None:
        """Cancel the monitoring loop and wait for it to finish."""
        if self._task is not None and not self._task.done():
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        log.info("Price monitor stopped")

    # ------------------------------------------------------------------
    # Internal loop
    # ------------------------------------------------------------------

    async def _run(self) -> None:
        """Main monitoring loop — runs forever until cancelled.

        State management contract:
        - ``_api_ok`` and ``_consecutive_failures`` are managed inside
          ``_run_cycle`` so per-symbol and batch-level degraded states survive
          to the status snapshot.
        - This outer loop only catches unexpected exceptions that escape
          ``_run_cycle`` entirely (bugs, unhandled OS errors, etc.) and marks
          the API as degraded in those cases too.
        - ``_last_refresh`` and ``_total_cycles`` are always updated after each
          attempt regardless of outcome.
        """
        while True:
            cycle_start = datetime.now(timezone.utc)
            self._next_refresh = datetime.fromtimestamp(
                cycle_start.timestamp() + self._interval, tz=timezone.utc
            )

            try:
                await self._run_cycle()
                # Do NOT reset api_ok / consecutive_failures here.
                # _run_cycle is fully responsible for those fields so that
                # partial-failure states (missing symbols, etc.) are preserved.
            except asyncio.CancelledError:
                raise
            except Exception as exc:  # noqa: BLE001
                # Unexpected crash escaping _run_cycle — treat as hard failure.
                self._consecutive_failures += 1
                self._api_ok = False
                log.error(
                    "Price monitor cycle crashed (consecutive failures: %d): %s",
                    self._consecutive_failures,
                    exc,
                    exc_info=True,
                )

            self._last_refresh = datetime.now(timezone.utc)
            self._total_cycles += 1
            self._next_refresh = datetime.fromtimestamp(
                self._last_refresh.timestamp() + self._interval, tz=timezone.utc
            )

            await asyncio.sleep(self._interval)

    async def _run_cycle(self) -> None:
        """Execute one monitoring cycle.

        1. Fetch all active grids from the DB.
        2. Collect the unique set of symbols.
        3. Batch-fetch live prices (single HTTP call to /exchange/ticker).
        4. For each active grid, compare price against buy/sell targets and
           trigger the trading engine when a target is crossed.
        """
        # Step 1 — active grids only (not paused)
        active_grids = await self._repos.grids.list_by_status(["active"])
        if not active_grids:
            self._monitored_symbols = []
            return

        # Step 2 — unique symbol set
        symbols: set[str] = {g["symbol"] for g in active_grids}
        self._monitored_symbols = sorted(symbols)

        # Step 3 — batch price fetch
        try:
            prices = await self._exchange.get_tickers_batch(symbols)
        except Exception as exc:  # noqa: BLE001
            log.error("Batch ticker fetch failed: %s", exc)
            self._api_ok = False
            self._consecutive_failures += 1
            # Log each symbol failure for transparency
            for sym in symbols:
                log.warning("Price unavailable for %s due to batch failure", sym)
            return

        # Flag partial failures (symbols that came back empty from the batch)
        missing = symbols - prices.keys()
        if missing:
            self._api_ok = False
            for sym in missing:
                log.warning("No price returned for %s in batch response", sym)
        else:
            # Full success — reset failure counters so recovery is visible in status.
            self._api_ok = True
            self._consecutive_failures = 0

        # Step 4 — trigger trading engine per grid
        for grid in active_grids:
            symbol: str = grid["symbol"]
            ticker = prices.get(symbol)
            if ticker is None:
                log.warning(
                    "Skipping trigger check for grid %s (%s): price unavailable",
                    grid["grid_id"], symbol,
                )
                continue
            try:
                await self._dca_manager.check_grid_triggers(
                    grid["grid_id"], ticker.last_price
                )
            except asyncio.CancelledError:
                raise
            except Exception as exc:  # noqa: BLE001
                # One grid failing must never stop monitoring of other grids
                log.error(
                    "Trigger check failed for grid %s (%s): %s",
                    grid["grid_id"], symbol, exc,
                )

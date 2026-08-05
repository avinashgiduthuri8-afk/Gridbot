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
from exchange.exceptions import ExchangeRateLimitError
from utils.helpers import is_valid_price
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

    # Same backoff schedule as OrderMonitor, for consistency: exponential
    # doubling per consecutive rate-limit hit, capped at _MAX_BACKOFF_SECONDS.
    # This is EXTRA sleep on top of the normal poll interval — without it, a
    # short configured interval (as low as 2s) would keep hammering an
    # already-rate-limited exchange at the same cadence that triggered the
    # limit in the first place.
    _BACKOFF_BASE_SECONDS: int = 30
    _MAX_BACKOFF_SECONDS: int = 300  # 5 minutes

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
        self._consecutive_rate_limit_hits: int = 0
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
        except ExchangeRateLimitError as exc:
            # Note: by the time this exception reaches us, exchange/coindcx.py's
            # own tenacity retry has already tried this same request up to 4
            # times internally (exponential wait, capped ~8s/attempt) and given
            # up — so this being raised at all means the exchange is under
            # SUSTAINED pressure, not a one-off blip. The backoff below is a
            # second, slower-moving tier on top of that: it spaces out entire
            # polling cycles (30s → 300s) rather than individual HTTP attempts.
            # Worst case, one cycle's total wall-clock cost is bounded by
            # coindcx.py's own internal retry ceiling (~tens of seconds) plus
            # this cycle's backoff sleep — not unbounded, but worth knowing
            # a badly-rate-limited stretch can take several minutes per cycle
            # at the top of this schedule.
            self._consecutive_rate_limit_hits += 1
            extra = min(
                self._BACKOFF_BASE_SECONDS * (2 ** (self._consecutive_rate_limit_hits - 1)),
                self._MAX_BACKOFF_SECONDS,
            )
            log.warning(
                "Rate limit hit in price monitor (consecutive=%d); sleeping "
                "extra %ds before next cycle: %s",
                self._consecutive_rate_limit_hits, extra, exc,
            )
            self._api_ok = False
            self._consecutive_failures += 1
            await asyncio.sleep(extra)
            return
        except Exception as exc:  # noqa: BLE001
            log.error("Batch ticker fetch failed: %s", exc)
            self._api_ok = False
            self._consecutive_failures += 1
            # Log each symbol failure for transparency
            for sym in symbols:
                log.warning("Price unavailable for %s due to batch failure", sym)
            return

        # Full success — reset rate-limit backoff too, not just the generic
        # failure counter, so a recovered exchange doesn't carry over a long
        # backoff from an earlier, unrelated failure streak.
        self._consecutive_rate_limit_hits = 0

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
            if not is_valid_price(ticker.last_price):
                # A real exchange can (rarely) return a garbage reading —
                # 0, negative, NaN, or +/-Infinity — during an outage or a
                # data bug. This must never reach DCAManager: e.g. a price
                # of 0 would otherwise satisfy a stop-loss condition for
                # any grid and trigger an unwanted full-position sell.
                # Skip only this symbol's grids this cycle; every other
                # symbol continues normally.
                log.warning(
                    "Skipping trigger check for grid %s (%s): invalid price %r "
                    "from exchange (must be a finite, positive number)",
                    grid["grid_id"], symbol, ticker.last_price,
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

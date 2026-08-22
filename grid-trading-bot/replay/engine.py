"""ReplayEngine: feeds a price feed into the real trading engine.

This is the orchestration layer. It does not contain any trading logic of
its own — every trigger evaluation, order placement, and fill goes through
the actual production DCAManager / OrderManager / OrderMonitor exactly as
in a live deployment. All the engine does is:

  1. advance a virtual clock and the replay exchange's current price
  2. ask OrderMonitor to resolve any orders whose simulated latency has
     now elapsed (reusing its existing poll cycle, unmodified)
  3. ask DCAManager to check triggers for every active grid on that symbol

Pause/resume/stop/seek all operate on this loop; they never touch trading
state directly.
"""
from __future__ import annotations

import asyncio
from dataclasses import dataclass, field

from config.constants import GridStatus
from replay.data_loader import Candle
from replay.market_data_exchange import ReplayMarketDataExchange
from storage.repositories import Repositories
from trading.dca_manager import DCAManager
from trading.order_monitor import OrderMonitor
from utils.logger import get_logger

log = get_logger("trading")


@dataclass
class ReplayClock:
    """A virtual clock the replay engine controls directly, injected into
    the fee-simulating exchange as its time_fn so simulated order latency
    (seconds) advances with replay ticks instead of wall-clock time."""
    _seconds: float = 0.0

    def now(self) -> float:
        return self._seconds

    def advance_to(self, seconds: float) -> None:
        if seconds > self._seconds:
            self._seconds = seconds

    def tick(self, delta: float) -> None:
        self._seconds += delta


@dataclass
class ReplayStats:
    """Running counters the engine updates as it processes the feed —
    consumed by report.py at the end of a run."""
    candles_processed: int = 0
    sub_ticks_processed: int = 0
    trigger_evaluations: int = 0
    symbols_seen: set[str] = field(default_factory=set)
    start_timestamp: float | None = None
    end_timestamp: float | None = None
    exceptions: list[str] = field(default_factory=list)


class ReplayEngine:
    def __init__(
        self,
        repos: Repositories,
        dca_manager: DCAManager,
        order_monitor: OrderMonitor,
        market_data_exchange: ReplayMarketDataExchange,
        clock: ReplayClock,
        *,
        sub_tick_within_candle: bool = True,
        speed: float | None = None,
        candle_interval_seconds: float = 60.0,
    ) -> None:
        """
        sub_tick_within_candle: if True, feed open/high/low/close as four
            separate ticks per candle (so an intra-bar stop-loss/dip/profit
            level gets a chance to fire, not just the close). If False,
            only the close price is fed — faster, coarser.
        speed: if set, a real-number multiplier used to throttle replay to
            (roughly) real time / speed between candles, for visualization.
            None (default) runs as fast as possible with no sleeping — the
            normal mode for stress testing.
        """
        self._repos = repos
        self._dca = dca_manager
        self._order_monitor = order_monitor
        self._exchange = market_data_exchange
        self._clock = clock
        self._sub_tick = sub_tick_within_candle
        self._speed = speed
        self._candle_interval = candle_interval_seconds

        self.stats = ReplayStats()

        self._paused = asyncio.Event()
        self._paused.set()  # not paused by default
        self._stop_requested = False

    # ------------------------------------------------------------------
    # Playback control
    # ------------------------------------------------------------------

    def pause(self) -> None:
        self._paused.clear()

    def resume(self) -> None:
        self._paused.set()

    def stop(self) -> None:
        self._stop_requested = True
        self._paused.set()  # unblock a paused loop so it can observe the stop

    def reset_stop(self) -> None:
        self._stop_requested = False

    @staticmethod
    def seek(feed: list[Candle], timestamp: float) -> list[Candle]:
        """Returns the sub-list of `feed` from the first candle at or after
        `timestamp` onward. Does not mutate `feed`."""
        return [c for c in feed if c.timestamp >= timestamp]

    # ------------------------------------------------------------------
    # Main loop
    # ------------------------------------------------------------------

    async def run(
        self, feed: list[Candle], symbols: list[str] | None = None,
        on_candle: "callable | None" = None,
    ) -> ReplayStats:
        """Replay `feed` (already chronologically sorted) through the real
        trading engine. If `symbols` is given, only candles for those
        symbols are processed (useful for "replay one symbol" out of a
        multi-symbol feed) — otherwise every symbol present is replayed.

        on_candle, if given, is awaited once per candle with the 0-based
        candle index — used by the CLI to periodically exercise manual
        trades (--manual-trade-every) without the engine itself needing
        any manual-trading-specific logic."""
        self._stop_requested = False
        wanted = {s.upper() for s in symbols} if symbols else None

        for candle in feed:
            if self._stop_requested:
                break
            if wanted is not None and candle.symbol.upper() not in wanted:
                continue

            await self._paused.wait()
            if self._stop_requested:
                break

            if self.stats.start_timestamp is None:
                self.stats.start_timestamp = candle.timestamp
            self.stats.end_timestamp = candle.timestamp
            self.stats.symbols_seen.add(candle.symbol.upper())

            self._clock.advance_to(candle.timestamp)
            prices = candle.prices_in_order if self._sub_tick else (candle.close,)

            for price in prices:
                self._exchange.set_price(candle.symbol, price)
                try:
                    await self._order_monitor._poll_once()  # noqa: SLF001 — deliberate reuse, see module docstring
                except Exception as exc:  # noqa: BLE001 — a bad tick must not kill the whole replay
                    log.exception("Replay: order_monitor poll failed on a tick")
                    self.stats.exceptions.append(f"order_monitor poll: {exc}")

                self.stats.sub_ticks_processed += 1
                await self._check_active_grids(candle.symbol, price)

                if self._speed is not None and self._speed > 0:
                    await asyncio.sleep(self._candle_interval / len(prices) / self._speed)

            self.stats.candles_processed += 1
            if on_candle is not None:
                await on_candle(self.stats.candles_processed - 1)

        return self.stats

    async def _check_active_grids(self, symbol: str, price: float) -> None:
        grids = await self._repos.grids.list_by_status(
            [GridStatus.ACTIVE.value, GridStatus.PAUSED.value]
        )
        for grid in grids:
            if grid["symbol"].upper() != symbol.upper():
                continue
            self.stats.trigger_evaluations += 1
            try:
                await self._dca.check_grid_triggers(grid["grid_id"], price)
            except Exception as exc:  # noqa: BLE001 — isolate one grid's failure from the rest of the replay
                log.exception("Replay: check_grid_triggers failed for grid %s", grid["grid_id"])
                self.stats.exceptions.append(f"check_grid_triggers({grid['grid_id']}): {exc}")

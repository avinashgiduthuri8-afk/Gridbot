"""Tests for the Price Monitoring Engine (trading/price_monitor.py)."""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from exchange.base import Ticker
from storage.repositories import VALID_MONITOR_INTERVALS, DEFAULT_MONITOR_INTERVAL
from trading.price_monitor import PriceMonitor, MonitorStatus


# ---------------------------------------------------------------------------
# Helpers / fixtures
# ---------------------------------------------------------------------------


def _make_grid(
    grid_id: str = "grd_001",
    symbol: str = "BTCINR",
    status: str = "active",
    next_buy_price: float = 5_000_000.0,
    next_sell_price: float = 5_500_000.0,
    current_level: int = 1,
) -> dict:
    return {
        "grid_id": grid_id,
        "symbol": symbol,
        "status": status,
        "next_buy_price": next_buy_price,
        "next_sell_price": next_sell_price,
        "current_level": current_level,
    }


def _make_monitor(
    active_grids: list[dict] | None = None,
    tickers: dict[str, Ticker] | None = None,
    interval_db: int = DEFAULT_MONITOR_INTERVAL,
) -> tuple[PriceMonitor, MagicMock, MagicMock, MagicMock]:
    """Build a PriceMonitor with all dependencies mocked."""
    exchange = MagicMock()
    repos = MagicMock()
    dca_manager = MagicMock()
    notifier = MagicMock()

    # repos.grids.list_by_status returns active_grids
    repos.grids.list_by_status = AsyncMock(return_value=active_grids or [])
    # repos.monitor_settings.get_interval returns interval_db
    repos.monitor_settings = MagicMock()
    repos.monitor_settings.get_interval = AsyncMock(return_value=interval_db)
    repos.monitor_settings.set_interval = AsyncMock()

    # exchange.get_tickers_batch returns tickers dict
    exchange.get_tickers_batch = AsyncMock(return_value=tickers or {})

    # dca_manager.check_grid_triggers is a no-op async
    dca_manager.check_grid_triggers = AsyncMock()

    monitor = PriceMonitor(
        exchange=exchange,
        repos=repos,
        dca_manager=dca_manager,
        notifier=notifier,
        default_interval=DEFAULT_MONITOR_INTERVAL,
    )
    return monitor, exchange, repos, dca_manager


# ---------------------------------------------------------------------------
# Initialisation
# ---------------------------------------------------------------------------


class TestInitialState:
    def test_default_interval_before_load(self):
        monitor, _, _, _ = _make_monitor()
        assert monitor._interval == DEFAULT_MONITOR_INTERVAL
        assert monitor._monitored_symbols == []
        assert monitor._last_refresh is None
        assert monitor._api_ok is True
        assert monitor._consecutive_failures == 0
        assert monitor._total_cycles == 0

    @pytest.mark.asyncio
    async def test_load_interval_reads_from_db(self):
        monitor, _, repos, _ = _make_monitor(interval_db=10)
        await monitor.load_interval()
        assert monitor._interval == 10
        repos.monitor_settings.get_interval.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_load_interval_uses_default_when_db_returns_default(self):
        monitor, _, _, _ = _make_monitor(interval_db=DEFAULT_MONITOR_INTERVAL)
        await monitor.load_interval()
        assert monitor._interval == DEFAULT_MONITOR_INTERVAL


# ---------------------------------------------------------------------------
# set_interval
# ---------------------------------------------------------------------------


class TestSetInterval:
    @pytest.mark.asyncio
    @pytest.mark.parametrize("seconds", VALID_MONITOR_INTERVALS)
    async def test_valid_intervals_accepted(self, seconds: int):
        monitor, _, repos, _ = _make_monitor()
        await monitor.set_interval(seconds)
        assert monitor._interval == seconds
        repos.monitor_settings.set_interval.assert_awaited_once_with(seconds)

    @pytest.mark.asyncio
    @pytest.mark.parametrize("bad", [0, 1, 3, 7, 45, 60, -5])
    async def test_invalid_interval_raises_value_error(self, bad: int):
        monitor, _, _, _ = _make_monitor()
        with pytest.raises(ValueError, match="Invalid interval"):
            await monitor.set_interval(bad)

    @pytest.mark.asyncio
    async def test_set_interval_propagates_db_error(self):
        monitor, _, repos, _ = _make_monitor()
        repos.monitor_settings.set_interval = AsyncMock(side_effect=RuntimeError("db down"))
        with pytest.raises(RuntimeError):
            await monitor.set_interval(10)


# ---------------------------------------------------------------------------
# get_status
# ---------------------------------------------------------------------------


class TestGetStatus:
    def test_returns_monitor_status_dataclass(self):
        monitor, _, _, _ = _make_monitor()
        status = monitor.get_status()
        assert isinstance(status, MonitorStatus)

    def test_status_reflects_current_state(self):
        monitor, _, _, _ = _make_monitor()
        monitor._interval = 15
        monitor._monitored_symbols = ["BTCINR", "ETHINR"]
        monitor._api_ok = False
        monitor._consecutive_failures = 3
        monitor._total_cycles = 42

        status = monitor.get_status()
        assert status.interval_seconds == 15
        assert set(status.monitored_symbols) == {"BTCINR", "ETHINR"}
        assert status.api_ok is False
        assert status.consecutive_failures == 3
        assert status.total_cycles == 42

    def test_status_monitored_symbols_is_a_copy(self):
        monitor, _, _, _ = _make_monitor()
        monitor._monitored_symbols = ["BTCINR"]
        status = monitor.get_status()
        status.monitored_symbols.append("ETHINR")
        assert monitor._monitored_symbols == ["BTCINR"]  # internal list unchanged


# ---------------------------------------------------------------------------
# _run_cycle — core monitoring logic
# ---------------------------------------------------------------------------


class TestRunCycle:
    @pytest.mark.asyncio
    async def test_no_active_grids_clears_monitored_symbols(self):
        monitor, exchange, repos, _ = _make_monitor(active_grids=[])
        await monitor._run_cycle()
        assert monitor._monitored_symbols == []
        exchange.get_tickers_batch.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_fetches_only_symbols_of_active_grids(self):
        grids = [
            _make_grid("grd_1", "BTCINR"),
            _make_grid("grd_2", "ETHINR"),
        ]
        tickers = {
            "BTCINR": Ticker(symbol="BTCINR", last_price=5_100_000.0),
            "ETHINR": Ticker(symbol="ETHINR", last_price=280_000.0),
        }
        monitor, exchange, _, _ = _make_monitor(active_grids=grids, tickers=tickers)
        await monitor._run_cycle()
        called_symbols = exchange.get_tickers_batch.call_args.args[0]
        assert called_symbols == {"BTCINR", "ETHINR"}

    @pytest.mark.asyncio
    async def test_triggers_dca_manager_for_each_active_grid(self):
        grids = [
            _make_grid("grd_1", "BTCINR"),
            _make_grid("grd_2", "ETHINR"),
        ]
        tickers = {
            "BTCINR": Ticker(symbol="BTCINR", last_price=5_100_000.0),
            "ETHINR": Ticker(symbol="ETHINR", last_price=280_000.0),
        }
        monitor, _, _, dca_manager = _make_monitor(active_grids=grids, tickers=tickers)
        await monitor._run_cycle()
        assert dca_manager.check_grid_triggers.await_count == 2
        calls = {call.args for call in dca_manager.check_grid_triggers.call_args_list}
        assert ("grd_1", 5_100_000.0) in calls
        assert ("grd_2", 280_000.0) in calls

    @pytest.mark.asyncio
    async def test_paused_grids_not_queried(self):
        """list_by_status is called with only ['active'], so paused grids never appear."""
        monitor, _, repos, _ = _make_monitor(active_grids=[])
        await monitor._run_cycle()
        repos.grids.list_by_status.assert_awaited_once_with(["active"])

    @pytest.mark.asyncio
    async def test_marks_api_ok_when_all_prices_returned(self):
        grids = [_make_grid("grd_1", "BTCINR")]
        tickers = {"BTCINR": Ticker(symbol="BTCINR", last_price=5_000_000.0)}
        monitor, _, _, _ = _make_monitor(active_grids=grids, tickers=tickers)
        monitor._api_ok = False  # start in degraded state
        await monitor._run_cycle()
        assert monitor._api_ok is True

    @pytest.mark.asyncio
    async def test_marks_api_degraded_when_symbol_missing_from_response(self):
        grids = [
            _make_grid("grd_1", "BTCINR"),
            _make_grid("grd_2", "ETHINR"),
        ]
        # ETHINR is missing from response
        tickers = {"BTCINR": Ticker(symbol="BTCINR", last_price=5_000_000.0)}
        monitor, _, _, dca_manager = _make_monitor(active_grids=grids, tickers=tickers)
        await monitor._run_cycle()
        assert monitor._api_ok is False
        # Only BTCINR grid should be triggered
        assert dca_manager.check_grid_triggers.await_count == 1
        assert dca_manager.check_grid_triggers.call_args.args[0] == "grd_1"

    @pytest.mark.asyncio
    async def test_batch_failure_skips_all_grids_and_sets_degraded(self):
        grids = [_make_grid("grd_1", "BTCINR")]
        monitor, exchange, _, dca_manager = _make_monitor(active_grids=grids)
        exchange.get_tickers_batch = AsyncMock(side_effect=RuntimeError("API down"))
        await monitor._run_cycle()
        assert monitor._api_ok is False
        assert monitor._consecutive_failures == 1
        dca_manager.check_grid_triggers.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_one_grid_trigger_failure_does_not_stop_others(self):
        """A single grid's trigger error must not prevent other grids from being checked."""
        grids = [
            _make_grid("grd_1", "BTCINR"),
            _make_grid("grd_2", "ETHINR"),
        ]
        tickers = {
            "BTCINR": Ticker(symbol="BTCINR", last_price=5_000_000.0),
            "ETHINR": Ticker(symbol="ETHINR", last_price=280_000.0),
        }
        monitor, _, _, dca_manager = _make_monitor(active_grids=grids, tickers=tickers)
        # grd_1 blows up; grd_2 should still be triggered
        call_count = 0

        async def _side_effect(grid_id: str, price: float) -> None:
            nonlocal call_count
            call_count += 1
            if grid_id == "grd_1":
                raise RuntimeError("trigger error")

        dca_manager.check_grid_triggers = AsyncMock(side_effect=_side_effect)
        await monitor._run_cycle()
        assert call_count == 2  # both grids attempted

    @pytest.mark.asyncio
    async def test_deduplicates_symbols_across_multiple_grids(self):
        """Two grids on the same coin must result in a single fetch symbol."""
        grids = [
            _make_grid("grd_1", "BTCINR"),
            _make_grid("grd_2", "BTCINR"),
        ]
        tickers = {"BTCINR": Ticker(symbol="BTCINR", last_price=5_000_000.0)}
        monitor, exchange, _, _ = _make_monitor(active_grids=grids, tickers=tickers)
        await monitor._run_cycle()
        called_symbols = exchange.get_tickers_batch.call_args.args[0]
        # Only one unique symbol should be passed to the batch call
        assert called_symbols == {"BTCINR"}

    @pytest.mark.asyncio
    async def test_monitored_symbols_updated_each_cycle(self):
        grids = [_make_grid("grd_1", "BTCINR")]
        tickers = {"BTCINR": Ticker(symbol="BTCINR", last_price=5_000_000.0)}
        monitor, _, repos, _ = _make_monitor(active_grids=grids, tickers=tickers)
        await monitor._run_cycle()
        assert "BTCINR" in monitor._monitored_symbols

        # Next cycle: grid stopped, no active grids
        repos.grids.list_by_status = AsyncMock(return_value=[])
        await monitor._run_cycle()
        assert monitor._monitored_symbols == []


# ---------------------------------------------------------------------------
# _run — outer loop state management
# ---------------------------------------------------------------------------


class TestRunLoopStateManagement:
    """Verify that _run does NOT blindly reset api_ok / consecutive_failures.

    _run_cycle is responsible for those fields; _run must preserve degraded
    states set during a cycle so the /monitor snapshot reflects reality.
    """

    @pytest.mark.asyncio
    async def test_run_preserves_degraded_api_state_from_cycle(self):
        """After a cycle with a missing symbol, api_ok must remain False."""
        grids = [
            _make_grid("grd_1", "BTCINR"),
            _make_grid("grd_2", "ETHINR"),
        ]
        # Only BTCINR comes back — ETHINR is missing → degraded
        tickers = {"BTCINR": Ticker(symbol="BTCINR", last_price=5_000_000.0)}
        monitor, _, repos, _ = _make_monitor(active_grids=grids, tickers=tickers)

        # Run exactly one cycle (then stop the loop)
        await monitor._run_cycle()

        assert monitor._api_ok is False

    @pytest.mark.asyncio
    async def test_run_resets_consecutive_failures_after_full_success(self):
        """After a fully successful cycle, consecutive_failures must drop to 0."""
        grids = [_make_grid("grd_1", "BTCINR")]
        tickers = {"BTCINR": Ticker(symbol="BTCINR", last_price=5_000_000.0)}
        monitor, _, _, _ = _make_monitor(active_grids=grids, tickers=tickers)
        monitor._consecutive_failures = 3  # simulate prior failures

        await monitor._run_cycle()

        assert monitor._consecutive_failures == 0
        assert monitor._api_ok is True

    @pytest.mark.asyncio
    async def test_run_increments_consecutive_failures_on_batch_failure(self):
        """Batch API failure must increment consecutive_failures each cycle."""
        grids = [_make_grid("grd_1", "BTCINR")]
        monitor, exchange, _, _ = _make_monitor(active_grids=grids)
        exchange.get_tickers_batch = AsyncMock(side_effect=RuntimeError("timeout"))

        await monitor._run_cycle()
        assert monitor._consecutive_failures == 1
        assert monitor._api_ok is False

        await monitor._run_cycle()
        assert monitor._consecutive_failures == 2

    @pytest.mark.asyncio
    async def test_consecutive_failures_preserved_across_partial_cycle(self):
        """Partial failure (missing symbol) must not reset consecutive_failures."""
        grids = [
            _make_grid("grd_1", "BTCINR"),
            _make_grid("grd_2", "ETHINR"),
        ]
        tickers = {"BTCINR": Ticker(symbol="BTCINR", last_price=5_000_000.0)}
        monitor, _, _, _ = _make_monitor(active_grids=grids, tickers=tickers)
        monitor._consecutive_failures = 2

        await monitor._run_cycle()

        # Partial failure should not reset the counter
        assert monitor._api_ok is False
        # consecutive_failures is left at its existing value (not incremented
        # on partial failure — only batch failure increments it)
        assert monitor._consecutive_failures == 2


# ---------------------------------------------------------------------------
# load_interval — respects constructor default when no DB value exists
# ---------------------------------------------------------------------------


class TestLoadInterval:
    @pytest.mark.asyncio
    async def test_load_interval_uses_constructor_default_when_db_empty(self):
        """If no value in DB, constructor default (e.g. from settings env var) is kept."""
        monitor, _, repos, _ = _make_monitor()
        repos.monitor_settings.get_interval = AsyncMock(return_value=None)
        monitor._interval = 10  # set to non-default to prove it's not overwritten

        await monitor.load_interval()

        assert monitor._interval == 10  # unchanged

    @pytest.mark.asyncio
    async def test_load_interval_overrides_constructor_default_with_db_value(self):
        """If a value IS persisted, it must override the constructor default."""
        monitor, _, repos, _ = _make_monitor()
        repos.monitor_settings.get_interval = AsyncMock(return_value=30)
        monitor._interval = 5  # constructor default

        await monitor.load_interval()

        assert monitor._interval == 30


# ---------------------------------------------------------------------------
# format_monitor_status
# ---------------------------------------------------------------------------


class TestFormatMonitorStatus:
    def test_format_contains_interval(self):
        from bot_telegram.formatters import format_monitor_status

        status = MonitorStatus(
            interval_seconds=10,
            monitored_symbols=["BTCINR", "ETHINR"],
            last_refresh=None,
            next_refresh=None,
            api_ok=True,
            consecutive_failures=0,
            total_cycles=5,
        )
        text = format_monitor_status(status)
        assert "10s" in text
        assert "BTCINR" in text
        assert "ETHINR" in text

    def test_format_shows_api_degraded(self):
        from bot_telegram.formatters import format_monitor_status

        status = MonitorStatus(
            interval_seconds=5,
            monitored_symbols=[],
            last_refresh=None,
            next_refresh=None,
            api_ok=False,
            consecutive_failures=3,
            total_cycles=10,
        )
        text = format_monitor_status(status)
        assert "DEGRADED" in text
        assert "3" in text

    def test_format_shows_no_active_grids_message_when_empty(self):
        from bot_telegram.formatters import format_monitor_status

        status = MonitorStatus(
            interval_seconds=5,
            monitored_symbols=[],
            last_refresh=None,
            next_refresh=None,
            api_ok=True,
            consecutive_failures=0,
            total_cycles=0,
        )
        text = format_monitor_status(status)
        assert "none" in text.lower() or "no active" in text.lower()

    def test_format_shows_all_valid_intervals_in_hint(self):
        from bot_telegram.formatters import format_monitor_status
        from storage.repositories import VALID_MONITOR_INTERVALS

        status = MonitorStatus(
            interval_seconds=5,
            monitored_symbols=[],
            last_refresh=None,
            next_refresh=None,
            api_ok=True,
            consecutive_failures=0,
            total_cycles=0,
        )
        text = format_monitor_status(status)
        for v in VALID_MONITOR_INTERVALS:
            assert str(v) in text


# ---------------------------------------------------------------------------
# Valid interval values
# ---------------------------------------------------------------------------


class TestValidIntervals:
    def test_valid_intervals_are_correct(self):
        assert VALID_MONITOR_INTERVALS == (2, 5, 10, 15, 30)

    def test_default_interval_is_in_valid_set(self):
        assert DEFAULT_MONITOR_INTERVAL in VALID_MONITOR_INTERVALS


# ---------------------------------------------------------------------------
# MonitorStatus dataclass
# ---------------------------------------------------------------------------


class TestMonitorStatus:
    def test_status_dataclass_fields(self):
        now = datetime.now(timezone.utc)
        status = MonitorStatus(
            interval_seconds=5,
            monitored_symbols=["BTCINR"],
            last_refresh=now,
            next_refresh=now,
            api_ok=True,
            consecutive_failures=0,
            total_cycles=1,
        )
        assert status.interval_seconds == 5
        assert status.monitored_symbols == ["BTCINR"]
        assert status.api_ok is True


# ---------------------------------------------------------------------------
# Invalid price rejection (0, negative, NaN, Infinity) — must never reach
# DCAManager, must skip only that symbol, and must not stop the cycle.
# ---------------------------------------------------------------------------


class TestInvalidPriceRejection:
    @pytest.mark.asyncio
    async def test_zero_price_skips_grid_and_logs_warning(self, caplog):
        grids = [_make_grid("grd_1", "BTCINR")]
        tickers = {"BTCINR": Ticker(symbol="BTCINR", last_price=0.0)}
        monitor, _, _, dca_manager = _make_monitor(active_grids=grids, tickers=tickers)
        with caplog.at_level("WARNING"):
            await monitor._run_cycle()
        dca_manager.check_grid_triggers.assert_not_awaited()
        assert any("BTCINR" in r.message and "invalid price" in r.message for r in caplog.records)

    @pytest.mark.asyncio
    async def test_negative_price_skips_grid_and_logs_warning(self, caplog):
        grids = [_make_grid("grd_1", "BTCINR")]
        tickers = {"BTCINR": Ticker(symbol="BTCINR", last_price=-5_000_000.0)}
        monitor, _, _, dca_manager = _make_monitor(active_grids=grids, tickers=tickers)
        with caplog.at_level("WARNING"):
            await monitor._run_cycle()
        dca_manager.check_grid_triggers.assert_not_awaited()
        assert any("BTCINR" in r.message and "invalid price" in r.message for r in caplog.records)

    @pytest.mark.asyncio
    async def test_nan_price_skips_grid_and_logs_warning(self, caplog):
        grids = [_make_grid("grd_1", "BTCINR")]
        tickers = {"BTCINR": Ticker(symbol="BTCINR", last_price=float("nan"))}
        monitor, _, _, dca_manager = _make_monitor(active_grids=grids, tickers=tickers)
        with caplog.at_level("WARNING"):
            await monitor._run_cycle()
        dca_manager.check_grid_triggers.assert_not_awaited()
        assert any("BTCINR" in r.message and "invalid price" in r.message for r in caplog.records)

    @pytest.mark.asyncio
    async def test_positive_infinity_price_skips_grid(self, caplog):
        grids = [_make_grid("grd_1", "BTCINR")]
        tickers = {"BTCINR": Ticker(symbol="BTCINR", last_price=float("inf"))}
        monitor, _, _, dca_manager = _make_monitor(active_grids=grids, tickers=tickers)
        with caplog.at_level("WARNING"):
            await monitor._run_cycle()
        dca_manager.check_grid_triggers.assert_not_awaited()
        assert any("BTCINR" in r.message and "invalid price" in r.message for r in caplog.records)

    @pytest.mark.asyncio
    async def test_negative_infinity_price_skips_grid(self, caplog):
        grids = [_make_grid("grd_1", "BTCINR")]
        tickers = {"BTCINR": Ticker(symbol="BTCINR", last_price=float("-inf"))}
        monitor, _, _, dca_manager = _make_monitor(active_grids=grids, tickers=tickers)
        with caplog.at_level("WARNING"):
            await monitor._run_cycle()
        dca_manager.check_grid_triggers.assert_not_awaited()
        assert any("BTCINR" in r.message and "invalid price" in r.message for r in caplog.records)

    @pytest.mark.asyncio
    async def test_valid_price_still_triggers_normally(self):
        """The fix must not affect any normal, valid price."""
        grids = [_make_grid("grd_1", "BTCINR")]
        tickers = {"BTCINR": Ticker(symbol="BTCINR", last_price=5_100_000.0)}
        monitor, _, _, dca_manager = _make_monitor(active_grids=grids, tickers=tickers)
        await monitor._run_cycle()
        dca_manager.check_grid_triggers.assert_awaited_once_with("grd_1", 5_100_000.0)

    @pytest.mark.asyncio
    async def test_invalid_price_for_one_symbol_does_not_block_other_symbols(self):
        """Only the symbol with the bad reading is skipped — the cycle
        continues normally for every other grid."""
        grids = [
            _make_grid("grd_1", "BTCINR"),
            _make_grid("grd_2", "ETHINR"),
        ]
        tickers = {
            "BTCINR": Ticker(symbol="BTCINR", last_price=0.0),  # invalid
            "ETHINR": Ticker(symbol="ETHINR", last_price=280_000.0),  # valid
        }
        monitor, _, _, dca_manager = _make_monitor(active_grids=grids, tickers=tickers)
        await monitor._run_cycle()
        assert dca_manager.check_grid_triggers.await_count == 1
        dca_manager.check_grid_triggers.assert_awaited_once_with("grd_2", 280_000.0)

    @pytest.mark.asyncio
    async def test_monitoring_loop_continues_after_invalid_price_cycle(self):
        """A cycle containing an invalid price must not raise or otherwise
        prevent a SUBSEQUENT cycle from running normally."""
        grids = [_make_grid("grd_1", "BTCINR")]
        bad_tickers = {"BTCINR": Ticker(symbol="BTCINR", last_price=float("nan"))}
        monitor, exchange, _, dca_manager = _make_monitor(active_grids=grids, tickers=bad_tickers)

        await monitor._run_cycle()  # cycle 1: invalid price, no trigger
        dca_manager.check_grid_triggers.assert_not_awaited()

        # cycle 2: exchange now returns a valid price
        exchange.get_tickers_batch = AsyncMock(
            return_value={"BTCINR": Ticker(symbol="BTCINR", last_price=5_000_000.0)}
        )
        await monitor._run_cycle()
        dca_manager.check_grid_triggers.assert_awaited_once_with("grd_1", 5_000_000.0)

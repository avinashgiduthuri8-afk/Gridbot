"""Automated Market Hours Scheduler & Scanner Daemon for Indian Equities.

Executes 12-stage institutional stock scans strictly between 09:15 and 15:30 IST
on trading days (excluding NSE holidays) and dispatches real-time Telegram alerts.
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from typing import Any

from engine.session.session_manager import IndianSessionManager
from engine.signals.scanner import IndianStockScanner, ScanResult
from services.telegram_notifier import TelegramNotifier
from storage.repositories.signals import SignalRepository
from utils.helpers import now_iso
from utils.logger import get_logger

log = get_logger("scanner")


class ScannerDaemon:
    """Background daemon running automated scans during Indian Market Hours (09:15-15:30 IST)."""

    def __init__(
        self,
        scanner: IndianStockScanner,
        repo: SignalRepository | None = None,
        notifier: TelegramNotifier | None = None,
        interval_seconds: int = 900,         # 15 minutes default
        universe_name: str = "NIFTY_100",
        max_signals: int = 3,
    ) -> None:
        self.scanner = scanner
        self.repo = repo
        self.notifier = notifier or TelegramNotifier()
        self.session_mgr = IndianSessionManager()
        self.interval_seconds = interval_seconds
        self.universe_name = universe_name
        self.max_signals = max_signals

        self._running = False
        self._task: asyncio.Task | None = None
        self.last_scan_result: ScanResult | None = None
        self.last_scan_timestamp: str = ""
        self.total_scans_executed: int = 0

    @property
    def is_running(self) -> bool:
        return self._running

    def start(self) -> None:
        """Starts the background scanning daemon."""
        if self._running:
            return
        self._running = True
        self._task = asyncio.create_task(self._daemon_loop())
        log.info("ScannerDaemon started. Scanning %s every %d seconds.", self.universe_name, self.interval_seconds)

    def stop(self) -> None:
        """Stops the background scanning daemon."""
        if not self._running:
            return
        self._running = False
        if self._task and not self._task.done():
            self._task.cancel()
        log.info("ScannerDaemon stopped.")

    async def _daemon_loop(self) -> None:
        """Main loop checking market hours and triggering scans."""
        while self._running:
            try:
                session_info = self.session_mgr.get_session_info()
                is_market_open = session_info["is_market_open"]

                if is_market_open:
                    log.info("IST Market Open. Executing scheduled scan across %s...", self.universe_name)
                    result = await self.scanner.scan(
                        universe_name=self.universe_name,
                        max_signals=self.max_signals,
                        allow_out_of_session=False,
                    )
                    self.last_scan_result = result
                    self.last_scan_timestamp = now_iso()
                    self.total_scans_executed += 1

                    # Persist and dispatch alerts for high-conviction signals
                    for sig in result.top_signals:
                        if self.repo:
                            await self.repo.save_signal(sig)
                        await self.notifier.send_signal_alert(sig)
                else:
                    log.info("IST Market Closed (%s). Next check in %d seconds.", session_info["session_state"], self.interval_seconds)

            except asyncio.CancelledError:
                break
            except Exception as exc:
                log.error("Error in ScannerDaemon iteration: %s", exc)

            await asyncio.sleep(self.interval_seconds)

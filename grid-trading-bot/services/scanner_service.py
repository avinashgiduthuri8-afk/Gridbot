"""Scanner Service layer bridging the Scanner Engine, SQLite database, and FastAPI REST APIs.

Manages cached scan results, background scan triggers during IST market hours,
signal persistence, and backtesting requests.
"""

from __future__ import annotations

import asyncio
from typing import Any

from config.constants import StockUniverseType
from engine.data.base import MarketDataProvider
from engine.data.yahoo_provider import YahooFinanceProvider
from engine.backtest.evaluator import BacktestReport, ScannerBacktestEvaluator
from engine.regime.regime_detector import MarketRegimeAnalysis
from engine.sectors.sector_analyzer import SectorMatrixAnalysis
from engine.signals.scanner import IndianStockScanner, ScanResult
from engine.signals.scoring import ScoredSignal
from storage.repositories import Repositories
from utils.logger import get_logger

log = get_logger("scanner_service")


class ScannerService:
    """Service layer managing Indian Stock Scanner lifecycle and persistence."""

    def __init__(
        self,
        provider: MarketDataProvider | None = None,
        scanner: IndianStockScanner | None = None,
    ) -> None:
        self.provider = provider or YahooFinanceProvider()
        self.scanner = scanner or IndianStockScanner(provider=self.provider)
        self.backtest_evaluator = ScannerBacktestEvaluator()
        self._latest_result: ScanResult | None = None
        self._lock = asyncio.Lock()

    async def execute_scan(
        self,
        universe: str = "NIFTY_100",
        max_signals: int = 3,
        repos: Repositories | None = None,
    ) -> ScanResult:
        """Executes a fresh scan run and optionally persists top signals."""
        async with self._lock:
            result = await self.scanner.scan(
                universe_name=universe,
                max_signals=max_signals,
                allow_out_of_session=True,
            )
            self._latest_result = result

            # Automatically persist top signals if repos available
            if repos and hasattr(repos, "signals") and result.top_signals:
                for sig in result.top_signals:
                    try:
                        await repos.signals.save_signal(sig)
                    except Exception as exc:
                        log.warning("Could not auto-save signal %s: %s", sig.symbol, exc)

            return result

    def get_latest_scan_result(self) -> ScanResult | None:
        """Returns the in-memory cached scan result."""
        return self._latest_result

    async def get_market_regime(self) -> MarketRegimeAnalysis:
        """Returns live or cached market regime analysis."""
        if self._latest_result:
            return self._latest_result.regime
        return await self.scanner.regime_detector.detect_current_regime(self.provider)

    async def get_sector_matrix(self) -> SectorMatrixAnalysis:
        """Returns live or cached sector strength matrix."""
        if self._latest_result:
            return self._latest_result.sector_matrix
        return await self.scanner.sector_analyzer.fetch_and_analyze(self.provider)

    async def list_persisted_signals(
        self,
        repos: Repositories,
        limit: int = 50,
        status: str | None = None,
        min_score: float | None = None,
    ) -> list[dict[str, Any]]:
        """Queries stored historical signals from the database."""
        if hasattr(repos, "signals"):
            return await repos.signals.list_signals(limit=limit, status=status, min_score=min_score)
        return []

    async def get_performance_stats(self, repos: Repositories) -> dict[str, Any]:
        """Queries aggregate signal performance analytics."""
        if hasattr(repos, "signals"):
            return await repos.signals.get_performance_summary()
        return {}

    async def run_backtest_simulation(
        self,
        universe: str = "NIFTY_50",
        lookback_bars: int = 60,
    ) -> BacktestReport:
        """Runs historical backtest evaluation simulation on candidate stock universe."""
        # 1. Run scanner to generate candidate setups
        scan_res = await self.scanner.scan(universe_name=universe, max_signals=10, allow_out_of_session=True)
        candidates = scan_res.all_scored_signals

        outcomes = []
        for sig in candidates:
            if not sig.is_tradable:
                continue
            # Fetch forward bars for simulation
            candles = await self.provider.get_historical_ohlcv(sig.symbol, "1d", lookback_bars)
            if len(candles) >= 15:
                # Use recent 15 bars as forward test
                forward = candles[-15:]
                out = self.backtest_evaluator.evaluate_signal_forward(sig, forward, max_holding_bars=10)
                outcomes.append(out)

        return self.backtest_evaluator.generate_report(outcomes)

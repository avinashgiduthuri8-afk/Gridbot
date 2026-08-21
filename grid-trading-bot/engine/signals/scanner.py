"""Master 12-Stage Institutional Stock Scanner Orchestrator for Indian Equities.

Coordinates:
Stage 1: Universe Selection (NIFTY 50 / 100 / 200 / 500)
Stage 2: Liquidity & Turnover Filtering
Stage 3: Market Regime Detection (NIFTY/BANKNIFTY/India VIX)
Stage 4: Sector Strength & Momentum Matrix
Stage 5: Multi-Timeframe Data Ingestion (1D, 1H, 15M)
Stage 6: Technical Indicator Engine & Confluence
Stage 7: Setup Pattern Identification (Breakout/Pullback/Continuation/Reversal)
Stage 8: Relative Strength Alpha Calculation
Stage 9: News Sentiment & Corporate Event Filter
Stage 10: Risk/Reward Geometry Calculation (Enforcing R:R >= 2.0)
Stage 11: 100-Point Weighted Scoring & Tier Classification
Stage 12: Ranking & Selection of Top 1–3 High-Conviction Signals
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from config.constants import DEFAULT_MAX_FINAL_SIGNALS, SignalStrength
from engine.data.base import MarketDataProvider, OHLCVCandle
from engine.indicators.technical import TechnicalIndicatorEngine
from engine.mtf.mtf_analyzer import MultiTimeframeAnalyzer
from engine.regime.regime_detector import MarketRegimeAnalysis, MarketRegimeDetector
from engine.relative_strength.rs_calculator import RelativeStrengthCalculator
from engine.risk_reward.rr_calculator import RiskRewardCalculator
from engine.sectors.sector_analyzer import SectorMatrixAnalysis, SectorStrengthAnalyzer
from engine.sentiment.news_evaluator import NewsSentimentEvaluator
from engine.session.session_manager import IndianSessionManager
from engine.signals.scoring import ScoredSignal, SignalScoringEngine
from engine.signals.setups import TechnicalSetupDetector
from engine.universe.universe_filter import LiquidityFilterConfig, StockUniverseFilter
from utils.helpers import now_iso
from utils.logger import get_logger

log = get_logger("scanner_pipeline")


@dataclass
class ScanResult:
    """Consolidated result of a full 12-stage scanner run."""
    timestamp: str
    session_info: dict[str, Any]
    regime: MarketRegimeAnalysis
    sector_matrix: SectorMatrixAnalysis
    total_scanned: int
    total_passed_liquidity: int
    top_signals: list[ScoredSignal] = field(default_factory=list)
    watchlist: list[ScoredSignal] = field(default_factory=list)
    all_scored_signals: list[ScoredSignal] = field(default_factory=list)
    scan_duration_seconds: float = 0.0


class IndianStockScanner:
    """Master institutional scanner for Indian Equities (NSE/BSE)."""

    def __init__(
        self,
        provider: MarketDataProvider,
        liquidity_config: LiquidityFilterConfig | None = None,
        min_rr: float = 2.0,
    ) -> None:
        self.provider = provider
        self.session_mgr = IndianSessionManager()
        self.universe_filter = StockUniverseFilter(liquidity_config)
        self.indicator_engine = TechnicalIndicatorEngine()
        self.mtf_analyzer = MultiTimeframeAnalyzer(self.indicator_engine)
        self.regime_detector = MarketRegimeDetector()
        self.sector_analyzer = SectorStrengthAnalyzer()
        self.rs_calculator = RelativeStrengthCalculator()
        self.sentiment_evaluator = NewsSentimentEvaluator()
        self.setup_detector = TechnicalSetupDetector()
        self.rr_calculator = RiskRewardCalculator(min_rr=min_rr)
        self.scoring_engine = SignalScoringEngine()

    async def scan(
        self,
        universe_name: str = "NIFTY_100",
        max_signals: int = DEFAULT_MAX_FINAL_SIGNALS,
        allow_out_of_session: bool = True,
    ) -> ScanResult:
        """Executes the full 12-stage scanner pipeline."""
        start_time = datetime.now(timezone.utc)
        session_info = self.session_mgr.get_session_info()

        log.info("Starting Indian Stock Scan across %s (out_of_session=%s)...", universe_name, allow_out_of_session)

        # STAGES 3 & 4: Fetch Market Regime & Sector Matrix concurrently
        regime_task = self.regime_detector.detect_current_regime(self.provider)
        sectors_task = self.sector_analyzer.fetch_and_analyze(self.provider)
        nifty_candles_task = self.provider.get_historical_ohlcv("^NSEI", "1d", 30)

        regime, sector_matrix, nifty_candles = await asyncio.gather(
            regime_task, sectors_task, nifty_candles_task
        )

        # STAGE 1: Universe Selection
        candidate_symbols = self.universe_filter.get_candidate_symbols(universe_name)
        total_scanned = len(candidate_symbols)

        # STAGES 2 & 5: Batch Fetch and evaluate candidates
        scored_candidates: list[ScoredSignal] = []
        passed_liquidity_count = 0

        # Concurrency semaphore to avoid rate limits
        semaphore = asyncio.Semaphore(10)

        async def _process_symbol(sym: str) -> ScoredSignal | None:
            nonlocal passed_liquidity_count
            async with semaphore:
                try:
                    # 1. Fetch 1D candles for liquidity & daily trend
                    c_1d = await self.provider.get_historical_ohlcv(sym, "1d", 100)
                    if not c_1d:
                        return None

                    # STAGE 2: Liquidity screening
                    is_liquid, _, _ = self.universe_filter.evaluate_liquidity(sym, c_1d)
                    if not is_liquid:
                        return None

                    passed_liquidity_count += 1

                    # STAGE 5 & 6: Fetch 1H and 15M candles concurrently
                    c_1h_task = self.provider.get_historical_ohlcv(sym, "1h", 60)
                    c_15m_task = self.provider.get_historical_ohlcv(sym, "15m", 50)
                    news_task = self.provider.get_news(sym, 5)

                    c_1h, c_15m, news_items = await asyncio.gather(c_1h_task, c_15m_task, news_task)

                    snap_1d = self.indicator_engine.compute_snapshot(sym, c_1d, "1d")
                    snap_15m = self.indicator_engine.compute_snapshot(sym, c_15m, "15m") if c_15m else None

                    # STAGE 6: Multi-Timeframe Confirmation
                    mtf = self.mtf_analyzer.analyze_confluence(sym, c_1d, c_1h, c_15m)

                    # STAGE 7: Setup Identification
                    setups = self.setup_detector.evaluate_all_setups(snap_1d, snap_15m)
                    if not setups:
                        return None
                    best_setup = setups[0]

                    # STAGE 4: Sector Strength mapping
                    sec_score, sec_name, sec_rank, sec_status = self.sector_analyzer.evaluate_stock_sector(
                        sym, sector_matrix
                    )

                    # STAGE 8: Relative Strength
                    rs_metrics = self.rs_calculator.calculate_alpha(c_1d, nifty_candles)

                    # STAGE 9: News / Sentiment
                    sentiment = self.sentiment_evaluator.evaluate_news(sym, news_items)

                    # STAGE 10: Risk / Reward Plan
                    rr_plan = self.rr_calculator.calculate_plan(
                        sym, snap_1d.last_price, snap_1d, snap_15m, best_setup.setup_type.value
                    )

                    # STAGE 11: 100-Point Weighted Scoring
                    scored = self.scoring_engine.calculate_score(
                        symbol=sym,
                        snap_1d=snap_1d,
                        mtf=mtf,
                        setup=best_setup,
                        regime=regime,
                        sector_score=sec_score,
                        rs_metrics=rs_metrics,
                        sentiment=sentiment,
                        rr_plan=rr_plan,
                        sector_name=sec_name,
                        sector_rank=sec_rank,
                    )
                    scored.timestamp = now_iso()
                    return scored

                except Exception as exc:
                    log.warning("Scanner error processing %s: %s", sym, exc)
                    return None

        # Execute candidate processing in parallel batches
        tasks = [_process_symbol(sym) for sym in candidate_symbols]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        for res in results:
            if isinstance(res, ScoredSignal):
                scored_candidates.append(res)

        # STAGE 11 & 12: Ranking & Filtering
        # Sort by total_score descending
        scored_candidates.sort(key=lambda s: s.total_score, reverse=True)

        top_signals: list[ScoredSignal] = []
        watchlist: list[ScoredSignal] = []

        for sig in scored_candidates:
            if sig.is_tradable and sig.strength in (SignalStrength.VERY_STRONG, SignalStrength.STRONG):
                if len(top_signals) < max_signals:
                    top_signals.append(sig)
                else:
                    watchlist.append(sig)
            elif sig.strength in (SignalStrength.VALID, SignalStrength.WATCHLIST):
                watchlist.append(sig)

        duration = (datetime.now(timezone.utc) - start_time).total_seconds()
        log.info(
            "Scan complete in %.2fs: %d scanned, %d liquid, %d top signals, %d watchlist.",
            duration, total_scanned, passed_liquidity_count, len(top_signals), len(watchlist),
        )

        return ScanResult(
            timestamp=now_iso(),
            session_info=session_info,
            regime=regime,
            sector_matrix=sector_matrix,
            total_scanned=total_scanned,
            total_passed_liquidity=passed_liquidity_count,
            top_signals=top_signals,
            watchlist=watchlist[:15],
            all_scored_signals=scored_candidates,
            scan_duration_seconds=round(duration, 2),
        )

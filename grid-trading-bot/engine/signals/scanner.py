"""Master 12-Stage Institutional Stock Scanner Orchestrator for Indian Equities.

Coordinates:
Stage 1: Universe Selection (NIFTY 50 / 100 / 200 / 500)
Stage 2: Liquidity & Turnover Filtering
Stage 3: Market Regime Detection (NIFTY/BANKNIFTY/India VIX)
Stage 4: Sector Strength & Momentum Matrix
Stage 5: Multi-Timeframe Data Ingestion (1D, 1H, 15M)
Stage 6: Technical Indicator Engine & Confluence
Stage 7: Setup Pattern Identification (VCP / Pocket Pivot / NR7 / High Delivery / Breakout)
Stage 8: Relative Strength Alpha Calculation (vs NIFTY & Sector)
Stage 9: News Sentiment & Corporate Event Risk Filter
Stage 10: Extension & Chasing Filter (ATR distance checks)
Stage 11: Structural Risk/Reward Geometry Calculation (Enforcing R:R >= 2.0)
Stage 12: 100-Point Weighted Scoring, IEI Ranking, Confidence Calibration & Deduplication
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from config.constants import DEFAULT_MAX_FINAL_SIGNALS, SignalStrength
from engine.data.base import MarketDataProvider, OHLCVCandle
from engine.data.stock_info_provider import StockInfoProvider
from engine.indicators.technical import TechnicalIndicatorEngine
from engine.mtf.mtf_analyzer import MultiTimeframeAnalyzer
from engine.regime.regime_detector import MarketRegimeAnalysis, MarketRegimeDetector
from engine.relative_strength.rs_calculator import RelativeStrengthCalculator
from engine.risk_reward.extension_filter import ExtensionFilter
from engine.risk_reward.nse_safety_filter import NSESafetyFilter
from engine.risk_reward.rr_calculator import RiskRewardCalculator
from engine.sectors.sector_analyzer import SectorMatrixAnalysis, SectorStrengthAnalyzer
from engine.sentiment.news_evaluator import NewsSentimentEvaluator
from engine.session.session_manager import IndianSessionManager
from engine.signals.lifecycle import SignalLifecycleManager
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
        stock_info_provider: StockInfoProvider | None = None,
    ) -> None:
        self.provider = provider
        self.stock_info_provider = stock_info_provider or StockInfoProvider()
        self.session_mgr = IndianSessionManager()
        self.universe_filter = StockUniverseFilter(liquidity_config)
        self.indicator_engine = TechnicalIndicatorEngine()
        self.mtf_analyzer = MultiTimeframeAnalyzer(self.indicator_engine)
        self.regime_detector = MarketRegimeDetector()
        self.sector_analyzer = SectorStrengthAnalyzer()
        self.rs_calculator = RelativeStrengthCalculator()
        self.sentiment_evaluator = NewsSentimentEvaluator()
        self.setup_detector = TechnicalSetupDetector()
        self.extension_filter = ExtensionFilter()
        self.safety_filter = NSESafetyFilter()
        self.rr_calculator = RiskRewardCalculator(min_rr=min_rr)
        self.scoring_engine = SignalScoringEngine()
        self.lifecycle_mgr = SignalLifecycleManager()

    async def scan(
        self,
        universe_name: str = "NIFTY_100",
        max_signals: int = DEFAULT_MAX_FINAL_SIGNALS,
        allow_out_of_session: bool = True,
    ) -> ScanResult:
        """Executes the full 12-stage scanner pipeline."""
        start_time = datetime.now(timezone.utc)
        session_info = self.session_mgr.get_session_info()

        # Prune expired signals from active cache
        self.lifecycle_mgr.prune_expired()

        log.info("Starting Indian Stock Scan across %s (out_of_session=%s)...", universe_name, allow_out_of_session)

        # STAGES 3 & 4: Fetch Market Regime & Sector Matrix concurrently
        regime_task = self.regime_detector.detect_current_regime(self.provider)
        sectors_task = self.sector_analyzer.fetch_and_analyze(self.provider)
        nifty_candles_task = self.provider.get_historical_ohlcv("^NSEI", "1d", 50)

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
                    # 1. Fetch 250 daily candles for 200 EMA & Stage-2 trend baseline
                    c_1d = await self.provider.get_historical_ohlcv(sym, "1d", 250)
                    if not c_1d:
                        return None

                    # STAGE 2: Liquidity screening
                    is_liquid, _, _ = self.universe_filter.evaluate_liquidity(sym, c_1d)
                    if not is_liquid:
                        return None

                    passed_liquidity_count += 1

                    # STAGE 5: Fetch 1H, 15M candles, news, and authentic stock info concurrently
                    c_1h_task = self.provider.get_historical_ohlcv(sym, "1h", 60)
                    c_15m_task = self.provider.get_historical_ohlcv(sym, "15m", 50)
                    news_task = self.provider.get_news(sym, 5)
                    stock_info_task = self.stock_info_provider.get_stock_info(sym)

                    c_1h, c_15m, news_items, stock_info = await asyncio.gather(
                        c_1h_task, c_15m_task, news_task, stock_info_task, return_exceptions=False
                    )

                    snap_1d = self.indicator_engine.compute_snapshot(sym, c_1d, "1d")
                    snap_15m = self.indicator_engine.compute_snapshot(sym, c_15m, "15m") if c_15m else None

                    # Authentic delivery percentage (None if unavailable)
                    delivery_pct = stock_info.delivery_pct if (stock_info and stock_info.delivery_pct and stock_info.delivery_pct > 0) else None

                    # STAGE 2.5: Binary Hard Safety & Regulatory Disqualification Gates
                    daily_turnover_cr = ((c_1d[-1].close * c_1d[-1].volume) / 10000000.0) if c_1d and c_1d[-1].volume > 0 else 50.0
                    safety_metrics = self.safety_filter.evaluate_safety(
                        symbol=sym,
                        current_price=snap_1d.last_price,
                        upper_circuit=stock_info.upper_circuit if stock_info else 0.0,
                        lower_circuit=stock_info.lower_circuit if stock_info else 0.0,
                    )
                    hard_gate = self.safety_filter.validate_binary_hard_gates(
                        symbol=sym,
                        current_price=snap_1d.last_price,
                        ema_20=snap_1d.ema_20,
                        ema_50=snap_1d.ema_50,
                        ema_200=snap_1d.ema_200,
                        atr=snap_1d.atr,
                        market_regime=regime.regime.value,
                        india_vix=regime.vix_value,
                        daily_turnover_cr=daily_turnover_cr,
                        safety_metrics=safety_metrics,
                        stock_info=stock_info,
                    )
                    if not hard_gate.passed:
                        log.debug("Symbol %s disqualified by hard gate %s: %s", sym, hard_gate.rejection_category, hard_gate.rejection_reason)
                        return None

                    # STAGE 6: Multi-Timeframe Confirmation
                    mtf = self.mtf_analyzer.analyze_confluence(sym, c_1d, c_1h, c_15m)

                    # STAGE 7: Setup Identification
                    setups = self.setup_detector.evaluate_all_setups(snap_1d, snap_15m, delivery_pct=delivery_pct)
                    if not setups:
                        return None
                    best_setup = setups[0]

                    # STAGE 4: Sector Strength mapping
                    sec_score, sec_name, sec_rank, sec_status = self.sector_analyzer.evaluate_stock_sector(
                        sym, sector_matrix
                    )

                    # STAGE 8: Relative Strength
                    rs_metrics = self.rs_calculator.calculate_alpha(c_1d, nifty_candles, sym)

                    # STAGE 9: News / Sentiment
                    sentiment = self.sentiment_evaluator.evaluate_news(sym, news_items)

                    # STAGE 10: Extension & Binary Hard Gates Filter
                    extension = self.extension_filter.evaluate_extension(sym, snap_1d, best_setup.key_level)

                    # STAGE 11: Risk / Reward Plan
                    rr_plan = self.rr_calculator.calculate_plan(
                        sym, snap_1d.last_price, snap_1d, snap_15m, best_setup.setup_type.value
                    )

                    # STAGE 12: 100-Point Weighted Scoring & Hard Quality Gates
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
                        extension=extension,
                        sector_name=sec_name,
                        sector_rank=sec_rank,
                        delivery_pct=delivery_pct,
                        stock_info=stock_info,
                    )
                    scored.timestamp = now_iso()

                    # Deduplication Check
                    is_dup, dup_reason = self.lifecycle_mgr.check_deduplication(
                        sym, scored.risk_reward.entry_price, scored.total_score
                    )
                    if is_dup:
                        scored.rejection_risks.append(f"Deduplicated: {dup_reason}")

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

        # STAGE 12: Institutional Expectancy Index (IEI) & Quality Gating
        # Sort candidates by (iei_score, total_score) descending
        scored_candidates.sort(key=lambda s: (s.iei_score, s.total_score), reverse=True)

        top_signals: list[ScoredSignal] = []
        watchlist: list[ScoredSignal] = []

        for sig in scored_candidates:
            if sig.is_tradable and sig.strength in (SignalStrength.VERY_STRONG, SignalStrength.STRONG):
                if len(top_signals) < max_signals:
                    top_signals.append(sig)
                    # Register active signal to prevent duplicates on next cycles
                    self.lifecycle_mgr.register_signal(
                        symbol=sig.symbol,
                        signal_id=f"sig_{sig.symbol}_{int(datetime.now(timezone.utc).timestamp())}",
                        entry_price=sig.risk_reward.entry_price,
                        stop_loss=sig.risk_reward.stop_loss,
                        target_1=sig.risk_reward.target_1,
                        score=sig.total_score,
                    )
                else:
                    watchlist.append(sig)
            elif sig.total_score >= 60.0:
                watchlist.append(sig)

        duration = (datetime.now(timezone.utc) - start_time).total_seconds()
        log.info(
            "Scan Complete: %d candidates scanned -> %d passed liquidity -> %d Top Signals -> %d Watchlist in %.2fs",
            total_scanned,
            passed_liquidity_count,
            len(top_signals),
            len(watchlist),
            duration,
        )

        return ScanResult(
            timestamp=now_iso(),
            session_info=session_info,
            regime=regime,
            sector_matrix=sector_matrix,
            total_scanned=total_scanned,
            total_passed_liquidity=passed_liquidity_count,
            top_signals=top_signals,
            watchlist=watchlist,
            all_scored_signals=scored_candidates,
            scan_duration_seconds=round(duration, 2),
        )

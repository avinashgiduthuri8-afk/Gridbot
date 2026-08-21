"""Sector Strength & Momentum Matrix for Indian Equities.

Tracks 11 key NSE sector indices, calculates relative strength vs NIFTY 50,
and assigns sector confirmation points to individual stock candidates.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from config.indian_universe import get_stock_sector
from engine.data.base import MarketDataProvider, SectorQuote
from utils.logger import get_logger

log = get_logger("sector_analyzer")


@dataclass
class SectorMatrixAnalysis:
    """Consolidated sector strength matrix and rankings."""
    sectors: dict[str, SectorQuote] = field(default_factory=dict)
    leading_sectors: list[str] = field(default_factory=list)
    improving_sectors: list[str] = field(default_factory=list)
    lagging_sectors: list[str] = field(default_factory=list)
    timestamp: str = ""


class SectorStrengthAnalyzer:
    """Evaluates relative strength and momentum across NSE industry sectors."""

    def evaluate_sectors(self, sector_quotes: dict[str, SectorQuote]) -> SectorMatrixAnalysis:
        """Processes raw sector quotes into ranked sector matrix."""
        if not sector_quotes:
            return SectorMatrixAnalysis()

        # Sort sectors by relative strength
        sorted_sectors = sorted(
            sector_quotes.values(),
            key=lambda s: s.relative_strength,
            reverse=True,
        )

        leading: list[str] = []
        improving: list[str] = []
        lagging: list[str] = []

        for rank, s in enumerate(sorted_sectors, start=1):
            s.momentum_rank = rank
            if s.relative_strength >= 0.5:
                leading.append(s.sector)
            elif s.relative_strength >= 0.0:
                improving.append(s.sector)
            else:
                lagging.append(s.sector)

        return SectorMatrixAnalysis(
            sectors=sector_quotes,
            leading_sectors=leading,
            improving_sectors=improving,
            lagging_sectors=lagging,
        )

    def evaluate_stock_sector(
        self,
        symbol: str,
        sector_matrix: SectorMatrixAnalysis,
    ) -> tuple[float, str, int, str]:
        """Evaluates sector confirmation for a given stock symbol.
        
        Returns:
            (sector_score: 0-5 pts, sector_name: str, rank: int, status: str)
        """
        sector_name = get_stock_sector(symbol)
        sec_quote = sector_matrix.sectors.get(sector_name)

        if not sec_quote:
            return 2.5, sector_name, 0, "NEUTRAL"

        score = 2.5  # Neutral default
        if sec_quote.status == "LEADING":
            score = 5.0
        elif sec_quote.status == "IMPROVING":
            score = 4.0
        elif sec_quote.status == "WEAKENING":
            score = 2.0
        elif sec_quote.status == "LAGGING":
            score = 1.0

        return score, sector_name, sec_quote.momentum_rank, sec_quote.status

    async def fetch_and_analyze(self, provider: MarketDataProvider) -> SectorMatrixAnalysis:
        """Fetches sector indices from provider and builds matrix."""
        sec_quotes = await provider.get_sector_indices()
        return self.evaluate_sectors(sec_quotes)

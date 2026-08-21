"""Abstract Market Data Provider interface and unified domain data models.

Defines OHLCVCandle, Quote, IndexQuote, SectorQuote, NewsItem, and the
MarketDataProvider ABC allowing pluggable data providers (Yahoo, NSE, Kite, etc.).
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any


@dataclass
class OHLCVCandle:
    timestamp: datetime | str
    open: float
    high: float
    low: float
    close: float
    volume: float
    timeframe: str = "1d"
    vwap: float | None = None

    @property
    def is_bullish(self) -> bool:
        return self.close >= self.open

    @property
    def range(self) -> float:
        return self.high - self.low

    @property
    def body(self) -> float:
        return abs(self.close - self.open)


@dataclass
class Quote:
    symbol: str
    last_price: float
    open: float
    high: float
    low: float
    previous_close: float
    volume: float
    change_pct: float
    timestamp: str = ""


@dataclass
class IndexQuote:
    symbol: str
    name: str
    last_price: float
    change_pct: float
    trend: str = "NEUTRAL"
    rsi: float | None = None
    ema_20: float | None = None
    ema_50: float | None = None


@dataclass
class SectorQuote:
    sector: str
    index_symbol: str
    change_pct_1d: float
    change_pct_5d: float = 0.0
    change_pct_20d: float = 0.0
    relative_strength: float = 0.0  # vs NIFTY 50
    momentum_rank: int = 0
    status: str = "NEUTRAL"  # LEADING, WEAKENING, LAGGING, IMPROVING


@dataclass
class NewsItem:
    symbol: str
    title: str
    published_at: str
    source: str
    sentiment: str = "NEUTRAL"  # POSITIVE, NEGATIVE, NEUTRAL
    impact_score: float = 0.0   # -1.0 to +1.0
    is_earnings_event: bool = False


class MarketDataProvider(ABC):
    """Abstract interface for all Indian market data feeds."""

    @abstractmethod
    async def get_historical_ohlcv(
        self,
        symbol: str,
        timeframe: str = "1d",
        lookback_bars: int = 100,
    ) -> list[OHLCVCandle]:
        """Fetch historical OHLCV candle series for a given symbol and timeframe."""
        ...

    @abstractmethod
    async def get_quote(self, symbol: str) -> Quote:
        """Fetch latest snapshot quote for a single stock."""
        ...

    @abstractmethod
    async def get_market_indices(self) -> dict[str, IndexQuote]:
        """Fetch major market indices (NIFTY 50, BANK NIFTY, INDIA VIX)."""
        ...

    @abstractmethod
    async def get_sector_indices(self) -> dict[str, SectorQuote]:
        """Fetch sector indices and compute relative sector strength."""
        ...

    async def get_quotes_batch(self, symbols: list[str]) -> dict[str, Quote]:
        """Batch fetch quotes across multiple symbols."""
        results: dict[str, Quote] = {}
        for sym in symbols:
            try:
                results[sym] = await self.get_quote(sym)
            except Exception:
                pass
        return results

    async def get_news(self, symbol: str, limit: int = 5) -> list[NewsItem]:
        """Fetch latest corporate/market news for a symbol."""
        return []

    async def close(self) -> None:
        """Clean up network sessions or connections."""
        pass

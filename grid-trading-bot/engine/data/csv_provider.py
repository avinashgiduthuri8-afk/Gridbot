"""Offline / CSV / In-Memory Market Data Provider for backtesting and testing.

Allows deterministic feeding of OHLCV candles, quotes, and market regimes
without requiring active internet connections.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from engine.data.base import IndexQuote, MarketDataProvider, NewsItem, OHLCVCandle, Quote, SectorQuote


class CsvReplayProvider(MarketDataProvider):
    """Offline and mock market data provider for backtesting and deterministic unit tests."""

    def __init__(self) -> None:
        self._ohlcv_store: dict[tuple[str, str], list[OHLCVCandle]] = {}
        self._quote_store: dict[str, Quote] = {}
        self._index_store: dict[str, IndexQuote] = {}
        self._sector_store: dict[str, SectorQuote] = {}
        self._news_store: dict[str, list[NewsItem]] = {}

    def set_candles(self, symbol: str, timeframe: str, candles: list[OHLCVCandle]) -> None:
        self._ohlcv_store[(symbol.upper(), timeframe.lower())] = candles

    def set_quote(self, symbol: str, quote: Quote) -> None:
        self._quote_store[symbol.upper()] = quote

    def set_indices(self, indices: dict[str, IndexQuote]) -> None:
        self._index_store = indices

    def set_sectors(self, sectors: dict[str, SectorQuote]) -> None:
        self._sector_store = sectors

    def set_news(self, symbol: str, news: list[NewsItem]) -> None:
        self._news_store[symbol.upper()] = news

    def load_synthetic_bullish_candles(
        self,
        symbol: str,
        start_price: float = 1000.0,
        num_bars: int = 100,
        timeframe: str = "1d",
        trend_factor: float = 1.002,
    ) -> list[OHLCVCandle]:
        """Generates realistic synthetic upward trending candles for testing."""
        candles: list[OHLCVCandle] = []
        p = start_price
        for i in range(num_bars):
            o = p
            c = p * trend_factor
            h = max(o, c) * 1.005
            l = min(o, c) * 0.995
            v = 1_000_000.0 + (i * 10_000.0)
            candles.append(
                OHLCVCandle(
                    timestamp=datetime.now(timezone.utc),
                    open=round(o, 2),
                    high=round(h, 2),
                    low=round(l, 2),
                    close=round(c, 2),
                    volume=v,
                    timeframe=timeframe,
                )
            )
            p = c
        self.set_candles(symbol, timeframe, candles)
        return candles

    async def get_historical_ohlcv(
        self,
        symbol: str,
        timeframe: str = "1d",
        lookback_bars: int = 100,
    ) -> list[OHLCVCandle]:
        key = (symbol.upper(), timeframe.lower())
        candles = self._ohlcv_store.get(key, [])
        return candles[-lookback_bars:]

    async def get_quote(self, symbol: str) -> Quote:
        sym = symbol.upper()
        if sym in self._quote_store:
            return self._quote_store[sym]
        candles = await self.get_historical_ohlcv(symbol, timeframe="1d", lookback_bars=2)
        if candles:
            latest = candles[-1]
            prev = candles[-2] if len(candles) >= 2 else latest
            chg = ((latest.close - prev.close) / prev.close * 100.0) if prev.close > 0 else 0.0
            return Quote(
                symbol=symbol,
                last_price=latest.close,
                open=latest.open,
                high=latest.high,
                low=latest.low,
                previous_close=prev.close,
                volume=latest.volume,
                change_pct=chg,
            )
        return Quote(
            symbol=symbol,
            last_price=1000.0,
            open=1000.0,
            high=1010.0,
            low=995.0,
            previous_close=1000.0,
            volume=500000.0,
            change_pct=0.0,
        )

    async def get_market_indices(self) -> dict[str, IndexQuote]:
        if self._index_store:
            return self._index_store
        return {
            "NIFTY_50": IndexQuote(symbol="NIFTY 50", name="Nifty 50", last_price=24500.0, change_pct=0.75, trend="BULLISH"),
            "NIFTY_BANK": IndexQuote(symbol="NIFTY BANK", name="Nifty Bank", last_price=52000.0, change_pct=0.90, trend="BULLISH"),
            "INDIA_VIX": IndexQuote(symbol="INDIA VIX", name="India VIX", last_price=13.8, change_pct=-2.5, trend="NEUTRAL"),
        }

    async def get_sector_indices(self) -> dict[str, SectorQuote]:
        if self._sector_store:
            return self._sector_store
        return {
            "IT": SectorQuote(sector="IT", index_symbol="^CNXIT", change_pct_1d=1.5, relative_strength=0.75, momentum_rank=1, status="LEADING"),
            "Banking": SectorQuote(sector="Banking", index_symbol="^NSEBANK", change_pct_1d=0.9, relative_strength=0.15, momentum_rank=2, status="IMPROVING"),
            "Auto": SectorQuote(sector="Auto", index_symbol="^CNXAUTO", change_pct_1d=0.6, relative_strength=-0.15, momentum_rank=3, status="NEUTRAL"),
        }

    async def get_news(self, symbol: str, limit: int = 5) -> list[NewsItem]:
        return self._news_store.get(symbol.upper(), [])

"""Yahoo Finance Market Data Provider for Indian Equities (NSE).

Fetches historical and intraday OHLCV candles, real-time quotes, market benchmarks
(^NSEI, ^NSEBANK, ^INDIAVIX), and sector indices using httpx with in-memory TTL caching.
"""

from __future__ import annotations

import asyncio
import time
from datetime import datetime, timezone
from typing import Any

import httpx

from config.indian_universe import INDEX_TICKERS, get_stock_sector
from engine.data.base import IndexQuote, MarketDataProvider, NewsItem, OHLCVCandle, Quote, SectorQuote
from utils.logger import get_logger

log = get_logger("yahoo_provider")


class YahooFinanceProvider(MarketDataProvider):
    """Asynchronous Yahoo Finance adapter for Indian Equities (NSE/BSE)."""

    BASE_URL = "https://query1.finance.yahoo.com/v8/finance/chart"

    def __init__(self, cache_ttl_seconds: int = 60, request_timeout: float = 12.0) -> None:
        self._cache_ttl = cache_ttl_seconds
        self._timeout = request_timeout
        self._cache: dict[str, tuple[float, Any]] = {}
        self._client: httpx.AsyncClient | None = None
        self._headers = {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
            ),
            "Accept": "application/json",
        }

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(
                timeout=httpx.Timeout(self._timeout),
                headers=self._headers,
                follow_redirects=True,
            )
        return self._client

    def _normalize_ticker(self, symbol: str) -> str:
        s = symbol.strip().upper()
        if s.startswith("^") or s.endswith(".NS") or s.endswith(".BO"):
            return s
        return f"{s}.NS"

    def _map_timeframe(self, tf: str) -> tuple[str, str]:
        """Maps standard timeframe string to Yahoo interval and range."""
        t = tf.lower()
        if t in ("15m", "15min"):
            return "15m", "1mo"
        if t in ("5m", "5min"):
            return "5m", "5d"
        if t in ("30m", "30min"):
            return "30m", "1mo"
        if t in ("1h", "60m"):
            return "60m", "3mo"
        if t in ("4h", "240m"):
            return "60m", "6mo"
        if t in ("1w", "1week"):
            return "1wk", "2y"
        return "1d", "1y"

    async def get_historical_ohlcv(
        self,
        symbol: str,
        timeframe: str = "1d",
        lookback_bars: int = 100,
    ) -> list[OHLCVCandle]:
        ticker = self._normalize_ticker(symbol)
        interval, range_param = self._map_timeframe(timeframe)
        cache_key = f"ohlcv_{ticker}_{interval}_{range_param}"

        now = time.time()
        if cache_key in self._cache:
            ts, data = self._cache[cache_key]
            if now - ts < self._cache_ttl:
                return data[-lookback_bars:]

        client = await self._get_client()
        url = f"{self.BASE_URL}/{ticker}?interval={interval}&range={range_param}&includePrePost=false"

        try:
            resp = await client.get(url)
            if resp.status_code != 200:
                log.warning("Yahoo Finance returned status %d for %s", resp.status_code, ticker)
                return []

            json_data = resp.json()
            result = json_data.get("chart", {}).get("result")
            if not result:
                return []

            res = result[0]
            timestamps = res.get("timestamp", [])
            indicators = res.get("indicators", {}).get("quote", [{}])[0]

            opens = indicators.get("open", [])
            highs = indicators.get("high", [])
            lows = indicators.get("low", [])
            closes = indicators.get("close", [])
            volumes = indicators.get("volume", [])

            candles: list[OHLCVCandle] = []
            for i, ts_val in enumerate(timestamps):
                if i >= len(opens) or i >= len(highs) or i >= len(lows) or i >= len(closes):
                    break
                o, h, l, c = opens[i], highs[i], lows[i], closes[i]
                v = volumes[i] if i < len(volumes) and volumes[i] is not None else 0.0

                if None in (o, h, l, c):
                    continue

                dt = datetime.fromtimestamp(ts_val, tz=timezone.utc)
                candles.append(
                    OHLCVCandle(
                        timestamp=dt,
                        open=float(o),
                        high=float(h),
                        low=float(l),
                        close=float(c),
                        volume=float(v),
                        timeframe=timeframe,
                    )
                )

            self._cache[cache_key] = (now, candles)
            return candles[-lookback_bars:]
        except Exception as exc:
            log.warning("Failed to fetch OHLCV for %s: %s", ticker, exc)
            return []

    async def get_quote(self, symbol: str) -> Quote:
        ticker = self._normalize_ticker(symbol)
        candles = await self.get_historical_ohlcv(symbol, timeframe="1d", lookback_bars=2)
        if not candles:
            return Quote(
                symbol=symbol,
                last_price=0.0,
                open=0.0,
                high=0.0,
                low=0.0,
                previous_close=0.0,
                volume=0.0,
                change_pct=0.0,
            )

        latest = candles[-1]
        prev_close = candles[-2].close if len(candles) >= 2 else latest.open
        change_pct = ((latest.close - prev_close) / prev_close * 100.0) if prev_close > 0 else 0.0

        return Quote(
            symbol=symbol,
            last_price=latest.close,
            open=latest.open,
            high=latest.high,
            low=latest.low,
            previous_close=prev_close,
            volume=latest.volume,
            change_pct=change_pct,
            timestamp=latest.timestamp.isoformat() if isinstance(latest.timestamp, datetime) else str(latest.timestamp),
        )

    async def get_market_indices(self) -> dict[str, IndexQuote]:
        benchmarks = {
            "NIFTY_50": "^NSEI",
            "NIFTY_BANK": "^NSEBANK",
            "INDIA_VIX": "^INDIAVIX",
        }
        results: dict[str, IndexQuote] = {}

        for key, ticker in benchmarks.items():
            try:
                candles = await self.get_historical_ohlcv(ticker, timeframe="1d", lookback_bars=50)
                if not candles:
                    continue
                latest = candles[-1]
                prev = candles[-2] if len(candles) >= 2 else latest
                chg = ((latest.close - prev.close) / prev.close * 100.0) if prev.close > 0 else 0.0

                # Basic trend check via short-term EMAs if sufficient bars
                trend = "BULLISH" if latest.close > prev.close else "BEARISH"
                if len(candles) >= 20:
                    c_closes = [c.close for c in candles]
                    ema_20 = sum(c_closes[-20:]) / 20.0  # Simple approx
                    trend = "BULLISH" if latest.close >= ema_20 else "BEARISH"
                else:
                    ema_20 = None

                results[key] = IndexQuote(
                    symbol=INDEX_TICKERS[key]["symbol"],
                    name=INDEX_TICKERS[key]["name"],
                    last_price=latest.close,
                    change_pct=chg,
                    trend=trend,
                    ema_20=ema_20,
                )
            except Exception as exc:
                log.warning("Could not fetch market index %s: %s", key, exc)

        return results

    async def get_sector_indices(self) -> dict[str, SectorQuote]:
        sectors = {
            "IT": "^CNXIT",
            "Auto": "^CNXAUTO",
            "Pharma": "^CNXPHARMA",
            "FMCG": "^CNXFMCG",
            "Metals": "^CNXMETAL",
            "Energy": "^CNXENERGY",
            "Realty": "^CNXREALTY",
            "Infrastructure": "^CNXINFRA",
            "PSE": "^CNXPSE",
            "Banking": "^NSEBANK",
        }

        # First get NIFTY 50 1d change for relative strength baseline
        nifty_quotes = await self.get_market_indices()
        nifty_1d_change = nifty_quotes.get("NIFTY_50").change_pct if "NIFTY_50" in nifty_quotes else 0.0

        sector_results: dict[str, SectorQuote] = {}
        for sector_name, ticker in sectors.items():
            try:
                candles = await self.get_historical_ohlcv(ticker, timeframe="1d", lookback_bars=25)
                if not candles:
                    continue
                latest = candles[-1]
                prev_1d = candles[-2] if len(candles) >= 2 else latest
                prev_5d = candles[-5] if len(candles) >= 5 else latest
                prev_20d = candles[-20] if len(candles) >= 20 else latest

                chg_1d = ((latest.close - prev_1d.close) / prev_1d.close * 100.0) if prev_1d.close > 0 else 0.0
                chg_5d = ((latest.close - prev_5d.close) / prev_5d.close * 100.0) if prev_5d.close > 0 else 0.0
                chg_20d = ((latest.close - prev_20d.close) / prev_20d.close * 100.0) if prev_20d.close > 0 else 0.0

                rel_strength = chg_1d - nifty_1d_change
                if rel_strength > 1.0:
                    status = "LEADING"
                elif rel_strength > 0.0:
                    status = "IMPROVING"
                elif rel_strength > -1.0:
                    status = "WEAKENING"
                else:
                    status = "LAGGING"

                sector_results[sector_name] = SectorQuote(
                    sector=sector_name,
                    index_symbol=ticker,
                    change_pct_1d=chg_1d,
                    change_pct_5d=chg_5d,
                    change_pct_20d=chg_20d,
                    relative_strength=rel_strength,
                    status=status,
                )
            except Exception as exc:
                log.warning("Could not fetch sector %s: %s", sector_name, exc)

        # Compute momentum ranks
        sorted_sectors = sorted(sector_results.values(), key=lambda s: s.relative_strength, reverse=True)
        for rank, s in enumerate(sorted_sectors, start=1):
            s.momentum_rank = rank

        return sector_results

    async def get_news(self, symbol: str, limit: int = 5) -> list[NewsItem]:
        # Basic news provider hook - can be extended with RSS feeds or Google News
        return []

    async def close(self) -> None:
        if self._client and not self._client.is_closed:
            await self._client.aclose()

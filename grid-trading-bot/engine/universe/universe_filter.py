"""Stock Universe and Liquidity Screening Engine for Indian Equities.

Applies configurable liquidity, traded value, price threshold, and data availability
filters to ensure only highly tradeable NSE equities enter the scanning pipeline.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from config.indian_universe import get_universe_stocks
from engine.data.base import MarketDataProvider, OHLCVCandle, Quote
from utils.logger import get_logger

log = get_logger("universe_filter")


@dataclass
class LiquidityFilterConfig:
    min_price: float = 50.0                  # Avoid micro-penny stocks
    max_price: float = 100000.0              # Upper limit guard
    min_avg_volume_20d: float = 200_000.0    # 20-day average daily volume
    min_avg_traded_value_inr: float = 10_000_000.0  # ₹1 Crore average daily turnover
    min_bars_required: int = 30              # Minimum required historical bars


class StockUniverseFilter:
    """Screens universe symbols against strict tradability & liquidity criteria."""

    def __init__(self, config: LiquidityFilterConfig | None = None) -> None:
        self.config = config or LiquidityFilterConfig()

    def get_candidate_symbols(self, universe_name: str = "NIFTY_100") -> list[str]:
        """Returns list of stock symbols for the selected universe."""
        stocks = get_universe_stocks(universe_name)
        return list(stocks.keys())

    def evaluate_liquidity(
        self,
        symbol: str,
        candles_1d: list[OHLCVCandle],
        quote: Quote | None = None,
    ) -> tuple[bool, str, dict[str, Any]]:
        """Evaluates whether a stock meets all liquidity and price constraints.
        
        Returns:
            (is_liquid: bool, reason: str, metrics: dict)
        """
        if len(candles_1d) < self.config.min_bars_required:
            return False, f"Insufficient historical bars ({len(candles_1d)} < {self.config.min_bars_required})", {}

        latest_price = quote.last_price if quote and quote.last_price > 0 else candles_1d[-1].close

        # 1. Price Threshold Filter
        if latest_price < self.config.min_price:
            return False, f"Price ₹{latest_price:.2f} is below minimum threshold ₹{self.config.min_price:.2f}", {}
        if latest_price > self.config.max_price:
            return False, f"Price ₹{latest_price:.2f} exceeds maximum threshold ₹{self.config.max_price:.2f}", {}

        # 2. 20-Day Average Volume Filter
        recent_20 = candles_1d[-20:]
        volumes = [c.volume for c in recent_20]
        avg_volume_20d = sum(volumes) / len(volumes) if volumes else 0.0

        if avg_volume_20d < self.config.min_avg_volume_20d:
            return (
                False,
                f"Avg 20d volume {avg_volume_20d:,.0f} < required {self.config.min_avg_volume_20d:,.0f}",
                {"avg_volume": avg_volume_20d, "latest_price": latest_price},
            )

        # 3. 20-Day Average Traded Value (Turnover in INR)
        daily_turnovers = [c.close * c.volume for c in recent_20]
        avg_turnover = sum(daily_turnovers) / len(daily_turnovers) if daily_turnovers else 0.0

        if avg_turnover < self.config.min_avg_traded_value_inr:
            return (
                False,
                f"Avg daily turnover ₹{avg_turnover/1e7:.2f} Cr < required ₹{self.config.min_avg_traded_value_inr/1e7:.2f} Cr",
                {"avg_volume": avg_volume_20d, "avg_turnover": avg_turnover, "latest_price": latest_price},
            )

        return (
            True,
            "Liquidity checks passed",
            {
                "avg_volume_20d": avg_volume_20d,
                "avg_turnover_inr": avg_turnover,
                "latest_price": latest_price,
            },
        )

    async def filter_universe(
        self,
        provider: MarketDataProvider,
        universe_name: str = "NIFTY_100",
    ) -> list[str]:
        """Runs batch liquidity evaluation across the selected universe."""
        symbols = self.get_candidate_symbols(universe_name)
        qualified_symbols: list[str] = []

        for sym in symbols:
            try:
                candles = await provider.get_historical_ohlcv(sym, timeframe="1d", lookback_bars=40)
                is_valid, reason, _ = self.evaluate_liquidity(sym, candles)
                if is_valid:
                    qualified_symbols.append(sym)
                else:
                    log.debug("Symbol %s filtered out: %s", sym, reason)
            except Exception as exc:
                log.warning("Liquidity check failed for %s: %s", sym, exc)

        return qualified_symbols

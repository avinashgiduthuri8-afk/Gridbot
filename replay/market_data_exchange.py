"""ExchangeClient implementation backed by a replay price feed.

This is the "market data" half of the exchange simulator: it answers
get_ticker()/get_market_info() from whatever candle the ReplayEngine is
currently on, instead of a live HTTP call. It does NOT implement order
simulation itself — production code and tests wrap it in
exchange.paper_exchange.PaperExchangeClient (see fee_exchange.py) for that,
reusing the exact same order-fill/slippage/latency/partial-fill simulation
already used by real paper trading. This is what lets the trading engine
run completely unaware it's in replay mode.
"""
from __future__ import annotations

from exchange.base import (
    Balance, ExchangeClient, ExchangeOrder, MarketInfo, Ticker, Trade,
)
from exchange.exceptions import ExchangeError


class ReplaySymbolNotSeeded(ExchangeError):
    """Raised when a symbol's market info was never registered before use."""


class ReplayMarketDataExchange(ExchangeClient):
    """Minimal ExchangeClient whose prices come from set_price() calls
    driven by the ReplayEngine, and whose per-symbol precision/minimum
    rules come from a caller-supplied table (register_market)."""

    def __init__(self) -> None:
        self._prices: dict[str, float] = {}
        self._market_info: dict[str, MarketInfo] = {}
        self._balance_inr: float = 1_000_000_000.0  # effectively unlimited for replay

    # ------------------------------------------------------------------
    # Replay-driving API — not part of ExchangeClient
    # ------------------------------------------------------------------

    def register_market(self, symbol: str, market_info: MarketInfo) -> None:
        self._market_info[symbol.upper()] = market_info

    def set_price(self, symbol: str, price: float) -> None:
        self._prices[symbol.upper()] = price

    def current_price(self, symbol: str) -> float | None:
        return self._prices.get(symbol.upper())

    # ------------------------------------------------------------------
    # ExchangeClient interface
    # ------------------------------------------------------------------

    async def get_ticker(self, symbol: str) -> Ticker:
        price = self._prices.get(symbol.upper())
        if price is None:
            raise ReplaySymbolNotSeeded(
                f"No replay price set yet for {symbol} — the feed hasn't reached it."
            )
        return Ticker(symbol=symbol, last_price=price)

    async def get_balances(self) -> list[Balance]:
        return [Balance(currency="INR", balance=self._balance_inr, locked_balance=0.0)]

    async def get_balance(self, currency: str) -> Balance:
        if currency.upper() == "INR":
            return Balance(currency="INR", balance=self._balance_inr, locked_balance=0.0)
        return Balance(currency=currency.upper(), balance=0.0, locked_balance=0.0)

    async def get_market_info(self, symbol: str) -> MarketInfo:
        info = self._market_info.get(symbol.upper())
        if info is None:
            raise ReplaySymbolNotSeeded(
                f"No market_info registered for {symbol} — call register_market() first."
            )
        return info

    # Order operations are intentionally not implemented here — the
    # trading engine always talks to a PaperExchangeClient/fee-simulating
    # wrapper (see fee_exchange.py) that wraps this instance for market
    # data and handles all order simulation itself.

    async def place_order(self, symbol, side, price, quantity, order_type="market_order",
                           client_order_id=None) -> ExchangeOrder:
        raise NotImplementedError(
            "ReplayMarketDataExchange never places orders directly — wrap it in "
            "PaperExchangeClient (see replay/fee_exchange.py)."
        )

    async def cancel_order(self, exchange_order_id: str) -> bool:
        raise NotImplementedError("See place_order note above.")

    async def get_order_status(self, exchange_order_id: str) -> ExchangeOrder:
        raise NotImplementedError("See place_order note above.")

    async def get_open_orders(self, symbol: str | None = None) -> list[ExchangeOrder]:
        return []

    async def get_trade_history(
        self, symbol: str | None = None, limit: int = 50, order_id: str | None = None,
    ) -> list[Trade]:
        return []

    async def close(self) -> None:
        pass

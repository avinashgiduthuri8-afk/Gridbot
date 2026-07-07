"""Abstract exchange interface and shared data structures.

Any exchange integration (CoinDCX today, others later) implements
ExchangeClient so the trading engine never depends on a specific wire format.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field

from config.constants import OrderSide


@dataclass
class Balance:
    currency: str
    balance: float
    locked_balance: float


@dataclass
class Ticker:
    symbol: str
    last_price: float


@dataclass
class MarketInfo:
    """Precision and minimum-size rules for a single trading pair."""
    symbol: str
    base_currency_precision: int
    quote_currency_precision: int
    min_quantity: float
    min_amount: float
    step_size: float = field(init=False)

    def __post_init__(self) -> None:
        self.step_size = 10 ** (-self.base_currency_precision)


@dataclass
class ExchangeOrder:
    exchange_order_id: str
    symbol: str
    side: str
    price: float
    quantity: float
    filled_quantity: float
    filled_price: float
    status: str
    raw_status: str


@dataclass
class Trade:
    exchange_order_id: str
    symbol: str
    side: str
    price: float
    quantity: float
    fee: float
    executed_at: str


class ExchangeClient(ABC):
    """Reusable interface every exchange integration must implement."""

    @abstractmethod
    async def get_ticker(self, symbol: str) -> Ticker: ...

    async def get_tickers_batch(self, symbols: set[str]) -> dict[str, Ticker]:
        """Fetch prices for multiple symbols in as few API calls as possible.

        Default implementation calls get_ticker individually — subclasses
        should override with a true batch request where the exchange supports it.
        Returns a dict mapping each successfully fetched symbol to its Ticker.
        Missing or failed symbols are simply absent from the result.
        """
        result: dict[str, Ticker] = {}
        for sym in symbols:
            try:
                result[sym] = await self.get_ticker(sym)
            except Exception:  # noqa: BLE001
                pass
        return result

    @abstractmethod
    async def get_balances(self) -> list[Balance]: ...

    @abstractmethod
    async def get_balance(self, currency: str) -> Balance: ...

    @abstractmethod
    async def get_market_info(self, symbol: str) -> MarketInfo: ...

    @abstractmethod
    async def place_order(
        self,
        symbol: str,
        side: OrderSide,
        price: float,
        quantity: float,
        order_type: str = "limit_order",
    ) -> ExchangeOrder: ...

    @abstractmethod
    async def cancel_order(self, exchange_order_id: str) -> bool: ...

    @abstractmethod
    async def get_order_status(self, exchange_order_id: str) -> ExchangeOrder: ...

    @abstractmethod
    async def get_open_orders(self, symbol: str | None = None) -> list[ExchangeOrder]: ...

    @abstractmethod
    async def get_trade_history(self, symbol: str | None = None, limit: int = 50) -> list[Trade]: ...

    @abstractmethod
    async def close(self) -> None: ...

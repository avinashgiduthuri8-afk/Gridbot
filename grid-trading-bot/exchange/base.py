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
class ExtendedTicker:
    """Full 24-hour market snapshot returned by a single ticker call."""

    symbol: str
    last_price: float
    change_24h: float       # percentage, e.g. -0.59 means −0.59 %
    high_24h: float
    low_24h: float
    volume_24h: float       # volume in base currency
    bid: float = 0.0
    ask: float = 0.0
    timestamp: int = 0      # unix ms

    def to_ticker(self) -> Ticker:
        return Ticker(symbol=self.symbol, last_price=self.last_price)


@dataclass
class MarketInfo:
    """Precision and minimum-size rules for a single trading pair."""

    symbol: str
    base_currency_precision: int
    quote_currency_precision: int
    min_quantity: float
    min_amount: float
    # Optional fields — populated when the exchange provides them
    status: str = "active"
    base_currency_short_name: str = ""
    target_currency_short_name: str = ""
    # Derived in __post_init__ — not part of __init__
    step_size: float = field(init=False)

    def __post_init__(self) -> None:
        self.step_size = 10 ** (-self.base_currency_precision)

    @property
    def is_active(self) -> bool:
        return self.status.lower() == "active"


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

    async def get_extended_ticker(self, symbol: str) -> ExtendedTicker:
        """Fetch a full 24-hour market snapshot for *symbol*.

        Default implementation delegates to get_ticker and fills 24-hour fields
        with zeros.  Subclasses should override to return real 24h data.
        """
        ticker = await self.get_ticker(symbol)
        return ExtendedTicker(
            symbol=symbol,
            last_price=ticker.last_price,
            change_24h=0.0,
            high_24h=0.0,
            low_24h=0.0,
            volume_24h=0.0,
        )

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

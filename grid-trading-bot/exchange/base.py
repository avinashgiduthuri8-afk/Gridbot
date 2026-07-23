"""Abstract exchange interface and shared data structures.

Any exchange integration (CoinDCX today, others later) implements
ExchangeClient so the trading engine never depends on a specific wire format.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass

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
    """Precision and minimum-size rules for a single trading pair.

    Field names mirror CoinDCX's own terminology, which is easy to
    misread because it is the reverse of the usual "base/quote" convention:

    - ``base_currency`` is the *pricing* asset of the pair (e.g. INR, BTC, USDT).
      ``base_currency_precision`` is how many decimals *prices* are quoted in.
    - ``target_currency`` is the asset actually being bought/sold (the coin).
      ``target_currency_precision`` is how many decimals *quantities* are
      allowed to have, and is what the quantity step size must be derived
      from — never from ``base_currency_precision``.

    ``step_size`` and ``min_amount`` are two independent exchange constraints
    on two different quantities (the target-currency quantity increment, and
    the minimum base-currency notional value of an order, i.e. CoinDCX's
    ``min_notional``). They must each come straight from the exchange's own
    market-details response for this exact symbol — never assumed, never
    derived from each other, and never copied from another market's rules.
    """

    symbol: str
    base_currency_precision: int      # decimals for PRICE formatting/rounding
    target_currency_precision: int    # decimals for QUANTITY formatting; step_size fallback
    min_quantity: float                # minimum tradeable quantity, in target currency units
    min_amount: float                  # minimum order notional, in base currency units (CoinDCX "min_notional")
    # Authoritative quantity increment reported by the exchange (CoinDCX "step").
    # Only falls back to a value derived from target_currency_precision if the
    # exchange genuinely did not supply one — it is NEVER derived from
    # base_currency_precision, which governs price precision, not quantity.
    step_size: float | None = None
    # Optional fields — populated when the exchange provides them
    status: str = "active"
    base_currency_short_name: str = ""
    target_currency_short_name: str = ""

    def __post_init__(self) -> None:
        if self.step_size is None or self.step_size <= 0:
            self.step_size = 10 ** (-self.target_currency_precision)

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
    fee: float = 0.0
    client_order_id: str = ""


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
        client_order_id: str | None = None,
    ) -> ExchangeOrder: ...

    async def get_order_by_client_order_id(self, client_order_id: str) -> ExchangeOrder | None:
        """Find an order by its immutable client id without fuzzy matching."""
        for order in await self.get_open_orders():
            if order.client_order_id == client_order_id:
                return order
        return None

    @abstractmethod
    async def cancel_order(self, exchange_order_id: str) -> bool: ...

    @abstractmethod
    async def get_order_status(self, exchange_order_id: str) -> ExchangeOrder: ...

    @abstractmethod
    async def get_open_orders(self, symbol: str | None = None) -> list[ExchangeOrder]: ...

    @abstractmethod
    async def get_trade_history(
        self,
        symbol: str | None = None,
        limit: int = 50,
        order_id: str | None = None,
    ) -> list[Trade]: ...

    @abstractmethod
    async def close(self) -> None: ...

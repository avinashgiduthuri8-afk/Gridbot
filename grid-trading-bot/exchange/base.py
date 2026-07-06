"""Abstract exchange interface. Any exchange (CoinDCX today, others later)
implements this contract so the trading engine never depends on a
specific exchange's wire format.
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
class ExchangeOrder:
    exchange_order_id: str
    symbol: str
    side: str
    price: float
    quantity: float
    filled_quantity: float
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

    @abstractmethod
    async def get_balances(self) -> list[Balance]:
        ...

    @abstractmethod
    async def get_balance(self, currency: str) -> Balance: ...

    @abstractmethod
    async def place_order(
        self, symbol: str, side: OrderSide, price: float, quantity: float
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

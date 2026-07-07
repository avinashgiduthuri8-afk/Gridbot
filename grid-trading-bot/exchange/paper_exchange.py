"""Paper (simulated) exchange client.

Wraps a real ExchangeClient for all market-data reads (get_ticker,
get_market_info) and simulates order placement without touching the real
exchange.  Paper orders are returned with status="open" so the normal
OrderMonitor polling loop picks them up and transitions them to "filled"
on the next poll — exactly mirroring the real order flow.
"""

from __future__ import annotations

from config.constants import OrderStatus
from exchange.base import Balance, ExchangeClient, ExchangeOrder, ExtendedTicker, MarketInfo, Ticker, Trade
from config.constants import OrderSide
from utils.logger import get_logger

log = get_logger("exchange")

PAPER_INITIAL_BALANCE = 100_000.0


class PaperExchangeClient(ExchangeClient):
    """Simulates exchange order operations; delegates market data to the real exchange."""

    def __init__(self, real_exchange: ExchangeClient) -> None:
        self._real = real_exchange
        self._paper_orders: dict[str, ExchangeOrder] = {}
        self._counter: int = 0

    # ------------------------------------------------------------------
    # Market data — always from the real exchange
    # ------------------------------------------------------------------

    async def get_ticker(self, symbol: str) -> Ticker:
        return await self._real.get_ticker(symbol)

    async def get_tickers_batch(self, symbols: set[str]) -> dict[str, Ticker]:
        """Delegate batch fetch to the real exchange — prices are always live."""
        return await self._real.get_tickers_batch(symbols)

    async def get_market_info(self, symbol: str) -> MarketInfo:
        return await self._real.get_market_info(symbol)

    async def get_extended_ticker(self, symbol: str) -> "ExtendedTicker":
        """Delegate extended ticker to the real exchange — prices are always live."""
        return await self._real.get_extended_ticker(symbol)

    async def get_balances(self) -> list[Balance]:
        return [Balance(currency="INR", balance=PAPER_INITIAL_BALANCE, locked_balance=0.0)]

    async def get_balance(self, currency: str) -> Balance:
        if currency.upper() == "INR":
            return Balance(currency="INR", balance=PAPER_INITIAL_BALANCE, locked_balance=0.0)
        return Balance(currency=currency.upper(), balance=0.0, locked_balance=0.0)

    async def get_open_orders(self, symbol: str | None = None) -> list[ExchangeOrder]:
        return []

    async def get_trade_history(self, symbol: str | None = None, limit: int = 50) -> list[Trade]:
        return []

    # ------------------------------------------------------------------
    # Order simulation
    # ------------------------------------------------------------------

    async def place_order(
        self,
        symbol: str,
        side: OrderSide,
        price: float,
        quantity: float,
        order_type: str = "market_order",
    ) -> ExchangeOrder:
        try:
            ticker = await self._real.get_ticker(symbol)
            fill_price = ticker.last_price
        except Exception:
            fill_price = price

        self._counter += 1
        eid = f"PAPER_{self._counter:06d}"

        order = ExchangeOrder(
            exchange_order_id=eid,
            symbol=symbol,
            side=side.value if hasattr(side, "value") else str(side),
            price=fill_price,
            quantity=quantity,
            filled_quantity=quantity,
            filled_price=fill_price,
            status=OrderStatus.OPEN.value,
            raw_status="open",
        )
        self._paper_orders[eid] = order
        log.info(
            "[PAPER] Order %s: %s %s qty=%.8f @ ₹%.4f",
            eid, side, symbol, quantity, fill_price,
        )
        return order

    async def cancel_order(self, exchange_order_id: str) -> bool:
        if exchange_order_id in self._paper_orders:
            o = self._paper_orders[exchange_order_id]
            self._paper_orders[exchange_order_id] = ExchangeOrder(
                exchange_order_id=o.exchange_order_id,
                symbol=o.symbol,
                side=o.side,
                price=o.price,
                quantity=o.quantity,
                filled_quantity=0.0,
                filled_price=0.0,
                status=OrderStatus.CANCELLED.value,
                raw_status="cancelled",
            )
        return True

    async def get_order_status(self, exchange_order_id: str) -> ExchangeOrder:
        if exchange_order_id in self._paper_orders:
            o = self._paper_orders[exchange_order_id]
            if o.status in (OrderStatus.CANCELLED.value, OrderStatus.FILLED.value):
                return o
            return ExchangeOrder(
                exchange_order_id=o.exchange_order_id,
                symbol=o.symbol,
                side=o.side,
                price=o.price,
                quantity=o.quantity,
                filled_quantity=o.filled_quantity,
                filled_price=o.filled_price,
                status=OrderStatus.FILLED.value,
                raw_status="filled",
            )
        return ExchangeOrder(
            exchange_order_id=exchange_order_id,
            symbol="",
            side="",
            price=0.0,
            quantity=0.0,
            filled_quantity=0.0,
            filled_price=0.0,
            status=OrderStatus.FILLED.value,
            raw_status="filled",
        )

    async def close(self) -> None:
        pass

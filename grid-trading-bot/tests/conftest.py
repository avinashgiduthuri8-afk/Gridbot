"""Shared pytest fixtures for the DCA grid bot test suite."""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

os.environ.setdefault("TELEGRAM_BOT_TOKEN", "test-token")
os.environ.setdefault("TELEGRAM_CHAT_ID", "123456")
os.environ.setdefault("COINDCX_API_KEY", "test-key")
os.environ.setdefault("COINDCX_API_SECRET", "test-secret")
os.environ.setdefault("DATABASE_PATH", ":memory:")

import pytest

from config.constants import OrderStatus
from config.settings import RiskSettings
from exchange.base import Balance, ExchangeClient, ExchangeOrder, MarketInfo, Ticker, Trade
from exchange.exceptions import ExchangeError
from notifications.notifier import Notifier
from storage.database import Database
from storage.repositories import Repositories


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.fixture
async def db():
    database = Database(":memory:")
    await database.connect()
    await database.migrate()
    yield database
    await database.close()


@pytest.fixture
async def repos(db):
    return Repositories(db)


# ---------------------------------------------------------------------------
# Shared mock objects
# ---------------------------------------------------------------------------


class MockExchange(ExchangeClient):
    """Deterministic exchange stub for unit tests.

    Configurable behaviours:
    - ``ticker_price``: price returned by get_ticker
    - ``inr_balance``: balance for INR
    - ``fail_on_place``: raise OrderRejectedError on place_order
    - ``place_exception``: raise a specific exception on place_order
    - ``partial_fill_qty``: if set, place_order returns PARTIALLY_FILLED with this qty
    - ``open_orders_override``: if set, returned by get_open_orders
    - ``status_overrides``: dict[exchange_order_id → ExchangeOrder] for get_order_status
    """

    def __init__(self) -> None:
        self.ticker_price: float = 54000.0
        self.inr_balance: float = 50000.0
        self.orders_placed: list[ExchangeOrder] = []
        self.cancelled: list[str] = []
        self.fail_on_place: bool = False
        self.place_exception: Exception | None = None
        self.partial_fill_qty: float | None = None   # triggers PARTIALLY_FILLED
        self.open_orders_override: list[ExchangeOrder] | None = None
        self.status_overrides: dict[str, ExchangeOrder] = {}
        self._order_counter: int = 0
        self.market_info_override: "MarketInfo | None" = None

    async def get_ticker(self, symbol: str) -> Ticker:
        return Ticker(symbol=symbol, last_price=self.ticker_price)

    async def get_balances(self) -> list[Balance]:
        return [Balance("INR", self.inr_balance, 0.0)]

    async def get_balance(self, currency: str) -> Balance:
        return Balance(currency.upper(), self.inr_balance, 0.0)

    async def get_market_info(self, symbol: str) -> MarketInfo:
        if self.market_info_override is not None:
            return self.market_info_override
        return MarketInfo(
            symbol=symbol,
            base_currency_precision=2,
            target_currency_precision=5,
            min_quantity=0.001,
            min_amount=10.0,
            step_size=1e-5,
        )

    async def place_order(
        self,
        symbol: str,
        side,
        price: float,
        quantity: float,
        order_type: str = "market_order",
    ) -> ExchangeOrder:
        if self.place_exception is not None:
            raise self.place_exception
        if self.fail_on_place:
            from exchange.exceptions import OrderRejectedError
            raise OrderRejectedError("Simulated rejection")
        self._order_counter += 1
        eid = f"EX{self._order_counter:04d}"
        side_str = side.value if hasattr(side, "value") else str(side)

        if self.partial_fill_qty is not None:
            filled = min(self.partial_fill_qty, quantity)
            order = ExchangeOrder(
                exchange_order_id=eid,
                symbol=symbol,
                side=side_str,
                price=price,
                quantity=quantity,
                filled_quantity=filled,
                filled_price=price,
                status=OrderStatus.PARTIALLY_FILLED.value,
                raw_status="partially_filled",
            )
        else:
            order = ExchangeOrder(
                exchange_order_id=eid,
                symbol=symbol,
                side=side_str,
                price=price,
                quantity=quantity,
                filled_quantity=quantity,
                filled_price=price,
                status=OrderStatus.FILLED.value,
                raw_status="filled",
            )
        self.orders_placed.append(order)
        return order

    async def cancel_order(self, exchange_order_id: str) -> bool:
        self.cancelled.append(exchange_order_id)
        return True

    async def get_order_status(self, exchange_order_id: str) -> ExchangeOrder:
        # Status override takes priority (for recovery / sync tests)
        if exchange_order_id in self.status_overrides:
            return self.status_overrides[exchange_order_id]
        for o in self.orders_placed:
            if o.exchange_order_id == exchange_order_id:
                return o
        raise ExchangeError(f"Order {exchange_order_id} not found")

    async def get_open_orders(self, symbol: str | None = None) -> list[ExchangeOrder]:
        if self.open_orders_override is not None:
            if symbol:
                return [o for o in self.open_orders_override if o.symbol == symbol]
            return list(self.open_orders_override)
        # Default: return non-terminal placed orders
        return [
            o for o in self.orders_placed
            if o.status in (OrderStatus.OPEN.value, OrderStatus.PARTIALLY_FILLED.value)
        ]

    async def get_trade_history(self, symbol: str | None = None, limit: int = 50) -> list[Trade]:
        return []

    async def close(self) -> None:
        pass


class MockNotifier:
    """Captures all notification calls so tests can assert on them."""

    def __init__(self) -> None:
        self.calls: list[tuple[str, tuple, dict]] = []

    def _record(self, name: str, *args, **kwargs):
        self.calls.append((name, args, kwargs))

    async def send(self, message: str) -> None:
        self._record("send", message)

    async def grid_started(self, **kwargs) -> None:
        self._record("grid_started", **kwargs)

    async def grid_paused(self, symbol: str, grid_id: str) -> None:
        self._record("grid_paused", symbol, grid_id)

    async def grid_resumed(self, symbol: str, grid_id: str) -> None:
        self._record("grid_resumed", symbol, grid_id)

    async def grid_stopped(self, symbol: str, grid_id: str, reason: str) -> None:
        self._record("grid_stopped", symbol, grid_id, reason)

    async def grid_completed(self, symbol: str, grid_id: str, cycles: int, total_profit: float) -> None:
        self._record("grid_completed", symbol, grid_id, cycles, total_profit)

    async def dip_buy_executed(self, **kwargs) -> None:
        self._record("dip_buy_executed", **kwargs)

    async def profit_sell_executed(self, **kwargs) -> None:
        self._record("profit_sell_executed", **kwargs)

    async def stop_loss_triggered(self, **kwargs) -> None:
        self._record("stop_loss_triggered", **kwargs)

    async def avg_entry_updated(self, symbol: str, grid_id: str, avg_entry: float, total_qty: float, total_investment: float) -> None:
        self._record("avg_entry_updated", symbol, grid_id, avg_entry, total_qty, total_investment)

    async def price_alert_triggered(self, symbol: str, price: float, target: float, direction: str) -> None:
        self._record("price_alert_triggered", symbol, price, target, direction)

    # Order lifecycle
    async def order_submitted(self, **kwargs) -> None:
        self._record("order_submitted", **kwargs)

    async def partial_fill_received(self, **kwargs) -> None:
        self._record("partial_fill_received", **kwargs)

    async def order_cancelled(self, **kwargs) -> None:
        self._record("order_cancelled", **kwargs)

    async def order_failed(self, **kwargs) -> None:
        self._record("order_failed", **kwargs)

    # System
    async def recovery_complete(self, **kwargs) -> None:
        self._record("recovery_complete", **kwargs)

    async def sync_completed(self, synced: int, fills_found: int) -> None:
        self._record("sync_completed", synced, fills_found)

    async def sync_error(self, context: str, message: str) -> None:
        self._record("sync_error", context, message)

    async def orphan_orders_detected(self, orphans: list) -> None:
        self._record("orphan_orders_detected", orphans)

    async def error(self, context: str, message: str) -> None:
        self._record("error", context, message)

    async def daily_summary(self, text: str) -> None:
        self._record("daily_summary", text)

    def was_called(self, name: str) -> bool:
        return any(c[0] == name for c in self.calls)

    def call_count(self, name: str) -> int:
        return sum(1 for c in self.calls if c[0] == name)

    def get_calls(self, name: str) -> list[tuple]:
        return [c for c in self.calls if c[0] == name]


@pytest.fixture
def mock_exchange():
    return MockExchange()


@pytest.fixture
def mock_notifier():
    return MockNotifier()


@pytest.fixture
def permissive_risk_settings():
    return RiskSettings(
        max_total_capital=1_000_000,
        max_capital_per_coin=500_000,
        max_simultaneous_grids=20,
        min_wallet_balance=0,
        daily_loss_limit=500_000,
    )

"""Paper (simulated) exchange client.

Wraps a real ExchangeClient for all market-data reads (get_ticker,
get_market_info) and simulates order placement without touching the real
exchange.

Realistic simulation, not an instant-fill toy:
  - Slippage: the fill price is nudged away from the decision-time ticker
    price (worse for the trader, matching real market-order behavior —
    buys fill slightly above, sells slightly below).
  - Latency: an order stays OPEN for a random delay before it's eligible to
    fill at all, so it takes a few real poll cycles to resolve — exactly
    like a live order does — instead of appearing FILLED the instant
    OrderMonitor's very first poll checks it.
  - Partial fills: a configurable fraction of orders pass through an
    intermediate PARTIALLY_FILLED state before completing, so that code
    path (already implemented in order_monitor.py for real trading) is
    actually exercised by paper trading too, instead of never running.

Time and randomness are both injectable (time_fn, rng) specifically so
tests can drive this deterministically and instantly rather than sleeping
for real seconds.
"""

from __future__ import annotations

import os
import random
import time
from collections.abc import Callable
from dataclasses import dataclass

from config.constants import OrderSide, OrderStatus
from exchange.base import Balance, ExchangeClient, ExchangeOrder, ExtendedTicker, MarketInfo, Ticker, Trade
from utils.logger import get_logger

log = get_logger("exchange")

PAPER_INITIAL_BALANCE = 100_000.0

# All tunable via env vars so advanced users can make paper trading feel
# closer to (or further from) real conditions without a code change.
PAPER_SLIPPAGE_BPS_MAX = float(os.getenv("PAPER_SLIPPAGE_BPS_MAX", "8"))
PAPER_LATENCY_MIN_SECONDS = float(os.getenv("PAPER_LATENCY_MIN_SECONDS", "1.0"))
PAPER_LATENCY_MAX_SECONDS = float(os.getenv("PAPER_LATENCY_MAX_SECONDS", "4.0"))
PAPER_PARTIAL_FILL_PROBABILITY = float(os.getenv("PAPER_PARTIAL_FILL_PROBABILITY", "0.25"))
PAPER_PARTIAL_FILL_MIN_RATIO = 0.3
PAPER_PARTIAL_FILL_MAX_RATIO = 0.7
PAPER_PARTIAL_FILL_EXTRA_DELAY_MIN_SECONDS = 1.0
PAPER_PARTIAL_FILL_EXTRA_DELAY_MAX_SECONDS = 3.0


@dataclass
class _SimulatedOrder:
    exchange_order_id: str
    symbol: str
    side: str
    quantity: float
    fill_price: float          # decision price with slippage already applied
    placed_at: float
    latency_seconds: float
    has_partial_stage: bool
    partial_ratio: float
    partial_extra_delay_seconds: float
    client_order_id: str = ""
    status: str = OrderStatus.OPEN.value
    filled_quantity: float = 0.0


class PaperExchangeClient(ExchangeClient):
    """Simulates exchange order operations; delegates market data to the real exchange."""

    def __init__(
        self,
        real_exchange: ExchangeClient,
        *,
        rng: random.Random | None = None,
        time_fn: Callable[[], float] = time.monotonic,
        slippage_bps_max: float = PAPER_SLIPPAGE_BPS_MAX,
        latency_seconds_range: tuple[float, float] = (
            PAPER_LATENCY_MIN_SECONDS, PAPER_LATENCY_MAX_SECONDS,
        ),
        partial_fill_probability: float = PAPER_PARTIAL_FILL_PROBABILITY,
    ) -> None:
        self._real = real_exchange
        self._paper_orders: dict[str, _SimulatedOrder] = {}
        self._counter: int = 0
        self._rng = rng if rng is not None else random.Random()
        self._time_fn = time_fn
        self._slippage_bps_max = slippage_bps_max
        self._latency_seconds_range = latency_seconds_range
        self._partial_fill_probability = partial_fill_probability

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

    async def get_trade_history(
        self,
        symbol: str | None = None,
        limit: int = 50,
        order_id: str | None = None,
    ) -> list[Trade]:
        return []

    # ------------------------------------------------------------------
    # Order simulation
    # ------------------------------------------------------------------

    def _apply_slippage(self, decision_price: float, side_value: str) -> float:
        """Nudge the fill price against the trader by a random amount up to
        slippage_bps_max — buys fill slightly higher, sells slightly lower,
        matching how a real market order actually executes against the book
        rather than at the exact last-traded price.
        """
        bps = self._rng.uniform(0.0, self._slippage_bps_max)
        multiplier = 1 + bps / 10_000 if side_value == "buy" else 1 - bps / 10_000
        return round(decision_price * multiplier, 8)

    async def place_order(
        self,
        symbol: str,
        side: OrderSide,
        price: float,
        quantity: float,
        order_type: str = "market_order",
        client_order_id: str | None = None,
    ) -> ExchangeOrder:
        if quantity <= 0:
            raise ValueError(f"Order quantity must be positive, got {quantity}")
        if price < 0:
            raise ValueError(f"Order price cannot be negative, got {price}")
        try:
            ticker = await self._real.get_ticker(symbol)
            decision_price = ticker.last_price
        except Exception:
            decision_price = price

        side_value = side.value if hasattr(side, "value") else str(side)
        fill_price = self._apply_slippage(decision_price, side_value)

        self._counter += 1
        eid = f"PAPER_{self._counter:06d}"

        latency = self._rng.uniform(*self._latency_seconds_range)
        has_partial = self._rng.random() < self._partial_fill_probability
        partial_ratio = (
            self._rng.uniform(PAPER_PARTIAL_FILL_MIN_RATIO, PAPER_PARTIAL_FILL_MAX_RATIO)
            if has_partial else 1.0
        )
        partial_extra_delay = (
            self._rng.uniform(
                PAPER_PARTIAL_FILL_EXTRA_DELAY_MIN_SECONDS, PAPER_PARTIAL_FILL_EXTRA_DELAY_MAX_SECONDS,
            )
            if has_partial else 0.0
        )

        sim = _SimulatedOrder(
            exchange_order_id=eid, symbol=symbol, side=side_value, quantity=quantity,
            fill_price=fill_price, placed_at=self._time_fn(), latency_seconds=latency,
            has_partial_stage=has_partial, partial_ratio=partial_ratio,
            partial_extra_delay_seconds=partial_extra_delay,
            client_order_id=client_order_id or "",
        )
        self._paper_orders[eid] = sim

        slippage_pct = (
            100 * (fill_price - decision_price) / decision_price if decision_price else 0.0
        )
        log.info(
            "[PAPER] Order %s: %s %s qty=%.8f decision=₹%.4f fill=₹%.4f "
            "(slippage %.4f%%) latency=%.2fs%s",
            eid, side_value, symbol, quantity, decision_price, fill_price,
            slippage_pct, latency, " [partial-fill stage simulated]" if has_partial else "",
        )

        # Mirrors a real exchange's initial acknowledgment: OPEN and
        # unfilled. The previous version of this simulator returned
        # status=OPEN but filled_quantity=quantity — a self-contradictory
        # state — and get_order_status() reported FILLED on literally the
        # first check, regardless of order_monitor's poll interval. Neither
        # matches how a real order actually behaves.
        return ExchangeOrder(
            exchange_order_id=eid, symbol=symbol, side=side_value,
            price=fill_price, quantity=quantity,
            filled_quantity=0.0, filled_price=0.0,
            status=OrderStatus.OPEN.value, raw_status="open",
            fee=0.0,
            client_order_id=client_order_id or "",
        )

    def _to_exchange_order(self, sim: _SimulatedOrder) -> ExchangeOrder:
        return ExchangeOrder(
            exchange_order_id=sim.exchange_order_id, symbol=sim.symbol, side=sim.side,
            price=sim.fill_price, quantity=sim.quantity,
            filled_quantity=sim.filled_quantity,
            filled_price=sim.fill_price if sim.filled_quantity > 0 else 0.0,
            status=sim.status, raw_status=sim.status,
            fee=0.0,
            client_order_id=sim.client_order_id,
        )

    async def cancel_order(self, exchange_order_id: str) -> bool:
        sim = self._paper_orders.get(exchange_order_id)
        if sim is not None and sim.status != OrderStatus.FILLED.value:
            # A real exchange lets you cancel a resting or partially-filled
            # order (keeping whatever already filled), but not one that's
            # already fully filled — there's nothing left to cancel.
            sim.status = OrderStatus.CANCELLED.value
        return True

    async def get_order_status(self, exchange_order_id: str) -> ExchangeOrder:
        sim = self._paper_orders.get(exchange_order_id)
        if sim is None:
            # Unchanged fallback for an untracked order ID — preserved from
            # the original implementation for backward compatibility with
            # any caller that queries an ID this instance never placed.
            return ExchangeOrder(
                exchange_order_id=exchange_order_id, symbol="", side="",
                price=0.0, quantity=0.0, filled_quantity=0.0, filled_price=0.0,
                status=OrderStatus.FILLED.value, raw_status="filled", fee=0.0,
            )

        if sim.status == OrderStatus.CANCELLED.value:
            return self._to_exchange_order(sim)

        elapsed = self._time_fn() - sim.placed_at

        if elapsed < sim.latency_seconds:
            # Still resting — not yet eligible to fill at all. This is what
            # makes a paper order take multiple real poll cycles to resolve,
            # instead of appearing FILLED on the very first check.
            return self._to_exchange_order(sim)

        if sim.has_partial_stage and elapsed < sim.latency_seconds + sim.partial_extra_delay_seconds:
            partial_qty = round(sim.quantity * sim.partial_ratio, 10)
            # Never regress a quantity already reported on an earlier poll.
            sim.filled_quantity = max(sim.filled_quantity, partial_qty)
            sim.status = OrderStatus.PARTIALLY_FILLED.value
            return self._to_exchange_order(sim)

        sim.filled_quantity = sim.quantity
        sim.status = OrderStatus.FILLED.value
        return self._to_exchange_order(sim)

    async def get_order_by_client_order_id(self, client_order_id: str) -> ExchangeOrder | None:
        for sim in self._paper_orders.values():
            if sim.client_order_id == client_order_id:
                return self._to_exchange_order(sim)
        return None

    async def close(self) -> None:
        pass

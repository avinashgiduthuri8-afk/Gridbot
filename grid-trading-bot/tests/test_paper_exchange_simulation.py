"""Tests for the realistic paper-exchange simulation: slippage direction,
latency delaying fills across multiple polls, partial fills, and
deterministic reproducibility via injected time/randomness."""

from __future__ import annotations

import random

import pytest

from config.constants import OrderSide, OrderStatus
from exchange.base import Ticker
from exchange.paper_exchange import PaperExchangeClient

pytestmark = pytest.mark.anyio


class FakeClock:
    """Controllable fake time source — advances instantly, no real sleeping."""

    def __init__(self):
        self.now = 0.0

    def __call__(self) -> float:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += seconds


class FakeRealExchange:
    def __init__(self, price: float = 100.0):
        self.price = price

    async def get_ticker(self, symbol: str) -> Ticker:
        return Ticker(symbol=symbol, last_price=self.price)


async def test_buy_fills_at_or_above_decision_price():
    real = FakeRealExchange(price=100.0)
    paper = PaperExchangeClient(
        real, rng=random.Random(42), time_fn=FakeClock(),
        latency_seconds_range=(0, 0), partial_fill_probability=0.0,
    )
    order = await paper.place_order("BTCINR", OrderSide.BUY, 100.0, 1.0)
    assert order.price >= 100.0, "slippage must go against a buyer (fill at or above decision price)"


async def test_sell_fills_at_or_below_decision_price():
    real = FakeRealExchange(price=100.0)
    paper = PaperExchangeClient(
        real, rng=random.Random(42), time_fn=FakeClock(),
        latency_seconds_range=(0, 0), partial_fill_probability=0.0,
    )
    order = await paper.place_order("BTCINR", OrderSide.SELL, 100.0, 1.0)
    assert order.price <= 100.0, "slippage must go against a seller (fill at or below decision price)"


async def test_order_is_open_and_unfilled_immediately_after_placement():
    real = FakeRealExchange()
    paper = PaperExchangeClient(real, rng=random.Random(1), time_fn=FakeClock())
    order = await paper.place_order("BTCINR", OrderSide.BUY, 100.0, 1.0)
    assert order.status == OrderStatus.OPEN.value
    assert order.filled_quantity == 0.0


async def test_stays_open_until_latency_elapses():
    clock = FakeClock()
    real = FakeRealExchange()
    paper = PaperExchangeClient(
        real, rng=random.Random(1), time_fn=clock,
        latency_seconds_range=(2.0, 2.0), partial_fill_probability=0.0,
    )
    order = await paper.place_order("BTCINR", OrderSide.BUY, 100.0, 1.0)
    eid = order.exchange_order_id

    assert (await paper.get_order_status(eid)).status == OrderStatus.OPEN.value

    clock.advance(1.0)
    assert (await paper.get_order_status(eid)).status == OrderStatus.OPEN.value, \
        "must still be open before the simulated latency has elapsed"

    clock.advance(1.5)  # total 2.5s > 2s latency
    final = await paper.get_order_status(eid)
    assert final.status == OrderStatus.FILLED.value
    assert final.filled_quantity == 1.0


async def test_partial_fill_stage_when_forced():
    clock = FakeClock()
    real = FakeRealExchange()
    paper = PaperExchangeClient(
        real, rng=random.Random(7), time_fn=clock,
        latency_seconds_range=(1.0, 1.0), partial_fill_probability=1.0,
    )
    order = await paper.place_order("BTCINR", OrderSide.BUY, 100.0, 10.0)
    eid = order.exchange_order_id

    clock.advance(1.5)  # past latency, still within the partial-fill window
    partial = await paper.get_order_status(eid)
    assert partial.status == OrderStatus.PARTIALLY_FILLED.value
    assert 0 < partial.filled_quantity < 10.0

    # Repeated poll at the same simulated time must not regress the filled amount
    partial_again = await paper.get_order_status(eid)
    assert partial_again.filled_quantity == partial.filled_quantity

    clock.advance(5.0)  # past the extra partial-fill delay too
    full = await paper.get_order_status(eid)
    assert full.status == OrderStatus.FILLED.value
    assert full.filled_quantity == 10.0


async def test_no_partial_fill_stage_when_disabled():
    clock = FakeClock()
    real = FakeRealExchange()
    paper = PaperExchangeClient(
        real, rng=random.Random(2), time_fn=clock,
        latency_seconds_range=(1.0, 1.0), partial_fill_probability=0.0,
    )
    order = await paper.place_order("BTCINR", OrderSide.BUY, 10.0, 1.0)
    eid = order.exchange_order_id

    clock.advance(2.0)
    result = await paper.get_order_status(eid)
    assert result.status == OrderStatus.FILLED.value, "must go straight to FILLED with partial fills disabled"


async def test_cancel_before_fill_succeeds():
    real = FakeRealExchange()
    paper = PaperExchangeClient(
        real, rng=random.Random(3), time_fn=FakeClock(),
        latency_seconds_range=(5.0, 5.0), partial_fill_probability=0.0,
    )
    order = await paper.place_order("BTCINR", OrderSide.BUY, 100.0, 1.0)
    assert await paper.cancel_order(order.exchange_order_id) is True
    result = await paper.get_order_status(order.exchange_order_id)
    assert result.status == OrderStatus.CANCELLED.value


async def test_same_seed_gives_reproducible_fill_price():
    """Reproducibility guard: the same seed must always produce the same
    simulated slippage, which is what makes this simulator testable at all."""
    real = FakeRealExchange()
    order_a = await PaperExchangeClient(
        real, rng=random.Random(99), time_fn=FakeClock(),
    ).place_order("BTCINR", OrderSide.BUY, 100.0, 1.0)
    order_b = await PaperExchangeClient(
        real, rng=random.Random(99), time_fn=FakeClock(),
    ).place_order("BTCINR", OrderSide.BUY, 100.0, 1.0)
    assert order_a.price == order_b.price


async def test_default_construction_still_works_with_no_kwargs(repos, mock_exchange, mock_notifier, permissive_risk_settings):
    """Regression guard: existing call sites construct PaperExchangeClient
    with just the positional real_exchange argument (main.py, and the
    pre-existing test in test_order_lifecycle.py) — this must keep working
    unchanged, with sensible defaults, not require the new kwargs."""
    from risk.risk_manager import RiskManager
    from trading.dca_manager import DCAManager
    from trading.mixed_order_manager import MixedOrderManager
    from trading.order_manager import OrderManager

    paper_ex = PaperExchangeClient(mock_exchange)
    real_om = OrderManager(mock_exchange, repos)
    paper_om = OrderManager(paper_ex, repos)
    mixed_om = MixedOrderManager(real=real_om, paper=paper_om, repos=repos)
    risk = RiskManager(permissive_risk_settings, repos)
    dca = DCAManager(exchange=mock_exchange, repos=repos, order_manager=mixed_om, notifier=mock_notifier, risk=risk)

    grid_id = await dca.start_grid({
        "symbol": "BTCINR", "entry_price": 54000.0, "base_investment": 500.0,
        "dip_buy_amount": 100.0, "dip_percentage": 5.0,
        "profit_sell_amount": 150.0, "profit_percentage": 7.0,
        "max_levels": 10, "stop_loss_percentage": 50.0, "mode": "paper",
    })
    grid_rec = await repos.grids.get(grid_id)
    assert grid_rec["mode"] == "paper"
    orders = await repos.orders.list_for_grid(grid_id)
    assert len(orders) >= 1

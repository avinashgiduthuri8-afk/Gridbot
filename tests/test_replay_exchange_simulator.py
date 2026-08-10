import random

import pytest

from config.constants import OrderSide, OrderStatus
from exchange.base import MarketInfo
from replay.fee_exchange import FeeSimulatingPaperExchange
from replay.market_data_exchange import ReplayMarketDataExchange, ReplaySymbolNotSeeded

pytestmark = pytest.mark.anyio


def _market_info(symbol="BTCINR"):
    return MarketInfo(
        symbol=symbol, base_currency_precision=2, target_currency_precision=5,
        min_quantity=0.001, min_amount=10.0, step_size=1e-5,
    )


async def test_get_ticker_returns_replay_price():
    ex = ReplayMarketDataExchange()
    ex.set_price("BTCINR", 12345.67)
    ticker = await ex.get_ticker("BTCINR")
    assert ticker.last_price == 12345.67


async def test_get_ticker_before_price_set_raises():
    ex = ReplayMarketDataExchange()
    with pytest.raises(ReplaySymbolNotSeeded):
        await ex.get_ticker("BTCINR")


async def test_get_market_info_before_registration_raises():
    ex = ReplayMarketDataExchange()
    with pytest.raises(ReplaySymbolNotSeeded):
        await ex.get_market_info("BTCINR")


async def test_get_market_info_returns_registered_info():
    ex = ReplayMarketDataExchange()
    info = _market_info()
    ex.register_market("BTCINR", info)
    fetched = await ex.get_market_info("BTCINR")
    assert fetched is info


async def test_place_order_directly_not_implemented():
    """The market-data-only exchange should never be handed directly to
    OrderManager — it must be wrapped by FeeSimulatingPaperExchange."""
    ex = ReplayMarketDataExchange()
    with pytest.raises(NotImplementedError):
        await ex.place_order("BTCINR", OrderSide.BUY, 100.0, 1.0)


async def test_fee_exchange_fills_and_charges_fee():
    md = ReplayMarketDataExchange()
    md.register_market("BTCINR", _market_info())
    md.set_price("BTCINR", 100.0)
    clock = {"t": 0.0}
    ex = FeeSimulatingPaperExchange(
        md, rng=random.Random(1), time_fn=lambda: clock["t"],
        latency_seconds_range=(0.0, 0.0), partial_fill_probability=0.0, fee_rate=0.001,
    )
    order = await ex.place_order("BTCINR", OrderSide.BUY, 100.0, 1.0)
    assert order.status == OrderStatus.OPEN.value
    assert order.fee == 0.0  # not filled yet

    clock["t"] = 10.0
    status = await ex.get_order_status(order.exchange_order_id)
    assert status.status == OrderStatus.FILLED.value
    assert status.filled_quantity == 1.0
    # fee ~ 0.1% of notional (~100), allow for slippage moving the fill price slightly
    assert 0.09 < status.fee < 0.11


async def test_fee_exchange_no_fee_while_unfilled():
    md = ReplayMarketDataExchange()
    md.register_market("BTCINR", _market_info())
    md.set_price("BTCINR", 100.0)
    clock = {"t": 0.0}
    ex = FeeSimulatingPaperExchange(
        md, rng=random.Random(1), time_fn=lambda: clock["t"],
        latency_seconds_range=(5.0, 5.0), partial_fill_probability=0.0, fee_rate=0.001,
    )
    order = await ex.place_order("BTCINR", OrderSide.SELL, 100.0, 1.0)
    status = await ex.get_order_status(order.exchange_order_id)  # still resting, latency not elapsed
    assert status.status == OrderStatus.OPEN.value
    assert status.fee == 0.0


async def test_fee_exchange_min_quantity_validation_available_via_market_info():
    """The Exchange Simulator satisfies "validate minimum quantity /
    investment / step size" by delegating get_market_info to the
    registered MarketInfo — the SAME validate_quantity()/validate_order()
    functions the real exchange path uses then apply identically. This
    confirms the simulator hands back exactly what was registered, since
    the validation logic itself is exercised end-to-end in
    test_replay_engine.py via real DCAManager grids."""
    md = ReplayMarketDataExchange()
    info = _market_info()
    md.register_market("BTCINR", info)
    fetched = await md.get_market_info("BTCINR")
    assert fetched.min_quantity == 0.001
    assert fetched.min_amount == 10.0
    assert fetched.step_size == 1e-5

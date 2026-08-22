"""Regression tests for FeeSimulatingPaperExchange's optional wallet-balance
tracking (debit on buy fills, credit on sell fills) — added so real-capital
replay mode can exercise RiskManager's capital-constraint checks, which
mode="paper" grids bypass entirely by design (DCAManager hardcodes a fixed
non-depleting balance for paper mode)."""
from __future__ import annotations

import random

import pytest

from config.constants import OrderSide, OrderStatus
from exchange.base import MarketInfo
from exchange.paper_exchange import PAPER_INITIAL_BALANCE
from replay.fee_exchange import FeeSimulatingPaperExchange
from replay.market_data_exchange import ReplayMarketDataExchange

pytestmark = pytest.mark.anyio


def _market_info(symbol="BTCINR"):
    return MarketInfo(
        symbol=symbol, base_currency_precision=2, target_currency_precision=5,
        min_quantity=0.001, min_amount=10.0, step_size=1e-5,
    )


def _make_exchange(initial_balance_inr=None, fee_rate=0.001, clock=None):
    md = ReplayMarketDataExchange()
    md.register_market("BTCINR", _market_info())
    md.set_price("BTCINR", 100.0)
    clock = clock if clock is not None else {"t": 0.0}
    ex = FeeSimulatingPaperExchange(
        md, rng=random.Random(1), time_fn=lambda: clock["t"],
        latency_seconds_range=(0.0, 0.0), partial_fill_probability=0.0,
        fee_rate=fee_rate, initial_balance_inr=initial_balance_inr,
    )
    return ex, clock


async def test_capital_tracking_disabled_by_default_preserves_existing_behavior():
    """Backward compatibility: omitting initial_balance_inr must behave
    exactly as before — get_balance delegates to PaperExchangeClient's
    fixed constant, unaffected by any fills."""
    ex, clock = _make_exchange(initial_balance_inr=None)

    balance_before = await ex.get_balance("INR")
    assert balance_before.balance == PAPER_INITIAL_BALANCE

    order = await ex.place_order("BTCINR", OrderSide.BUY, 100.0, 10.0)
    clock["t"] = 10.0
    await ex.get_order_status(order.exchange_order_id)

    balance_after = await ex.get_balance("INR")
    assert balance_after.balance == PAPER_INITIAL_BALANCE, "fills must not affect balance when tracking is disabled"


async def test_capital_tracking_reports_initial_balance_before_any_trade():
    ex, clock = _make_exchange(initial_balance_inr=10_000.0)
    balance = await ex.get_balance("INR")
    assert balance.balance == 10_000.0
    balances = await ex.get_balances()
    assert balances[0].balance == 10_000.0
    assert balances[0].currency == "INR"


async def test_buy_fill_debits_notional_plus_fee():
    ex, clock = _make_exchange(initial_balance_inr=10_000.0, fee_rate=0.001)

    order = await ex.place_order("BTCINR", OrderSide.BUY, 100.0, 10.0)
    balance_while_open = await ex.get_balance("INR")
    assert balance_while_open.balance == 10_000.0, "no debit until the order actually fills"

    clock["t"] = 10.0
    status = await ex.get_order_status(order.exchange_order_id)
    assert status.status == OrderStatus.FILLED.value

    balance_after = await ex.get_balance("INR")
    expected_notional = status.filled_quantity * status.filled_price
    expected_debit = expected_notional + status.fee
    assert balance_after.balance == pytest.approx(10_000.0 - expected_debit)


async def test_sell_fill_credits_notional_minus_fee():
    ex, clock = _make_exchange(initial_balance_inr=10_000.0, fee_rate=0.001)

    order = await ex.place_order("BTCINR", OrderSide.SELL, 100.0, 10.0)
    clock["t"] = 10.0
    status = await ex.get_order_status(order.exchange_order_id)
    assert status.status == OrderStatus.FILLED.value

    balance_after = await ex.get_balance("INR")
    expected_notional = status.filled_quantity * status.filled_price
    expected_credit = expected_notional - status.fee
    assert balance_after.balance == pytest.approx(10_000.0 + expected_credit)


async def test_polling_the_same_filled_order_multiple_times_does_not_double_charge():
    """get_order_status can legitimately be called many times for the same
    order (OrderMonitor polls every tick) — the balance delta must only be
    applied once, the first time the fill is observed, not once per poll."""
    ex, clock = _make_exchange(initial_balance_inr=10_000.0)
    order = await ex.place_order("BTCINR", OrderSide.BUY, 100.0, 10.0)
    clock["t"] = 10.0

    status1 = await ex.get_order_status(order.exchange_order_id)
    balance_1 = (await ex.get_balance("INR")).balance

    # Poll again — and again — nothing should change now that it's settled.
    await ex.get_order_status(order.exchange_order_id)
    await ex.get_order_status(order.exchange_order_id)
    balance_3 = (await ex.get_balance("INR")).balance

    assert balance_1 == balance_3


async def test_round_trip_buy_then_sell_leaves_balance_reduced_by_fees_only():
    """Buying then selling the exact same quantity at the exact same price
    should leave the balance reduced by exactly the two fees paid (no
    phantom gain or loss from the capital-tracking arithmetic itself)."""
    ex, clock = _make_exchange(initial_balance_inr=10_000.0, fee_rate=0.001)

    buy_order = await ex.place_order("BTCINR", OrderSide.BUY, 100.0, 10.0)
    clock["t"] = 10.0
    buy_status = await ex.get_order_status(buy_order.exchange_order_id)

    sell_order = await ex.place_order("BTCINR", OrderSide.SELL, buy_status.filled_price, 10.0)
    clock["t"] = 20.0
    sell_status = await ex.get_order_status(sell_order.exchange_order_id)

    final_balance = (await ex.get_balance("INR")).balance
    total_fees = buy_status.fee + sell_status.fee
    # Sell filled at the same reference price as the buy's actual fill,
    # so the notional roughly cancels out — only fees should be lost.
    assert final_balance == pytest.approx(10_000.0 - total_fees, abs=0.5)


async def test_capital_tracking_survives_multiple_symbols_independently_priced():
    """Balance tracking is a single shared INR balance across symbols
    (matching how a real exchange wallet works), not per-symbol."""
    md = ReplayMarketDataExchange()
    md.register_market("BTCINR", _market_info("BTCINR"))
    md.register_market("ETHINR", _market_info("ETHINR"))
    md.set_price("BTCINR", 100.0)
    md.set_price("ETHINR", 50.0)
    clock = {"t": 0.0}
    ex = FeeSimulatingPaperExchange(
        md, rng=random.Random(1), time_fn=lambda: clock["t"],
        latency_seconds_range=(0.0, 0.0), partial_fill_probability=0.0,
        fee_rate=0.001, initial_balance_inr=10_000.0,
    )

    btc_order = await ex.place_order("BTCINR", OrderSide.BUY, 100.0, 5.0)
    eth_order = await ex.place_order("ETHINR", OrderSide.BUY, 50.0, 5.0)
    clock["t"] = 10.0
    btc_status = await ex.get_order_status(btc_order.exchange_order_id)
    eth_status = await ex.get_order_status(eth_order.exchange_order_id)

    final_balance = (await ex.get_balance("INR")).balance
    expected_spent = (
        btc_status.filled_quantity * btc_status.filled_price + btc_status.fee
        + eth_status.filled_quantity * eth_status.filled_price + eth_status.fee
    )
    assert final_balance == pytest.approx(10_000.0 - expected_spent)

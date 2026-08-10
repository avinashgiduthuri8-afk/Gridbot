"""Crash-simulation tests for the replay framework.

These simulate the bot PROCESS crashing/restarting mid-operation, while the
exchange itself (a real exchange like CoinDCX would be) is unaffected —
only the bot-side Python objects (Repositories/DCAManager/OrderMonitor/
RiskManager/Notifier) get torn down and rebuilt, exactly like main.py
restarting. The exchange and its in-flight order state are kept alive
across the "restart", since a real exchange does not restart when your
bot's process does.

Not covered here (out of scope for a price-feed replay engine, not a gap
in the trading logic):
  - "Restart during backup": the Google Drive backup system is unrelated
    to price replay — it belongs with the backup test suite
    (test_backup_integrity.py, test_restorebackup.py, etc.), which already
    exercises it.
  - "Restart during a raw database write": simulating a torn write requires
    corrupting the SQLite file mid-transaction, which is a test of
    SQLite/aiosqlite's own crash-consistency guarantees (WAL mode), not of
    this trading engine's logic. What IS covered below is the equivalent
    business-logic question that actually matters: does recovery correctly
    reconcile whatever state was durably committed before the crash.
"""
from __future__ import annotations

import random

import pytest

from config.constants import GridStatus, OrderStatus
from config.settings import RiskSettings
from exchange.base import MarketInfo
from replay.counting_notifier import CountingNotifier
from replay.data_loader import Candle
from replay.engine import ReplayClock, ReplayEngine
from replay.fee_exchange import FeeSimulatingPaperExchange
from replay.market_data_exchange import ReplayMarketDataExchange
from risk.risk_manager import RiskManager
from storage.database import Database
from storage.repositories import Repositories
from trading.dca_manager import DCAManager
from trading.mixed_order_manager import MixedOrderManager
from trading.order_manager import OrderManager
from trading.order_monitor import OrderMonitor
from trading.recovery import RecoveryManager

pytestmark = pytest.mark.anyio


def _market_info(symbol):
    return MarketInfo(
        symbol=symbol, base_currency_precision=2, target_currency_precision=5,
        min_quantity=0.001, min_amount=10.0, step_size=1e-5,
    )


def _risk_settings():
    return RiskSettings(
        max_total_capital=10_000_000, max_capital_per_coin=5_000_000,
        max_simultaneous_grids=50, min_wallet_balance=0, daily_loss_limit=5_000_000,
    )


async def _build_bot_stack(db_path, exchange):
    """Builds a fresh 'bot process generation' — repos, DCAManager,
    OrderMonitor, RiskManager, Notifier — against db_path, but reusing the
    SAME exchange object passed in. This is the realistic shape of a
    restart: your process restarts, the exchange does not."""
    db = Database(str(db_path))
    await db.connect()
    await db.migrate()
    repos = Repositories(db)
    risk = RiskManager(_risk_settings(), repos)
    await risk.load_emergency_stop()
    notifier = CountingNotifier()
    real_om = OrderManager(exchange, repos)
    paper_om = OrderManager(exchange, repos)
    mixed_om = MixedOrderManager(real=real_om, paper=paper_om, repos=repos)
    dca = DCAManager(exchange=exchange, repos=repos, order_manager=mixed_om, notifier=notifier, risk=risk)
    order_monitor = OrderMonitor(
        repos=repos, order_manager=mixed_om, dca_manager=dca, notifier=notifier,
        exchange=exchange, poll_interval=1,
    )
    return db, repos, dca, order_monitor, notifier


async def _crash_and_restart(db_path, exchange):
    """Tears down nothing exchange-side (it's the same object, simulating
    a real external exchange), builds a brand-new bot-side stack, and runs
    RecoveryManager against it — exactly what main.py does on startup."""
    db2, repos2, dca2, order_monitor2, notifier2 = await _build_bot_stack(db_path, exchange)
    recovery = RecoveryManager(exchange=exchange, repos=repos2, notifier=notifier2, dca_manager=dca2)
    summary = await recovery.recover()
    return db2, repos2, dca2, order_monitor2, notifier2, summary


async def _start_grid(dca, symbol, **overrides):
    params = dict(
        symbol=symbol, entry_price=0, base_investment=500.0, dip_buy_amount=100.0,
        dip_percentage=5.0, profit_sell_amount=150.0, profit_percentage=5.0,
        max_levels=10, stop_loss_percentage=20.0, mode="paper",
    )
    params.update(overrides)
    return await dca.start_grid(params)


async def test_restart_mid_pending_buy_order_recovers_correctly(tmp_path):
    """A buy is placed but hasn't cleared its simulated latency yet when
    the bot 'crashes'. After restart, recovery must pick it up from the
    (still-alive) exchange and correctly process the fill once it's ready
    — without creating a duplicate order or losing the position."""
    db_path = tmp_path / "crash_buy.sqlite3"
    exchange = ReplayMarketDataExchange()
    exchange.register_market("BTCINR", _market_info("BTCINR"))
    exchange.set_price("BTCINR", 100.0)
    clock = ReplayClock()
    # 5-second latency: long enough that the initial buy is still OPEN
    # when we "crash", but will be FILLED by the time recovery checks it.
    fee_exchange = FeeSimulatingPaperExchange(
        exchange, rng=random.Random(1), time_fn=clock.now,
        latency_seconds_range=(5.0, 5.0), partial_fill_probability=0.0, fee_rate=0.001,
    )

    db, repos, dca, order_monitor, notifier = await _build_bot_stack(db_path, fee_exchange)
    grid_id = await _start_grid(dca, "BTCINR")

    orders_before = await repos.orders.list_for_grid(grid_id)
    assert len(orders_before) == 1
    assert orders_before[0]["status"] in (OrderStatus.OPEN.value, OrderStatus.PENDING.value, OrderStatus.SUBMITTED.value)

    # --- crash: bot process dies before the buy's latency has elapsed ---
    await db.close()
    clock.tick(10.0)  # time passes while the bot is down; latency now elapsed
    db2, repos2, dca2, order_monitor2, notifier2, summary = await _crash_and_restart(db_path, fee_exchange)

    orders_after = await repos2.orders.list_for_grid(grid_id)
    assert len(orders_after) == 1, "recovery must not duplicate the order"
    assert orders_after[0]["status"] == OrderStatus.FILLED.value

    grid_after = await repos2.grids.get(grid_id)
    assert grid_after["total_quantity"] > 0, "the buy's fill must be reflected on the grid after recovery"
    assert grid_after["status"] == GridStatus.ACTIVE.value

    await db2.close()


async def test_restart_mid_pending_sell_order_recovers_correctly(tmp_path):
    """Same as above, but for a manual sell in flight at crash time."""
    db_path = tmp_path / "crash_sell.sqlite3"
    exchange = ReplayMarketDataExchange()
    exchange.register_market("BTCINR", _market_info("BTCINR"))
    exchange.set_price("BTCINR", 100.0)
    clock = ReplayClock()
    fee_exchange = FeeSimulatingPaperExchange(
        exchange, rng=random.Random(2), time_fn=clock.now,
        latency_seconds_range=(0.0, 0.0), partial_fill_probability=0.0, fee_rate=0.001,
    )

    db, repos, dca, order_monitor, notifier = await _build_bot_stack(db_path, fee_exchange)
    grid_id = await _start_grid(dca, "BTCINR")
    # Let the initial buy fill before placing the sell we'll crash on.
    await order_monitor._poll_once()
    grid = await repos.grids.get(grid_id)
    assert grid["total_quantity"] > 0

    # Now place a manual sell with real latency, and crash before it clears.
    fee_exchange._latency_seconds_range = (5.0, 5.0)
    await dca.manual_sell(grid_id, None)
    sell_orders_before = [o for o in await repos.orders.list_for_grid(grid_id) if o["side"] == "sell"]
    assert len(sell_orders_before) == 1
    assert sell_orders_before[0]["status"] == OrderStatus.OPEN.value

    await db.close()
    clock.tick(10.0)
    db2, repos2, dca2, order_monitor2, notifier2, summary = await _crash_and_restart(db_path, fee_exchange)

    sell_orders_after = [o for o in await repos2.orders.list_for_grid(grid_id) if o["side"] == "sell"]
    assert len(sell_orders_after) == 1, "recovery must not duplicate the sell order"
    assert sell_orders_after[0]["status"] == OrderStatus.FILLED.value

    grid_after = await repos2.grids.get(grid_id)
    assert grid_after["total_quantity"] == 0.0
    assert grid_after["status"] == GridStatus.COMPLETED.value  # a full exit via normal fill processing

    await db2.close()


async def test_restart_during_active_trailing_with_pending_order_recovers_correctly(tmp_path):
    """Combines both concerns at once: an active trailing-TP cycle AND an
    in-flight order at the moment of the crash. Both the trailing peak
    (a plain DB column) and the pending order must resolve correctly
    after restart."""
    db_path = tmp_path / "crash_trailing.sqlite3"
    exchange = ReplayMarketDataExchange()
    exchange.register_market("BTCINR", _market_info("BTCINR"))
    exchange.set_price("BTCINR", 100.0)
    clock = ReplayClock()
    fee_exchange = FeeSimulatingPaperExchange(
        exchange, rng=random.Random(3), time_fn=clock.now,
        latency_seconds_range=(0.0, 0.0), partial_fill_probability=0.0, fee_rate=0.001,
    )

    db, repos, dca, order_monitor, notifier = await _build_bot_stack(db_path, fee_exchange)
    grid_id = await _start_grid(dca, "BTCINR", trailing_enabled=True, trailing_percentage=3.0, profit_percentage=5.0)
    await order_monitor._poll_once()  # let the initial buy fill

    engine = ReplayEngine(repos, dca, order_monitor, exchange, clock)
    await engine.run([
        Candle(symbol="BTCINR", timestamp=0, open=100, high=100, low=100, close=100),
        Candle(symbol="BTCINR", timestamp=60, open=100, high=106, low=100, close=106),  # crosses profit target, trailing activates
        Candle(symbol="BTCINR", timestamp=120, open=106, high=112, low=106, close=112),  # peak rises further
    ])
    grid_before = await repos.grids.get(grid_id)
    assert grid_before["trailing_peak_price"] == 112.0

    # Fire off one more manual buy so there's a genuinely in-flight order at crash time.
    fee_exchange._latency_seconds_range = (5.0, 5.0)
    await dca.manual_buy(grid_id, 50.0)
    buy_orders_before = [o for o in await repos.orders.list_for_grid(grid_id) if o["side"] == "buy"]
    open_buy = [o for o in buy_orders_before if o["status"] == OrderStatus.OPEN.value]
    assert len(open_buy) == 1

    await db.close()
    clock.tick(10.0)
    db2, repos2, dca2, order_monitor2, notifier2, summary = await _crash_and_restart(db_path, fee_exchange)

    # The in-flight manual buy resolved correctly...
    buy_orders_after = [o for o in await repos2.orders.list_for_grid(grid_id) if o["side"] == "buy"]
    assert len(buy_orders_after) == len(buy_orders_before), "recovery must not duplicate the pending buy"
    assert all(o["status"] == OrderStatus.FILLED.value for o in buy_orders_after)

    # ...and the trailing peak survived the restart untouched.
    grid_after = await repos2.grids.get(grid_id)
    assert grid_after["trailing_peak_price"] == 112.0

    # Continuing the replay after restart must still fire the trailing-stop sell correctly.
    engine2 = ReplayEngine(repos2, dca2, order_monitor2, exchange, clock)
    await engine2.run([
        Candle(symbol="BTCINR", timestamp=180, open=112, high=112, low=108, close=108),  # ~3.6% pullback from 112
    ])
    sells_after = [o for o in await repos2.orders.list_for_grid(grid_id) if o["side"] == "sell"]
    assert sells_after, "trailing-stop sell must still fire correctly after the simulated crash"

    await db2.close()

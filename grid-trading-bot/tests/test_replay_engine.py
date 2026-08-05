import random

import pytest

from config.constants import GridStatus
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


async def _build_stack(db_path, symbols, seed=1):
    db = Database(str(db_path))
    await db.connect()
    await db.migrate()
    repos = Repositories(db)

    exchange = ReplayMarketDataExchange()
    for s in symbols:
        exchange.register_market(s, _market_info(s))

    clock = ReplayClock()
    fee_exchange = FeeSimulatingPaperExchange(
        exchange, rng=random.Random(seed), time_fn=clock.now,
        latency_seconds_range=(0.0, 0.0), partial_fill_probability=0.0, fee_rate=0.001,
    )

    from config.settings import RiskSettings
    risk_settings = RiskSettings(
        max_total_capital=10_000_000, max_capital_per_coin=5_000_000,
        max_simultaneous_grids=50, min_wallet_balance=0, daily_loss_limit=5_000_000,
    )
    risk = RiskManager(risk_settings, repos)
    await risk.load_emergency_stop()

    notifier = CountingNotifier()
    real_om = OrderManager(fee_exchange, repos)
    paper_om = OrderManager(fee_exchange, repos)
    mixed_om = MixedOrderManager(real=real_om, paper=paper_om, repos=repos)
    dca = DCAManager(exchange=fee_exchange, repos=repos, order_manager=mixed_om, notifier=notifier, risk=risk)
    order_monitor = OrderMonitor(
        repos=repos, order_manager=mixed_om, dca_manager=dca, notifier=notifier,
        exchange=fee_exchange, poll_interval=1,
    )
    return db, repos, exchange, fee_exchange, clock, dca, order_monitor, notifier


def _flat_candles(symbol, bars, price=100.0, interval=60.0):
    return [
        Candle(symbol=symbol, timestamp=i * interval, open=price, high=price, low=price, close=price)
        for i in range(bars)
    ]


async def _start_default_grid(dca, symbol, **overrides):
    params = dict(
        symbol=symbol, entry_price=0, base_investment=500.0, dip_buy_amount=100.0,
        dip_percentage=5.0, profit_sell_amount=150.0, profit_percentage=5.0,
        max_levels=10, stop_loss_percentage=20.0, mode="paper",
    )
    params.update(overrides)
    return await dca.start_grid(params)


async def test_single_symbol_replay_runs_without_error(tmp_path):
    db, repos, exchange, fee_exchange, clock, dca, order_monitor, notifier = await _build_stack(tmp_path / "a.sqlite3", ["BTCINR"])
    exchange.set_price("BTCINR", 100.0)
    await _start_default_grid(dca, "BTCINR")

    engine = ReplayEngine(repos, dca, order_monitor, exchange, clock)
    feed = _flat_candles("BTCINR", 50)
    stats = await engine.run(feed)

    assert stats.candles_processed == 50
    assert not stats.exceptions
    await db.close()


async def test_multi_symbol_replay_processes_all_symbols(tmp_path):
    symbols = ["BTCINR", "ETHINR"]
    db, repos, exchange, fee_exchange, clock, dca, order_monitor, notifier = await _build_stack(tmp_path / "b.sqlite3", symbols)
    for s in symbols:
        exchange.set_price(s, 100.0)
        await _start_default_grid(dca, s)

    engine = ReplayEngine(repos, dca, order_monitor, exchange, clock)
    feed = sorted(_flat_candles("BTCINR", 30) + _flat_candles("ETHINR", 30), key=lambda c: c.timestamp)
    stats = await engine.run(feed)

    assert stats.symbols_seen == {"BTCINR", "ETHINR"}
    assert stats.candles_processed == 60
    await db.close()


async def test_replay_one_symbol_out_of_multi_symbol_feed(tmp_path):
    symbols = ["BTCINR", "ETHINR"]
    db, repos, exchange, fee_exchange, clock, dca, order_monitor, notifier = await _build_stack(tmp_path / "c.sqlite3", symbols)
    for s in symbols:
        exchange.set_price(s, 100.0)
        await _start_default_grid(dca, s)

    engine = ReplayEngine(repos, dca, order_monitor, exchange, clock)
    feed = sorted(_flat_candles("BTCINR", 20) + _flat_candles("ETHINR", 20), key=lambda c: c.timestamp)
    stats = await engine.run(feed, symbols=["BTCINR"])

    assert stats.symbols_seen == {"BTCINR"}
    assert stats.candles_processed == 20
    await db.close()


async def test_stop_halts_the_loop_early(tmp_path):
    db, repos, exchange, fee_exchange, clock, dca, order_monitor, notifier = await _build_stack(tmp_path / "d.sqlite3", ["BTCINR"])
    exchange.set_price("BTCINR", 100.0)
    await _start_default_grid(dca, "BTCINR")

    engine = ReplayEngine(repos, dca, order_monitor, exchange, clock)
    feed = _flat_candles("BTCINR", 100)

    async def stop_after_5(index: int) -> None:
        if index == 4:
            engine.stop()

    stats = await engine.run(feed, on_candle=stop_after_5)
    assert stats.candles_processed == 5
    await db.close()


async def test_pause_blocks_until_resumed(tmp_path):
    import asyncio
    db, repos, exchange, fee_exchange, clock, dca, order_monitor, notifier = await _build_stack(tmp_path / "e.sqlite3", ["BTCINR"])
    exchange.set_price("BTCINR", 100.0)
    await _start_default_grid(dca, "BTCINR")

    engine = ReplayEngine(repos, dca, order_monitor, exchange, clock)
    feed = _flat_candles("BTCINR", 10)
    engine.pause()

    task = asyncio.create_task(engine.run(feed))
    await asyncio.sleep(0.05)
    assert not task.done(), "run() must block while paused"
    engine.resume()
    stats = await asyncio.wait_for(task, timeout=5)
    assert stats.candles_processed == 10
    await db.close()


def test_seek_returns_candles_at_or_after_timestamp():
    feed = _flat_candles("BTCINR", 10, interval=60.0)  # timestamps 0,60,...,540
    seeked = ReplayEngine.seek(feed, 180.0)
    assert seeked[0].timestamp == 180.0
    assert len(seeked) == 7
    # original feed is untouched
    assert feed[0].timestamp == 0.0


async def test_on_candle_hook_invoked_once_per_candle(tmp_path):
    db, repos, exchange, fee_exchange, clock, dca, order_monitor, notifier = await _build_stack(tmp_path / "f.sqlite3", ["BTCINR"])
    exchange.set_price("BTCINR", 100.0)
    await _start_default_grid(dca, "BTCINR")

    engine = ReplayEngine(repos, dca, order_monitor, exchange, clock)
    feed = _flat_candles("BTCINR", 15)
    seen_indices = []

    async def record(index: int) -> None:
        seen_indices.append(index)

    await engine.run(feed, on_candle=record)
    assert seen_indices == list(range(15))
    await db.close()


async def test_trigger_fires_correctly_within_replay(tmp_path):
    """A real end-to-end check: a profit target reached mid-replay must
    actually produce a sell, exercised through the real DCAManager."""
    db, repos, exchange, fee_exchange, clock, dca, order_monitor, notifier = await _build_stack(tmp_path / "g.sqlite3", ["BTCINR"])
    exchange.set_price("BTCINR", 100.0)
    grid_id = await _start_default_grid(dca, "BTCINR", profit_percentage=5.0)

    engine = ReplayEngine(repos, dca, order_monitor, exchange, clock)
    # Rise straight through the profit target (105) and stay there.
    feed = [
        Candle(symbol="BTCINR", timestamp=0, open=100, high=100, low=100, close=100),
        Candle(symbol="BTCINR", timestamp=60, open=100, high=110, low=100, close=108),
        Candle(symbol="BTCINR", timestamp=120, open=108, high=108, low=108, close=108),
    ]
    await engine.run(feed)

    orders = await repos.orders.list_for_grid(grid_id)
    sell_orders = [o for o in orders if o["side"] == "sell"]
    assert sell_orders, "profit target crossed mid-replay must produce a real sell order"
    await db.close()


async def test_restart_simulation_continues_correctly(tmp_path):
    """Simulates a genuine process restart mid-replay: a completely fresh
    set of DCAManager/OrderMonitor/RiskManager/Notifier objects (plus
    RecoveryManager.recover()), same underlying DB file, continuing the
    same feed — must not lose or duplicate any state."""
    db_path = tmp_path / "restart.sqlite3"
    db, repos, exchange, fee_exchange, clock, dca, order_monitor, notifier = await _build_stack(db_path, ["BTCINR"])
    exchange.set_price("BTCINR", 100.0)
    grid_id = await _start_default_grid(dca, "BTCINR", profit_percentage=5.0)

    engine = ReplayEngine(repos, dca, order_monitor, exchange, clock)
    first_half = [
        Candle(symbol="BTCINR", timestamp=0, open=100, high=100, low=100, close=100),
        Candle(symbol="BTCINR", timestamp=60, open=100, high=102, low=100, close=102),
    ]
    await engine.run(first_half)
    grid_before = await repos.grids.get(grid_id)
    assert grid_before["status"] == GridStatus.ACTIVE.value

    # --- simulate restart: close everything, rebuild fresh against the same file ---
    await db.close()
    db2, repos2, exchange2, fee_exchange2, clock2, dca2, order_monitor2, notifier2 = await _build_stack(db_path, ["BTCINR"], seed=2)
    recovery = RecoveryManager(exchange=fee_exchange2, repos=repos2, notifier=notifier2, dca_manager=dca2)
    await recovery.recover()

    engine2 = ReplayEngine(repos2, dca2, order_monitor2, exchange2, clock2)
    engine2.stats = engine.stats
    second_half = [
        Candle(symbol="BTCINR", timestamp=120, open=102, high=108, low=100, close=106),
        Candle(symbol="BTCINR", timestamp=180, open=106, high=106, low=106, close=106),
    ]
    await engine2.run(second_half)

    grid_after = await repos2.grids.get(grid_id)
    orders_after = await repos2.orders.list_for_grid(grid_id)
    sells_after = [o for o in orders_after if o["side"] == "sell"]
    assert sells_after, "the profit trigger crossed AFTER the simulated restart must still fire"
    assert grid_after is not None

    total_stats = engine2.stats
    assert total_stats.candles_processed == 4  # 2 before + 2 after the restart

    await db2.close()

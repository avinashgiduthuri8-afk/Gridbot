"""Command-line entry point for the replay & stress-testing framework.

Example:
    python replay.py --symbols BTCINR ETHINR SOLINR \\
        --scenario bull --speed 100x --report report.json

    python replay.py --symbols BTCINR --data-dir ./historical \\
        --from 2025-01-01 --to 2025-06-30 --restart-test

See replay/README.md (module docstrings) for the full option list.
"""
from __future__ import annotations

import argparse
import asyncio
import random
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

from config.constants import GridStatus
from config.settings import RiskSettings
from exchange.base import MarketInfo
from replay.counting_notifier import CountingNotifier
from replay.data_loader import Candle, DataLoaderError, HistoricalDataLoader
from replay.engine import ReplayClock, ReplayEngine
from replay.fee_exchange import FeeSimulatingPaperExchange
from replay.market_data_exchange import ReplayMarketDataExchange
from replay.report import ResourceSampler, build_report
from replay.scenarios import SCENARIO_NAMES, generate_multi_symbol_scenario
from replay.validation import ReplayValidator
from risk.risk_manager import RiskManager
from storage.database import Database
from storage.repositories import Repositories
from trading.dca_manager import DCAManager
from trading.mixed_order_manager import MixedOrderManager
from trading.order_manager import OrderManager
from trading.order_monitor import OrderMonitor
from trading.recovery import RecoveryManager
from utils.logger import get_logger

log = get_logger("trading")

DEFAULT_MARKET_INFO_KWARGS = dict(
    base_currency_precision=2, target_currency_precision=5,
    min_quantity=0.001, min_amount=10.0, step_size=1e-5,
)

DEFAULT_GRID_PARAMS = dict(
    base_investment=500.0, dip_buy_amount=100.0, dip_percentage=5.0,
    profit_sell_amount=150.0, profit_percentage=5.0, max_levels=10,
    stop_loss_percentage=20.0, mode="paper",
)

MULTI_GRID_VARIANTS = [
    dict(DEFAULT_GRID_PARAMS, profit_percentage=3.0, stop_loss_percentage=15.0),
    dict(DEFAULT_GRID_PARAMS, profit_percentage=5.0, stop_loss_percentage=20.0,
         trailing_enabled=True, trailing_percentage=2.0),
    dict(DEFAULT_GRID_PARAMS, profit_percentage=8.0, stop_loss_percentage=30.0),
]


def _parse_speed(raw: str | None) -> float | None:
    if raw is None:
        return None
    raw = raw.strip().lower().rstrip("x")
    if raw in ("", "max", "0"):
        return None
    return float(raw)


def _parse_date(raw: str) -> float:
    return datetime.strptime(raw, "%Y-%m-%d").replace(tzinfo=timezone.utc).timestamp()


def build_arg_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="replay.py", description=__doc__)
    p.add_argument("--symbols", nargs="+", required=True, help="Symbols to replay, e.g. BTCINR ETHINR")
    p.add_argument("--from", dest="date_from", help="Start date YYYY-MM-DD (informational when using --scenario)")
    p.add_argument("--to", dest="date_to", help="End date YYYY-MM-DD (informational when using --scenario)")
    p.add_argument("--speed", default=None, help="Replay speed, e.g. 10x, 100x, 1000x. Omit for max speed.")
    p.add_argument("--scenario", choices=SCENARIO_NAMES, help="Generate a synthetic scenario instead of loading files")
    p.add_argument("--bars", type=int, default=2000, help="Number of candles to generate for --scenario (default 2000)")
    p.add_argument("--interval-seconds", type=float, default=60.0, help="Seconds per candle (default 60)")
    p.add_argument("--data-dir", help="Directory containing {SYMBOL}.csv historical files")
    p.add_argument("--data-format", choices=("csv", "json"), default="csv")
    p.add_argument("--db", default=None, help="SQLite file to use (default: a fresh temp file)")
    p.add_argument("--report", help="Path to write the JSON report to")
    p.add_argument("--restart-test", action="store_true", help="Simulate a process restart partway through the replay")
    p.add_argument("--multi-grid", action="store_true", help="Create several grids per symbol instead of one")
    p.add_argument("--no-sub-tick", action="store_true", help="Only feed candle close prices, not open/high/low/close")
    p.add_argument("--fee-rate", type=float, default=0.001, help="Simulated trading fee, as a fraction (default 0.001 = 0.1%%)")
    p.add_argument("--seed", type=int, default=42)
    p.add_argument("--manual-trade-every", type=int, default=0,
                    help="Every N candles, exercise a manual buy/sell on a random active grid (0 = disabled)")
    p.add_argument(
        "--wallet-balance", type=float, default=None,
        help=(
            "Enable real-capital replay mode with this starting INR balance. "
            "Grids are created in mode='real' instead of 'paper', and the "
            "simulated exchange tracks a genuinely depleting/replenishing "
            "balance (debited on buys, credited on sells) so RiskManager's "
            "capital-constraint checks (max_capital_per_coin, "
            "min_wallet_balance) actually get exercised — mode='paper' grids "
            "always use a fixed, non-depleting balance by design. Omit for "
            "existing paper-mode behavior (default)."
        ),
    )
    return p


async def _build_feed(args: argparse.Namespace) -> tuple[list[Candle], dict[str, MarketInfo]]:
    market_infos = {s.upper(): MarketInfo(symbol=s.upper(), **DEFAULT_MARKET_INFO_KWARGS) for s in args.symbols}

    if args.scenario:
        start_ts = _parse_date(args.date_from) if args.date_from else 0.0
        per_symbol = generate_multi_symbol_scenario(
            args.scenario, args.symbols, bars=args.bars,
            interval_seconds=args.interval_seconds, start_timestamp=start_ts, seed=args.seed,
        )
        loader = HistoricalDataLoader()
        for symbol, candles in per_symbol.items():
            loader.add_candles(symbol, candles)
        return loader.merged_feed(), market_infos

    if not args.data_dir:
        raise SystemExit("Either --scenario or --data-dir is required.")

    loader = HistoricalDataLoader()
    data_dir = Path(args.data_dir)
    for symbol in args.symbols:
        path = data_dir / f"{symbol}.{args.data_format}"
        if not path.exists():
            raise SystemExit(f"No data file found for {symbol} at {path}")
        if args.data_format == "csv":
            loader.load_csv(symbol, path)
        else:
            loader.load_json(symbol, path)

    feed = loader.merged_feed()
    if args.date_from:
        lo = _parse_date(args.date_from)
        feed = [c for c in feed if c.timestamp >= lo]
    if args.date_to:
        hi = _parse_date(args.date_to)
        feed = [c for c in feed if c.timestamp <= hi]
    if not feed:
        raise SystemExit("No candles in the requested date range.")
    return feed, market_infos


def _build_stack(
    db_path: str, exchange: ReplayMarketDataExchange, clock: ReplayClock,
    risk_settings: RiskSettings, fee_rate: float, seed: int,
    wallet_balance: float | None = None,
) -> tuple[Database, FeeSimulatingPaperExchange]:
    """Builds one full, independent trading stack against db_path. Called
    twice for --restart-test to simulate a genuine process restart: a
    completely new set of Python objects, same underlying database.

    wallet_balance, if given, enables real-capital tracking on the
    exchange — see FeeSimulatingPaperExchange's docstring."""
    db = Database(db_path)
    fee_exchange = FeeSimulatingPaperExchange(
        exchange, rng=random.Random(seed), time_fn=clock.now,
        latency_seconds_range=(0.0, 0.0),  # replay ticks are the clock; no artificial latency needed
        partial_fill_probability=0.0, fee_rate=fee_rate,
        initial_balance_inr=wallet_balance,
    )
    return db, fee_exchange


async def _init_stack(
    db: Database, fee_exchange: FeeSimulatingPaperExchange, risk_settings: RiskSettings,
) -> tuple[Repositories, DCAManager, OrderMonitor, CountingNotifier]:
    await db.connect()
    await db.migrate()
    repos = Repositories(db)
    notifier = CountingNotifier()
    risk = RiskManager(risk_settings, repos)
    await risk.load_emergency_stop()
    real_om = OrderManager(fee_exchange, repos)
    paper_om = OrderManager(fee_exchange, repos)
    mixed_om = MixedOrderManager(real=real_om, paper=paper_om, repos=repos)
    dca = DCAManager(exchange=fee_exchange, repos=repos, order_manager=mixed_om, notifier=notifier, risk=risk)
    order_monitor = OrderMonitor(
        repos=repos, order_manager=mixed_om, dca_manager=dca, notifier=notifier,
        exchange=fee_exchange, poll_interval=1,
    )
    return repos, dca, order_monitor, notifier


async def _create_grids(
    dca: DCAManager, symbols: list[str], multi_grid: bool, real_capital_mode: bool = False,
) -> None:
    """Creates one grid per symbol. --multi-grid cycles through several
    different grid configurations across symbols (to exercise varied
    parameters — trailing enabled, different profit/stop-loss percentages
    — under the same replay), rather than multiple grids on one symbol:
    only one ACTIVE grid per symbol is ever allowed (RiskManager enforces
    this), so trying several configs on the same symbol would just have
    the first succeed and the rest get correctly rejected.

    real_capital_mode (set when --wallet-balance is given) creates grids
    with mode="real" instead of "paper": DCAManager._get_wallet_balance()
    hardcodes a fixed, non-depleting balance for mode="paper" regardless of
    what the exchange reports, so real capital constraints can only ever be
    exercised through mode="real" grids."""
    mode = "real" if real_capital_mode else "paper"
    for i, symbol in enumerate(symbols):
        variant = MULTI_GRID_VARIANTS[i % len(MULTI_GRID_VARIANTS)] if multi_grid else DEFAULT_GRID_PARAMS
        params = dict(variant, symbol=symbol, entry_price=0, mode=mode)
        try:
            await dca.start_grid(params)
        except ValueError as exc:
            log.warning("Could not start grid for %s: %s", symbol, exc)


async def run_replay(args: argparse.Namespace) -> int:
    feed, market_infos = await _build_feed(args)
    if not feed:
        print("Nothing to replay — empty feed.", file=sys.stderr)
        return 1

    db_path = args.db or f"/tmp/replay_{int(time.time() * 1000)}.sqlite3"
    speed = _parse_speed(args.speed)
    risk_settings = RiskSettings(
        max_total_capital=10_000_000, max_capital_per_coin=5_000_000,
        max_simultaneous_grids=100, min_wallet_balance=0, daily_loss_limit=5_000_000,
    )

    exchange = ReplayMarketDataExchange()
    for symbol, info in market_infos.items():
        exchange.register_market(symbol, info)
    clock = ReplayClock()

    db, fee_exchange = _build_stack(
        db_path, exchange, clock, risk_settings, args.fee_rate, args.seed,
        wallet_balance=args.wallet_balance,
    )
    repos, dca, order_monitor, notifier = await _init_stack(db, fee_exchange, risk_settings)

    # Seed the exchange with the first price for every symbol so grid
    # creation (which reads a live ticker for entry_price=0) works.
    first_price_by_symbol: dict[str, float] = {}
    for candle in feed:
        if candle.symbol not in first_price_by_symbol:
            first_price_by_symbol[candle.symbol] = candle.open
    for symbol, price in first_price_by_symbol.items():
        exchange.set_price(symbol, price)

    await _create_grids(dca, args.symbols, args.multi_grid, real_capital_mode=args.wallet_balance is not None)

    engine = ReplayEngine(
        repos, dca, order_monitor, exchange, clock,
        sub_tick_within_candle=not args.no_sub_tick, speed=speed,
        candle_interval_seconds=args.interval_seconds,
    )

    sampler = ResourceSampler()
    manual_trade_counter = {"count": 0}
    rng_manual = random.Random(args.seed + 1000)
    start_wall = time.monotonic()

    async def _maybe_manual_trade(dca_manager: DCAManager, repos_ref: Repositories, index: int) -> None:
        if not args.manual_trade_every or index % args.manual_trade_every != 0:
            return
        active = await repos_ref.grids.list_by_status([GridStatus.ACTIVE.value])
        if not active:
            return
        grid = rng_manual.choice(active)
        try:
            if rng_manual.random() < 0.5:
                await dca_manager.manual_buy(grid["grid_id"], DEFAULT_GRID_PARAMS["dip_buy_amount"])
            else:
                await dca_manager.manual_sell(grid["grid_id"], None)
            manual_trade_counter["count"] += 1
        except ValueError as exc:
            log.info("Manual-trade stress hook: %s", exc)

    if args.restart_test and len(feed) > 1:
        midpoint = len(feed) // 2
        first_half, second_half = feed[:midpoint], feed[midpoint:]
        await engine.run(first_half, symbols=args.symbols, on_candle=lambda idx: _maybe_manual_trade(dca, repos, idx))
        sampler.sample()

        log.info("--restart-test: tearing down the trading stack and rebuilding fresh instances")
        await db.close()
        db2, fee_exchange2 = _build_stack(
            db_path, exchange, clock, risk_settings, args.fee_rate, args.seed,
            wallet_balance=args.wallet_balance,
        )
        repos2, dca2, order_monitor2, notifier2 = await _init_stack(db2, fee_exchange2, risk_settings)

        recovery = RecoveryManager(exchange=fee_exchange2, repos=repos2, notifier=notifier2, dca_manager=dca2)
        await recovery.recover()

        engine2 = ReplayEngine(
            repos2, dca2, order_monitor2, exchange, clock,
            sub_tick_within_candle=not args.no_sub_tick, speed=speed,
            candle_interval_seconds=args.interval_seconds,
        )
        engine2.stats = engine.stats  # keep one running stats object across the "restart"
        await engine2.run(second_half, symbols=args.symbols, on_candle=lambda idx: _maybe_manual_trade(dca2, repos2, idx))
        repos, notifier = repos2, notifier2
        final_stats = engine2.stats
    else:
        await engine.run(feed, symbols=args.symbols, on_candle=lambda idx: _maybe_manual_trade(dca, repos, idx))
        final_stats = engine.stats

    sampler.sample()
    replay_duration = time.monotonic() - start_wall

    validator = ReplayValidator(repos)
    validation = await validator.validate()

    report = await build_report(
        repos=repos, stats=final_stats, validation=validation,
        replay_duration_seconds=replay_duration, speed=speed, sampler=sampler,
        trailing_activations=notifier.counts.get("trailing_activated", 0),
        stop_loss_activations=notifier.counts.get("stop_loss_triggered", 0),
        manual_trades=manual_trade_counter["count"], db_path=db_path,
    )

    print(report.render_text())
    if args.report:
        Path(args.report).write_text(report.render_json())
        print(f"\nJSON report written to {args.report}")

    if args.restart_test and len(feed) > 1:
        await db2.close()  # db was already closed mid-run when we rebuilt the stack
    else:
        await db.close()

    return 0 if report.passed else 2


def main(argv: list[str] | None = None) -> int:
    parser = build_arg_parser()
    args = parser.parse_args(argv)
    try:
        return asyncio.run(run_replay(args))
    except DataLoaderError as exc:
        print(f"Data loading error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())

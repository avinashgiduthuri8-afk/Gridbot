# Replay & Stress Testing Framework

Accelerated historical-data replay for PROJECT-ALPHA's trading engine.
Feeds price data (real historical or synthetically generated) into the
**real, unmodified** `DCAManager` / `OrderMonitor` / `RiskManager` — every
trigger evaluation, order placement, and fill goes through actual
production code, not a simulation of it. See `replay/__init__.py` for the
module-by-module breakdown.

Contents:
- [Quick start](#quick-start)
- [CLI reference](#cli-reference)
- [Scenarios](#scenarios)
- [Real historical data](#real-historical-data)
- [Validation checks](#validation-checks)
- [Report format](#report-format)
- [Restart / crash simulation](#restart--crash-simulation)
- [Architecture notes](#architecture-notes)

## Quick start

```bash
# Fast synthetic run, single symbol, default grid config
python replay.py --symbols BTCINR --scenario bull --bars 2000

# Multiple symbols, varied grid configs, write a JSON report
python replay.py --symbols BTCINR ETHINR SOLINR --scenario high_volatility \
    --bars 5000 --multi-grid --report report.json

# Simulate a bot process crash/restart partway through
python replay.py --symbols BTCINR --scenario flash_crash --bars 3000 --restart-test

# Replay real historical data (see "Real historical data" below)
python replay.py --symbols BTCINR --data-dir ./historical \
    --from 2025-01-01 --to 2025-06-30
```

Exit code is `0` if every validation check passed, `2` if any failed, `1`
on a setup/data error (e.g. missing data file).

## CLI reference

| Flag | Description |
|---|---|
| `--symbols SYM [SYM ...]` | **Required.** Symbols to replay, e.g. `BTCINR ETHINR`. |
| `--scenario NAME` | Generate synthetic data instead of loading files. See [Scenarios](#scenarios). |
| `--bars N` | Candle count for `--scenario` (default 2000). |
| `--interval-seconds N` | Seconds per candle for `--scenario` (default 60). |
| `--data-dir DIR` | Directory containing `{SYMBOL}.csv`/`.json` files (real historical data). |
| `--data-format {csv,json}` | Format of files under `--data-dir` (default csv). |
| `--from DATE` / `--to DATE` | `YYYY-MM-DD`. Filters real data by date; sets the synthetic feed's start timestamp for `--scenario`. |
| `--speed N[x]` | Throttle to roughly real-time / N between candles (e.g. `100x`). Omit for max speed — the normal mode for stress testing. |
| `--db PATH` | SQLite file to use. Default: a fresh temp file (so runs never collide). |
| `--report PATH` | Write the full JSON report to this path (also always printed as text to stdout). |
| `--restart-test` | Simulate a bot process crash/restart at the halfway point of the feed — tears down and rebuilds the entire trading stack, runs `RecoveryManager`, and continues. |
| `--multi-grid` | Cycle through several different grid configurations across symbols (varied profit %, stop-loss %, trailing on/off), instead of one identical config per symbol. **Note:** this varies config *across symbols*, not multiple grids on one symbol — only one ACTIVE grid per symbol is ever allowed (a real `RiskManager` rule), so stacking configs on a single symbol would just have the first succeed and the rest correctly rejected. |
| `--no-sub-tick` | Only feed each candle's close price, not open/high/low/close as four sub-ticks. Faster, coarser — a trigger that would only fire mid-bar won't be caught. |
| `--fee-rate N` | Simulated trading fee as a fraction (default `0.001` = 0.1%, CoinDCX's typical taker fee). |
| `--seed N` | RNG seed for `--scenario` and the fee simulator (default 42) — same seed reproduces the same run. |
| `--manual-trade-every N` | Every N candles, exercise a manual buy or sell on a random active grid (stress-tests manual-trade compatibility; 0 = disabled). |

## Scenarios

`replay/scenarios.py` — deterministic given the same seed. All eight:

| Name | Shape |
|---|---|
| `bull` | Steady upward drift, small noise band. |
| `bear` | Steady downward drift, small noise band. |
| `sideways` | No net drift, small noise band. |
| `flash_crash` | Flat, then a sharp 1–3%/bar drop for the middle third of the run, then a partial recovery — the classic "V". |
| `gap_up` | Flat, with one single 5–15% jump bar at the midpoint. |
| `gap_down` | Flat, with one single 5–15% drop bar at the midpoint. |
| `high_volatility` | Wide (±2%/bar) noise band, no net drift. |
| `low_volatility` | Very narrow (±0.05%/bar) noise band, no net drift. |

Prices are rounded to a realistic precision (2 decimals by default) —
unrounded synthetic prices previously tripped `DCAManager`'s own
price-precision validation on nearly every tick, which is a real
production safety check working as intended, not a bug (see git history /
session notes for how this was found and fixed).

`generate_multi_symbol_scenario()` gives each symbol its own seeded RNG
stream (`seed + index`), so symbols don't move in lockstep even under the
same named scenario.

## Real historical data

This sandbox has no live network access to CoinDCX, so real data must be
fetched from an environment that does. `replay/fetch_coindcx_history.py`
does this against CoinDCX's public candles API (no auth required):

```bash
pip install requests --break-system-packages
python replay/fetch_coindcx_history.py \
    --symbols BTCINR ETHINR SOLINR XRPINR DOGEINR AVAXINR ADAINR \
    --interval 1h --months 6 --out-dir ./historical
```

This writes one `{SYMBOL}.csv` per symbol in the format
`HistoricalDataLoader` expects (`timestamp,open,high,low,close,volume`,
unix seconds). It looks up each symbol's actual CoinDCX `pair` identifier
from the public `markets_details` endpoint rather than guessing the pair
string format, and paginates automatically (the candles API caps at 1000
per request).

Then replay it:

```bash
python replay.py --symbols BTCINR ETHINR SOLINR --data-dir ./historical \
    --from 2025-01-01 --to 2025-06-30
```

`HistoricalDataLoader` (`replay/data_loader.py`) also supports `.json`
(a list of candle objects, or `{"candles": [...]}`) and SQLite tables, if
your data comes from elsewhere.

## Validation checks

Run automatically at the end of every replay (`replay/validation.py`),
each reported as `[PASS]`/`[FAIL]` with a human-readable detail:

| Check | What it catches |
|---|---|
| `no_active_grid_with_zero_quantity` | A grid marked ACTIVE with no position — should have been closed. |
| `no_negative_quantity` | Any grid with negative `total_quantity` — impossible in correct accounting. |
| `no_negative_investment` | Any grid with negative `total_investment`. |
| `no_orphan_orders` | An order referencing a grid_id that no longer exists (defense-in-depth — the DB's own foreign key constraint should already prevent this). |
| `no_duplicate_exchange_order_ids` | Two local orders sharing one exchange fill — a reconciliation bug. |
| `trade_history_references_valid_grids` | Every trade_history row points at a real grid. |
| `completed_cycles_backed_by_sell_history` | A grid can't report more completed cycles than it has recorded sells. |
| `stopped_grids_no_negative_remainder` | A STOPPED grid never has a negative quantity/investment remainder. |

`ReplayValidator(repos).validate()` returns a `ValidationReport` with
`.all_passed`, `.failed`, and the full `.checks` list — usable
programmatically, not just via the CLI.

## Report format

Every run prints a text report and (with `--report PATH`) writes the same
data as JSON, in three sections plus validation:

- **Replay summary** — symbols, date range, candles/sub-ticks processed,
  trigger evaluations, speed setting.
- **Trading summary** — buys, sells, dust write-offs, realized profit, win
  rate, max drawdown (computed on cumulative realized P&L across sells in
  execution order — a simple proxy, not a mark-to-market equity curve),
  profit factor (gross profit / gross loss; `None` if there were no
  losing trades), completed cycles, trailing-TP activations, stop-loss
  triggers, manual trades exercised.
- **System summary** — replay wall-clock duration, peak RSS, CPU%,
  exception count, DB size (main file + WAL/SHM). RSS/CPU require
  `psutil`; if it isn't installed, those fields are `None` rather than
  failing the run.
- **Validation** — every check from the table above, PASS/FAIL with
  detail, plus an overall PASS/FAIL used as the process exit code.

## Restart / crash simulation

`--restart-test` simulates the bot **process** crashing and restarting
mid-replay: it tears down `Repositories`/`DCAManager`/`OrderMonitor`/
`RiskManager`/`Notifier` and builds a completely fresh set of Python
objects against the same SQLite file, runs the real `RecoveryManager`,
and continues the remaining feed. This is what `main.py` does on every
real restart.

For more surgical crash testing, see `tests/test_replay_crash_simulation.py`
for the pattern of keeping the **exchange** object alive across a
simulated restart (a real exchange like CoinDCX doesn't restart when your
bot does) while only rebuilding the bot-side stack — used to test restart
recovery mid-pending-buy, mid-pending-sell, and mid-active-trailing-TP
with an order in flight.

Two related scenarios are explicitly **out of scope** for this framework,
not gaps:
- "Restart during backup" — the Google Drive backup system is unrelated
  to price replay; it's covered by `tests/test_backup_integrity.py`,
  `tests/test_restorebackup.py`, etc.
- "Restart during a raw database write" — simulating a torn write means
  corrupting the SQLite file mid-transaction, which tests SQLite/aiosqlite's
  own WAL crash-consistency guarantees, not this trading engine's logic.

## Architecture notes

- **No duplicate trading logic.** The engine drives the real
  `DCAManager.check_grid_triggers()` and reuses `OrderMonitor._poll_once()`
  for fill resolution — the same functions a live deployment calls.
- **Exchange simulation is layered, not reimplemented.**
  `ReplayMarketDataExchange` only answers `get_ticker()`/`get_market_info()`
  from the replay feed; all order simulation (fills, slippage, latency,
  partial fills) is delegated to the existing, already-tested
  `exchange.paper_exchange.PaperExchangeClient`. `FeeSimulatingPaperExchange`
  adds only what that class deliberately doesn't do — charging a trading
  fee on fills — as a thin subclass.
- **Notifications are counted, not sent.** `CountingNotifier` overrides
  `send()` to a no-op (replay must never spam a real Telegram chat) but
  still calls through to each real `Notifier` method for its message
  formatting, so the counts (trailing activations, stop-loss triggers,
  dust write-offs) reflect the actual logic paths taken.
- **A virtual clock, not wall-clock time.** `ReplayClock` is injected into
  `FeeSimulatingPaperExchange` as its `time_fn`, so simulated order latency
  advances with replay ticks — this is what makes 1000x-speed replay of
  months of data possible without literally waiting months.

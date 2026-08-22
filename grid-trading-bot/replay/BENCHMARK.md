# Replay Framework — Performance Benchmark

All numbers below are from real runs of `replay.py` against synthetic
scenarios, executed in the development sandbox (single container, shared
CPU, Python 3.12). They are a baseline for *relative* comparison (e.g. "did
a later change slow things down"), not a guarantee of throughput on
Railway or any other production host — re-run these on your actual
deployment target before relying on the absolute numbers.

## Methodology

- `ResourceSampler` (`replay/report.py`) uses `psutil` to sample RSS and
  CPU% for the current process. Peak RSS is the maximum observed across
  all samples taken during a run; CPU% is `Process.cpu_percent()` measured
  over the whole run's wall-clock duration.
- "Sub-ticks" = candles × 4 when sub-tick mode is on (open/high/low/close
  fed as four separate price points per candle, the default — see
  `--no-sub-tick` to disable), which is also roughly proportional to the
  number of `check_grid_triggers()` calls per active grid.
- All runs used the default fee-simulating paper exchange with zero
  artificial latency (`latency_seconds_range=(0.0, 0.0)`), since replay
  throughput should reflect trading-logic cost, not simulated network
  delay.
- DB size includes the SQLite main file plus its `-wal`/`-shm` files
  (WAL mode keeps most recent writes there, not in the main file).

## Results

### Run 1 — moderate, 3 symbols, sub-ticked

| Metric | Value |
|---|---|
| Symbols | BTCINR, ETHINR, SOLINR |
| Scenario | sideways |
| Candles | 15,000 (5,000/symbol) |
| Sub-ticks | 60,000 |
| Wall time | 12.75s |
| Throughput | ~1,176 candles/sec, ~4,700 sub-ticks/sec |

### Run 2 — large multi-symbol stress, with manual-trade hook

| Metric | Value |
|---|---|
| Symbols | 10 (BTCINR, ETHINR, SOLINR, XRPINR, DOGEINR, AVAXINR, ADAINR, DOTINR, LTCINR, LINKINR) |
| Scenario | high_volatility |
| Grids | `--multi-grid` (varied config per symbol) |
| Candles | 100,000 (10,000/symbol) |
| Sub-ticks | 400,000 |
| Wall time | 41.95s |
| Throughput | ~2,384 candles/sec, ~9,536 sub-ticks/sec |
| Trades recorded | 88 (47 sells, 8 dust write-offs, 47 completed cycles) |
| Manual trades (hook, every 500 candles) | executed successfully throughout |
| Peak RSS | 67.7 MB |
| CPU | ~100% (single core; this is a pure-Python, single-threaded workload) |
| DB size (main + WAL) | ~4.3 MB |
| Exceptions | 0 |
| Validation | ALL PASS |

### Run 3 — memory-over-time sampling (leak check), 5 symbols, 150k candles

| Metric | Value |
|---|---|
| Symbols | 5 |
| Candles | 150,000 (30,000/symbol) |
| Sub-ticks | 600,000 |
| Sampling | peak RSS sampled every 20,000 candles |
| Memory trend | flat at ~84.7 MB for the entire run — **no growth observed** |
| Exceptions | 0 |
| Validation | ALL PASS |

**Interpretation:** memory stayed essentially constant across a 4x longer
run than the stress test above, which is the expected signature of no
leak — a real leak would show RSS climbing roughly linearly with candles
processed. This is not a substitute for a multi-day continuous soak test
(which also exercises the real Python/asyncio runtime's long-run behavior,
OS-level file handle accumulation, log file growth, etc.), but it rules out
the most common replay-specific culprits: unbounded in-memory lists,
growing dicts keyed by ever-new IDs, or event-loop task leaks.

## Notes on trade volume

Runs 2 and 3 produced modest trade counts (tens, not thousands) relative
to candle count. This is a property of the *scenario and grid design*, not
a throughput limitation: once a grid is closed (dust write-off, stop-loss,
or a full profit-take that empties the position), nothing automatically
opens a new one for that symbol — exactly like the real bot, where a fresh
`/newgrid` is a deliberate user action. Driving much higher trade volume
in a single replay run would require either many more symbols/grids, a
scenario with more profit-target crossings, or a CLI option to
auto-restart a grid after closure (not implemented, since it doesn't
correspond to any real production behavior — adding it purely to inflate
a benchmark number would make the benchmark less representative, not
more).

## Reproducing these numbers

```bash
python replay.py --symbols BTCINR ETHINR SOLINR SOLINR XRPINR DOGEINR \
    AVAXINR ADAINR DOTINR LTCINR LINKINR --scenario high_volatility \
    --bars 10000 --multi-grid --manual-trade-every 500 \
    --db /tmp/bench.sqlite3 --report /tmp/bench.json
```

The report's `system` section includes `peak_rss_mb`, `cpu_percent`,
`replay_duration_seconds`, and `db_size_bytes` for every run — no separate
benchmarking harness is needed; just check the numbers in any report.

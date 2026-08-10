---
name: Price Monitor Architecture
description: Key design decisions for the PriceMonitor class and its integration.
---

## Rule
`PriceMonitor._run_cycle` is the single owner of `api_ok` and `consecutive_failures`.
`_run` must NOT reset these after a successful cycle return — it only increments them on unexpected exceptions that escape `_run_cycle` entirely.

**Why:** `_run_cycle` sets degraded states for partial failures (missing symbols in batch response). If `_run` resets them after every clean return, those partial failures become invisible to `/monitor`.

**How to apply:** Any future change to the run loop must preserve this contract. If you add outer-loop success handling, do not touch `api_ok` or `consecutive_failures` there.

## Batch ticker fetch
`get_tickers_batch(symbols)` hits `/exchange/ticker` once per cycle and filters client-side. This is in `CoinDCXClient` (override) and `PaperExchangeClient` (delegates to real). The base class has a default fallback that calls `get_ticker` individually.

## Interval persistence
Stored in `monitor_settings` table (key: `price_monitor_interval`). `MonitorSettingsRepository.get_interval()` returns `None` when not set — callers must fall back to their own default, not a hardcoded constant, so PRICE_POLL_INTERVAL_SECONDS env var is honoured on first start.

## Valid intervals
(2, 5, 10, 15, 30) seconds — enforced in both the repository and the monitor. Stored in `VALID_MONITOR_INTERVALS` in `storage/repositories.py`.

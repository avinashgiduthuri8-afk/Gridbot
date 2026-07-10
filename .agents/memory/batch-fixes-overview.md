---
name: Batch fixes overview
description: Summary of all batches applied, test count, and where to find the full roadmap.
---

**Batches 1–4 applied. 335 tests pass.**

Full 40-item roadmap is in replit.md.

Batch 4 items completed:
- #27 Ticker caching (4s→1.5s TTL, single-flight lock, shared across get_ticker/get_tickers_batch/get_extended_ticker)
- #7 Duplicate order prevention — stuck SUBMITTED orders resolved in order monitor sync cycle (resolve_uncertain_submitted, exchange-failure defers rather than FAILing)
- #17 Orphan order Telegram notifications — _detect_orphan_orders sends orphan_orders_detected message; no auto-cancel
- #8 Dynamic price formatting — fmt_price() in utils/helpers.py; used in notifier.py and formatters.py (heuristic: ≥100→2dp, ≥1→4dp, ≥0.01→6dp, <0.01→8dp)

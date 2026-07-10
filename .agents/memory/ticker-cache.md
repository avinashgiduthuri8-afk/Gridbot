---
name: Ticker cache design
description: How and why the CoinDCX ticker response is cached, including TTL and concurrency rules.
---

CoinDCXClient caches the full /exchange/ticker response to avoid an HTTP round-trip per price poll per symbol.

**Rule:** TTL defaults to 1.5s (constructor param `ticker_cache_ttl`). This is safe down to the 2s minimum poll interval — same-cycle concurrent calls share one fetch, but consecutive cycles always see fresh data.

**Why:** 4s was the first attempt but breaks when the user sets `/monitor 2`. Within a poll cycle (5–10 active grids calling get_ticker in sequence), all calls hit the same cached response, saving bandwidth and rate limit budget.

**How to apply:** If the price monitor poll interval is ever made configurable below 2s, lower the TTL further or pass `ticker_cache_ttl=interval*0.7` when constructing the client in main.py.

**Concurrency:** A single `asyncio.Lock` (_ticker_refresh_lock) guards the refresh path. Double-checked locking (check outside, re-check inside lock) prevents multiple coroutines from issuing parallel requests on a cache miss.

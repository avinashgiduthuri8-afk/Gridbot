#!/usr/bin/env python3
"""Fetch real historical OHLCV candles from CoinDCX's public API and save
them in the CSV format replay.HistoricalDataLoader expects.

This script is NOT run as part of the test suite or CI — it needs live
internet access to CoinDCX, which this development sandbox does not have.
Run it yourself, e.g.:

    python replay/fetch_coindcx_history.py \\
        --symbols BTCINR ETHINR SOLINR XRPINR DOGEINR AVAXINR ADAINR \\
        --interval 1h --months 6 --out-dir ./historical

Then replay it:

    python replay.py --symbols BTCINR ETHINR SOLINR --data-dir ./historical \\
        --data-format csv --from 2025-01-01 --to 2025-06-30

API reference (public, no auth required):
    https://coindcx.com/api/help/Market%20Data%20on%20CoinDCX%20API/Candles
    GET https://public.coindcx.com/market_data/candles/?pair=...&interval=...&startTime=...&endTime=...&limit=...
    - interval: 1m/5m/15m/30m, 1h/2h/4h/6h/8h, 1d/3d, 1w, 1M
    - limit: max 1000 per request (this script paginates automatically)
    - the "pair" parameter is CoinDCX's own market identifier, distinct
      from the symbol shown in the app (e.g. "BTCINR") — this script looks
      it up for you from GET /exchange/v1/markets_details (also public)
      by matching each requested symbol against that response's
      coindcx_name field, so it doesn't have to guess the pair string
      format.
"""
from __future__ import annotations

import argparse
import csv
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

try:
    import requests
except ImportError:
    print("This script needs `requests`: pip install requests --break-system-packages", file=sys.stderr)
    raise

MARKETS_DETAILS_URL = "https://public.coindcx.com/exchange/v1/markets_details"
CANDLES_URL = "https://public.coindcx.com/market_data/candles"
MAX_LIMIT_PER_REQUEST = 1000

MAX_RETRIES = 3
RETRY_BACKOFF_BASE_SECONDS = 1.0
RETRYABLE_STATUS_CODES = {429, 500, 502, 503, 504}
# A run is flagged (warned + non-zero exit) if a symbol's actual candle
# coverage is less than this fraction of the requested date range — this
# catches a silent pagination/parameter failure that would otherwise look
# like a successful fetch with just a smaller-than-expected file.
COVERAGE_WARNING_RATIO = 0.8


def _get_with_retry(url: str, *, params: dict | None = None, timeout: float) -> "requests.Response":
    """GET with retry-with-backoff, but only for transient failures:
    connection errors, timeouts, and HTTP 429/5xx. Any other error (e.g. a
    4xx client error, which indicates a genuine problem with the request
    itself, not a transient blip) raises immediately, unretried."""
    last_exc: Exception | None = None
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            resp = requests.get(url, params=params, timeout=timeout)
        except (requests.exceptions.ConnectionError, requests.exceptions.Timeout) as exc:
            last_exc = exc
            if attempt == MAX_RETRIES:
                raise
            backoff = RETRY_BACKOFF_BASE_SECONDS * (2 ** (attempt - 1))
            print(
                f"  ! transient network error ({exc}); retrying in {backoff:.1f}s "
                f"(attempt {attempt}/{MAX_RETRIES})",
                file=sys.stderr,
            )
            time.sleep(backoff)
            continue

        if resp.status_code in RETRYABLE_STATUS_CODES:
            if attempt == MAX_RETRIES:
                resp.raise_for_status()
            backoff = RETRY_BACKOFF_BASE_SECONDS * (2 ** (attempt - 1))
            print(
                f"  ! HTTP {resp.status_code}; retrying in {backoff:.1f}s "
                f"(attempt {attempt}/{MAX_RETRIES})",
                file=sys.stderr,
            )
            time.sleep(backoff)
            continue

        resp.raise_for_status()  # any other non-2xx is a permanent error — fail immediately, no retry
        return resp

    # Unreachable in practice (the loop always returns or raises above),
    # but keeps this function's control flow explicit for static analysis.
    if last_exc is not None:
        raise last_exc
    raise RuntimeError("unreachable: retry loop exited without returning or raising")


def _pair_for_symbol(symbol: str) -> str:
    """Looks up CoinDCX's `pair` identifier for the app's symbol (e.g.
    "BTCINR") by matching against the public markets_details response's
    coindcx_name field — the same field exchange/coindcx.py's
    _load_market_details() already keys off internally."""
    resp = _get_with_retry(MARKETS_DETAILS_URL, timeout=15)
    resp.raise_for_status()
    for item in resp.json():
        if item.get("coindcx_name", "").upper() == symbol.upper():
            pair = item.get("pair")
            if pair:
                return pair
    raise SystemExit(f"Could not find a CoinDCX pair for symbol {symbol!r} in markets_details.")


def _fetch_candles(pair: str, interval: str, start_ms: int, end_ms: int) -> list[dict]:
    """Paginates backward from end_ms to start_ms, MAX_LIMIT_PER_REQUEST
    candles at a time, since the API returns at most 1000 per call."""
    all_candles: list[dict] = []
    cursor_end = end_ms
    while cursor_end > start_ms:
        params = {
            "pair": pair, "interval": interval,
            "startTime": start_ms, "endTime": cursor_end,
            "limit": MAX_LIMIT_PER_REQUEST,
        }
        resp = _get_with_retry(CANDLES_URL, params=params, timeout=30)
        resp.raise_for_status()
        batch = resp.json()
        if not batch:
            break
        all_candles.extend(batch)
        oldest_time = min(c["time"] for c in batch)
        if oldest_time >= cursor_end:
            break  # safety valve against an unexpected non-paginating response
        cursor_end = oldest_time - 1
        time.sleep(0.2)  # be polite to a public, unauthenticated endpoint

    # de-dupe (pagination boundaries can overlap by one candle) and sort ascending
    by_time = {c["time"]: c for c in all_candles}
    return sorted(by_time.values(), key=lambda c: c["time"])


def _check_coverage(symbol: str, candles: list[dict], start_ms: int, end_ms: int) -> bool:
    """Returns True if candles/coverage look fine, False (with a warning
    printed) if the actual date range covered is significantly shorter
    than requested — which could mean a genuinely short trading history
    for a newly-listed coin, OR a silent pagination/parameter failure that
    quietly returned far less data than asked for. Either way, this is
    worth surfacing rather than writing a truncated CSV with no warning."""
    if not candles:
        print(f"  ! WARNING: no candles returned for {symbol} at all.", file=sys.stderr)
        return False

    requested_span_ms = end_ms - start_ms
    actual_span_ms = candles[-1]["time"] - candles[0]["time"]
    if requested_span_ms <= 0:
        return True

    coverage_ratio = actual_span_ms / requested_span_ms
    if coverage_ratio < COVERAGE_WARNING_RATIO:
        print(
            f"  ! WARNING: {symbol} coverage is only {coverage_ratio:.0%} of the requested "
            f"range (requested {requested_span_ms / 1000 / 86400:.1f} days, got "
            f"{actual_span_ms / 1000 / 86400:.1f} days). This can mean a genuinely short "
            f"trading history for a newly-listed coin, OR a pagination/parameter problem — "
            f"worth double-checking before using this data for validation.",
            file=sys.stderr,
        )
        return False
    return True


def _write_csv(path: Path, candles: list[dict]) -> None:
    with path.open("w", newline="") as fh:
        writer = csv.writer(fh)
        writer.writerow(["timestamp", "open", "high", "low", "close", "volume"])
        for c in candles:
            writer.writerow([
                c["time"] / 1000.0,  # this project's Candle.timestamp is unix SECONDS
                c["open"], c["high"], c["low"], c["close"], c.get("volume", 0),
            ])


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--symbols", nargs="+", required=True)
    p.add_argument("--interval", default="1h", help="1m/5m/15m/30m, 1h/2h/4h/6h/8h, 1d/3d, 1w, 1M")
    p.add_argument("--months", type=float, default=6.0, help="How many months back to fetch")
    p.add_argument("--out-dir", default="./historical")
    args = p.parse_args(argv)

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    end = datetime.now(timezone.utc)
    start = end - timedelta(days=args.months * 30.44)
    start_ms, end_ms = int(start.timestamp() * 1000), int(end.timestamp() * 1000)

    all_coverage_ok = True
    for symbol in args.symbols:
        print(f"Looking up CoinDCX pair for {symbol}...")
        pair = _pair_for_symbol(symbol)
        print(f"  -> {pair}. Fetching {args.interval} candles from {start.date()} to {end.date()}...")
        candles = _fetch_candles(pair, args.interval, start_ms, end_ms)
        out_path = out_dir / f"{symbol.upper()}.csv"
        _write_csv(out_path, candles)
        print(f"  -> wrote {len(candles)} candles to {out_path}")
        if not _check_coverage(symbol, candles, start_ms, end_ms):
            all_coverage_ok = False

    return 0 if all_coverage_ok else 1


if __name__ == "__main__":
    sys.exit(main())

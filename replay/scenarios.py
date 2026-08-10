"""Synthetic OHLCV scenario generators.

These produce Candle lists for named market conditions so the trading
engine can be stress-tested without needing real historical data on hand.
Every generator is deterministic given a seed, for reproducible runs.
"""
from __future__ import annotations

import random

from replay.data_loader import Candle

SCENARIO_NAMES = (
    "bull", "bear", "sideways", "flash_crash", "gap_up", "gap_down",
    "high_volatility", "low_volatility",
)


def _bar(symbol: str, ts: float, o: float, h: float, low: float, c: float, vol: float) -> Candle:
    return Candle(symbol=symbol, timestamp=ts, open=o, high=max(h, o, c), low=min(low, o, c),
                  close=c, volume=vol)


def _wiggle(rng: random.Random, price: float, noise_pct: float) -> tuple[float, float]:
    """Returns (bar_high, bar_low) around `price` for the given noise band."""
    hi = price * (1 + rng.uniform(0, noise_pct))
    lo = price * (1 - rng.uniform(0, noise_pct))
    return hi, lo


def generate_scenario(
    name: str, symbol: str, *, start_price: float = 100.0, bars: int = 500,
    interval_seconds: float = 60.0, start_timestamp: float = 0.0, seed: int = 42,
    price_precision: int = 2,
) -> list[Candle]:
    """Generate `bars` candles for the named scenario. Raises ValueError for
    an unknown scenario name.

    price_precision rounds every generated price to that many decimals —
    real exchange prices always have bounded precision, and DCAManager's
    own price-precision guard (correctly) rejects anything that doesn't,
    so synthetic data must respect the same constraint the registered
    MarketInfo declares for the symbol (default 2, matching this module's
    default MarketInfo in cli.py)."""
    if name not in SCENARIO_NAMES:
        raise ValueError(f"Unknown scenario {name!r}; choose from {SCENARIO_NAMES}")
    rng = random.Random(seed)
    candles: list[Candle] = []
    price = start_price
    ts = start_timestamp

    for i in range(bars):
        o = price
        if name == "bull":
            drift = rng.uniform(0.0002, 0.004)
            c = o * (1 + drift)
            hi, lo = _wiggle(rng, (o + c) / 2, 0.003)
        elif name == "bear":
            drift = rng.uniform(0.0002, 0.004)
            c = o * (1 - drift)
            hi, lo = _wiggle(rng, (o + c) / 2, 0.003)
        elif name == "sideways":
            c = o * (1 + rng.uniform(-0.0015, 0.0015))
            hi, lo = _wiggle(rng, (o + c) / 2, 0.002)
        elif name == "flash_crash":
            # A sharp, deep drop concentrated in the middle third of the
            # run, then a partial recovery — the classic "V".
            third = bars / 3
            if third <= i < 2 * third:
                drift = rng.uniform(0.01, 0.03)  # 1-3% per bar, down
                c = o * (1 - drift)
            elif i >= 2 * third:
                drift = rng.uniform(0.002, 0.01)  # partial recovery
                c = o * (1 + drift)
            else:
                c = o * (1 + rng.uniform(-0.001, 0.001))
            hi, lo = _wiggle(rng, (o + c) / 2, 0.01)
        elif name == "gap_up":
            if i == bars // 2:
                c = o * rng.uniform(1.05, 1.15)  # a single 5-15% gap bar
            else:
                c = o * (1 + rng.uniform(-0.001, 0.001))
            hi, lo = _wiggle(rng, (o + c) / 2, 0.002)
        elif name == "gap_down":
            if i == bars // 2:
                c = o * rng.uniform(0.85, 0.95)  # a single 5-15% gap-down bar
            else:
                c = o * (1 + rng.uniform(-0.001, 0.001))
            hi, lo = _wiggle(rng, (o + c) / 2, 0.002)
        elif name == "high_volatility":
            c = o * (1 + rng.uniform(-0.02, 0.02))
            hi, lo = _wiggle(rng, (o + c) / 2, 0.02)
        else:  # low_volatility
            c = o * (1 + rng.uniform(-0.0005, 0.0005))
            hi, lo = _wiggle(rng, (o + c) / 2, 0.0005)

        c = max(c, 1e-8)  # never let a synthetic price go to zero or negative
        c, hi, lo, o = (round(v, price_precision) for v in (c, hi, lo, o))
        hi, lo = max(hi, o, c), min(lo, o, c)  # rounding can violate hi >= max(o,c) at the margins
        vol = rng.uniform(1.0, 100.0)
        candles.append(_bar(symbol, ts, o, hi, lo, c, vol))
        price = c
        ts += interval_seconds

    return candles


def generate_multi_symbol_scenario(
    name: str, symbols: list[str], *, start_price: float = 100.0, bars: int = 500,
    interval_seconds: float = 60.0, start_timestamp: float = 0.0, seed: int = 42,
    price_precision: int = 2,
) -> dict[str, list[Candle]]:
    """Same scenario applied independently to each symbol (each gets its
    own seeded RNG stream, derived from the base seed, so symbols don't
    move in lockstep)."""
    return {
        symbol: generate_scenario(
            name, symbol, start_price=start_price, bars=bars,
            interval_seconds=interval_seconds, start_timestamp=start_timestamp,
            seed=seed + i, price_precision=price_precision,
        )
        for i, symbol in enumerate(symbols)
    }

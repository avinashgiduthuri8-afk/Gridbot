"""Historical OHLCV data loading for replay.

Supports CSV, JSON, and (optionally) SQLite sources. Every loader produces
the same normalized ``Candle`` shape regardless of source format, and
multiple symbols can be loaded and merged into a single chronological feed.
"""
from __future__ import annotations

import csv
import json
import sqlite3
from dataclasses import dataclass
from pathlib import Path


class DataLoaderError(RuntimeError):
    """Raised when historical data can't be parsed into a valid Candle feed."""


@dataclass(frozen=True)
class Candle:
    """One OHLCV bar for a single symbol."""

    symbol: str
    timestamp: float  # unix seconds
    open: float
    high: float
    low: float
    close: float
    volume: float = 0.0

    @property
    def prices_in_order(self) -> tuple[float, float, float, float]:
        """(open, high, low, close) — the order the replay engine feeds
        prices to the trading engine within a single candle, so that any
        trigger reachable within the bar's range gets a chance to fire
        (e.g. a stop-loss dip that happens *within* the bar, not just at
        its close)."""
        return (self.open, self.high, self.low, self.close)


REQUIRED_FIELDS = ("timestamp", "open", "high", "low", "close")


def _row_to_candle(symbol: str, row: dict) -> Candle:
    missing = [f for f in REQUIRED_FIELDS if row.get(f) in (None, "")]
    if missing:
        raise DataLoaderError(f"{symbol}: row missing required field(s) {missing}: {row}")
    try:
        return Candle(
            symbol=symbol,
            timestamp=float(row["timestamp"]),
            open=float(row["open"]),
            high=float(row["high"]),
            low=float(row["low"]),
            close=float(row["close"]),
            volume=float(row.get("volume") or 0.0),
        )
    except (TypeError, ValueError) as exc:
        raise DataLoaderError(f"{symbol}: could not parse row as numeric OHLCV: {row}") from exc


class HistoricalDataLoader:
    """Loads OHLCV candles for one or more symbols from disk.

    Usage:
        loader = HistoricalDataLoader()
        loader.load_csv("BTCINR", "data/btcinr_2025.csv")
        loader.load_json("ETHINR", "data/ethinr_2025.json")
        feed = loader.merged_feed()   # chronological across all symbols
    """

    def __init__(self) -> None:
        self._candles: dict[str, list[Candle]] = {}

    @property
    def symbols(self) -> list[str]:
        return list(self._candles.keys())

    def candles_for(self, symbol: str) -> list[Candle]:
        return list(self._candles.get(symbol.upper(), []))

    def add_candles(self, symbol: str, candles: list[Candle]) -> None:
        """Add already-constructed candles directly (used by scenarios.py).

        De-duplicates by timestamp within this symbol, keeping the LATEST
        occurrence — whether that's an already-stored candle or one from
        this new batch, and whether the duplicate is between this call and
        a previous one, or within `candles` itself. This matters because
        loading two files with overlapping date ranges for the same symbol
        (e.g. re-running a historical-data fetch into the same directory)
        would otherwise silently feed the same real-world candle into the
        replay engine twice.
        """
        symbol = symbol.upper()
        existing = self._candles.get(symbol, [])
        by_timestamp: dict[float, Candle] = {c.timestamp: c for c in existing}
        for c in candles:
            by_timestamp[c.timestamp] = c  # last write wins, per symbol+timestamp
        self._candles[symbol] = sorted(by_timestamp.values(), key=lambda c: c.timestamp)

    def load_csv(self, symbol: str, path: str | Path) -> int:
        """Load a CSV with columns timestamp,open,high,low,close[,volume].
        Returns the number of candles loaded."""
        path = Path(path)
        if not path.exists():
            raise DataLoaderError(f"CSV file not found: {path}")
        candles: list[Candle] = []
        with path.open(newline="", encoding="utf-8") as fh:
            reader = csv.DictReader(fh)
            for row in reader:
                candles.append(_row_to_candle(symbol, row))
        self.add_candles(symbol, candles)
        return len(candles)

    def load_json(self, symbol: str, path: str | Path) -> int:
        """Load a JSON file containing either a list of OHLCV objects, or
        an object with a "candles" key holding that list."""
        path = Path(path)
        if not path.exists():
            raise DataLoaderError(f"JSON file not found: {path}")
        with path.open(encoding="utf-8") as fh:
            data = json.load(fh)
        rows = data["candles"] if isinstance(data, dict) and "candles" in data else data
        if not isinstance(rows, list):
            raise DataLoaderError(f"{symbol}: JSON must be a list of candles or {{'candles': [...]}}")
        candles = [_row_to_candle(symbol, row) for row in rows]
        self.add_candles(symbol, candles)
        return len(candles)

    def load_sqlite(
        self, symbol: str, path: str | Path, table: str = "candles",
        symbol_column: str | None = None,
    ) -> int:
        """Load candles from a SQLite table with columns
        timestamp,open,high,low,close[,volume][,symbol].
        If symbol_column is given, rows are filtered to symbol_column == symbol."""
        path = Path(path)
        if not path.exists():
            raise DataLoaderError(f"SQLite file not found: {path}")
        conn = sqlite3.connect(str(path))
        try:
            conn.row_factory = sqlite3.Row
            query = f"SELECT * FROM {table}"  # noqa: S608 - table name is operator-supplied, not user input
            params: tuple = ()
            if symbol_column:
                query += f" WHERE {symbol_column} = ?"
                params = (symbol,)
            query += " ORDER BY timestamp ASC"
            rows = [dict(r) for r in conn.execute(query, params).fetchall()]
        finally:
            conn.close()
        candles = [_row_to_candle(symbol, row) for row in rows]
        self.add_candles(symbol, candles)
        return len(candles)

    def merged_feed(self) -> list[Candle]:
        """All loaded candles across all symbols, in chronological order
        (stable sort, so same-timestamp candles for different symbols
        keep a deterministic relative order across runs)."""
        all_candles: list[Candle] = []
        for candles in self._candles.values():
            all_candles.extend(candles)
        all_candles.sort(key=lambda c: c.timestamp)
        return all_candles

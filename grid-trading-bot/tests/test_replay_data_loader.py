import json
import sqlite3

import pytest

from replay.data_loader import DataLoaderError, HistoricalDataLoader


def _write_csv(path, rows):
    import csv
    with open(path, "w", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=["timestamp", "open", "high", "low", "close", "volume"])
        writer.writeheader()
        writer.writerows(rows)


def test_load_csv_basic(tmp_path):
    path = tmp_path / "BTCINR.csv"
    _write_csv(path, [
        {"timestamp": 0, "open": 100, "high": 105, "low": 99, "close": 103, "volume": 10},
        {"timestamp": 60, "open": 103, "high": 106, "low": 102, "close": 104, "volume": 12},
    ])
    loader = HistoricalDataLoader()
    count = loader.load_csv("BTCINR", path)
    assert count == 2
    candles = loader.candles_for("BTCINR")
    assert len(candles) == 2
    assert candles[0].close == 103.0
    assert candles[1].timestamp == 60.0


def test_load_csv_missing_file_raises(tmp_path):
    loader = HistoricalDataLoader()
    with pytest.raises(DataLoaderError):
        loader.load_csv("BTCINR", tmp_path / "nope.csv")


def test_load_csv_missing_field_raises(tmp_path):
    path = tmp_path / "bad.csv"
    with open(path, "w") as fh:
        fh.write("timestamp,open,high,low\n0,100,105,99\n")  # missing close
    loader = HistoricalDataLoader()
    with pytest.raises(DataLoaderError):
        loader.load_csv("BTCINR", path)


def test_load_json_list_form(tmp_path):
    path = tmp_path / "ETHINR.json"
    path.write_text(json.dumps([
        {"timestamp": 0, "open": 50, "high": 52, "low": 49, "close": 51, "volume": 5},
    ]))
    loader = HistoricalDataLoader()
    count = loader.load_json("ETHINR", path)
    assert count == 1
    assert loader.candles_for("ETHINR")[0].open == 50.0


def test_load_json_wrapped_form(tmp_path):
    path = tmp_path / "ETHINR.json"
    path.write_text(json.dumps({"candles": [
        {"timestamp": 0, "open": 50, "high": 52, "low": 49, "close": 51},
    ]}))
    loader = HistoricalDataLoader()
    count = loader.load_json("ETHINR", path)
    assert count == 1


def test_load_sqlite(tmp_path):
    db_path = tmp_path / "data.sqlite3"
    conn = sqlite3.connect(str(db_path))
    conn.execute(
        "CREATE TABLE candles (timestamp REAL, open REAL, high REAL, low REAL, close REAL, volume REAL, symbol TEXT)"
    )
    conn.execute(
        "INSERT INTO candles VALUES (0, 10, 11, 9, 10.5, 100, 'SOLINR')"
    )
    conn.execute(
        "INSERT INTO candles VALUES (60, 10.5, 12, 10, 11, 90, 'SOLINR')"
    )
    conn.commit()
    conn.close()

    loader = HistoricalDataLoader()
    count = loader.load_sqlite("SOLINR", db_path, symbol_column="symbol")
    assert count == 2
    assert loader.candles_for("SOLINR")[0].close == 10.5


def test_multi_symbol_merged_feed_is_chronological(tmp_path):
    loader = HistoricalDataLoader()
    _write_csv(tmp_path / "BTCINR.csv", [
        {"timestamp": 0, "open": 100, "high": 101, "low": 99, "close": 100, "volume": 1},
        {"timestamp": 120, "open": 100, "high": 101, "low": 99, "close": 100, "volume": 1},
    ])
    _write_csv(tmp_path / "ETHINR.csv", [
        {"timestamp": 60, "open": 50, "high": 51, "low": 49, "close": 50, "volume": 1},
        {"timestamp": 180, "open": 50, "high": 51, "low": 49, "close": 50, "volume": 1},
    ])
    loader.load_csv("BTCINR", tmp_path / "BTCINR.csv")
    loader.load_csv("ETHINR", tmp_path / "ETHINR.csv")

    feed = loader.merged_feed()
    timestamps = [c.timestamp for c in feed]
    assert timestamps == sorted(timestamps)
    assert len(feed) == 4
    assert {c.symbol for c in feed} == {"BTCINR", "ETHINR"}


def test_candle_prices_in_order():
    from replay.data_loader import Candle
    c = Candle(symbol="BTCINR", timestamp=0, open=100, high=110, low=90, close=105)
    assert c.prices_in_order == (100, 110, 90, 105)


def test_duplicate_timestamps_within_one_batch_keep_last_occurrence():
    from replay.data_loader import Candle
    loader = HistoricalDataLoader()
    loader.add_candles("BTCINR", [
        Candle(symbol="BTCINR", timestamp=0, open=100, high=100, low=100, close=100),
        Candle(symbol="BTCINR", timestamp=60, open=100, high=100, low=100, close=100),
        Candle(symbol="BTCINR", timestamp=60, open=100, high=100, low=100, close=999),  # dup, later -> wins
    ])
    candles = loader.candles_for("BTCINR")
    assert len(candles) == 2
    assert candles[1].timestamp == 60
    assert candles[1].close == 999


def test_duplicate_timestamps_across_two_loads_keep_latest_load(tmp_path):
    """Simulates re-running a historical-data fetch into overlapping date
    ranges: loading two files for the same symbol where some timestamps
    overlap must not produce duplicate candles, and the SECOND (later)
    load's data wins for the overlapping timestamps."""
    loader = HistoricalDataLoader()
    _write_csv(tmp_path / "first.csv", [
        {"timestamp": 0, "open": 100, "high": 101, "low": 99, "close": 100, "volume": 1},
        {"timestamp": 60, "open": 100, "high": 101, "low": 99, "close": 100, "volume": 1},
    ])
    _write_csv(tmp_path / "second.csv", [
        {"timestamp": 60, "open": 100, "high": 105, "low": 99, "close": 104, "volume": 5},  # overlaps, different data
        {"timestamp": 120, "open": 104, "high": 106, "low": 103, "close": 105, "volume": 2},
    ])
    loader.load_csv("BTCINR", tmp_path / "first.csv")
    loader.load_csv("BTCINR", tmp_path / "second.csv")

    candles = loader.candles_for("BTCINR")
    timestamps = [c.timestamp for c in candles]
    assert timestamps == [0, 60, 120], "no duplicate timestamp entries, chronological order preserved"
    ts_60 = next(c for c in candles if c.timestamp == 60)
    assert ts_60.close == 104, "the later load's data must win for an overlapping timestamp"


def test_no_duplicates_across_different_symbols():
    """Same timestamp for DIFFERENT symbols is not a duplicate — dedup is
    per-symbol, not global."""
    from replay.data_loader import Candle
    loader = HistoricalDataLoader()
    loader.add_candles("BTCINR", [Candle(symbol="BTCINR", timestamp=0, open=100, high=100, low=100, close=100)])
    loader.add_candles("ETHINR", [Candle(symbol="ETHINR", timestamp=0, open=50, high=50, low=50, close=50)])
    assert len(loader.candles_for("BTCINR")) == 1
    assert len(loader.candles_for("ETHINR")) == 1
    assert len(loader.merged_feed()) == 2

"""Regression tests for the SQLite busy_timeout PRAGMA and the startup
DB-connect retry-with-backoff fix (main.py's _connect_db_with_retry)."""
from __future__ import annotations

import sqlite3
from unittest.mock import AsyncMock

import pytest

from main import _DB_CONNECT_BACKOFF_SECONDS, _DB_CONNECT_MAX_ATTEMPTS, _connect_db_with_retry
from storage.database import Database

pytestmark = pytest.mark.anyio


# ---------------------------------------------------------------------------
# storage/database.py: busy_timeout PRAGMA is actually applied
# ---------------------------------------------------------------------------


async def test_busy_timeout_pragma_is_applied(tmp_path):
    db = Database(str(tmp_path / "busy_timeout.sqlite3"))
    await db.connect()
    try:
        cur = await db.connection.execute("PRAGMA busy_timeout;")
        row = await cur.fetchone()
        assert row[0] == 5000
    finally:
        await db.close()


# ---------------------------------------------------------------------------
# main.py: _connect_db_with_retry
# ---------------------------------------------------------------------------


class _FakeDB:
    """Duck-typed stand-in for Database, so these tests exercise the retry
    logic itself without needing a real SQLite file or real locking."""

    def __init__(self, connect_side_effects, migrate_side_effect=None):
        self.connect = AsyncMock(side_effect=connect_side_effects)
        self.migrate = AsyncMock(side_effect=migrate_side_effect)


async def test_connect_succeeds_immediately_no_retry_needed(monkeypatch):
    sleep_calls = []
    monkeypatch.setattr("main.asyncio.sleep", AsyncMock(side_effect=lambda s: sleep_calls.append(s)))

    db = _FakeDB(connect_side_effects=[None])
    await _connect_db_with_retry(db)

    assert db.connect.await_count == 1
    assert db.migrate.await_count == 1
    assert sleep_calls == [], "no backoff sleep should happen when the first attempt succeeds"


async def test_first_attempt_locked_second_succeeds(monkeypatch):
    sleep_calls = []
    monkeypatch.setattr("main.asyncio.sleep", AsyncMock(side_effect=lambda s: sleep_calls.append(s)))

    db = _FakeDB(connect_side_effects=[sqlite3.OperationalError("database is locked"), None])
    await _connect_db_with_retry(db)

    assert db.connect.await_count == 2
    assert db.migrate.await_count == 1  # migrate only ever runs after a successful connect
    assert sleep_calls == [_DB_CONNECT_BACKOFF_SECONDS[0]]  # 1 second backoff after attempt 1


async def test_first_two_attempts_locked_third_succeeds(monkeypatch):
    sleep_calls = []
    monkeypatch.setattr("main.asyncio.sleep", AsyncMock(side_effect=lambda s: sleep_calls.append(s)))

    db = _FakeDB(connect_side_effects=[
        sqlite3.OperationalError("database is locked"),
        sqlite3.OperationalError("database is locked"),
        None,
    ])
    await _connect_db_with_retry(db)

    assert db.connect.await_count == 3
    assert db.migrate.await_count == 1
    assert sleep_calls == [_DB_CONNECT_BACKOFF_SECONDS[0], _DB_CONNECT_BACKOFF_SECONDS[1]]  # 1s, then 2s


async def test_all_three_attempts_locked_raises(monkeypatch):
    sleep_calls = []
    monkeypatch.setattr("main.asyncio.sleep", AsyncMock(side_effect=lambda s: sleep_calls.append(s)))

    db = _FakeDB(connect_side_effects=[
        sqlite3.OperationalError("database is locked"),
        sqlite3.OperationalError("database is locked"),
        sqlite3.OperationalError("database is locked"),
    ])
    with pytest.raises(sqlite3.OperationalError):
        await _connect_db_with_retry(db)

    assert db.connect.await_count == _DB_CONNECT_MAX_ATTEMPTS == 3
    assert db.migrate.await_count == 0  # never succeeded, so migrate never ran
    # Backoff is only logged/slept BETWEEN attempts, so 2 sleeps for 3 attempts.
    assert sleep_calls == [_DB_CONNECT_BACKOFF_SECONDS[0], _DB_CONNECT_BACKOFF_SECONDS[1]]


async def test_non_sqlite_exceptions_are_never_retried(monkeypatch):
    sleep_calls = []
    monkeypatch.setattr("main.asyncio.sleep", AsyncMock(side_effect=lambda s: sleep_calls.append(s)))

    db = _FakeDB(connect_side_effects=[ValueError("some unrelated config problem")])
    with pytest.raises(ValueError):
        await _connect_db_with_retry(db)

    assert db.connect.await_count == 1, "a non-OperationalError must fail immediately, no retry"
    assert sleep_calls == []


async def test_migrate_failure_is_not_retried(monkeypatch):
    """The retry wraps connect+migrate together, but only OperationalError
    from EITHER step should be retried — this confirms a non-OperationalError
    raised specifically during migrate() also isn't swallowed or retried."""
    monkeypatch.setattr("main.asyncio.sleep", AsyncMock())

    db = _FakeDB(connect_side_effects=[None], migrate_side_effect=RuntimeError("bad schema"))
    with pytest.raises(RuntimeError):
        await _connect_db_with_retry(db)

    assert db.connect.await_count == 1
    assert db.migrate.await_count == 1


async def test_operational_error_during_migrate_is_retried(monkeypatch):
    """An OperationalError raised during migrate() (not just connect())
    must also trigger the retry — the whole connect+migrate sequence is
    what's being protected, not just the initial connection."""
    sleep_calls = []
    monkeypatch.setattr("main.asyncio.sleep", AsyncMock(side_effect=lambda s: sleep_calls.append(s)))

    db = _FakeDB(
        connect_side_effects=[None, None],
        migrate_side_effect=[sqlite3.OperationalError("database is locked"), None],
    )
    await _connect_db_with_retry(db)

    assert db.connect.await_count == 2
    assert db.migrate.await_count == 2
    assert sleep_calls == [_DB_CONNECT_BACKOFF_SECONDS[0]]

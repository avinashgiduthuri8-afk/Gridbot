"""Tests for the restart-based restore flow (storage/restore.py):
apply_pending_restore_if_any() and its safety guarantees — this is the
most consequential code in the whole backup system, since a mistake here
means real data loss, so it's tested against real files, not mocks."""

from __future__ import annotations

import json
import sqlite3
import sys
import types

import pytest

pytestmark = pytest.mark.anyio


def _install_drive_stubs():
    if "httpx" not in sys.modules:
        httpx_stub = types.ModuleType("httpx")
        class _FakeAsyncClient:
            def __init__(self, *a, **k): pass
        httpx_stub.AsyncClient = _FakeAsyncClient
        sys.modules["httpx"] = httpx_stub
    for name in ["google", "google.auth", "google.auth.transport",
                 "google.auth.transport.requests", "google.oauth2", "google.oauth2.service_account"]:
        if name not in sys.modules:
            sys.modules[name] = types.ModuleType(name)
    if not hasattr(sys.modules["google.auth.transport.requests"], "Request"):
        sys.modules["google.auth.transport.requests"].Request = type("Request", (), {})
    if not hasattr(sys.modules["google.oauth2.service_account"], "Credentials"):
        sys.modules["google.oauth2.service_account"].Credentials = type("Credentials", (), {})


_install_drive_stubs()

from storage.restore import (  # noqa: E402
    _marker_path,
    _staged_path,
    apply_pending_restore_if_any,
    cancel_pending_restore,
    get_pending_restore,
)


def _make_valid_db(path, marker_value="data") -> None:
    conn = sqlite3.connect(str(path))
    conn.execute("CREATE TABLE dca_grids (grid_id TEXT)")
    conn.execute("CREATE TABLE orders (order_id TEXT)")
    conn.execute("CREATE TABLE trade_history (trade_id TEXT)")
    conn.execute(f"INSERT INTO dca_grids VALUES ('{marker_value}')")
    conn.commit()
    conn.close()


def _read_marker_value(path) -> str:
    conn = sqlite3.connect(str(path))
    val = conn.execute("SELECT grid_id FROM dca_grids").fetchone()[0]
    conn.close()
    return val


def test_no_marker_returns_none_with_no_side_effects(tmp_path):
    db_path = str(tmp_path / "grid_bot.db")
    assert apply_pending_restore_if_any(db_path) is None


def test_marker_with_missing_staged_file_cleans_up_and_returns_none(tmp_path):
    db_path = str(tmp_path / "grid_bot.db")
    _marker_path(db_path).write_text(json.dumps({"source_name": "x", "source_file_id": "y"}))

    result = apply_pending_restore_if_any(db_path)

    assert result is None
    assert not _marker_path(db_path).exists()


def test_successful_restore_swaps_file_and_preserves_original(tmp_path):
    db_path = str(tmp_path / "grid_bot.db")
    _make_valid_db(db_path, marker_value="CURRENT_LIVE_DATA")

    # Simulate stale WAL/SHM sidecar files left over from the live db.
    (tmp_path / "grid_bot.db-wal").write_bytes(b"stale wal")
    (tmp_path / "grid_bot.db-shm").write_bytes(b"stale shm")

    staged_source = tmp_path / "staged_source.db"
    _make_valid_db(staged_source, marker_value="RESTORED_BACKUP_DATA")
    _staged_path(db_path).write_bytes(staged_source.read_bytes())
    _marker_path(db_path).write_text(json.dumps({
        "source_name": "dca_bot_backup_2026-07-01.db", "source_file_id": "FILE_XYZ", "schema_version": 2,
    }))

    result = apply_pending_restore_if_any(db_path)

    assert result is not None
    assert result["source_name"] == "dca_bot_backup_2026-07-01.db"
    assert result["backup_of_previous_db"] is not None

    from pathlib import Path
    assert Path(result["backup_of_previous_db"]).exists()
    assert _read_marker_value(result["backup_of_previous_db"]) == "CURRENT_LIVE_DATA", \
        "the original live data must be preserved in the pre-restore backup"
    assert _read_marker_value(db_path) == "RESTORED_BACKUP_DATA", \
        "the live db path must now contain the restored backup's data"

    assert not (tmp_path / "grid_bot.db-wal").exists(), "stale WAL must be removed"
    assert not (tmp_path / "grid_bot.db-shm").exists(), "stale SHM must be removed"
    assert get_pending_restore(db_path) is None


def test_corrupt_staged_file_aborts_without_touching_live_db(tmp_path):
    db_path = str(tmp_path / "grid_bot.db")
    _make_valid_db(db_path, marker_value="SHOULD_NOT_CHANGE")
    _staged_path(db_path).write_bytes(b"totally corrupt garbage, not a real sqlite file")
    _marker_path(db_path).write_text(json.dumps({"source_name": "bad_backup.db", "source_file_id": "BAD"}))

    result = apply_pending_restore_if_any(db_path)

    assert result is None
    assert _read_marker_value(db_path) == "SHOULD_NOT_CHANGE", \
        "the live database must be completely untouched when the staged file is corrupt"
    assert get_pending_restore(db_path) is None, "marker must still be cleaned up even on abort"


def test_restore_with_no_existing_live_db_skips_backup_step(tmp_path):
    """A fresh install (no current database file yet) restoring from a
    backup must still work — there's simply nothing to back up first."""
    db_path = str(tmp_path / "grid_bot.db")  # deliberately does not exist yet
    staged_source = tmp_path / "staged_source.db"
    _make_valid_db(staged_source, marker_value="FRESH_RESTORE")
    _staged_path(db_path).write_bytes(staged_source.read_bytes())
    _marker_path(db_path).write_text(json.dumps({"source_name": "backup.db", "source_file_id": "F1"}))

    result = apply_pending_restore_if_any(db_path)

    assert result is not None
    assert result["backup_of_previous_db"] is None
    assert _read_marker_value(db_path) == "FRESH_RESTORE"


def test_cancel_pending_restore_removes_marker_and_staged_file(tmp_path):
    db_path = str(tmp_path / "grid_bot.db")
    _marker_path(db_path).write_text("{}")
    _staged_path(db_path).write_bytes(b"x")

    had_one = cancel_pending_restore(db_path)

    assert had_one is True
    assert not _marker_path(db_path).exists()
    assert not _staged_path(db_path).exists()


def test_cancel_pending_restore_is_a_safe_noop_when_nothing_pending(tmp_path):
    db_path = str(tmp_path / "grid_bot.db")
    assert cancel_pending_restore(db_path) is False

"""Tests for backup integrity verification (TASK-15E):
verify_sqlite_integrity() as a pure function, and the pre-upload /
post-upload verification wired into DriveBackupManager.create_backup_and_upload().
"""

from __future__ import annotations

import sqlite3
import sys
import types
from pathlib import Path

import pytest

pytestmark = pytest.mark.anyio


def _install_drive_stubs():
    """Stub httpx and google-auth just enough to import storage.drive_backup
    without either being installed — same approach used throughout this
    project's Drive-backup tests."""
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
        class _FakeCredentials:
            @staticmethod
            def from_service_account_file(path, scopes=None):
                return _FakeCredentials()
            valid = True
            token = "fake-token"
            def refresh(self, req):
                pass
        sys.modules["google.oauth2.service_account"].Credentials = _FakeCredentials


_install_drive_stubs()

from storage.drive_backup import (  # noqa: E402
    CRITICAL_TABLES,
    DriveBackupError,
    DriveBackupManager,
    verify_sqlite_integrity,
)


def _make_valid_db(path: Path) -> None:
    conn = sqlite3.connect(str(path))
    conn.execute("CREATE TABLE dca_grids (grid_id TEXT)")
    conn.execute("CREATE TABLE orders (order_id TEXT)")
    conn.execute("CREATE TABLE trade_history (trade_id TEXT)")
    conn.execute("CREATE TABLE schema_migrations (version INTEGER)")
    conn.execute("INSERT INTO schema_migrations VALUES (2)")
    conn.execute("INSERT INTO dca_grids VALUES ('g1')")
    conn.execute("INSERT INTO dca_grids VALUES ('g2')")
    conn.commit()
    conn.close()


# ---------------------------------------------------------------------------
# verify_sqlite_integrity — pure function tests
# ---------------------------------------------------------------------------


def test_valid_database_passes(tmp_path):
    db_path = tmp_path / "valid.db"
    _make_valid_db(db_path)

    result = verify_sqlite_integrity(db_path)

    assert result["valid"] is True
    assert result["integrity_check"] == "ok"
    assert result["schema_version"] == 2
    assert result["row_counts"]["dca_grids"] == 2
    assert result["missing_critical_tables"] == []


def test_missing_critical_tables_fails(tmp_path):
    db_path = tmp_path / "missing.db"
    conn = sqlite3.connect(str(db_path))
    conn.execute("CREATE TABLE dca_grids (grid_id TEXT)")
    conn.commit()
    conn.close()

    result = verify_sqlite_integrity(db_path)

    assert result["valid"] is False
    assert "orders" in result["missing_critical_tables"]
    assert "trade_history" in result["missing_critical_tables"]


def test_corrupt_file_fails_without_crashing(tmp_path):
    db_path = tmp_path / "corrupt.db"
    db_path.write_bytes(b"not a sqlite database, just garbage bytes")

    result = verify_sqlite_integrity(db_path)  # must not raise

    assert result["valid"] is False
    assert result["error"] is not None


def test_nonexistent_file_fails_without_crashing(tmp_path):
    result = verify_sqlite_integrity(tmp_path / "does_not_exist.db")  # must not raise

    assert result["valid"] is False
    assert "does not exist" in result["error"].lower()


def test_old_backup_missing_only_optional_tables_still_valid(tmp_path):
    """A genuinely old backup taken before later migrations added
    grid_defaults/price_alerts/schema_migrations must still verify as
    valid — only the tables in CRITICAL_TABLES are mandatory."""
    db_path = tmp_path / "old.db"
    conn = sqlite3.connect(str(db_path))
    for table in CRITICAL_TABLES:
        conn.execute(f"CREATE TABLE {table} (id TEXT)")
    conn.commit()
    conn.close()

    result = verify_sqlite_integrity(db_path)

    assert result["valid"] is True
    assert "schema_migrations" in result["missing_optional_tables"]
    assert result["schema_version"] is None


# ---------------------------------------------------------------------------
# create_backup_and_upload — pre/post integrity verification wiring
# ---------------------------------------------------------------------------


class _FakeResponse:
    def __init__(self, status_code, json_data=None, content=b"", text=""):
        self.status_code = status_code
        self._json = json_data or {}
        self.content = content
        self.text = text

    def json(self):
        return self._json


class _FakeAsyncClient:
    call_log: list = []
    responses: list = []

    def __init__(self, *a, **k):
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        return False

    async def post(self, url, headers=None, files=None, **kw):
        _FakeAsyncClient.call_log.append(("POST", url))
        return _FakeAsyncClient.responses.pop(0)

    async def get(self, url, headers=None, params=None, **kw):
        _FakeAsyncClient.call_log.append(("GET", url, params))
        return _FakeAsyncClient.responses.pop(0)

    async def delete(self, url, headers=None, **kw):
        _FakeAsyncClient.call_log.append(("DELETE", url))
        return _FakeAsyncClient.responses.pop(0)


@pytest.fixture(autouse=True)
def _patch_httpx_client(monkeypatch):
    import storage.drive_backup as db_mod
    _FakeAsyncClient.call_log = []
    _FakeAsyncClient.responses = []
    monkeypatch.setattr(db_mod.httpx, "AsyncClient", _FakeAsyncClient)
    yield


async def test_successful_backup_runs_pre_and_post_verification(tmp_path):
    db_path = tmp_path / "grid_bot.db"
    _make_valid_db(db_path)
    mgr = DriveBackupManager(db_path=str(db_path), folder_id="F1", service_account_json_path="x", retention_count=30)

    real_bytes = db_path.read_bytes()
    _FakeAsyncClient.responses = [
        _FakeResponse(200, {"id": "FILE_A"}),      # upload
        _FakeResponse(200, content=real_bytes),     # download for post-check
        _FakeResponse(200, {"files": []}),           # prune list
    ]

    file_id = await mgr.create_backup_and_upload(backup_type="auto")

    assert file_id == "FILE_A"
    calls = [c[0] for c in _FakeAsyncClient.call_log]
    assert calls == ["POST", "GET", "GET"]


async def test_pre_upload_failure_makes_zero_network_calls(tmp_path):
    db_path = tmp_path / "grid_bot.db"
    conn = sqlite3.connect(str(db_path))
    conn.execute("CREATE TABLE unrelated_table (x TEXT)")
    conn.commit()
    conn.close()
    mgr = DriveBackupManager(db_path=str(db_path), folder_id="F1", service_account_json_path="x", retention_count=30)

    with pytest.raises(DriveBackupError, match="before upload"):
        await mgr.create_backup_and_upload(backup_type="auto")

    assert _FakeAsyncClient.call_log == [], "a known-bad snapshot must never be uploaded"


async def test_post_upload_corruption_is_detected(tmp_path):
    db_path = tmp_path / "grid_bot.db"
    _make_valid_db(db_path)
    mgr = DriveBackupManager(db_path=str(db_path), folder_id="F1", service_account_json_path="x", retention_count=30)

    _FakeAsyncClient.responses = [
        _FakeResponse(200, {"id": "FILE_C"}),                        # upload succeeds
        _FakeResponse(200, content=b"corrupted garbage, not sqlite"),  # round-trip comes back bad
    ]

    with pytest.raises(DriveBackupError, match="post-upload|round trip"):
        await mgr.create_backup_and_upload(backup_type="auto")


async def test_verify_after_upload_can_be_disabled(tmp_path):
    """verify_after_upload=False must skip the download+verify step
    entirely — used if a caller wants faster/cheaper backups and accepts
    the reduced guarantee."""
    db_path = tmp_path / "grid_bot.db"
    _make_valid_db(db_path)
    mgr = DriveBackupManager(db_path=str(db_path), folder_id="F1", service_account_json_path="x", retention_count=30)

    _FakeAsyncClient.responses = [
        _FakeResponse(200, {"id": "FILE_D"}),
        _FakeResponse(200, {"files": []}),  # prune list only -- no download call expected
    ]

    file_id = await mgr.create_backup_and_upload(backup_type="auto", verify_after_upload=False)

    assert file_id == "FILE_D"
    calls = [c[0] for c in _FakeAsyncClient.call_log]
    assert calls == ["POST", "GET"], "should skip the post-upload download when disabled"


async def test_verify_backup_by_id_downloads_and_checks(tmp_path):
    db_path = tmp_path / "grid_bot.db"
    _make_valid_db(db_path)
    mgr = DriveBackupManager(db_path=str(db_path), folder_id="F1", service_account_json_path="x", retention_count=30)

    real_bytes = db_path.read_bytes()
    _FakeAsyncClient.responses = [_FakeResponse(200, content=real_bytes)]

    result = await mgr.verify_backup_by_id("SOME_FILE_ID")

    assert result["valid"] is True
    assert result["schema_version"] == 2

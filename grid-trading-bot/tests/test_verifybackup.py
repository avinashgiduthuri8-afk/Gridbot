"""Tests for /verifybackup: resolving 'latest'/numeric arguments against
/restorelist's newest-first numbering, valid/failed verification display,
and graceful handling of Drive errors at every stage."""

from __future__ import annotations

from dataclasses import replace

import pytest

import bot_telegram.handlers as handlers_mod

pytestmark = pytest.mark.anyio


class FakeMessage:
    def __init__(self):
        self.replies: list[str] = []
        self.edits: list[str] = []

    async def reply_text(self, text: str, **kwargs) -> "FakeMessage":
        self.replies.append(text)
        return self

    async def edit_text(self, text: str, **kwargs) -> None:
        self.edits.append(text)


class FakeUser:
    def __init__(self, user_id: int):
        self.id = user_id


class FakeUpdate:
    def __init__(self, user_id: int = 111):
        self.effective_user = FakeUser(user_id)
        self.message = FakeMessage()


class FakeContext:
    def __init__(self, args=None):
        self.args = args or []


class FakeDriveBackupManager:
    def __init__(self, backups=None, verify_results=None, raise_on_list=None, raise_on_verify=None):
        self._backups = backups or []
        self._verify_results = verify_results or {}
        self._raise_on_list = raise_on_list
        self._raise_on_verify = raise_on_verify

    async def list_backups(self):
        if self._raise_on_list:
            raise self._raise_on_list
        return self._backups

    async def verify_backup_by_id(self, file_id):
        if self._raise_on_verify:
            raise self._raise_on_verify
        return self._verify_results.get(file_id, {"valid": False, "error": "not configured in test"})


def _make_backup(i: int, file_id: str | None = None) -> dict:
    return {
        "id": file_id or f"file_{i}",
        "name": f"dca_bot_backup_2026-07-{i:02d}.db",
        "createdTime": f"2026-07-{i:02d}T06:00:00.000Z",
        "size": "1000",
        "properties": {"backup_type": "auto", "schema_version": "2"},
    }


VALID_RESULT = {
    "valid": True, "integrity_check": "ok", "schema_version": 2,
    "row_counts": {"dca_grids": 3, "orders": 5, "trade_history": 2},
    "missing_optional_tables": [],
}
FAILED_RESULT = {
    "valid": False, "error": "Not a valid SQLite database: file is not a database",
    "integrity_check": None, "missing_critical_tables": [],
}


def _with_drive_manager(app_context, drive_backup_manager):
    new_settings = replace(app_context.settings, backup=replace(app_context.settings.backup, enabled=True))
    return replace(app_context, settings=new_settings, drive_backup_manager=drive_backup_manager)


def _get_cmd(app_context):
    class _StubApp:
        def __init__(self):
            self.handlers = []
        def add_handler(self, h):
            self.handlers.append(h)
    stub_app = _StubApp()
    handlers_mod.register_handlers(stub_app, app_context)
    return next(h.callback for h in stub_app.handlers if "verifybackup" in getattr(h, "commands", set()))


async def test_no_args_shows_usage(app_context):
    backups = [_make_backup(i) for i in range(1, 4)]
    ctx = _with_drive_manager(app_context, FakeDriveBackupManager(backups=backups))
    cmd = _get_cmd(ctx)
    update = FakeUpdate()
    await cmd(update, FakeContext())
    assert "Usage" in update.message.replies[-1]


async def test_latest_verifies_newest_backup(app_context):
    backups = [_make_backup(i) for i in range(1, 4)]  # file_3 is newest
    ctx = _with_drive_manager(
        app_context, FakeDriveBackupManager(backups=backups, verify_results={"file_3": VALID_RESULT}),
    )
    cmd = _get_cmd(ctx)
    update = FakeUpdate()
    await cmd(update, FakeContext(args=["latest"]))
    reply = update.message.edits[-1]
    assert "✅" in reply
    assert "Backup Verified" in reply
    assert "dca_bot_backup_2026-07-03" in reply


async def test_numeric_index_resolves_to_correct_backup(app_context):
    backups = [_make_backup(i) for i in range(1, 4)]
    # Newest-first: #1=file_3, #2=file_2, #3=file_1
    ctx = _with_drive_manager(
        app_context, FakeDriveBackupManager(backups=backups, verify_results={"file_2": VALID_RESULT}),
    )
    cmd = _get_cmd(ctx)
    update = FakeUpdate()
    await cmd(update, FakeContext(args=["2"]))
    reply = update.message.edits[-1]
    assert "✅" in reply
    assert "dca_bot_backup_2026-07-02" in reply


async def test_out_of_range_index_rejected(app_context):
    backups = [_make_backup(i) for i in range(1, 4)]
    ctx = _with_drive_manager(app_context, FakeDriveBackupManager(backups=backups))
    cmd = _get_cmd(ctx)
    update = FakeUpdate()
    await cmd(update, FakeContext(args=["99"]))
    assert "No backup #99" in update.message.replies[-1]


async def test_non_numeric_non_latest_arg_rejected(app_context):
    backups = [_make_backup(i) for i in range(1, 4)]
    ctx = _with_drive_manager(app_context, FakeDriveBackupManager(backups=backups))
    cmd = _get_cmd(ctx)
    update = FakeUpdate()
    await cmd(update, FakeContext(args=["banana"]))
    assert "must be an integer" in update.message.replies[-1]


async def test_failed_verification_shown_clearly(app_context):
    backups = [_make_backup(i) for i in range(1, 4)]
    ctx = _with_drive_manager(
        app_context, FakeDriveBackupManager(backups=backups, verify_results={"file_3": FAILED_RESULT}),
    )
    cmd = _get_cmd(ctx)
    update = FakeUpdate()
    await cmd(update, FakeContext(args=["latest"]))
    reply = update.message.edits[-1]
    assert "❌" in reply
    assert "FAILED Verification" in reply
    assert "not a database" in reply


async def test_empty_backup_list_handled(app_context):
    ctx = _with_drive_manager(app_context, FakeDriveBackupManager(backups=[]))
    cmd = _get_cmd(ctx)
    update = FakeUpdate()
    await cmd(update, FakeContext(args=["latest"]))
    assert "No backups found" in update.message.replies[-1]


async def test_drive_list_failure_handled_gracefully(app_context):
    ctx = _with_drive_manager(app_context, FakeDriveBackupManager(raise_on_list=ConnectionError("drive down")))
    cmd = _get_cmd(ctx)
    update = FakeUpdate()
    await cmd(update, FakeContext(args=["latest"]))
    assert "Could not reach Google Drive" in update.message.replies[-1]


async def test_drive_download_failure_during_verify_handled_gracefully(app_context):
    backups = [_make_backup(i) for i in range(1, 4)]
    ctx = _with_drive_manager(
        app_context, FakeDriveBackupManager(backups=backups, raise_on_verify=ConnectionError("download failed")),
    )
    cmd = _get_cmd(ctx)
    update = FakeUpdate()
    await cmd(update, FakeContext(args=["latest"]))
    assert "Could not verify" in update.message.edits[-1]


async def test_disabled_backup_shows_clear_message(app_context):
    ctx = replace(app_context, drive_backup_manager=None)
    cmd = _get_cmd(ctx)
    update = FakeUpdate()
    await cmd(update, FakeContext(args=["latest"]))
    assert "isn't enabled" in update.message.replies[-1]

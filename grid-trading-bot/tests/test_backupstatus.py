"""Tests for /backupstatus: disabled state, never-run state, recorded
success/failure display, and live Drive folder query (with graceful
failure handling)."""

from __future__ import annotations

import pytest
from dataclasses import replace

import bot_telegram.handlers as handlers_mod

pytestmark = pytest.mark.anyio


class FakeMessage:
    def __init__(self):
        self.replies: list[str] = []

    async def reply_text(self, text: str, **kwargs) -> None:
        self.replies.append(text)


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
    def __init__(self, backups=None, raise_on_list=None):
        self._backups = backups or []
        self._raise_on_list = raise_on_list

    async def list_backups(self):
        if self._raise_on_list:
            raise self._raise_on_list
        return self._backups


def _get_backupstatus_cmd(app_context):
    class _StubApp:
        def __init__(self):
            self.handlers = []
        def add_handler(self, h):
            self.handlers.append(h)
    stub_app = _StubApp()
    handlers_mod.register_handlers(stub_app, app_context)
    return next(h.callback for h in stub_app.handlers if getattr(h, "command", None) == "backupstatus")


def _with_backup_enabled(app_context, enabled: bool, drive_backup_manager=None):
    new_settings = replace(app_context.settings, backup=replace(app_context.settings.backup, enabled=enabled))
    return replace(app_context, settings=new_settings, drive_backup_manager=drive_backup_manager)


async def test_shows_disabled_when_backup_not_enabled(app_context):
    ctx = _with_backup_enabled(app_context, enabled=False)
    cmd = _get_backupstatus_cmd(ctx)
    update = FakeUpdate()
    await cmd(update, FakeContext())
    assert "Disabled" in update.message.replies[-1]


async def test_shows_never_run_when_enabled_but_no_backup_yet(app_context):
    ctx = _with_backup_enabled(app_context, enabled=True)
    cmd = _get_backupstatus_cmd(ctx)
    update = FakeUpdate()
    await cmd(update, FakeContext())
    assert "No backup has run yet" in update.message.replies[-1]


async def test_shows_last_success(app_context, repos):
    await repos.monitor_settings.record_backup_success("FILE_ABC")
    ctx = _with_backup_enabled(app_context, enabled=True)
    cmd = _get_backupstatus_cmd(ctx)
    update = FakeUpdate()
    await cmd(update, FakeContext())
    reply = update.message.replies[-1]
    assert "Last successful backup" in reply
    assert "FILE_ABC" in reply


async def test_shows_error_prominently_when_more_recent_than_success(app_context, repos):
    await repos.monitor_settings.record_backup_success("FILE_ABC")
    await repos.monitor_settings.record_backup_failure("Drive quota exceeded")
    ctx = _with_backup_enabled(app_context, enabled=True)
    cmd = _get_backupstatus_cmd(ctx)
    update = FakeUpdate()
    await cmd(update, FakeContext())
    reply = update.message.replies[-1]
    assert "🔴 Last error" in reply
    assert "Drive quota exceeded" in reply
    assert "FILE_ABC" in reply, "must still show the last known good backup alongside the error"


async def test_includes_live_drive_folder_count_when_manager_available(app_context):
    drive_mgr = FakeDriveBackupManager(backups=[{"id": "a"}, {"id": "b"}, {"id": "c"}])
    ctx = _with_backup_enabled(app_context, enabled=True, drive_backup_manager=drive_mgr)
    cmd = _get_backupstatus_cmd(ctx)
    update = FakeUpdate()
    await cmd(update, FakeContext())
    assert "3 backup(s) currently in the Drive folder" in update.message.replies[-1]


async def test_live_drive_query_failure_handled_gracefully(app_context):
    drive_mgr = FakeDriveBackupManager(raise_on_list=ConnectionError("simulated network failure"))
    ctx = _with_backup_enabled(app_context, enabled=True, drive_backup_manager=drive_mgr)
    cmd = _get_backupstatus_cmd(ctx)
    update = FakeUpdate()
    await cmd(update, FakeContext())
    assert "Could not reach Google Drive" in update.message.replies[-1]

"""Tests for /restorebackup: confirmation flow, staging, pending-restore
status display, cancellation, and graceful failure handling at every stage.

The actual file-swap logic is tested separately in tests/test_restore.py —
these tests cover the Telegram-facing command and its interaction with
storage.restore's staging functions.
"""

from __future__ import annotations

from dataclasses import replace

import pytest

import bot_telegram.handlers as handlers_mod
from storage.restore import cancel_pending_restore, get_pending_restore

pytestmark = pytest.mark.anyio


class FakeMessage:
    def __init__(self):
        self.replies: list[str] = []
        self.markups: list = []

    async def reply_text(self, text: str, reply_markup=None, **kwargs) -> None:
        self.replies.append(text)
        self.markups.append(reply_markup)


class FakeUser:
    def __init__(self, user_id: int):
        self.id = user_id


class FakeCallbackQuery:
    def __init__(self, data: str, user_id: int):
        self.data = data
        self.from_user = FakeUser(user_id)
        self.edited: list[str] = []
        self.answered: list[tuple] = []

    async def answer(self, text: str | None = None, show_alert: bool = False) -> None:
        self.answered.append((text, show_alert))

    async def edit_message_text(self, text: str, **kwargs) -> None:
        self.edited.append(text)


class FakeUpdate:
    def __init__(self, user_id: int = 111):
        self.effective_user = FakeUser(user_id)
        self.message = FakeMessage()
        self.callback_query: FakeCallbackQuery | None = None


class FakeContext:
    def __init__(self, args=None):
        self.args = args or []


class FakeDriveBackupManager:
    def __init__(self, backups=None, raise_on_list=None, raise_on_verify=None):
        self._backups = backups or []
        self._raise_on_list = raise_on_list
        self._raise_on_verify = raise_on_verify

    async def list_backups(self):
        if self._raise_on_list:
            raise self._raise_on_list
        return self._backups

    async def verify_backup_by_id(self, file_id):
        if self._raise_on_verify:
            raise self._raise_on_verify
        return {"valid": True, "integrity_check": "ok", "schema_version": 2}

    async def download_backup(self, file_id):
        return b"fake sqlite bytes for staging"


def _make_backup(i: int, file_id: str | None = None) -> dict:
    return {
        "id": file_id or f"file_{i}",
        "name": f"dca_bot_backup_2026-07-{i:02d}.db",
        "createdTime": f"2026-07-{i:02d}T06:00:00.000Z",
        "size": "1000",
        "properties": {"backup_type": "auto", "schema_version": "2"},
    }


def _with_drive_manager(app_context, drive_backup_manager, db_path):
    new_settings = replace(
        app_context.settings,
        backup=replace(app_context.settings.backup, enabled=True),
        database_path=str(db_path),
    )
    return replace(app_context, settings=new_settings, drive_backup_manager=drive_backup_manager)


def _get_commands(app_context):
    class _StubApp:
        def __init__(self):
            self.handlers = []
        def add_handler(self, h):
            self.handlers.append(h)
    stub_app = _StubApp()
    handlers_mod.register_handlers(stub_app, app_context)
    cmd = next(h.callback for h in stub_app.handlers if "restorebackup" in getattr(h, "commands", set()))
    confirm_cb = next(
        h.callback for h in stub_app.handlers if getattr(getattr(h, "pattern", None), "pattern", None) == "^restorebackup_confirm:"
    )
    return cmd, confirm_cb


@pytest.fixture(autouse=True)
def _clean_restore_state(tmp_path):
    db_path = tmp_path / "grid_bot.db"
    cancel_pending_restore(str(db_path))
    yield db_path
    cancel_pending_restore(str(db_path))


async def test_no_args_no_pending_shows_usage(app_context, _clean_restore_state):
    db_path = _clean_restore_state
    backups = [_make_backup(i) for i in range(1, 4)]
    ctx = _with_drive_manager(app_context, FakeDriveBackupManager(backups=backups), db_path)
    cmd, _ = _get_commands(ctx)
    update = FakeUpdate()
    await cmd(update, FakeContext())
    assert "Usage" in update.message.replies[-1]


async def test_cancel_with_nothing_pending(app_context, _clean_restore_state):
    db_path = _clean_restore_state
    ctx = _with_drive_manager(app_context, FakeDriveBackupManager(), db_path)
    cmd, _ = _get_commands(ctx)
    update = FakeUpdate()
    await cmd(update, FakeContext(args=["cancel"]))
    assert "no pending" in update.message.replies[-1].lower()


async def test_valid_target_shows_confirmation_screen(app_context, _clean_restore_state):
    db_path = _clean_restore_state
    backups = [_make_backup(i) for i in range(1, 4)]
    ctx = _with_drive_manager(app_context, FakeDriveBackupManager(backups=backups), db_path)
    cmd, _ = _get_commands(ctx)
    update = FakeUpdate()
    await cmd(update, FakeContext(args=["latest"]))
    reply = update.message.replies[-1]
    assert "Confirm Database Restore" in reply
    assert "replace your entire database" in reply
    assert update.message.markups[-1] is not None


async def test_confirming_stages_the_restore(app_context, _clean_restore_state):
    db_path = _clean_restore_state
    backups = [_make_backup(i) for i in range(1, 4)]
    ctx = _with_drive_manager(app_context, FakeDriveBackupManager(backups=backups), db_path)
    cmd, confirm_cb = _get_commands(ctx)

    update = FakeUpdate()
    await cmd(update, FakeContext(args=["latest"]))
    confirm_data = update.message.markups[-1].inline_keyboard[0][0].callback_data

    cb_update = FakeUpdate()
    cb_update.callback_query = FakeCallbackQuery(confirm_data, 111)
    await confirm_cb(cb_update, FakeContext())

    assert "Restore staged" in cb_update.callback_query.edited[-1]
    pending = get_pending_restore(str(db_path))
    assert pending is not None
    assert pending["source_name"] == "dca_bot_backup_2026-07-03.db"


async def test_no_args_with_pending_shows_status(app_context, _clean_restore_state):
    db_path = _clean_restore_state
    backups = [_make_backup(i) for i in range(1, 4)]
    ctx = _with_drive_manager(app_context, FakeDriveBackupManager(backups=backups), db_path)
    cmd, confirm_cb = _get_commands(ctx)

    update = FakeUpdate()
    await cmd(update, FakeContext(args=["latest"]))
    confirm_data = update.message.markups[-1].inline_keyboard[0][0].callback_data
    cb_update = FakeUpdate()
    cb_update.callback_query = FakeCallbackQuery(confirm_data, 111)
    await confirm_cb(cb_update, FakeContext())

    status_update = FakeUpdate()
    await cmd(status_update, FakeContext())
    assert "already staged" in status_update.message.replies[-1]


async def test_cancel_removes_staged_restore(app_context, _clean_restore_state):
    db_path = _clean_restore_state
    backups = [_make_backup(i) for i in range(1, 4)]
    ctx = _with_drive_manager(app_context, FakeDriveBackupManager(backups=backups), db_path)
    cmd, confirm_cb = _get_commands(ctx)

    update = FakeUpdate()
    await cmd(update, FakeContext(args=["latest"]))
    confirm_data = update.message.markups[-1].inline_keyboard[0][0].callback_data
    cb_update = FakeUpdate()
    cb_update.callback_query = FakeCallbackQuery(confirm_data, 111)
    await confirm_cb(cb_update, FakeContext())

    cancel_update = FakeUpdate()
    await cmd(cancel_update, FakeContext(args=["cancel"]))
    assert "cancelled" in cancel_update.message.replies[-1].lower()
    assert get_pending_restore(str(db_path)) is None


async def test_declining_confirmation_stages_nothing(app_context, _clean_restore_state):
    db_path = _clean_restore_state
    backups = [_make_backup(i) for i in range(1, 4)]
    ctx = _with_drive_manager(app_context, FakeDriveBackupManager(backups=backups), db_path)
    cmd, confirm_cb = _get_commands(ctx)

    update = FakeUpdate()
    await cmd(update, FakeContext(args=["1"]))
    cancel_data = update.message.markups[-1].inline_keyboard[0][1].callback_data

    cb_update = FakeUpdate()
    cb_update.callback_query = FakeCallbackQuery(cancel_data, 111)
    await confirm_cb(cb_update, FakeContext())

    assert "cancelled" in cb_update.callback_query.edited[-1].lower()
    assert get_pending_restore(str(db_path)) is None


async def test_unauthorized_user_rejected_on_confirm(app_context, _clean_restore_state):
    db_path = _clean_restore_state
    backups = [_make_backup(i) for i in range(1, 4)]
    ctx = _with_drive_manager(app_context, FakeDriveBackupManager(backups=backups), db_path)
    cmd, confirm_cb = _get_commands(ctx)

    update = FakeUpdate()
    await cmd(update, FakeContext(args=["1"]))
    confirm_data = update.message.markups[-1].inline_keyboard[0][0].callback_data

    cb_update = FakeUpdate(user_id=999)
    cb_update.callback_query = FakeCallbackQuery(confirm_data, 999)
    await confirm_cb(cb_update, FakeContext())

    assert cb_update.callback_query.answered[-1][0] == "Not authorized."
    assert get_pending_restore(str(db_path)) is None


async def test_staging_failure_handled_gracefully(app_context, _clean_restore_state):
    db_path = _clean_restore_state
    backups = [_make_backup(i) for i in range(1, 4)]
    ctx = _with_drive_manager(
        app_context,
        FakeDriveBackupManager(backups=backups, raise_on_verify=ConnectionError("Drive down")),
        db_path,
    )
    cmd, confirm_cb = _get_commands(ctx)

    update = FakeUpdate()
    await cmd(update, FakeContext(args=["1"]))
    confirm_data = update.message.markups[-1].inline_keyboard[0][0].callback_data

    cb_update = FakeUpdate()
    cb_update.callback_query = FakeCallbackQuery(confirm_data, 111)
    await confirm_cb(cb_update, FakeContext())

    assert "Could not stage" in cb_update.callback_query.edited[-1]
    assert get_pending_restore(str(db_path)) is None


async def test_disabled_backup_shows_clear_message(app_context, _clean_restore_state):
    db_path = _clean_restore_state
    ctx = _with_drive_manager(app_context, None, db_path)
    cmd, _ = _get_commands(ctx)
    update = FakeUpdate()
    await cmd(update, FakeContext(args=["latest"]))
    assert "isn't enabled" in update.message.replies[-1]

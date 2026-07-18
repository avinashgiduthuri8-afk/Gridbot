"""Tests for /restorelist: newest-first ordering, pagination, empty folder,
Drive API failures, and malformed/missing backup metadata — all six
scenarios required by TASK-15C."""

from __future__ import annotations

from dataclasses import replace

import pytest

import bot_telegram.handlers as handlers_mod

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
    def __init__(self, backups=None, raise_exc: Exception | None = None):
        self._backups = backups or []
        self._raise_exc = raise_exc

    async def list_backups(self):
        if self._raise_exc:
            raise self._raise_exc
        return self._backups


def _make_backup(i: int, **overrides) -> dict:
    base = {
        "id": f"file_{i}",
        "name": f"dca_bot_backup_2026-07-{i:02d}T06-00-00.db",
        "createdTime": f"2026-07-{i:02d}T06:00:00.000Z",
        "size": "123456",
        "properties": {"backup_type": "auto", "schema_version": "2"},
    }
    base.update(overrides)
    return base


def _with_drive_manager(app_context, drive_backup_manager):
    new_settings = replace(app_context.settings, backup=replace(app_context.settings.backup, enabled=True))
    return replace(app_context, settings=new_settings, drive_backup_manager=drive_backup_manager)


def _get_commands(app_context):
    class _StubApp:
        def __init__(self):
            self.handlers = []
        def add_handler(self, h):
            self.handlers.append(h)
    stub_app = _StubApp()
    handlers_mod.register_handlers(stub_app, app_context)
    cmd = next(h.callback for h in stub_app.handlers if getattr(h, "command", None) == "restorelist")
    page_cb = next(h.callback for h in stub_app.handlers if getattr(h, "pattern", None) == "^restorelist_page:")
    return cmd, page_cb


# ---------------------------------------------------------------------------
# 1. No backups
# ---------------------------------------------------------------------------

async def test_no_backups_shows_empty_message(app_context):
    ctx = _with_drive_manager(app_context, FakeDriveBackupManager(backups=[]))
    cmd, _ = _get_commands(ctx)
    update = FakeUpdate()
    await cmd(update, FakeContext())
    assert "No backups found" in update.message.replies[-1]


# ---------------------------------------------------------------------------
# 2. One backup
# ---------------------------------------------------------------------------

async def test_one_backup_shows_correctly(app_context):
    ctx = _with_drive_manager(app_context, FakeDriveBackupManager(backups=[_make_backup(1)]))
    cmd, _ = _get_commands(ctx)
    update = FakeUpdate()
    await cmd(update, FakeContext())
    reply = update.message.replies[-1]
    assert "Total backups: 1" in reply
    assert "Page 1/1" in reply
    assert update.message.markups[-1] is None, "a single page must show no pagination buttons"


# ---------------------------------------------------------------------------
# 3. Multiple backups — newest first
# ---------------------------------------------------------------------------

async def test_multiple_backups_sorted_newest_first(app_context):
    backups = [_make_backup(i) for i in range(1, 6)]  # oldest-first, as list_backups() returns
    ctx = _with_drive_manager(app_context, FakeDriveBackupManager(backups=backups))
    cmd, _ = _get_commands(ctx)
    update = FakeUpdate()
    await cmd(update, FakeContext())
    reply = update.message.replies[-1]
    first_entry_line = next(line for line in reply.split("\n") if line.startswith("1. "))
    assert first_entry_line.startswith("1. 2026-07-05"), "backup #5 (newest) must be listed first"


# ---------------------------------------------------------------------------
# 4. Pagination across multiple pages
# ---------------------------------------------------------------------------

async def test_pagination_across_multiple_pages(app_context):
    backups = [_make_backup(i) for i in range(1, 26)]  # 25 backups -> 3 pages of 10
    ctx = _with_drive_manager(app_context, FakeDriveBackupManager(backups=backups))
    cmd, page_cb = _get_commands(ctx)

    update = FakeUpdate()
    await cmd(update, FakeContext())
    assert "Page 1/3" in update.message.replies[-1]
    buttons = update.message.markups[-1].rows[0]
    assert len(buttons) == 1 and "Next" in buttons[0].text, "page 1 must only show Next, no Prev"

    next_update = FakeUpdate()
    next_update.callback_query = FakeCallbackQuery(buttons[0].callback_data, 111)
    await page_cb(next_update, FakeContext())
    assert "Page 2/3" in next_update.callback_query.edited[-1]
    assert "11. " in next_update.callback_query.edited[-1], "page 2 must continue numbering from 11, not reset"

    last_page_update = FakeUpdate()
    last_page_update.callback_query = FakeCallbackQuery("restorelist_page:3", 111)
    await page_cb(last_page_update, FakeContext())
    assert "Page 3/3" in last_page_update.callback_query.edited[-1]


async def test_restorelist_with_page_argument_jumps_directly(app_context):
    backups = [_make_backup(i) for i in range(1, 26)]
    ctx = _with_drive_manager(app_context, FakeDriveBackupManager(backups=backups))
    cmd, _ = _get_commands(ctx)
    update = FakeUpdate()
    await cmd(update, FakeContext(args=["2"]))
    assert "Page 2/3" in update.message.replies[-1]


# ---------------------------------------------------------------------------
# 5. Drive API failure
# ---------------------------------------------------------------------------

async def test_drive_api_failure_handled_gracefully(app_context):
    ctx = _with_drive_manager(
        app_context, FakeDriveBackupManager(raise_exc=ConnectionError("simulated Drive outage")),
    )
    cmd, _ = _get_commands(ctx)
    update = FakeUpdate()
    await cmd(update, FakeContext())
    assert "Could not reach Google Drive" in update.message.replies[-1]


async def test_drive_api_failure_during_pagination_handled_gracefully(app_context):
    ctx = _with_drive_manager(
        app_context, FakeDriveBackupManager(raise_exc=TimeoutError("timed out")),
    )
    _, page_cb = _get_commands(ctx)
    update = FakeUpdate()
    update.callback_query = FakeCallbackQuery("restorelist_page:2", 111)
    await page_cb(update, FakeContext())
    assert "Could not reach Google Drive" in update.callback_query.edited[-1]


# ---------------------------------------------------------------------------
# 6. Invalid / missing metadata
# ---------------------------------------------------------------------------

async def test_missing_and_malformed_metadata_handled_gracefully(app_context):
    malformed = [
        {"id": "f1", "name": "dca_bot_backup_weird.db"},  # missing everything else
        {"id": "f2", "name": "dca_bot_backup_bad_size.db", "size": "not_a_number",
         "createdTime": "2026-07-10T06:00:00.000Z"},
        {"id": "f3", "name": "dca_bot_backup_no_props.db", "size": "5000",
         "createdTime": "2026-07-11T06:00:00.000Z", "properties": None},
    ]
    ctx = _with_drive_manager(app_context, FakeDriveBackupManager(backups=malformed))
    cmd, _ = _get_commands(ctx)
    update = FakeUpdate()
    await cmd(update, FakeContext())  # must not raise
    reply = update.message.replies[-1]
    assert "unknown date" in reply
    assert "unknown size" in reply
    assert "Schema vunknown" in reply
    assert "Auto" in reply  # missing properties still defaults to Auto, not a crash


async def test_disabled_backup_shows_clear_message(app_context):
    ctx = replace(app_context, drive_backup_manager=None)
    cmd, _ = _get_commands(ctx)
    update = FakeUpdate()
    await cmd(update, FakeContext())
    assert "isn't enabled" in update.message.replies[-1]

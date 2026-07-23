"""Safe, restart-based restore-from-backup flow.

Restoring the live database while the bot is actively running (an open
aiosqlite connection, background monitor loops, and Telegram handlers all
holding references built once at startup in main.py's async_main()) is not
something this codebase attempts to do live. Hot-swapping the DB connection
out from under DCAManager/OrderMonitor/PriceMonitor/RiskManager would mean
rebuilding that entire dependency graph at runtime — far riskier than
asking for one restart.

Instead: /restorebackup downloads, verifies, and *stages* the target backup
file, then writes a small marker recording what's pending and tells the
user to restart the bot. On the *next* startup, main.py calls
apply_pending_restore_if_any() before ever opening a database connection —
it safely swaps the file in (backing up the current live DB first, and
clearing any stale -wal/-shm sidecar files so they can never be misapplied
against the new main file — a mismatched WAL file next to a swapped-in main
file is a real corruption risk, not a theoretical one), then normal startup
proceeds against the restored database.
"""

from __future__ import annotations

import json
import os
import shutil
import time
from pathlib import Path

from storage.drive_backup import verify_sqlite_integrity
from utils.logger import get_logger

log = get_logger("database")

_MARKER_FILENAME = ".pending_restore.json"
_STAGED_FILENAME = ".staged_restore.db"


def _marker_path(db_path: str) -> Path:
    return Path(db_path).parent / _MARKER_FILENAME


def _staged_path(db_path: str) -> Path:
    return Path(db_path).parent / _STAGED_FILENAME


async def stage_restore(drive_backup_manager, file_id: str, db_path: str, source_name: str) -> dict:
    """Download and verify the target backup, write it to a staging path,
    and record a pending-restore marker. Does NOT touch the live database —
    that only happens on the next startup, via apply_pending_restore_if_any().

    Raises DriveBackupError (propagated from download/verify) if the backup
    can't be fetched or fails integrity verification — a bad backup is
    never staged, so there's nothing for the next startup to accidentally
    apply.
    """
    staged = _staged_path(db_path)
    result = await drive_backup_manager.verify_backup_by_id(file_id)
    if not result["valid"]:
        from storage.drive_backup import DriveBackupError
        raise DriveBackupError(
            f"Refusing to stage this backup — it failed integrity verification: "
            f"{result.get('error') or result}"
        )

    file_bytes = await drive_backup_manager.download_backup(file_id)
    staged.write_bytes(file_bytes)

    marker = {
        "staged_at": time.time(),
        "source_file_id": file_id,
        "source_name": source_name,
        "schema_version": result.get("schema_version"),
    }
    _marker_path(db_path).write_text(json.dumps(marker))
    log.warning(
        "Restore staged from backup %s (file_id=%s) — will be applied on the NEXT "
        "restart, before this session's live database is touched.",
        source_name, file_id,
    )
    return marker


def get_pending_restore(db_path: str) -> dict | None:
    marker = _marker_path(db_path)
    if not marker.exists():
        return None
    try:
        return json.loads(marker.read_text())
    except (json.JSONDecodeError, OSError):
        return None


def cancel_pending_restore(db_path: str) -> bool:
    """Remove any pending restore marker and staged file. Returns True if
    there was one to cancel."""
    had_one = False
    marker = _marker_path(db_path)
    if marker.exists():
        marker.unlink()
        had_one = True
    staged = _staged_path(db_path)
    if staged.exists():
        staged.unlink()
        had_one = True
    return had_one


def apply_pending_restore_if_any(db_path: str) -> dict | None:
    """Called once, at the very start of main.py's async_main(), before
    Database(...) is ever constructed. If a restore is pending: verify the
    staged file one more time (defense in depth against tampering or a
    partial write since staging), back up the current live DB, clear stale
    WAL/SHM sidecar files, and atomically swap the staged file into place.

    Returns a summary dict if a restore was applied, or None if there was
    nothing pending. Deliberately synchronous (blocking) I/O — this runs
    before the event loop is doing anything else that matters, and the
    files involved are already local, not network calls.
    """
    marker = get_pending_restore(db_path)
    if marker is None:
        return None

    staged = _staged_path(db_path)
    if not staged.exists():
        log.error(
            "Pending restore marker found but the staged file is missing (%s) — "
            "discarding the marker and starting up against the existing database "
            "unchanged.", staged,
        )
        cancel_pending_restore(db_path)
        return None

    # Defense in depth: re-verify the staged file right before applying it,
    # not just when it was first staged — catches disk corruption or
    # tampering in between.
    recheck = verify_sqlite_integrity(staged)
    if not recheck["valid"]:
        log.error(
            "Staged restore file failed re-verification at apply time — aborting "
            "the restore and starting up against the existing database unchanged. "
            "Details: %s", recheck.get("error") or recheck,
        )
        cancel_pending_restore(db_path)
        return None

    db_path_obj = Path(db_path)
    backup_of_current: str | None = None
    if db_path_obj.exists():
        timestamp = time.strftime("%Y%m%dT%H%M%S", time.gmtime())
        pre_restore_backup = db_path_obj.parent / f"{db_path_obj.stem}.pre_restore_{timestamp}.bak"
        shutil.copy2(db_path_obj, pre_restore_backup)
        backup_of_current = str(pre_restore_backup)
        log.warning("Backed up the current live database to %s before restoring.", pre_restore_backup)

    # A WAL/SHM file is tied to a specific main database file's write-ahead
    # log — leaving the OLD database's sidecar files sitting next to the
    # NEWLY swapped-in main file risks SQLite applying unrelated WAL frames
    # against it, which is real corruption, not a cosmetic issue.
    for suffix in ("-wal", "-shm"):
        stale = Path(f"{db_path}{suffix}")
        if stale.exists():
            stale.unlink()
            log.info("Removed stale %s before restore.", stale)

    os.replace(staged, db_path_obj)  # atomic on the same filesystem
    cancel_pending_restore(db_path)  # marker only at this point; staged file already moved

    summary = {
        "source_name": marker.get("source_name"),
        "source_file_id": marker.get("source_file_id"),
        "schema_version": marker.get("schema_version"),
        "backup_of_previous_db": backup_of_current,
    }
    log.warning(
        "Restore applied from backup %s (file_id=%s). Previous database backed up to %s.",
        summary["source_name"], summary["source_file_id"], backup_of_current,
    )
    return summary

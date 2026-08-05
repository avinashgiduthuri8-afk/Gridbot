"""Monitor settings table repository (key-value store: price monitor
interval, emergency stop flag, Drive backup status)."""
from __future__ import annotations

import json
from typing import Any

from storage.database import Database
from utils.helpers import now_iso

VALID_MONITOR_INTERVALS = (2, 5, 10, 15, 30)
DEFAULT_MONITOR_INTERVAL = 5

class MonitorSettingsRepository:
    """Persists key-value pairs for the price monitor (interval, etc.)."""

    _KEY_INTERVAL = "price_monitor_interval"
    _KEY_EMERGENCY_STOP = "emergency_stop"
    _KEY_BACKUP_STATUS = "drive_backup_status"

    def __init__(self, db: Database) -> None:
        self._db = db

    async def get_backup_status(self) -> dict[str, Any] | None:
        """Return the last-known Drive backup outcome, or None if a backup
        has never run this database's lifetime. Shape:
        {last_success_at, last_success_file_id, last_error_at, last_error_message}
        (any of these may be None/absent individually).
        """
        cur = await self._db.connection.execute(
            "SELECT value FROM monitor_settings WHERE key = ?",
            (self._KEY_BACKUP_STATUS,),
        )
        row = await cur.fetchone()
        if row is None:
            return None
        return json.loads(row["value"])

    async def record_backup_success(self, file_id: str) -> None:
        """Record a successful backup, clearing any previously-recorded
        error (a fresh success supersedes it for status-reporting purposes)."""
        status = await self.get_backup_status() or {}
        status["last_success_at"] = now_iso()
        status["last_success_file_id"] = file_id
        status["last_error_at"] = None
        status["last_error_message"] = None
        await self._save_backup_status(status)

    async def record_backup_failure(self, error_message: str) -> None:
        """Record a failed backup attempt. Deliberately does NOT clear the
        last recorded success — /backupstatus should still be able to show
        "last good backup was N hours ago" even while also showing the most
        recent failure.
        """
        status = await self.get_backup_status() or {}
        status["last_error_at"] = now_iso()
        status["last_error_message"] = error_message
        await self._save_backup_status(status)

    async def _save_backup_status(self, status: dict[str, Any]) -> None:
        await self._db.connection.execute(
            """INSERT INTO monitor_settings (key, value, updated_at)
               VALUES (?, ?, ?)
               ON CONFLICT(key) DO UPDATE SET value = excluded.value,
                                              updated_at = excluded.updated_at""",
            (self._KEY_BACKUP_STATUS, json.dumps(status), now_iso()),
        )
        await self._db.connection.commit()

    async def get_emergency_stop(self) -> bool:
        """Return the persisted emergency-stop state (defaults to False)."""
        cur = await self._db.connection.execute(
            "SELECT value FROM monitor_settings WHERE key = ?",
            (self._KEY_EMERGENCY_STOP,),
        )
        row = await cur.fetchone()
        if row is None:
            return False
        return row["value"] == "1"

    async def set_emergency_stop(self, active: bool) -> None:
        """Persist the emergency-stop flag so it survives a restart."""
        await self._db.connection.execute(
            """INSERT INTO monitor_settings (key, value, updated_at)
               VALUES (?, ?, ?)
               ON CONFLICT(key) DO UPDATE SET value = excluded.value,
                                              updated_at = excluded.updated_at""",
            (self._KEY_EMERGENCY_STOP, "1" if active else "0", now_iso()),
        )
        await self._db.connection.commit()

    async def get_interval(self) -> int | None:
        """Return the stored interval, or None if never explicitly set.

        Callers should fall back to their own default when None is returned
        so that environment-variable configuration is honoured on first start.
        """
        cur = await self._db.connection.execute(
            "SELECT value FROM monitor_settings WHERE key = ?",
            (self._KEY_INTERVAL,),
        )
        row = await cur.fetchone()
        if row is None:
            return None
        try:
            value = int(row["value"])
        except (ValueError, KeyError):
            return None
        if value not in VALID_MONITOR_INTERVALS:
            return None
        return value

    async def set_interval(self, seconds: int) -> None:
        """Persist the monitor interval (must be one of VALID_MONITOR_INTERVALS)."""
        if seconds not in VALID_MONITOR_INTERVALS:
            raise ValueError(
                f"Invalid monitor interval {seconds}s. "
                f"Allowed: {', '.join(str(v) for v in VALID_MONITOR_INTERVALS)}s"
            )
        await self._db.connection.execute(
            """INSERT INTO monitor_settings (key, value, updated_at)
               VALUES (?, ?, ?)
               ON CONFLICT(key) DO UPDATE SET value = excluded.value,
                                              updated_at = excluded.updated_at""",
            (self._KEY_INTERVAL, str(seconds), now_iso()),
        )
        await self._db.connection.commit()

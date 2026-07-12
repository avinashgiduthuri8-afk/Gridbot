"""Automatic off-box backup of the SQLite database to Google Drive.

Uses a service account (no interactive OAuth flow needed for a headless
bot) and talks to the Drive v3 REST API directly via httpx, rather than
pulling in the full google-api-python-client — this keeps the dependency
surface small and consistent with how exchange/coindcx.py already talks to
CoinDCX directly over REST rather than through an SDK.

Setup (see README for the full walkthrough):
  1. Create a Google Cloud service account, download its JSON key file.
  2. Create (or reuse) a Drive folder, share it with the service account's
     email address (Editor access), and note the folder ID from its URL.
  3. Set GOOGLE_DRIVE_ENABLED=true, GOOGLE_DRIVE_FOLDER_ID=<folder id>,
     GOOGLE_DRIVE_SERVICE_ACCOUNT_JSON=<path to the key file>.
"""

from __future__ import annotations

import asyncio
import json
import sqlite3
from pathlib import Path

import httpx
from google.auth.transport.requests import Request as GoogleAuthRequest
from google.oauth2.service_account import Credentials as ServiceAccountCredentials

from utils.helpers import now_iso
from utils.logger import get_logger

log = get_logger("drive_backup")

_SCOPES = ["https://www.googleapis.com/auth/drive.file"]
_UPLOAD_URL = "https://www.googleapis.com/upload/drive/v3/files?uploadType=multipart"
_FILES_URL = "https://www.googleapis.com/drive/v3/files"
_TIMEOUT = 60.0


class DriveBackupError(Exception):
    """Raised when a backup upload, list, or prune operation fails."""


class DriveBackupManager:
    def __init__(
        self,
        db_path: str,
        folder_id: str,
        service_account_json_path: str,
        retention_count: int = 14,
    ) -> None:
        self._db_path = db_path
        self._folder_id = folder_id
        self._service_account_json_path = service_account_json_path
        self._retention_count = max(1, retention_count)
        self._credentials: ServiceAccountCredentials | None = None

    # ------------------------------------------------------------------
    # Auth
    # ------------------------------------------------------------------

    def _get_access_token(self) -> str:
        """Mint (or refresh) a bearer token. Blocking — call via asyncio.to_thread."""
        if self._credentials is None:
            self._credentials = ServiceAccountCredentials.from_service_account_file(
                self._service_account_json_path, scopes=_SCOPES,
            )
        if not self._credentials.valid:
            self._credentials.refresh(GoogleAuthRequest())
        return self._credentials.token

    async def _auth_headers(self) -> dict[str, str]:
        token = await asyncio.to_thread(self._get_access_token)
        return {"Authorization": f"Bearer {token}"}

    # ------------------------------------------------------------------
    # Consistent snapshot
    # ------------------------------------------------------------------

    def _make_consistent_snapshot(self, snapshot_path: Path) -> None:
        """Produce a self-consistent copy of the WAL-mode database.

        The existing manual /backup command reads the raw .db file directly,
        which — under WAL mode — can miss rows still sitting in the -wal
        sidecar file that haven't been checkpointed into the main file yet.
        Using sqlite3's own backup API (via a short-lived blocking
        connection) guarantees a complete, consistent snapshot regardless of
        WAL state, without needing to touch the live aiosqlite connection.
        Blocking — call via asyncio.to_thread.
        """
        src = sqlite3.connect(f"file:{self._db_path}?mode=ro", uri=True)
        try:
            dst = sqlite3.connect(str(snapshot_path))
            try:
                src.backup(dst)
            finally:
                dst.close()
        finally:
            src.close()

    # ------------------------------------------------------------------
    # Upload / list / prune
    # ------------------------------------------------------------------

    async def create_backup_and_upload(self) -> str:
        """Snapshot the DB, upload it to Drive, prune old backups. Returns the
        uploaded file's Drive ID."""
        if not Path(self._db_path).exists():
            raise DriveBackupError(f"No database file found at {self._db_path}")

        snapshot_name = f"dca_bot_backup_{now_iso().replace(':', '-')}.db"
        snapshot_path = Path(self._db_path).parent / f".drive_snapshot_{snapshot_name}"
        try:
            await asyncio.to_thread(self._make_consistent_snapshot, snapshot_path)
            file_id = await self._upload(snapshot_path, snapshot_name)
        finally:
            snapshot_path.unlink(missing_ok=True)

        await self._prune_old_backups()
        return file_id

    async def _upload(self, file_path: Path, filename: str) -> str:
        headers = await self._auth_headers()
        metadata = {"name": filename, "parents": [self._folder_id]}
        file_bytes = await asyncio.to_thread(file_path.read_bytes)

        async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
            files = {
                "metadata": (None, json.dumps(metadata), "application/json"),
                "file": (filename, file_bytes, "application/x-sqlite3"),
            }
            resp = await client.post(_UPLOAD_URL, headers=headers, files=files)
        if resp.status_code >= 400:
            raise DriveBackupError(f"Drive upload failed ({resp.status_code}): {resp.text[:300]}")
        data = resp.json()
        file_id = data.get("id")
        if not file_id:
            raise DriveBackupError(f"Drive upload response missing file id: {data}")
        log.info("Uploaded backup to Google Drive: %s (id=%s)", filename, file_id)
        return file_id

    async def list_backups(self) -> list[dict]:
        """Return backups in the configured folder, oldest first."""
        headers = await self._auth_headers()
        params = {
            "q": f"'{self._folder_id}' in parents and trashed = false and name contains 'dca_bot_backup_'",
            "orderBy": "createdTime",
            "fields": "files(id,name,createdTime)",
            "pageSize": 1000,
        }
        async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
            resp = await client.get(_FILES_URL, headers=headers, params=params)
        if resp.status_code >= 400:
            raise DriveBackupError(f"Drive list failed ({resp.status_code}): {resp.text[:300]}")
        return resp.json().get("files", [])

    async def _prune_old_backups(self) -> int:
        """Delete the oldest backups beyond the configured retention count.
        Returns the number of files deleted. A failure to prune is logged
        but never raised — a backup upload that succeeded should not be
        reported as failed just because cleanup of old copies didn't.
        """
        try:
            backups = await self.list_backups()
        except DriveBackupError as exc:
            log.warning("Could not list Drive backups for pruning: %s", exc)
            return 0

        excess = len(backups) - self._retention_count
        if excess <= 0:
            return 0

        headers = await self._auth_headers()
        deleted = 0
        async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
            for old in backups[:excess]:
                resp = await client.delete(f"{_FILES_URL}/{old['id']}", headers=headers)
                if resp.status_code >= 400 and resp.status_code != 404:
                    log.warning(
                        "Failed to prune old Drive backup %s: %s", old.get("name"), resp.text[:200]
                    )
                    continue
                deleted += 1
        if deleted:
            log.info("Pruned %d old Drive backup(s), retaining %d most recent", deleted, self._retention_count)
        return deleted

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
import tempfile
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


# Tables that have existed since the very first schema version — a backup
# missing any of these is not a viable restore target regardless of when it
# was taken. Tables added by later migrations (grid_defaults, price_alerts,
# schema_migrations itself) are checked too but reported as informational
# only, since a genuinely old backup can legitimately predate them.
CRITICAL_TABLES = ("dca_grids", "orders", "trade_history")
ALL_EXPECTED_TABLES = (
    "dca_grids", "orders", "trade_history", "daily_stats", "logs",
    "monitor_settings", "price_alerts", "grid_defaults", "schema_migrations",
)


def verify_sqlite_integrity(db_path: Path) -> dict:
    """Open db_path as SQLite and check it's actually a usable backup —
    not just a file that happens to exist.

    Returns a dict, never raises for an integrity problem (a corrupt file
    is an expected, reportable outcome, not a bug in this function):
      {
        "valid": bool,                 # overall pass/fail
        "integrity_check": str,        # SQLite's own PRAGMA integrity_check result
        "openable": bool,              # could we even open it as SQLite at all
        "tables_found": [...],
        "missing_critical_tables": [...],
        "missing_optional_tables": [...],
        "schema_version": int | None,
        "row_counts": {"dca_grids": N, "orders": N, "trade_history": N},
        "error": str | None,
      }

    valid=True requires: openable, integrity_check == "ok", and every
    CRITICAL_TABLES table present. Missing optional tables alone don't fail
    verification, just get reported.
    """
    result = {
        "valid": False, "integrity_check": None, "openable": False,
        "tables_found": [], "missing_critical_tables": [], "missing_optional_tables": [],
        "schema_version": None, "row_counts": {}, "error": None,
    }

    if not Path(db_path).exists():
        result["error"] = f"File does not exist: {db_path}"
        return result

    try:
        conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    except sqlite3.Error as exc:
        result["error"] = f"Could not open as SQLite: {exc}"
        return result

    try:
        result["openable"] = True

        try:
            cur = conn.execute("PRAGMA integrity_check")
            row = cur.fetchone()
            result["integrity_check"] = row[0] if row else "no result"
        except sqlite3.DatabaseError as exc:
            # A file that opens but isn't actually a valid SQLite database
            # (e.g. truncated mid-transfer) fails right here.
            result["error"] = f"Not a valid SQLite database: {exc}"
            return result

        try:
            cur = conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
            tables_found = {row[0] for row in cur.fetchall()}
            result["tables_found"] = sorted(tables_found)
        except sqlite3.Error as exc:
            result["error"] = f"Could not list tables: {exc}"
            return result

        result["missing_critical_tables"] = sorted(set(CRITICAL_TABLES) - tables_found)
        result["missing_optional_tables"] = sorted(
            (set(ALL_EXPECTED_TABLES) - set(CRITICAL_TABLES)) - tables_found
        )

        if "schema_migrations" in tables_found:
            try:
                cur = conn.execute("SELECT MAX(version) FROM schema_migrations")
                row = cur.fetchone()
                result["schema_version"] = row[0] if row and row[0] is not None else None
            except sqlite3.Error:
                pass  # non-critical — leave as None

        for table in CRITICAL_TABLES:
            if table in tables_found:
                try:
                    cur = conn.execute(f"SELECT COUNT(*) FROM {table}")
                    result["row_counts"][table] = cur.fetchone()[0]
                except sqlite3.Error:
                    pass  # non-critical — row count is informational only

        result["valid"] = (
            result["openable"]
            and result["integrity_check"] == "ok"
            and not result["missing_critical_tables"]
        )
        return result
    finally:
        conn.close()


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

    async def create_backup_and_upload(
        self, backup_type: str = "auto", verify_after_upload: bool = True,
    ) -> str:
        """Snapshot the DB, verify it, upload it to Drive, verify the
        round-trip, prune old backups. Returns the uploaded file's Drive ID.

        Two integrity checks, not one — closing the "upload and trust it"
        gap:
          1. Pre-upload: the local snapshot itself must pass
             verify_sqlite_integrity() before we spend any bandwidth
             uploading it. A corrupt snapshot never reaches Drive at all.
          2. Post-upload (verify_after_upload=True, the default): download
             the file we *just* uploaded and verify that copy too. This is
             the only way to actually confirm the round trip through Drive
             didn't truncate or corrupt anything — a 200 response from the
             upload API only proves Drive accepted bytes, not that they're
             intact and restorable.

        Either check failing raises DriveBackupError — a backup that can't
        be verified as intact is treated as a failed backup, not a
        successful one with a caveat, so record_backup_failure() and the
        drive_backup_failed notification both fire on it.

        backup_type is purely descriptive metadata (stored as a Drive file
        property and shown by /restorelist) — "auto" for the periodic
        background loop, "manual" for anything triggered on demand.
        """
        if not Path(self._db_path).exists():
            raise DriveBackupError(f"No database file found at {self._db_path}")

        snapshot_name = f"dca_bot_backup_{now_iso().replace(':', '-')}.db"
        snapshot_path = Path(self._db_path).parent / f".drive_snapshot_{snapshot_name}"
        try:
            await asyncio.to_thread(self._make_consistent_snapshot, snapshot_path)

            pre_check = await asyncio.to_thread(verify_sqlite_integrity, snapshot_path)
            if not pre_check["valid"]:
                raise DriveBackupError(
                    f"Snapshot failed integrity verification before upload — aborting "
                    f"without uploading a known-bad backup. Details: {pre_check.get('error') or pre_check}"
                )

            schema_version = pre_check.get("schema_version")
            properties = {"backup_type": backup_type}
            if schema_version is not None:
                properties["schema_version"] = str(schema_version)
            file_id = await self._upload(snapshot_path, snapshot_name, properties)

            if verify_after_upload:
                post_check = await self.verify_backup_by_id(file_id)
                if not post_check["valid"]:
                    raise DriveBackupError(
                        f"Uploaded backup {file_id} failed post-upload integrity "
                        f"verification — the round trip through Drive corrupted it. "
                        f"Details: {post_check.get('error') or post_check}"
                    )
        finally:
            snapshot_path.unlink(missing_ok=True)

        await self._prune_old_backups()
        return file_id

    async def download_backup(self, file_id: str) -> bytes:
        headers = await self._auth_headers()
        async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
            resp = await client.get(f"{_FILES_URL}/{file_id}", headers=headers, params={"alt": "media"})
        if resp.status_code >= 400:
            raise DriveBackupError(f"Drive download failed ({resp.status_code}): {resp.text[:300]}")
        return resp.content

    async def verify_backup_by_id(self, file_id: str) -> dict:
        """Download a specific backup from Drive and run
        verify_sqlite_integrity() against it. Used both for the automatic
        post-upload check above and for the on-demand /verifybackup command
        — the latter is how a user confirms an *existing*, possibly weeks-old
        backup is still good, not just newly-created ones.
        """
        file_bytes = await self.download_backup(file_id)
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tmp:
            tmp_path = Path(tmp.name)
            tmp.write(file_bytes)
        try:
            return await asyncio.to_thread(verify_sqlite_integrity, tmp_path)
        finally:
            tmp_path.unlink(missing_ok=True)

    async def _upload(self, file_path: Path, filename: str, properties: dict[str, str] | None = None) -> str:
        headers = await self._auth_headers()
        metadata: dict = {"name": filename, "parents": [self._folder_id]}
        if properties:
            # Drive's "properties" field stores arbitrary string key-value
            # pairs on a file and is returned by files.list/files.get when
            # requested via `fields` — this is how backup_type and
            # schema_version travel with the file for /restorelist to show
            # later, without needing a separate metadata store.
            metadata["properties"] = properties
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
        """Return backups in the configured folder, oldest first (callers
        needing newest-first, like /restorelist, should reverse this).
        Each entry includes id, name, createdTime, size (bytes, as a
        string per Drive's API), and properties (backup_type,
        schema_version if the uploader set them — may be absent on backups
        created before those properties existed).
        """
        headers = await self._auth_headers()
        params = {
            "q": f"'{self._folder_id}' in parents and trashed = false and name contains 'dca_bot_backup_'",
            "orderBy": "createdTime",
            "fields": "files(id,name,createdTime,size,properties)",
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

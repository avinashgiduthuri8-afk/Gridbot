"""Creates a consistent, safe-to-copy snapshot of the live SQLite database.

WAL mode (used by storage/database.py) keeps recent writes in a separate
`-wal` file until checkpointed into the main database file. Copying the main
`.db` file directly while WAL is active can produce a snapshot missing
recent transactions (though not a corrupt file — SQLite's WAL design
prevents that). Checkpointing first guarantees the copy reflects everything
committed up to that moment.
"""

from __future__ import annotations

import shutil
from pathlib import Path

from storage.database import Database
from utils.helpers import now_iso
from utils.logger import get_logger

log = get_logger("database")


async def create_snapshot(db: Database, dest_dir: str | Path) -> Path:
    """Checkpoint the WAL into the main DB file, then copy it to dest_dir.

    Returns the path to the newly created snapshot file. Safe to call while
    the bot is running and actively trading — it does not block writers for
    longer than the PRAGMA statement itself takes.
    """
    dest_dir = Path(dest_dir)
    dest_dir.mkdir(parents=True, exist_ok=True)

    # TRUNCATE checkpoints all WAL frames into the main file and truncates
    # the WAL file back to zero, so the plain .db file alone is a complete,
    # consistent snapshot with nothing left behind in -wal/-shm sidecars.
    await db.connection.execute("PRAGMA wal_checkpoint(TRUNCATE);")
    await db.connection.commit()

    timestamp = now_iso().replace(":", "-").replace(".", "-")
    snapshot_name = f"grid_bot_backup_{timestamp}.db"
    snapshot_path = dest_dir / snapshot_name

    source_path = Path(db.db_path)
    shutil.copy2(source_path, snapshot_path)
    log.info("Created DB snapshot: %s (%.1f KB)", snapshot_path, snapshot_path.stat().st_size / 1024)
    return snapshot_path

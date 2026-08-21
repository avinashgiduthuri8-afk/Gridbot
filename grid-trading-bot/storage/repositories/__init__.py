"""Repository classes providing typed CRUD access per table for Indian Stock Scanner."""

from __future__ import annotations

from storage.database import Database
from storage.repositories.bot_registry import BotRegistryRepository
from storage.repositories.signal_ledger import SignalLedgerRepository
from storage.repositories.signals import SignalRepository

__all__ = [
    "SignalRepository",
    "SignalLedgerRepository",
    "BotRegistryRepository",
    "Repositories",
]


class Repositories:
    """Bundles repositories behind a single object."""

    def __init__(self, db: Database) -> None:
        self.db = db
        self.signals = SignalRepository(db)
        self.ledger = SignalLedgerRepository(db)
        self.bots = BotRegistryRepository(db)

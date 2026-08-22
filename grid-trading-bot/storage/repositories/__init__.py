"""Repository classes providing typed CRUD access per table.

Each repository owns queries for exactly one table. Callers never touch
SQL directly — they work through these typed, async methods.

This package was split from a single storage/repositories.py module (one
class per file, grouped by table) for maintainability; every existing
import site (`from storage.repositories import Repositories`, etc.)
continues to work unchanged via the re-exports below.
"""
from __future__ import annotations

from storage.database import Database
from storage.repositories.daily_stats import DailyStatsRepository
from storage.repositories.grid_defaults import GridDefaultsRepository
from storage.repositories.grids import DCAGridRepository
from storage.repositories.logs import LogRepository
from storage.repositories.monitor_settings import (
    DEFAULT_MONITOR_INTERVAL,
    VALID_MONITOR_INTERVALS,
    MonitorSettingsRepository,
)
from storage.repositories.orders import OrderRepository
from storage.repositories.price_alerts import PriceAlertRepository
from storage.repositories.trade_history import TradeHistoryRepository

__all__ = [
    "DCAGridRepository",
    "OrderRepository",
    "TradeHistoryRepository",
    "DailyStatsRepository",
    "LogRepository",
    "MonitorSettingsRepository",
    "PriceAlertRepository",
    "GridDefaultsRepository",
    "Repositories",
    "VALID_MONITOR_INTERVALS",
    "DEFAULT_MONITOR_INTERVAL",
]


class Repositories:
    """Bundles every repository behind a single object."""

    def __init__(self, db: Database) -> None:
        self.db = db
        self.grids = DCAGridRepository(db)
        self.orders = OrderRepository(db)
        self.trade_history = TradeHistoryRepository(db)
        self.daily_stats = DailyStatsRepository(db)
        self.logs = LogRepository(db)
        self.monitor_settings = MonitorSettingsRepository(db)
        self.price_alerts = PriceAlertRepository(db)
        self.grid_defaults = GridDefaultsRepository(db)

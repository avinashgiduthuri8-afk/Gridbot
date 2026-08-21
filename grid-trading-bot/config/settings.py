"""Application configuration for Indian Stock Market Scanner (PROJECT-BETA)."""

from __future__ import annotations

import os
from dataclasses import dataclass
from dotenv import load_dotenv

load_dotenv()


@dataclass(frozen=True)
class ScannerSettings:
    database_path: str
    default_universe: str
    min_rr: float
    max_signals: int
    log_level: str


def load_settings() -> ScannerSettings:
    return ScannerSettings(
        database_path=os.getenv("DATABASE_PATH", "data/indian_scanner.db").strip(),
        default_universe=os.getenv("DEFAULT_UNIVERSE", "NIFTY_100").strip(),
        min_rr=float(os.getenv("MIN_RR", "2.0")),
        max_signals=int(os.getenv("MAX_SIGNALS", "3")),
        log_level=os.getenv("LOG_LEVEL", "INFO").strip(),
    )

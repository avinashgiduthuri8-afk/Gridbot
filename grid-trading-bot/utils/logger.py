"""Structured, per-domain logging setup.

Each functional area of the bot (trading, exchange, telegram, database,
grid engine, errors) gets its own rotating log file plus a combined
console stream, so operators can tail exactly the subsystem they care
about on a VPS.
"""

from __future__ import annotations

import logging
import logging.handlers
import sys
from pathlib import Path

_CONFIGURED = False

LOG_CHANNELS = (
    "trading",
    "exchange",
    "telegram",
    "database",
    "grid",
    "errors",
    "drive_backup",
    "scanner",
    "yahoo_provider",
    "universe_filter",
    "mtf_analyzer",
    "regime_detector",
    "sector_analyzer",
    "news_evaluator",
    "risk_reward",
    "setup_detector",
    "scoring_engine",
    "scanner_pipeline",
    "backtest_evaluator",
    "signal_repo",
    "scanner_service",
    "stock_info_provider",
    "stock_info_router",
)

_LOG_FORMAT = (
    "%(asctime)s | %(levelname)-8s | %(name)-12s | "
    "%(module)s:%(lineno)d | %(message)s"
)


def setup_logging(log_dir: str = "logs", level: str = "INFO") -> None:
    """Configure structured logging for every channel.

    Safe to call multiple times; only configures handlers once.
    """
    global _CONFIGURED
    if _CONFIGURED:
        return

    log_path = Path(log_dir)
    log_path.mkdir(parents=True, exist_ok=True)

    root_level = getattr(logging, level.upper(), logging.INFO)
    formatter = logging.Formatter(_LOG_FORMAT, datefmt="%Y-%m-%d %H:%M:%S")

    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(formatter)
    console_handler.setLevel(root_level)

    root_logger = logging.getLogger("grid_bot")
    root_logger.setLevel(root_level)
    root_logger.handlers.clear()
    root_logger.addHandler(console_handler)
    root_logger.propagate = False

    class _ErrorRelayFilter(logging.Filter):
        def filter(self, record: logging.LogRecord) -> bool:
            return record.levelno >= logging.WARNING

    for channel in LOG_CHANNELS:
        channel_logger = logging.getLogger(f"grid_bot.{channel}")
        channel_logger.setLevel(root_level)
        channel_logger.propagate = True

        file_handler = logging.handlers.RotatingFileHandler(
            log_path / f"{channel}.log",
            maxBytes=10 * 1024 * 1024,
            backupCount=5,
            encoding="utf-8",
        )
        file_handler.setFormatter(formatter)
        file_handler.setLevel(root_level)
        channel_logger.addHandler(file_handler)

        relay = logging.handlers.RotatingFileHandler(
            log_path / "errors.log",
            maxBytes=10 * 1024 * 1024,
            backupCount=5,
            encoding="utf-8",
        )
        relay.setFormatter(formatter)
        relay.addFilter(_ErrorRelayFilter())
        relay.setLevel(logging.WARNING)
        channel_logger.addHandler(relay)

    # Quiet noisy third-party libraries unless they escalate to warnings.
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
    logging.getLogger("telegram").setLevel(logging.WARNING)
    logging.getLogger("apscheduler").setLevel(logging.WARNING)

    _CONFIGURED = True


def get_logger(channel: str) -> logging.Logger:
    """Return the logger for a given channel (trading/exchange/telegram/...)."""
    if channel not in LOG_CHANNELS:
        raise ValueError(f"Unknown log channel: {channel}. Valid: {LOG_CHANNELS}")
    return logging.getLogger(f"grid_bot.{channel}")

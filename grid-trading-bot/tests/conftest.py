"""Shared pytest fixtures. Adds the project root to sys.path so tests can
import top-level packages (config, grid, storage, ...) regardless of how
pytest is invoked."""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

os.environ.setdefault("TELEGRAM_BOT_TOKEN", "test-token")
os.environ.setdefault("TELEGRAM_CHAT_ID", "123456")
os.environ.setdefault("COINDCX_API_KEY", "test-key")
os.environ.setdefault("COINDCX_API_SECRET", "test-secret")
os.environ.setdefault("DATABASE_PATH", ":memory:")

import pytest


@pytest.fixture
def anyio_backend():
    return "asyncio"

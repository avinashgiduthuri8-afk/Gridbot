"""Shared pytest fixtures for the DCA grid bot test suite."""

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

from storage.database import Database
from storage.repositories import Repositories


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.fixture
async def db():
    database = Database(":memory:")
    await database.connect()
    await database.migrate()
    yield database
    await database.close()


@pytest.fixture
async def repos(db):
    return Repositories(db)

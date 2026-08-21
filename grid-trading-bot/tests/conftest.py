"""Shared pytest fixtures for the Indian Stock Market Scanner test suite."""

from __future__ import annotations

import os
import sys
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

os.environ.setdefault("DATABASE_PATH", ":memory:")
os.environ.setdefault("DEFAULT_UNIVERSE", "NIFTY_100")
os.environ.setdefault("MIN_RR", "2.0")

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

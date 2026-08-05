"""Shared helper used across storage.repositories.* modules."""
from __future__ import annotations

from typing import Any

import aiosqlite


def _row(row: aiosqlite.Row) -> dict[str, Any]:
    return {key: row[key] for key in row.keys()}

"""Regression test for startup ordering.

Recovery must finish before the order and price monitors are started, or the
bot can begin polling live state against a half-restored database.
"""

from __future__ import annotations

import asyncio

import pytest

from main import _start_monitors_after_recovery

pytestmark = pytest.mark.anyio


class _BlockingRecovery:
    def __init__(self, started: asyncio.Event, release: asyncio.Event, calls: list[str]) -> None:
        self._started = started
        self._release = release
        self._calls = calls

    async def recover(self) -> None:
        self._calls.append("recover:start")
        self._started.set()
        await self._release.wait()
        self._calls.append("recover:done")


class _RecordingMonitor:
    def __init__(self, name: str, calls: list[str]) -> None:
        self._name = name
        self._calls = calls

    def start(self) -> None:
        self._calls.append(f"{self._name}:start")


async def test_monitor_start_waits_for_recovery_to_finish():
    started = asyncio.Event()
    release = asyncio.Event()
    calls: list[str] = []

    recovery = _BlockingRecovery(started, release, calls)
    order_monitor = _RecordingMonitor("order", calls)
    price_monitor = _RecordingMonitor("price", calls)

    task = asyncio.create_task(
        _start_monitors_after_recovery(recovery, order_monitor, price_monitor)
    )

    await started.wait()
    await asyncio.sleep(0)
    assert calls == ["recover:start"]

    release.set()
    await task

    assert calls == [
        "recover:start",
        "recover:done",
        "order:start",
        "price:start",
    ]

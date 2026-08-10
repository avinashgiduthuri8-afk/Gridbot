"""Regression test for main.py's graceful-shutdown pattern.

main.py itself (real Telegram Application, live HTTP clients, real
Railway environment wiring) isn't practically unit-testable end-to-end
without a large amount of mocking that would amount to its own refactor.
What IS testable, and is the actual thing that was fixed, is the
shutdown *pattern*: cancel every background task, then actually wait for
all of them to finish cancelling (asyncio.gather(..., return_exceptions=True))
before closing shared resources those tasks might still be touching.

This test reproduces that exact pattern with stand-in tasks and confirms:
  1. every background task is fully done() before the "close resources"
     step runs — not just cancel()-requested.
  2. a normal CancelledError from a cancelled task doesn't propagate out
     and skip/abort the resource-closing step.
  3. a task that takes a moment to actually stop (does real work between
     await points before yielding to cancellation) is still fully waited
     on, not raced past.
"""
from __future__ import annotations

import asyncio

import pytest

pytestmark = pytest.mark.anyio


async def _shutdown_like_main(tasks: list[asyncio.Task], close_resource) -> None:
    """Mirrors the exact sequence in main.py's shutdown block."""
    for task in tasks:
        task.cancel()
    await asyncio.gather(*tasks, return_exceptions=True)
    await close_resource()


async def test_all_background_tasks_are_done_before_resource_close():
    events: list[str] = []
    still_running = asyncio.Event()

    async def slow_background_loop(name: str):
        try:
            still_running.set()
            while True:
                await asyncio.sleep(1)
        except asyncio.CancelledError:
            # Simulates real cleanup work a background task might do
            # before actually finishing (e.g. flushing a partial write).
            await asyncio.sleep(0.02)
            events.append(f"{name}_finished_cancelling")
            raise

    async def close_resource():
        events.append("resource_closed")

    tasks = [asyncio.create_task(slow_background_loop(f"task{i}")) for i in range(4)]
    await still_running.wait()

    await asyncio.wait_for(_shutdown_like_main(tasks, close_resource), timeout=5)

    assert all(t.done() for t in tasks), "every cancelled task must be fully done before shutdown proceeds"
    # Every task's cancellation cleanup must have completed BEFORE the
    # resource close — this is exactly the race the fix closes.
    assert events == [
        "task0_finished_cancelling", "task1_finished_cancelling",
        "task2_finished_cancelling", "task3_finished_cancelling",
        "resource_closed",
    ] or (
        # asyncio.gather doesn't guarantee completion order across tasks,
        # only that ALL of them finish before it returns — so just check
        # the invariant that actually matters: resource_closed is last.
        events[-1] == "resource_closed" and len(events) == 5
    )


async def test_a_cancelled_tasks_exception_does_not_abort_the_close_step():
    """return_exceptions=True must mean a task that raises something other
    than CancelledError (a genuine bug in that task) still doesn't prevent
    the resource-closing step from running — the old bare cancel()-without-await
    pattern couldn't have this problem since it never awaited the tasks at
    all, but a naive `await asyncio.gather(*tasks)` WITHOUT
    return_exceptions=True would raise and skip the close step entirely."""
    closed = {"value": False}

    async def buggy_task():
        await asyncio.sleep(0.01)
        raise RuntimeError("boom - unrelated bug in this background task")

    async def close_resource():
        closed["value"] = True

    task = asyncio.create_task(buggy_task())
    await asyncio.sleep(0.03)  # let it actually raise before we "shut down"

    await _shutdown_like_main([task], close_resource)

    assert closed["value"] is True, "a background task's own exception must not prevent resource cleanup"


async def test_task_that_ignores_cancellation_briefly_is_still_fully_awaited():
    """A task that does a little bit of async work in response to
    cancellation (not instant) must be FULLY finished, not just
    'cancel() was called', before the close step runs."""
    finished_at = {"time": None}

    async def task_with_cleanup():
        try:
            await asyncio.sleep(10)
        except asyncio.CancelledError:
            await asyncio.sleep(0.05)  # deliberate cleanup delay
            finished_at["time"] = asyncio.get_event_loop().time()
            raise

    closed_at = {"time": None}

    async def close_resource():
        closed_at["time"] = asyncio.get_event_loop().time()

    task = asyncio.create_task(task_with_cleanup())
    await asyncio.sleep(0.01)

    await _shutdown_like_main([task], close_resource)

    assert finished_at["time"] is not None
    assert closed_at["time"] >= finished_at["time"], (
        "resource close must happen at/after the task's cleanup finishes, never before"
    )

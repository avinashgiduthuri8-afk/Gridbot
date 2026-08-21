"""Tests for Signal Lifecycle State Machine & Deduplication."""

import time
from datetime import datetime, timezone

from engine.signals.lifecycle import SignalLifecycleManager, SignalLifecycleState


def test_signal_lifecycle_deduplication():
    manager = SignalLifecycleManager(default_ttl_seconds=3600)

    # First cycle for RELIANCE
    is_dup, _ = manager.check_deduplication("RELIANCE", new_entry=1250.0, new_score=91.0)
    assert is_dup is False

    # Register the signal
    manager.register_signal(
        symbol="RELIANCE",
        signal_id="sig_rel_1",
        entry_price=1250.0,
        stop_loss=1225.0,
        target_1=1300.0,
        score=91.0,
        state=SignalLifecycleState.CONFIRMED,
    )

    # Scan 5 minutes later: same price 1251.0 and score 91.5 -> Must be detected as duplicate!
    is_dup_second, reason = manager.check_deduplication("RELIANCE", new_entry=1251.0, new_score=91.5)
    assert is_dup_second is True
    assert "Duplicate" in reason

    # Scan with material price shift to 1275.0 (+2.0%) -> Not a duplicate (material update)
    is_dup_material, _ = manager.check_deduplication("RELIANCE", new_entry=1275.0, new_score=85.0)
    assert is_dup_material is False


def test_signal_lifecycle_invalidation_on_stop_loss():
    manager = SignalLifecycleManager(default_ttl_seconds=3600)

    manager.register_signal(
        symbol="TCS",
        signal_id="sig_tcs_1",
        entry_price=3500.0,
        stop_loss=3450.0,
        target_1=3600.0,
        score=88.0,
    )

    # Price drops to 3440 (below SL 3450) -> Invalidates signal!
    was_invalidated = manager.invalidate_if_breached("TCS", current_price=3440.0)
    assert was_invalidated is True

    # Check that it is removed from active signals
    is_dup_after, _ = manager.check_deduplication("TCS", new_entry=3440.0, new_score=50.0)
    assert is_dup_after is False

"""Tests for the in-memory AlertManager."""

from __future__ import annotations

import pytest

from trading.alert_manager import AlertManager
from utils.helpers import now_iso


@pytest.fixture
def manager():
    return AlertManager()


def test_add_above_alert(manager):
    direction = manager.add("BTCINR", 60000.0, 54000.0, now_iso())
    assert direction == "above"
    alerts = manager.list_all()
    assert len(alerts) == 1
    assert alerts[0].symbol == "BTCINR"
    assert alerts[0].direction == "above"
    assert alerts[0].target_price == 60000.0


def test_add_below_alert(manager):
    direction = manager.add("BTCINR", 50000.0, 54000.0, now_iso())
    assert direction == "below"
    alerts = manager.list_all()
    assert alerts[0].direction == "below"


def test_add_alert_at_current_price_raises(manager):
    with pytest.raises(ValueError, match="equals current price"):
        manager.add("BTCINR", 54000.0, 54000.0, now_iso())


def test_add_deduplicates_same_symbol_and_target(manager):
    manager.add("BTCINR", 60000.0, 54000.0, now_iso())
    manager.add("BTCINR", 60000.0, 54000.0, now_iso())
    assert len(manager.list_all()) == 1


def test_add_keeps_different_targets_same_symbol(manager):
    manager.add("BTCINR", 60000.0, 54000.0, now_iso())
    manager.add("BTCINR", 65000.0, 54000.0, now_iso())
    assert len(manager.list_all()) == 2


def test_add_multiple_symbols(manager):
    manager.add("BTCINR", 60000.0, 54000.0, now_iso())
    manager.add("ETHINR", 250000.0, 220000.0, now_iso())
    assert len(manager.list_all()) == 2


def test_delete_removes_all_alerts_for_symbol(manager):
    manager.add("BTCINR", 60000.0, 54000.0, now_iso())
    manager.add("BTCINR", 65000.0, 54000.0, now_iso())
    manager.add("ETHINR", 250000.0, 220000.0, now_iso())
    removed = manager.delete("BTCINR")
    assert removed == 2
    remaining = manager.list_all()
    assert len(remaining) == 1
    assert remaining[0].symbol == "ETHINR"


def test_delete_nonexistent_symbol_returns_zero(manager):
    assert manager.delete("XRPINR") == 0


def test_symbols_with_alerts_unique(manager):
    manager.add("BTCINR", 60000.0, 54000.0, now_iso())
    manager.add("BTCINR", 65000.0, 54000.0, now_iso())
    manager.add("ETHINR", 250000.0, 220000.0, now_iso())
    symbols = manager.symbols_with_alerts()
    assert set(symbols) == {"BTCINR", "ETHINR"}


def test_check_and_fire_above_triggered(manager):
    manager.add("BTCINR", 60000.0, 54000.0, now_iso())
    fired = manager.check_and_fire("BTCINR", 60500.0)
    assert len(fired) == 1
    assert fired[0].target_price == 60000.0
    assert len(manager.list_all()) == 0


def test_check_and_fire_below_triggered(manager):
    manager.add("BTCINR", 50000.0, 54000.0, now_iso())
    fired = manager.check_and_fire("BTCINR", 49999.0)
    assert len(fired) == 1
    assert len(manager.list_all()) == 0


def test_check_and_fire_not_triggered(manager):
    manager.add("BTCINR", 60000.0, 54000.0, now_iso())
    fired = manager.check_and_fire("BTCINR", 58000.0)
    assert len(fired) == 0
    assert len(manager.list_all()) == 1


def test_check_and_fire_exactly_at_target(manager):
    manager.add("BTCINR", 60000.0, 54000.0, now_iso())
    fired = manager.check_and_fire("BTCINR", 60000.0)
    assert len(fired) == 1


def test_check_and_fire_only_fires_matching_symbol(manager):
    manager.add("BTCINR", 60000.0, 54000.0, now_iso())
    manager.add("ETHINR", 250000.0, 220000.0, now_iso())
    fired = manager.check_and_fire("BTCINR", 61000.0)
    assert len(fired) == 1
    assert fired[0].symbol == "BTCINR"
    assert len(manager.list_all()) == 1
    assert manager.list_all()[0].symbol == "ETHINR"


def test_check_and_fire_is_one_shot(manager):
    manager.add("BTCINR", 60000.0, 54000.0, now_iso())
    manager.check_and_fire("BTCINR", 61000.0)
    fired_again = manager.check_and_fire("BTCINR", 62000.0)
    assert len(fired_again) == 0

"""Tests for trading/portfolio_metrics.py — the P&L/portfolio calculation
functions extracted from bot_telegram/formatters.py so both the Telegram
bot and a future dashboard API can reuse the same math."""
from __future__ import annotations

import pytest

from trading.portfolio_metrics import (
    bot_position_by_currency,
    grid_pnl_breakdown,
    pnl_pct,
    portfolio_totals,
    unrealized_pnl,
)


class TestPnlPct:
    def test_positive_pnl(self):
        assert pnl_pct(50.0, 1000.0) == pytest.approx(5.0)

    def test_negative_pnl(self):
        assert pnl_pct(-100.0, 1000.0) == pytest.approx(-10.0)

    def test_zero_invested_returns_zero(self):
        assert pnl_pct(50.0, 0.0) == 0.0

    def test_negative_invested_returns_zero(self):
        assert pnl_pct(50.0, -100.0) == 0.0


class TestUnrealizedPnl:
    def test_price_above_entry_is_positive(self):
        assert unrealized_pnl(110.0, 100.0, 10.0) == pytest.approx(100.0)

    def test_price_below_entry_is_negative(self):
        assert unrealized_pnl(90.0, 100.0, 10.0) == pytest.approx(-100.0)

    def test_zero_quantity_is_zero(self):
        assert unrealized_pnl(110.0, 100.0, 0.0) == 0.0


class TestBotPositionByCurrency:
    def test_aggregates_active_and_paused_grids(self):
        grids = [
            {"status": "active", "symbol": "BTCINR", "average_entry_price": 100.0, "total_quantity": 2.0},
            {"status": "paused", "symbol": "BTCINR", "average_entry_price": 200.0, "total_quantity": 1.0},
        ]
        result = bot_position_by_currency(grids)
        assert result["BTC"] == (3.0, 2.0 * 100.0 + 1.0 * 200.0)

    def test_ignores_stopped_and_completed_grids(self):
        grids = [
            {"status": "stopped", "symbol": "BTCINR", "average_entry_price": 100.0, "total_quantity": 2.0},
            {"status": "completed", "symbol": "ETHINR", "average_entry_price": 50.0, "total_quantity": 1.0},
        ]
        assert bot_position_by_currency(grids) == {}

    def test_ignores_zero_or_negative_avg_or_qty(self):
        grids = [
            {"status": "active", "symbol": "BTCINR", "average_entry_price": 0.0, "total_quantity": 2.0},
            {"status": "active", "symbol": "ETHINR", "average_entry_price": 100.0, "total_quantity": 0.0},
        ]
        assert bot_position_by_currency(grids) == {}

    def test_ignores_non_inr_quoted_symbols(self):
        grids = [{"status": "active", "symbol": "BTCUSDT", "average_entry_price": 100.0, "total_quantity": 2.0}]
        assert bot_position_by_currency(grids) == {}

    def test_separate_currencies_kept_independent(self):
        grids = [
            {"status": "active", "symbol": "BTCINR", "average_entry_price": 100.0, "total_quantity": 1.0},
            {"status": "active", "symbol": "ETHINR", "average_entry_price": 50.0, "total_quantity": 2.0},
        ]
        result = bot_position_by_currency(grids)
        assert result["BTC"] == (1.0, 100.0)
        assert result["ETH"] == (2.0, 100.0)


class TestGridPnlBreakdown:
    def test_full_breakdown_with_price(self):
        grid = {"total_quantity": 2.0, "average_entry_price": 100.0, "realized_profit": 50.0, "total_investment": 200.0}
        result = grid_pnl_breakdown(grid, current_price=110.0)
        assert result["realized"] == 50.0
        assert result["unrealized"] == pytest.approx(20.0)
        assert result["combined"] == pytest.approx(70.0)
        assert result["invested"] == 200.0

    def test_no_price_available_gives_zero_unrealized(self):
        grid = {"total_quantity": 2.0, "average_entry_price": 100.0, "realized_profit": 50.0, "total_investment": 200.0}
        result = grid_pnl_breakdown(grid, current_price=None)
        assert result["unrealized"] == 0.0
        assert result["combined"] == 50.0

    def test_zero_quantity_gives_zero_unrealized_even_with_price(self):
        grid = {"total_quantity": 0.0, "average_entry_price": 0.0, "realized_profit": 50.0, "total_investment": 0.0}
        result = grid_pnl_breakdown(grid, current_price=110.0)
        assert result["unrealized"] == 0.0


class TestPortfolioTotals:
    def test_aggregates_across_multiple_grids(self):
        grids = [
            {"symbol": "BTCINR", "total_quantity": 1.0, "average_entry_price": 100.0,
             "realized_profit": 50.0, "total_investment": 100.0},
            {"symbol": "ETHINR", "total_quantity": 2.0, "average_entry_price": 50.0,
             "realized_profit": -10.0, "total_investment": 100.0},
        ]
        prices = {"BTCINR": 120.0, "ETHINR": 45.0}
        result = portfolio_totals(grids, prices)
        assert result["total_realized"] == pytest.approx(40.0)
        assert result["total_unrealized"] == pytest.approx(20.0 + (-10.0))
        assert result["total_invested"] == pytest.approx(200.0)
        assert result["combined_total"] == pytest.approx(result["total_realized"] + result["total_unrealized"])
        assert result["portfolio_return_pct"] == pytest.approx(pnl_pct(result["combined_total"], 200.0))

    def test_empty_grids_gives_all_zeros(self):
        result = portfolio_totals([], {})
        assert result == {
            "total_realized": 0.0, "total_unrealized": 0.0, "total_invested": 0.0,
            "combined_total": 0.0, "portfolio_return_pct": 0.0,
        }

    def test_missing_price_for_a_symbol_treated_as_zero_unrealized_for_that_grid(self):
        grids = [{"symbol": "BTCINR", "total_quantity": 1.0, "average_entry_price": 100.0,
                  "realized_profit": 10.0, "total_investment": 100.0}]
        result = portfolio_totals(grids, {})  # no price for BTCINR
        assert result["total_unrealized"] == 0.0
        assert result["total_realized"] == 10.0

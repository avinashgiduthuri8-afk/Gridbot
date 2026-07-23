"""Display-only P&L percentage formatting tests."""

from __future__ import annotations

from bot_telegram.formatters import format_grid_list, format_paper_grids


def _grid(**overrides: object) -> dict:
    base = {
        "grid_id": "grd_test_001",
        "symbol": "BTCINR",
        "status": "active",
        "mode": "paper",
        "average_entry_price": 100.0,
        "total_quantity": 1.0,
        "total_investment": 100.0,
        "realized_profit": 0.0,
        "completed_cycles": 0,
        "current_level": 1,
        "max_levels": 10,
        "entry_price": 100.0,
        "dip_percentage": 5.0,
        "profit_percentage": 7.0,
    }
    base.update(overrides)
    return base


def test_grid_list_shows_positive_realized_pnl_percentage():
    text = format_grid_list([
        _grid(total_investment=1000.0, realized_profit=50.3, mode="real"),
    ])

    assert "Net realized P&amp;L: ₹+50.30 (+5.03%)" in text


def test_grid_list_shows_negative_realized_pnl_percentage():
    text = format_grid_list([
        _grid(total_investment=500.0, realized_profit=-12.5, mode="real"),
    ])

    assert "Net realized P&amp;L: ₹-12.50 (-2.50%)" in text


def test_grid_list_handles_zero_investment_safely():
    text = format_grid_list([
        _grid(total_investment=0.0, realized_profit=7.25, mode="real"),
    ])

    assert "Net realized P&amp;L: ₹+7.25 (+0.00%)" in text


def test_paper_grids_show_partial_sell_breakdown_and_portfolio_return():
    text = format_paper_grids(
        [
            _grid(
                total_quantity=2.0,
                total_investment=200.0,
                realized_profit=50.0,
                completed_cycles=1,
                average_entry_price=100.0,
                entry_price=100.0,
                current_level=2,
            )
        ],
        {"BTCINR": 108.0},
    )

    assert "Net realized P&amp;L: ₹+50.00 (+25.00%)" in text
    assert "Unrealized: ₹+16.00 (+8.00%)" in text
    assert "Net total P&amp;L: ₹+66.00 (+33.00%)" in text
    assert "Portfolio Return:  +33.00%" in text

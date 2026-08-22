"""Tests for Multi-Strategy Stock Backtesting Engine and REST API."""

import pytest
from httpx import AsyncClient, ASGITransport

from dashboard.app import create_app
from engine.backtest.strategy_evaluator import MultiStrategyBacktester
from engine.data.base import OHLCVCandle
from storage.database import Database
from storage.repositories import Repositories


def _generate_synthetic_candles(num_bars: int = 150) -> list[OHLCVCandle]:
    """Generates synthetic price data with trend and volatility contraction."""
    candles = []
    base_price = 1000.0

    for i in range(num_bars):
        # Gradual uptrend with periodic compression
        if i % 20 < 10:
            price_change = 2.0
            vol = 100000
        elif i % 20 < 15:
            # Volatility contraction
            price_change = 0.5
            vol = 40000
        else:
            # Breakout bar
            price_change = 15.0
            vol = 250000

        base_price += price_change
        high = base_price + 5.0
        low = base_price - 4.0
        close = base_price + 2.0

        candles.append(
            OHLCVCandle(
                timestamp=f"2024-{(i//30)+1:02d}-{(i%28)+1:02d}T09:15:00Z",
                open=base_price,
                high=high,
                low=low,
                close=close,
                volume=vol,
            )
        )
    return candles


def test_vcp_multi_strategy_simulation():
    backtester = MultiStrategyBacktester()
    candles = _generate_synthetic_candles(120)

    result = backtester.run_simulation(
        symbol="TATAMOTORS.NS",
        candles=candles,
        strategy="VCP_BREAKOUT",
        initial_capital=500000.0,
        risk_pct_per_trade=1.0,
        target_1_rr=2.0,
        target_2_rr=3.5,
    )

    assert result.symbol == "TATAMOTORS.NS"
    assert result.strategy == "VCP_BREAKOUT"
    assert result.initial_capital == 500000.0
    assert len(result.equity_curve) > 50
    assert isinstance(result.win_rate_pct, float)


def test_pocket_pivot_and_nr7_simulations():
    backtester = MultiStrategyBacktester()
    candles = _generate_synthetic_candles(120)

    # Pocket Pivot
    res_pp = backtester.run_simulation(
        symbol="RELIANCE.NS",
        candles=candles,
        strategy="POCKET_PIVOT",
    )
    assert res_pp.strategy == "POCKET_PIVOT"

    # NR7 Compression
    res_nr7 = backtester.run_simulation(
        symbol="INFY.NS",
        candles=candles,
        strategy="NR7_COMPRESSION",
    )
    assert res_nr7.strategy == "NR7_COMPRESSION"


@pytest.mark.asyncio
async def test_backtest_rest_api():
    db = Database(":memory:")
    await db.connect()
    await db.migrate()

    app = create_app()
    app.state.db = db
    app.state.repos = Repositories(db)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        # 1. Get Available Strategies
        res_strat = await client.get("/api/v1/backtest/strategies")
        assert res_strat.status_code == 200
        strategies = res_strat.json()
        assert len(strategies) >= 4
        assert any(s["id"] == "VCP_BREAKOUT" for s in strategies)

        # 2. Run Strategy Backtest
        res_run = await client.post(
            "/api/v1/backtest/run",
            json={
                "symbol": "TATAMOTORS.NS",
                "strategy": "VCP_BREAKOUT",
                "lookback_bars": 60,
                "initial_capital": 500000.0,
                "risk_pct_per_trade": 1.0,
            },
        )
        assert res_run.status_code == 200
        data = res_run.json()
        assert "win_rate_pct" in data
        assert "equity_curve" in data

    await db.close()

"""FastAPI router for Historical Backtesting and Evaluation Simulations."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Request
from pydantic import BaseModel

from services.scanner_service import ScannerService

router = APIRouter(prefix="/backtest", tags=["Backtest & Evaluation"])


class BacktestRequest(BaseModel):
    universe: str = "NIFTY_50"
    lookback_bars: int = 60


@router.post("/run")
async def run_backtest(request: Request, body: BacktestRequest) -> dict[str, Any]:
    """Runs a historical simulation across the stock universe and returns a full metrics report."""
    scanner_svc: ScannerService = getattr(request.app.state, "scanner_service", None)
    if not scanner_svc:
        scanner_svc = ScannerService()
        request.app.state.scanner_service = scanner_svc

    report = await scanner_svc.run_backtest_simulation(universe=body.universe, lookback_bars=body.lookback_bars)

    outcomes_list = []
    for o in report.outcomes:
        outcomes_list.append({
            "symbol": o.signal.symbol,
            "signal_type": o.signal.signal_type.value if hasattr(o.signal.signal_type, "value") else str(o.signal.signal_type),
            "score": o.signal.total_score,
            "status": o.status,
            "mfe_pct": o.mfe_pct,
            "mae_pct": o.mae_pct,
            "realized_pnl_pct": o.realized_pnl_pct,
            "holding_bars": o.holding_bars,
            "exit_price": o.exit_price,
            "entry_price": o.signal.risk_reward.entry_price,
            "stop_loss": o.signal.risk_reward.stop_loss,
            "target_1": o.signal.risk_reward.target_1,
        })

    return {
        "universe": body.universe,
        "total_signals": report.total_signals,
        "winning_signals": report.winning_signals,
        "losing_signals": report.losing_signals,
        "expired_signals": report.expired_signals,
        "win_rate_pct": report.win_rate_pct,
        "profit_factor": report.profit_factor,
        "avg_return_pct": report.avg_return_pct,
        "avg_mfe_pct": report.avg_mfe_pct,
        "avg_mae_pct": report.avg_mae_pct,
        "max_drawdown_pct": report.max_drawdown_pct,
        "avg_holding_bars": report.avg_holding_bars,
        "by_regime": report.by_regime,
        "by_setup": report.by_setup,
        "outcomes": outcomes_list,
    }

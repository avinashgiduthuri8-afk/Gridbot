"""Replay report: trading summary, system summary, and validation results.

psutil is an optional dependency — if it isn't installed, system-resource
figures are simply omitted from the report rather than failing the run.
"""
from __future__ import annotations

import json
import os
import time
from dataclasses import asdict, dataclass, field

from replay.engine import ReplayStats
from replay.validation import ValidationReport
from storage.repositories import Repositories

try:
    import psutil
    _HAS_PSUTIL = True
except ImportError:  # pragma: no cover - exercised only when psutil is absent
    _HAS_PSUTIL = False


@dataclass
class TradingSummary:
    total_buys: int = 0
    total_sells: int = 0
    total_dust_writeoffs: int = 0
    total_realized_profit: float = 0.0
    win_rate_pct: float = 0.0
    max_drawdown_pct: float = 0.0
    profit_factor: float | None = None
    completed_cycles: int = 0
    trailing_activations: int = 0
    stop_loss_activations: int = 0
    manual_trades: int = 0


@dataclass
class SystemSummary:
    peak_rss_mb: float | None = None
    cpu_percent: float | None = None
    exception_count: int = 0
    db_size_bytes: int | None = None
    replay_duration_seconds: float = 0.0


@dataclass
class ReplaySummary:
    symbols: list[str] = field(default_factory=list)
    start_timestamp: float | None = None
    end_timestamp: float | None = None
    candles_processed: int = 0
    sub_ticks_processed: int = 0
    trigger_evaluations: int = 0
    speed: float | None = None


@dataclass
class ReplayReport:
    replay: ReplaySummary
    trading: TradingSummary
    system: SystemSummary
    validation: ValidationReport

    @property
    def passed(self) -> bool:
        return self.validation.all_passed

    def to_dict(self) -> dict:
        return {
            "replay": asdict(self.replay),
            "trading": asdict(self.trading),
            "system": asdict(self.system),
            "validation": {
                "all_passed": self.validation.all_passed,
                "checks": [asdict(c) for c in self.validation.checks],
            },
        }

    def render_json(self) -> str:
        return json.dumps(self.to_dict(), indent=2, default=str)

    def render_text(self) -> str:
        lines: list[str] = []
        lines.append("=" * 70)
        lines.append("REPLAY REPORT")
        lines.append("=" * 70)

        lines.append("\n-- Replay Summary --")
        lines.append(f"Symbols:            {', '.join(self.replay.symbols) or '(none)'}")
        lines.append(f"Date range:         {self.replay.start_timestamp} -> {self.replay.end_timestamp}")
        lines.append(f"Candles processed:  {self.replay.candles_processed}")
        lines.append(f"Sub-ticks:          {self.replay.sub_ticks_processed}")
        lines.append(f"Trigger evals:      {self.replay.trigger_evaluations}")
        lines.append(f"Speed:              {self.replay.speed if self.replay.speed else 'max (no throttling)'}")

        lines.append("\n-- Trading Summary --")
        t = self.trading
        lines.append(f"Total buys:          {t.total_buys}")
        lines.append(f"Total sells:         {t.total_sells}")
        lines.append(f"Dust write-offs:     {t.total_dust_writeoffs}")
        lines.append(f"Realized profit:     {t.total_realized_profit:.2f}")
        lines.append(f"Win rate:            {t.win_rate_pct:.1f}%")
        lines.append(f"Max drawdown:        {t.max_drawdown_pct:.2f}%")
        lines.append(
            f"Profit factor:       {t.profit_factor:.2f}" if t.profit_factor is not None
            else "Profit factor:       n/a (no losing trades)"
        )
        lines.append(f"Completed cycles:    {t.completed_cycles}")
        lines.append(f"Trailing activations:{t.trailing_activations}")
        lines.append(f"Stop-loss triggers:  {t.stop_loss_activations}")
        lines.append(f"Manual trades:       {t.manual_trades}")

        lines.append("\n-- System Summary --")
        s = self.system
        lines.append(f"Replay duration (s): {s.replay_duration_seconds:.2f}")
        lines.append(f"Peak RSS (MB):       {s.peak_rss_mb:.1f}" if s.peak_rss_mb is not None else "Peak RSS (MB):       n/a (psutil not installed)")
        lines.append(f"CPU %%:               {s.cpu_percent:.1f}" if s.cpu_percent is not None else "CPU %:               n/a (psutil not installed)")
        lines.append(f"Exceptions:          {s.exception_count}")
        lines.append(f"DB size (bytes):     {s.db_size_bytes if s.db_size_bytes is not None else 'n/a'}")

        lines.append("\n-- Validation --")
        for check in self.validation.checks:
            status = "PASS" if check.passed else "FAIL"
            lines.append(f"[{status}] {check.name}: {check.detail}")
        lines.append("\n" + ("=" * 70))
        lines.append(f"OVERALL: {'PASS' if self.passed else 'FAIL'}")
        lines.append("=" * 70)
        return "\n".join(lines)


class ResourceSampler:
    """Samples peak RSS / CPU% across a run, if psutil is available."""

    def __init__(self) -> None:
        self._process = psutil.Process(os.getpid()) if _HAS_PSUTIL else None
        self._peak_rss_mb: float | None = None
        if self._process is not None:
            self._process.cpu_percent(interval=None)  # prime the counter

    def sample(self) -> None:
        if self._process is None:
            return
        rss_mb = self._process.memory_info().rss / (1024 * 1024)
        if self._peak_rss_mb is None or rss_mb > self._peak_rss_mb:
            self._peak_rss_mb = rss_mb

    def finalize(self) -> tuple[float | None, float | None]:
        if self._process is None:
            return None, None
        self.sample()
        cpu = self._process.cpu_percent(interval=None)
        return self._peak_rss_mb, cpu


async def build_trading_summary(repos: Repositories) -> TradingSummary:
    all_grids = await repos.grids.list_all()
    trades = await repos.trade_history.list_all(limit=1_000_000)

    buys = [t for t in trades if t["side"] == "buy"]
    sells = [t for t in trades if t["side"] == "sell" and t["order_id"] != "(dust-writeoff)"]
    dust_writeoffs = [t for t in trades if t.get("order_id") == "(dust-writeoff)"]

    realized_pnls = [t["pnl"] for t in sells]
    wins = [p for p in realized_pnls if p > 0]
    losses = [p for p in realized_pnls if p < 0]
    win_rate = (len(wins) / len(realized_pnls) * 100.0) if realized_pnls else 0.0
    gross_profit = sum(wins)
    gross_loss = abs(sum(losses))
    profit_factor = (gross_profit / gross_loss) if gross_loss > 0 else None

    total_realized_profit = sum(g["realized_profit"] for g in all_grids)
    completed_cycles = sum(g["completed_cycles"] for g in all_grids)

    # Drawdown, computed on the running cumulative realized P&L across
    # trades in execution order — a simple, understandable proxy suitable
    # for a stress-test report (not a mark-to-market equity curve, which
    # would need continuous position valuation this report doesn't track).
    running = 0.0
    peak = 0.0
    max_dd_pct = 0.0
    for t in sorted(sells, key=lambda x: x["executed_at"]):
        running += t["pnl"]
        peak = max(peak, running)
        if peak > 0:
            dd_pct = (peak - running) / peak * 100.0
            max_dd_pct = max(max_dd_pct, dd_pct)

    return TradingSummary(
        total_buys=len(buys),
        total_sells=len(sells),
        total_dust_writeoffs=len(dust_writeoffs),
        total_realized_profit=total_realized_profit,
        win_rate_pct=win_rate,
        max_drawdown_pct=max_dd_pct,
        profit_factor=profit_factor,
        completed_cycles=completed_cycles,
        # trailing_activations / stop_loss_activations / manual_trades are
        # populated by the CLI from notifier call counts, since that's the
        # only place those events are currently observable without adding
        # new persisted columns — see cli.py.
    )


async def build_report(
    *, repos: Repositories, stats: ReplayStats, validation: ValidationReport,
    replay_duration_seconds: float, speed: float | None,
    sampler: ResourceSampler | None = None,
    trailing_activations: int = 0, stop_loss_activations: int = 0,
    manual_trades: int = 0, db_path: str | None = None,
) -> ReplayReport:
    trading = await build_trading_summary(repos)
    trading.trailing_activations = trailing_activations
    trading.stop_loss_activations = stop_loss_activations
    trading.manual_trades = manual_trades

    peak_rss, cpu = (sampler.finalize() if sampler is not None else (None, None))
    db_size = None
    if db_path:
        db_size = 0
        for suffix in ("", "-wal", "-shm"):
            candidate = f"{db_path}{suffix}"
            if os.path.exists(candidate):
                db_size += os.path.getsize(candidate)

    system = SystemSummary(
        peak_rss_mb=peak_rss, cpu_percent=cpu,
        exception_count=len(stats.exceptions),
        db_size_bytes=db_size,
        replay_duration_seconds=replay_duration_seconds,
    )
    replay_summary = ReplaySummary(
        symbols=sorted(stats.symbols_seen),
        start_timestamp=stats.start_timestamp,
        end_timestamp=stats.end_timestamp,
        candles_processed=stats.candles_processed,
        sub_ticks_processed=stats.sub_ticks_processed,
        trigger_evaluations=stats.trigger_evaluations,
        speed=speed,
    )
    return ReplayReport(replay=replay_summary, trading=trading, system=system, validation=validation)

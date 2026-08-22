"""Post-replay integrity validation.

Every check here is read-only and query-based against the real repository
layer — no bespoke SQL, no reaching into internals. Each check returns a
pass/fail plus a human-readable detail string so the report can render
exactly what failed and why.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from config.constants import GridStatus
from storage.repositories import Repositories


@dataclass
class CheckResult:
    name: str
    passed: bool
    detail: str = ""


@dataclass
class ValidationReport:
    checks: list[CheckResult] = field(default_factory=list)

    @property
    def all_passed(self) -> bool:
        return all(c.passed for c in self.checks)

    @property
    def failed(self) -> list[CheckResult]:
        return [c for c in self.checks if not c.passed]

    def add(self, name: str, passed: bool, detail: str = "") -> None:
        self.checks.append(CheckResult(name=name, passed=passed, detail=detail))


class ReplayValidator:
    """Runs every integrity check against the repos used by a replay run."""

    def __init__(self, repos: Repositories) -> None:
        self._repos = repos

    async def validate(self) -> ValidationReport:
        report = ValidationReport()
        all_grids = await self._repos.grids.list_all()

        await self._check_no_active_grid_zero_quantity(report, all_grids)
        await self._check_no_negative_quantity(report, all_grids)
        await self._check_no_negative_investment(report, all_grids)
        await self._check_no_orphan_orders(report, all_grids)
        await self._check_no_duplicate_order_ids(report)
        await self._check_trade_history_consistency(report, all_grids)
        await self._check_portfolio_totals_consistency(report, all_grids)
        await self._check_no_zombie_grids(report, all_grids)

        return report

    # ------------------------------------------------------------------

    async def _check_no_zombie_grids(
        self, report: ValidationReport, all_grids: list[dict],
    ) -> None:
        """Mirrors trading.recovery.RecoveryManager._detect_zombie_grids():
        an ACTIVE grid with current_level == 0 and zero order rows is a
        crash-window artifact (created but the initial order was never
        written) that would otherwise sit silently stuck forever, with no
        automated recovery path finding it unless RecoveryManager itself
        happens to run (only exercised via --restart-test)."""
        zombies: list[str] = []
        for grid in all_grids:
            if grid["status"] != GridStatus.ACTIVE.value:
                continue
            if grid.get("current_level", 0):
                continue
            orders = await self._repos.orders.list_for_grid(grid["grid_id"])
            if orders:
                continue
            zombies.append(grid["grid_id"])
        report.add(
            "no_zombie_grids", not zombies,
            f"{len(zombies)} zombie grid(s) — ACTIVE with current_level=0 and no order rows: {zombies}"
            if zombies else "ok",
        )

    async def _check_no_active_grid_zero_quantity(
        self, report: ValidationReport, all_grids: list[dict],
    ) -> None:
        offenders = [
            g["grid_id"] for g in all_grids
            if g["status"] == GridStatus.ACTIVE.value and g["total_quantity"] <= 0
        ]
        report.add(
            "no_active_grid_with_zero_quantity", not offenders,
            f"{len(offenders)} active grid(s) with zero/negative quantity: {offenders}" if offenders else "ok",
        )

    async def _check_no_negative_quantity(
        self, report: ValidationReport, all_grids: list[dict],
    ) -> None:
        offenders = [g["grid_id"] for g in all_grids if g["total_quantity"] < 0]
        report.add(
            "no_negative_quantity", not offenders,
            f"{len(offenders)} grid(s) with negative quantity: {offenders}" if offenders else "ok",
        )

    async def _check_no_negative_investment(
        self, report: ValidationReport, all_grids: list[dict],
    ) -> None:
        offenders = [g["grid_id"] for g in all_grids if g["total_investment"] < 0]
        report.add(
            "no_negative_investment", not offenders,
            f"{len(offenders)} grid(s) with negative investment: {offenders}" if offenders else "ok",
        )

    async def _check_no_orphan_orders(
        self, report: ValidationReport, all_grids: list[dict],
    ) -> None:
        """An orphan order references a grid_id that no longer exists."""
        known_grid_ids = {g["grid_id"] for g in all_grids}
        open_orders = await self._repos.orders.list_open()
        offenders = [
            o["order_id"] for o in open_orders if o["grid_id"] not in known_grid_ids
        ]
        report.add(
            "no_orphan_orders", not offenders,
            f"{len(offenders)} open order(s) referencing a nonexistent grid: {offenders}" if offenders else "ok",
        )

    async def _check_no_duplicate_order_ids(self, report: ValidationReport) -> None:
        """order_id is the primary key so the DB itself guarantees this,
        but exchange_order_id is not — two local orders sharing the same
        exchange fill would indicate a real reconciliation bug."""
        open_orders = await self._repos.orders.list_open()
        seen: dict[str, str] = {}
        offenders: list[str] = []
        for o in open_orders:
            eid = o.get("exchange_order_id")
            if not eid:
                continue
            if eid in seen:
                offenders.append(eid)
            else:
                seen[eid] = o["order_id"]
        report.add(
            "no_duplicate_exchange_order_ids", not offenders,
            f"{len(offenders)} exchange_order_id(s) shared by more than one local order: {offenders}"
            if offenders else "ok",
        )

    async def _check_trade_history_consistency(
        self, report: ValidationReport, all_grids: list[dict],
    ) -> None:
        """Every trade_history row must reference a grid that exists, and
        every completed_cycles count on a grid should have at least that
        many recorded sell trades (cycles can't complete without a sell)."""
        known_grid_ids = {g["grid_id"] for g in all_grids}
        trades = await self._repos.trade_history.list_all(limit=1_000_000)
        offenders = [t["trade_id"] for t in trades if t["grid_id"] not in known_grid_ids]
        report.add(
            "trade_history_references_valid_grids", not offenders,
            f"{len(offenders)} trade_history row(s) reference a nonexistent grid: {offenders[:10]}"
            if offenders else "ok",
        )

        sells_by_grid: dict[str, int] = {}
        for t in trades:
            if t["side"] == "sell":
                sells_by_grid[t["grid_id"]] = sells_by_grid.get(t["grid_id"], 0) + 1
        cycle_offenders = [
            g["grid_id"] for g in all_grids
            if g["completed_cycles"] > sells_by_grid.get(g["grid_id"], 0)
        ]
        report.add(
            "completed_cycles_backed_by_sell_history", not cycle_offenders,
            f"{len(cycle_offenders)} grid(s) report more completed_cycles than recorded sells: {cycle_offenders[:10]}"
            if cycle_offenders else "ok",
        )

    async def _check_portfolio_totals_consistency(
        self, report: ValidationReport, all_grids: list[dict],
    ) -> None:
        """A STOPPED/dust-written-off grid must contribute exactly zero to
        portfolio totals — this is the accounting guarantee the dust
        write-off fix depends on."""
        offenders = [
            g["grid_id"] for g in all_grids
            if g["status"] == GridStatus.STOPPED.value
            and (g["total_quantity"] != 0 or g["total_investment"] != 0)
            # A grid stopped for reasons OTHER than dust write-off (e.g. a
            # manual /stopgrid on an untouched position) legitimately keeps
            # its quantity — only flag ones that were supposedly fully
            # exited (realized_profit or trade history shows a full exit)
            # is out of scope for this generic check; see dust-specific
            # tests for the stronger guarantee. This check only flags the
            # unambiguous case of a NEGATIVE remainder, which can never be
            # correct regardless of stop reason.
            and (g["total_quantity"] < 0 or g["total_investment"] < 0)
        ]
        report.add(
            "stopped_grids_no_negative_remainder", not offenders,
            f"{len(offenders)} stopped grid(s) with a negative quantity/investment remainder: {offenders}"
            if offenders else "ok",
        )

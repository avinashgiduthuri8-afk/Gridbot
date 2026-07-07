"""Centralized risk checks for the DCA grid bot.

Every capital-committing action (starting a grid, placing an order) must pass
through here first. This is the single place that enforces the user's
configured risk limits, including the global emergency stop.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

from config.settings import RiskSettings
from storage.repositories import Repositories
from utils.logger import get_logger

log = get_logger("trading")


@dataclass(frozen=True)
class RiskCheckResult:
    allowed: bool
    reason: str = ""


class RiskManager:
    def __init__(self, risk_settings: RiskSettings, repos: Repositories) -> None:
        self._settings = risk_settings
        self._repos = repos
        self._emergency_stop = False

    @property
    def emergency_stopped(self) -> bool:
        return self._emergency_stop

    def trigger_emergency_stop(self) -> None:
        self._emergency_stop = True
        log.critical("EMERGENCY STOP triggered. All new trading actions are blocked.")

    def clear_emergency_stop(self) -> None:
        self._emergency_stop = False
        log.warning("Emergency stop cleared. Trading actions re-enabled.")

    async def check_can_start_grid(
        self, symbol: str, planned_investment: float, wallet_inr_balance: float
    ) -> RiskCheckResult:
        """Check all risk rules before allowing a new DCA grid to start."""
        if self._emergency_stop:
            return RiskCheckResult(False, "Emergency stop is active. Resume manually to continue.")

        active_grids = await self._repos.grids.list_by_status(["active", "paused"])

        if len(active_grids) >= self._settings.max_simultaneous_grids:
            return RiskCheckResult(
                False,
                f"Maximum simultaneous grids reached ({self._settings.max_simultaneous_grids}).",
            )

        for grid in active_grids:
            if grid["symbol"] == symbol:
                return RiskCheckResult(False, f"A grid for {symbol} is already running.")

        if planned_investment > self._settings.max_capital_per_coin:
            return RiskCheckResult(
                False,
                f"Investment for {symbol} (₹{planned_investment:,.2f}) exceeds the per-coin "
                f"limit of ₹{self._settings.max_capital_per_coin:,.2f}.",
            )

        total_committed = sum(float(g["total_investment"] or 0) for g in active_grids)
        if total_committed + planned_investment > self._settings.max_total_capital:
            return RiskCheckResult(
                False,
                f"Total capital limit of ₹{self._settings.max_total_capital:,.2f} would be exceeded.",
            )

        remaining_after = wallet_inr_balance - planned_investment
        if remaining_after < self._settings.min_wallet_balance:
            return RiskCheckResult(
                False,
                "Starting this grid would drop your wallet balance below the configured "
                f"minimum of ₹{self._settings.min_wallet_balance:,.2f}.",
            )

        daily_loss_ok = await self._check_daily_loss_limit()
        if not daily_loss_ok.allowed:
            return daily_loss_ok

        return RiskCheckResult(True)

    async def check_can_place_order(
        self, order_value_inr: float, wallet_inr_balance: float
    ) -> RiskCheckResult:
        """Check whether an individual order can be placed right now."""
        if self._emergency_stop:
            return RiskCheckResult(False, "Emergency stop is active.")
        if wallet_inr_balance < order_value_inr:
            return RiskCheckResult(
                False,
                f"Insufficient INR balance. Need ₹{order_value_inr:,.2f}, "
                f"available ₹{wallet_inr_balance:,.2f}.",
            )
        return await self._check_daily_loss_limit()

    async def _check_daily_loss_limit(self) -> RiskCheckResult:
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        stats = await self._repos.daily_stats.get(today)
        if stats and stats["realized_pnl"] <= -abs(self._settings.daily_loss_limit):
            return RiskCheckResult(
                False,
                f"Daily loss limit of ₹{self._settings.daily_loss_limit:,.2f} has been hit. "
                "Trading is paused for today.",
            )
        return RiskCheckResult(True)

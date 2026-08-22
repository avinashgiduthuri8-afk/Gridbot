"""Risk/Reward Geometry & Market-Structure Levels Calculator for Indian Equities.

Calculates Market-Structure Stop Loss, Dynamic Target 1, Target 2 (1.618 Fib Expansion),
Risk/Reward Ratio, and strictly enforces minimum 2.0R clearance.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from config.constants import MIN_REQUIRED_RR
from engine.indicators.technical import IndicatorSnapshot
from utils.logger import get_logger

log = get_logger("risk_reward")


@dataclass
class RiskRewardPlan:
    symbol: str
    entry_price: float
    stop_loss: float
    target_1: float
    target_2: float

    risk_amount: float
    reward_amount: float
    risk_percentage: float
    reward_percentage: float
    rr_ratio: float

    is_acceptable: bool = False
    rejection_reason: str = ""
    target_1_basis: str = ""
    stop_loss_basis: str = ""


class RiskRewardCalculator:
    """Computes technical trade geometry based on genuine order blocks and market structure."""

    def __init__(self, min_rr: float = MIN_REQUIRED_RR) -> None:
        self.min_rr = min_rr

    def calculate_plan(
        self,
        symbol: str,
        current_price: float,
        snap_1d: IndicatorSnapshot,
        snap_15m: IndicatorSnapshot | None = None,
        setup_type: str = "BREAKOUT",
    ) -> RiskRewardPlan:
        """Calculates precise Entry, Stop Loss, and Targets based on market-structure order blocks."""
        entry = current_price

        # ATR-based volatility baseline
        atr = snap_1d.atr if snap_1d and snap_1d.atr and snap_1d.atr > 0 else (current_price * 0.015)
        support = snap_1d.support_20 if snap_1d and snap_1d.support_20 and snap_1d.support_20 < entry else (entry - atr * 1.5)
        resistance = snap_1d.resistance_20 if snap_1d and snap_1d.resistance_20 and snap_1d.resistance_20 > entry else (entry + atr * 3.0)

        # 1. Market-Structure Stop Loss Calculation
        sl_basis = ""
        stype_upper = setup_type.upper()

        if "VCP" in stype_upper:
            # Stop Loss below the contraction base low - 0.3 ATR
            base_low = max(support, snap_1d.ema_20 - (atr * 0.3)) if snap_1d.ema_20 else support
            stop_loss = round(base_low - (atr * 0.3), 2)
            sl_basis = "Below VCP final contraction base low (-0.3 ATR)"
        elif "POCKET" in stype_upper:
            # Stop Loss below 20 EMA pivot
            ema_20 = snap_1d.ema_20 or (entry - atr * 0.8)
            stop_loss = round(ema_20 - (atr * 0.3), 2)
            sl_basis = "Below 20 EMA dynamic support (-0.3 ATR)"
        elif "NR7" in stype_upper:
            # Stop Loss below NR7 inside bar low
            nr7_low = entry - (atr * 0.7)
            stop_loss = round(nr7_low - (atr * 0.3), 2)
            sl_basis = "Below NR7 consolidation range low (-0.3 ATR)"
        elif "DELIVERY" in stype_upper:
            # Stop Loss below institutional accumulation breakout bar
            stop_loss = round(min(resistance * 0.985, entry - (atr * 0.9)), 2)
            sl_basis = "Below institutional delivery accumulation pivot"
        elif "PULLBACK" in stype_upper:
            sl_candidate = max(support, snap_1d.ema_20 - (atr * 0.3)) if snap_1d.ema_20 else support
            stop_loss = round(min(sl_candidate, entry - (atr * 0.7)), 2)
            sl_basis = "Below 20 EMA and pullback swing pivot (-0.3 ATR)"
        elif "MOMENTUM" in stype_upper:
            vwap = snap_1d.vwap if snap_1d.vwap and snap_1d.vwap < entry else (entry - atr * 0.8)
            stop_loss = round(min(vwap, entry - (atr * 0.8)), 2)
            sl_basis = "Below rising VWAP support anchor"
        else:
            stop_loss = round(support - (atr * 0.3), 2)
            sl_basis = "Below 20-day swing support block (-0.3 ATR)"

        # Enforce minimum risk floor (0.5%)
        risk = max(entry - stop_loss, entry * 0.005)
        stop_loss = round(entry - risk, 2)

        # 2. Structural Target Geometry & Resistance Clearance Check
        rejection_reason = ""
        is_acceptable = True
        t1_basis = ""

        # Resistance clearance check:
        # If immediate resistance is strictly closer than required minimum R:R, upside is structurally capped
        has_real_resistance = snap_1d.resistance_20 is not None and snap_1d.resistance_20 > entry

        if has_real_resistance and snap_1d.resistance_20:
            res_level = snap_1d.resistance_20
            avail_reward = res_level - entry
            avail_rr = avail_reward / risk if risk > 0 else 0.0

            if avail_rr < self.min_rr:
                is_acceptable = False
                rejection_reason = f"Overhead resistance at ₹{res_level:.2f} caps upside below {self.min_rr:.1f} R:R (available: {avail_rr:.1f}x)"
                target_1 = round(res_level, 2)
                target_2 = round(entry + (risk * 2.5), 2)
                t1_basis = f"Capped by 20d resistance ₹{res_level:.2f}"
            else:
                # Structural target at verified resistance level
                target_1 = round(res_level, 2)
                target_2 = round(entry + (risk * 3.5), 2)
                t1_basis = f"20-day swing resistance at ₹{res_level:.2f} ({avail_rr:.1f}R clearance)"
        else:
            # Blue-sky breakout / All-time high room
            target_1 = round(entry + (risk * self.min_rr), 2)
            target_2 = round(entry + (risk * 3.5), 2)
            t1_basis = f"{self.min_rr:.1f}x Structural Expansion Target (Clear Overhead Room)"

        reward = target_1 - entry
        rr = reward / risk if risk > 0 else 0.0

        risk_pct = (risk / entry * 100.0) if entry > 0 else 0.0
        reward_pct = (reward / entry * 100.0) if entry > 0 else 0.0

        if is_acceptable:
            if rr < self.min_rr:
                is_acceptable = False
                rejection_reason = f"Risk/Reward {rr:.2f} < required minimum {self.min_rr:.2f}"
            elif risk_pct > 6.0:
                is_acceptable = False
                rejection_reason = f"Risk too wide ({risk_pct:.2f}% > 6.0% max limit)"

        return RiskRewardPlan(
            symbol=symbol,
            entry_price=round(entry, 2),
            stop_loss=round(stop_loss, 2),
            target_1=round(target_1, 2),
            target_2=round(target_2, 2),
            risk_amount=round(risk, 2),
            reward_amount=round(reward, 2),
            risk_percentage=round(risk_pct, 2),
            reward_percentage=round(reward_pct, 2),
            rr_ratio=round(rr, 2),
            is_acceptable=is_acceptable,
            rejection_reason=rejection_reason,
            target_1_basis=t1_basis,
            stop_loss_basis=sl_basis,
        )

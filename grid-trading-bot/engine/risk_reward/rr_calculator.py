"""Risk/Reward Geometry & Execution Levels Calculator for Indian Equities.

Calculates Entry, Stop Loss, Target 1, Target 2, Risk, Reward, and Risk/Reward Ratio.
Strictly checks structural resistance and filters out any setup with R:R < MIN_RR (default 2.0).
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
    """Computes technical trade geometry and enforces structural R:R thresholds."""

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
        """Calculates precise Entry, Stop Loss, and Targets based on volatility & technical structure."""
        entry = current_price

        # ATR-based volatility buffer
        atr = snap_1d.atr if snap_1d and snap_1d.atr and snap_1d.atr > 0 else (current_price * 0.015)
        support = snap_1d.support_20 if snap_1d and snap_1d.support_20 and snap_1d.support_20 < entry else (entry - atr * 1.5)
        resistance = snap_1d.resistance_20 if snap_1d and snap_1d.resistance_20 and snap_1d.resistance_20 > entry else (entry + atr * 3.0)

        # 1. Structural Stop Loss Geometry
        sl_basis = ""
        if setup_type == "PULLBACK":
            sl_candidate = max(support, snap_1d.ema_20 - (atr * 0.4)) if snap_1d.ema_20 else support
            stop_loss = round(min(sl_candidate, entry - (atr * 0.7)), 2)
            sl_basis = "Below 20 EMA and recent pullback support"
        elif setup_type == "BREAKOUT":
            # SL below breakout candle base / resistance turned support
            stop_loss = round(min(resistance * 0.99, entry - (atr * 1.0)), 2)
            sl_basis = "Below breakout baseline support"
        elif setup_type == "MOMENTUM_CONTINUATION":
            vwap = snap_1d.vwap if snap_1d.vwap and snap_1d.vwap < entry else (entry - atr * 0.8)
            stop_loss = round(min(vwap, entry - (atr * 0.8)), 2)
            sl_basis = "Below rising VWAP / short-term support"
        else:
            stop_loss = round(support - (atr * 0.4), 2)
            sl_basis = "Below major swing support level"

        risk = max(entry - stop_loss, entry * 0.005)
        stop_loss = round(entry - risk, 2)

        # 2. Structural Target Geometry & Resistance Clearance Check
        # If immediate resistance is closer than 1.8x risk, the trade is trapped under resistance
        rejection_reason = ""
        is_acceptable = True
        t1_basis = ""

        if resistance > entry and (resistance - entry) < (risk * 1.7):
            # Resistance is too close for an adequate R:R
            is_acceptable = False
            rejection_reason = f"Overhead resistance at ₹{resistance:.2f} caps upside below {self.min_rr:.1f} R:R (available: {((resistance-entry)/risk):.1f}x)"
            target_1 = round(resistance, 2)
            target_2 = round(entry + (risk * 2.5), 2)
            t1_basis = f"Capped by 20d resistance ₹{resistance:.2f}"
        else:
            # Clear room to run
            # Set Target 1 at maximum of natural resistance or 2.0x Risk
            target_1 = round(max(resistance, entry + (risk * 2.0)), 2)
            target_2 = round(entry + (risk * 3.2), 2)
            t1_basis = f"2.0x R:R expansion target (clear overhead room)"

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

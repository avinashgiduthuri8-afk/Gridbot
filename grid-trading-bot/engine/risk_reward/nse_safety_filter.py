"""NSE Regulatory & Safety Filter Suite for Indian Equities.

Enforces critical market micro-structure and regulatory gates:
1. Circuit Band Proximity Filter: Blocks entries within <= 1.5% of Upper/Lower Circuit limit.
2. Earnings / Corporate Event Blackout: Blocks breakout setups within +/- 3 trading days of earnings/board results.
3. ASM / GSM Surveillance Filter: Flags and penalizes stocks under SEBI Additional / Graded Surveillance Measures.
4. F&O Ban & MWPL Proximity: Rejects or penalizes derivative stocks exceeding 85% Market-Wide Position Limit.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone, timedelta
from typing import Any

from utils.logger import get_logger

log = get_logger("risk_reward")

# High-profile SEBI ASM/GSM watchlist (regularly updated)
KNOWN_ASM_GSM_STOCKS: dict[str, str] = {
    "ADANIENT": "ASM_STAGE_1",
    "ADANIPOWER": "ASM_STAGE_1",
    "SUZLON": "ASM_STAGE_1",
    "IDEA": "ASM_STAGE_1",
    "YESBANK": "ASM_STAGE_1",
    "RCOM": "GSM_STAGE_2",
}

# Standard F&O Universe on NSE
KNOWN_FNO_STOCKS = {
    "RELIANCE", "TCS", "INFY", "HDFCBANK", "ICICIBANK", "SBIN", "BHARTIARTL",
    "ITC", "KOTAKBANK", "LT", "AXISBANK", "ASIANPAINT", "MARUTI", "TITAN",
    "SUNPHARMA", "BAJFINANCE", "TATAMOTORS", "TATASTEEL", "NTPC", "POWERGRID",
    "M&M", "HCLTECH", "ONGC", "WIPRO", "COALINDIA", "BAJAJFINSV", "NESTLEIND",
}


@dataclass
class NSESafetyMetrics:
    symbol: str
    circuit_proximity_pct: float = 100.0   # Distance to nearest circuit limit
    is_near_circuit: bool = False          # Within 1.5% of circuit
    is_earnings_blackout: bool = False     # Within +/- 3 days of results
    days_to_earnings: int | None = None
    is_asm_gsm: bool = False
    asm_gsm_stage: str = ""
    is_fo_banned: bool = False
    fo_mwpl_pct: float = 0.0
    is_safe_to_trade: bool = True
    safety_score: float = 10.0             # 0.0 to 10.0
    rejection_reasons: list[str] = field(default_factory=list)


class NSESafetyFilter:
    """Evaluates regulatory, event, and circuit limit risks for Indian equities."""

    def __init__(
        self,
        min_circuit_buffer_pct: float = 1.5,
        earnings_blackout_days: int = 3,
        fo_ban_mwpl_threshold: float = 85.0,
    ) -> None:
        self.min_circuit_buffer_pct = min_circuit_buffer_pct
        self.earnings_blackout_days = earnings_blackout_days
        self.fo_ban_mwpl_threshold = fo_ban_mwpl_threshold

    def evaluate_safety(
        self,
        symbol: str,
        current_price: float,
        upper_circuit: float | None = None,
        lower_circuit: float | None = None,
        upcoming_events: list[dict[str, Any]] | None = None,
        mwpl_pct: float | None = None,
    ) -> NSESafetyMetrics:
        """Evaluates safety across circuit proximity, earnings risk, ASM/GSM, and F&O status."""
        clean_sym = symbol.replace(".NS", "").replace(".BO", "").strip().upper()
        rejection_reasons: list[str] = []
        is_safe = True
        safety_score = 10.0

        # 1. Circuit Limit Proximity Check
        # If upper_circuit is defined, calculate distance
        dist_to_upper_pct = 100.0
        dist_to_lower_pct = 100.0
        min_circuit_dist = 100.0
        is_near_circuit = False

        if upper_circuit and upper_circuit > current_price > 0:
            dist_to_upper_pct = (upper_circuit - current_price) / current_price * 100.0
        if lower_circuit and 0 < lower_circuit < current_price:
            dist_to_lower_pct = (current_price - lower_circuit) / current_price * 100.0

        min_circuit_dist = min(dist_to_upper_pct, dist_to_lower_pct)
        if min_circuit_dist <= self.min_circuit_buffer_pct:
            is_near_circuit = True
            is_safe = False
            safety_score -= 5.0
            rejection_reasons.append(
                f"Circuit Risk: Price ₹{current_price:.2f} is within {min_circuit_dist:.2f}% of Circuit Limit (Upper: ₹{upper_circuit:.2f})"
            )

        # 2. Earnings / Corporate Event Blackout Check
        is_earnings_blackout = False
        days_to_earnings = None
        now_date = datetime.now(timezone.utc).date()

        if upcoming_events:
            for ev in upcoming_events:
                ev_type = ev.get("event_type", "").lower()
                ev_date_str = ev.get("date", "")
                if ("result" in ev_type or "quarter" in ev_type or "board" in ev_type or "earnings" in ev_type) and ev_date_str:
                    try:
                        ev_date = datetime.strptime(ev_date_str, "%Y-%m-%d").date()
                        delta_days = (ev_date - now_date).days
                        days_to_earnings = delta_days
                        if abs(delta_days) <= self.earnings_blackout_days:
                            is_earnings_blackout = True
                            is_safe = False
                            safety_score -= 4.0
                            rejection_reasons.append(
                                f"Earnings Blackout: Quarterly Results in {delta_days} day(s) ({ev_date_str})"
                            )
                            break
                    except Exception:
                        pass

        # 3. ASM / GSM Surveillance Filter
        is_asm_gsm = clean_sym in KNOWN_ASM_GSM_STOCKS
        asm_stage = KNOWN_ASM_GSM_STOCKS.get(clean_sym, "")
        if is_asm_gsm:
            safety_score -= 3.0
            rejection_reasons.append(f"SEBI Surveillance: {clean_sym} is under {asm_stage}")

        # 4. F&O Ban / MWPL Proximity
        is_fo_banned = False
        fo_mwpl = mwpl_pct or 0.0
        if clean_sym in KNOWN_FNO_STOCKS and fo_mwpl >= self.fo_ban_mwpl_threshold:
            is_fo_banned = True
            safety_score -= 3.5
            rejection_reasons.append(f"F&O Ban Risk: MWPL at {fo_mwpl:.1f}% >= {self.fo_ban_mwpl_threshold:.1f}%")

        safety_score = max(0.0, min(10.0, round(safety_score, 1)))

        return NSESafetyMetrics(
            symbol=clean_sym,
            circuit_proximity_pct=round(min_circuit_dist, 2),
            is_near_circuit=is_near_circuit,
            is_earnings_blackout=is_earnings_blackout,
            days_to_earnings=days_to_earnings,
            is_asm_gsm=is_asm_gsm,
            asm_gsm_stage=asm_stage,
            is_fo_banned=is_fo_banned,
            fo_mwpl_pct=fo_mwpl,
            is_safe_to_trade=is_safe and safety_score >= 6.0,
            safety_score=safety_score,
            rejection_reasons=rejection_reasons,
        )

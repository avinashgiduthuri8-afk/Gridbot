"""Market Regime & India VIX Volatility Detector for Indian Equities.

Evaluates broader macro/market regime using NIFTY 50, BANK NIFTY, and INDIA VIX
to classify market state (STRONG_BULLISH, BULLISH, NEUTRAL, BEARISH, STRONG_BEARISH, HIGH_VOLATILITY)
and provide risk weighting multipliers.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from config.constants import MarketRegime
from engine.data.base import IndexQuote, MarketDataProvider
from utils.logger import get_logger

log = get_logger("regime_detector")


@dataclass
class MarketRegimeAnalysis:
    """Consolidated market regime state."""
    regime: MarketRegime = MarketRegime.NEUTRAL
    nifty_50_change: float = 0.0
    nifty_bank_change: float = 0.0
    vix_value: float = 14.0
    vix_change: float = 0.0
    vix_status: str = "NORMAL"         # LOW, NORMAL, ELEVATED, EXTREME

    nifty_trend: str = "NEUTRAL"       # BULLISH, BEARISH, NEUTRAL
    bank_trend: str = "NEUTRAL"

    regime_score: float = 5.0          # 0.0 to 10.0 pts in signal score
    long_confidence_multiplier: float = 1.0  # Multiplier for long setups
    summary: str = ""


class MarketRegimeDetector:
    """Evaluates NIFTY 50, BANK NIFTY, and INDIA VIX to determine market health."""

    def evaluate_regime(
        self,
        indices: dict[str, IndexQuote],
    ) -> MarketRegimeAnalysis:
        """Determines market regime from index snapshots."""
        nifty = indices.get("NIFTY_50")
        bank = indices.get("NIFTY_BANK")
        vix = indices.get("INDIA_VIX")

        nifty_chg = nifty.change_pct if nifty else 0.0
        bank_chg = bank.change_pct if bank else 0.0
        vix_val = vix.last_price if vix and vix.last_price > 0 else 14.0
        vix_chg = vix.change_pct if vix else 0.0

        nifty_trend = nifty.trend if nifty else ("BULLISH" if nifty_chg > 0.3 else ("BEARISH" if nifty_chg < -0.3 else "NEUTRAL"))
        bank_trend = bank.trend if bank else ("BULLISH" if bank_chg > 0.3 else ("BEARISH" if bank_chg < -0.3 else "NEUTRAL"))

        # 1. India VIX Volatility Assessment
        if vix_val < 12.0:
            vix_status = "LOW"
        elif vix_val <= 16.5:
            vix_status = "NORMAL"
        elif vix_val <= 21.0:
            vix_status = "ELEVATED"
        else:
            vix_status = "EXTREME"

        # 2. Regime Classification
        if vix_status == "EXTREME" or (vix_val > 19.0 and vix_chg > 10.0):
            regime = MarketRegime.HIGH_VOLATILITY
            regime_score = 1.0
            mult = 0.2
            summary = f"Extreme market volatility (India VIX {vix_val:.1f}). Extreme caution advised."

        elif nifty_trend == "BULLISH" and bank_trend == "BULLISH" and nifty_chg > 0.5:
            regime = MarketRegime.STRONG_BULLISH
            regime_score = 10.0
            mult = 1.0
            summary = f"Strong bullish market: NIFTY (+{nifty_chg:.2f}%) & Bank NIFTY (+{bank_chg:.2f}%) both trending up."

        elif nifty_trend == "BULLISH" or nifty_chg > 0.2:
            regime = MarketRegime.BULLISH
            regime_score = 8.0
            mult = 0.9
            summary = f"Bullish market: NIFTY up {nifty_chg:.2f}%, VIX steady at {vix_val:.1f}."

        elif nifty_trend == "BEARISH" and bank_trend == "BEARISH" and nifty_chg < -0.8:
            regime = MarketRegime.STRONG_BEARISH
            regime_score = 0.0
            mult = 0.1
            summary = f"Strong bearish selloff: NIFTY ({nifty_chg:.2f}%) & Bank NIFTY ({bank_chg:.2f}%) breaking support."

        elif nifty_trend == "BEARISH" or nifty_chg < -0.3:
            regime = MarketRegime.BEARISH
            regime_score = 2.0
            mult = 0.4
            summary = f"Bearish market pressure: NIFTY down {nifty_chg:.2f}%."

        else:
            regime = MarketRegime.NEUTRAL
            regime_score = 5.0
            mult = 0.7
            summary = f"Consolidating/Neutral market: NIFTY {nifty_chg:+.2f}%, VIX {vix_val:.1f}."

        return MarketRegimeAnalysis(
            regime=regime,
            nifty_50_change=nifty_chg,
            nifty_bank_change=bank_chg,
            vix_value=vix_val,
            vix_change=vix_chg,
            vix_status=vix_status,
            nifty_trend=nifty_trend,
            bank_trend=bank_trend,
            regime_score=regime_score,
            long_confidence_multiplier=mult,
            summary=summary,
        )

    async def detect_current_regime(self, provider: MarketDataProvider) -> MarketRegimeAnalysis:
        """Fetches live index metrics from provider and runs regime detection."""
        indices = await provider.get_market_indices()
        return self.evaluate_regime(indices)

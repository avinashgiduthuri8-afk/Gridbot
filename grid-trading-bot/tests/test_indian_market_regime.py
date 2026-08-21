"""Tests for Market Regime & India VIX Volatility Detector."""

from config.constants import MarketRegime
from engine.data.base import IndexQuote
from engine.regime.regime_detector import MarketRegimeDetector


def test_regime_strong_bullish():
    detector = MarketRegimeDetector()
    indices = {
        "NIFTY_50": IndexQuote(symbol="NIFTY 50", name="Nifty 50", last_price=24500.0, change_pct=1.2, trend="BULLISH"),
        "NIFTY_BANK": IndexQuote(symbol="NIFTY BANK", name="Bank Nifty", last_price=52000.0, change_pct=1.5, trend="BULLISH"),
        "INDIA_VIX": IndexQuote(symbol="INDIA VIX", name="India VIX", last_price=13.2, change_pct=-3.0, trend="NEUTRAL"),
    }
    regime = detector.evaluate_regime(indices)
    assert regime.regime == MarketRegime.STRONG_BULLISH
    assert regime.regime_score == 10.0
    assert regime.long_confidence_multiplier == 1.0
    assert regime.vix_status == "NORMAL"


def test_regime_high_volatility_vix_spike():
    detector = MarketRegimeDetector()
    indices = {
        "NIFTY_50": IndexQuote(symbol="NIFTY 50", name="Nifty 50", last_price=23800.0, change_pct=-1.5, trend="BEARISH"),
        "NIFTY_BANK": IndexQuote(symbol="NIFTY BANK", name="Bank Nifty", last_price=50000.0, change_pct=-2.0, trend="BEARISH"),
        "INDIA_VIX": IndexQuote(symbol="INDIA VIX", name="India VIX", last_price=24.5, change_pct=18.0, trend="BULLISH"),
    }
    regime = detector.evaluate_regime(indices)
    assert regime.regime == MarketRegime.HIGH_VOLATILITY
    assert regime.vix_status == "EXTREME"
    assert regime.long_confidence_multiplier <= 0.3


def test_regime_bearish():
    detector = MarketRegimeDetector()
    indices = {
        "NIFTY_50": IndexQuote(symbol="NIFTY 50", name="Nifty 50", last_price=24000.0, change_pct=-1.0, trend="BEARISH"),
        "NIFTY_BANK": IndexQuote(symbol="NIFTY BANK", name="Bank Nifty", last_price=51000.0, change_pct=-0.9, trend="BEARISH"),
        "INDIA_VIX": IndexQuote(symbol="INDIA VIX", name="India VIX", last_price=15.0, change_pct=2.0, trend="NEUTRAL"),
    }
    regime = detector.evaluate_regime(indices)
    assert regime.regime in (MarketRegime.BEARISH, MarketRegime.STRONG_BEARISH)
    assert regime.long_confidence_multiplier < 0.5

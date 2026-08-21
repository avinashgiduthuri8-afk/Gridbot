"""Tests for NSE Safety & Regulatory Filter Suite."""

import pytest
from datetime import datetime, timezone, timedelta
from engine.risk_reward.nse_safety_filter import NSESafetyFilter


def test_circuit_proximity_rejection():
    filter_suite = NSESafetyFilter(min_circuit_buffer_pct=1.5)

    # Current price is ₹995, Upper Circuit is ₹1000 (0.5% distance -> within 1.5%)
    res = filter_suite.evaluate_safety(
        symbol="TATASTEEL",
        current_price=995.0,
        upper_circuit=1000.0,
        lower_circuit=800.0,
    )
    assert not res.is_safe_to_trade
    assert res.is_near_circuit
    assert any("Circuit Risk" in r for r in res.rejection_reasons)

    # Safe price: ₹900 (10% away from ₹1000 circuit)
    safe_res = filter_suite.evaluate_safety(
        symbol="TATASTEEL",
        current_price=900.0,
        upper_circuit=1000.0,
        lower_circuit=800.0,
    )
    assert safe_res.is_safe_to_trade
    assert not safe_res.is_near_circuit


def test_earnings_blackout_rejection():
    filter_suite = NSESafetyFilter(earnings_blackout_days=3)
    today = datetime.now(timezone.utc).date()
    earnings_date_str = (today + timedelta(days=2)).strftime("%Y-%m-%d")

    # Earnings in 2 days -> Blackout
    res = filter_suite.evaluate_safety(
        symbol="INFY",
        current_price=1600.0,
        upcoming_events=[
            {"event_type": "Quarterly Financial Results", "date": earnings_date_str}
        ],
    )
    assert not res.is_safe_to_trade
    assert res.is_earnings_blackout
    assert any("Earnings Blackout" in r for r in res.rejection_reasons)


def test_asm_gsm_surveillance():
    filter_suite = NSESafetyFilter()

    # ADANIENT is in KNOWN_ASM_GSM_STOCKS
    res = filter_suite.evaluate_safety(symbol="ADANIENT", current_price=2800.0)
    assert res.is_asm_gsm
    assert res.asm_gsm_stage == "ASM_STAGE_1"
    assert any("SEBI Surveillance" in r for r in res.rejection_reasons)


def test_fo_ban_mwpl_filter():
    filter_suite = NSESafetyFilter(fo_ban_mwpl_threshold=85.0)

    # RELIANCE with 92% MWPL -> Ban risk
    res = filter_suite.evaluate_safety(
        symbol="RELIANCE",
        current_price=2900.0,
        mwpl_pct=92.5,
    )
    assert res.is_fo_banned
    assert any("F&O Ban Risk" in r for r in res.rejection_reasons)

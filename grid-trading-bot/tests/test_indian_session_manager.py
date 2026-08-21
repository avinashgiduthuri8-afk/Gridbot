"""Tests for Indian Stock Market IST Session & Holiday Manager."""

from datetime import date, datetime, time, timezone

from config.constants import SessionState
from engine.session.session_manager import IST_TIMEZONE, IndianSessionManager


def test_ist_now_timezone():
    now_ist = IndianSessionManager.now_ist()
    assert now_ist.tzinfo is not None
    assert now_ist.utcoffset().total_seconds() == 5.5 * 3600


def test_is_holiday():
    assert IndianSessionManager.is_holiday(date(2025, 1, 26)) is True   # Republic Day
    assert IndianSessionManager.is_holiday(date(2025, 8, 15)) is True   # Independence Day
    assert IndianSessionManager.is_holiday(date(2025, 12, 25)) is True  # Christmas
    assert IndianSessionManager.is_holiday(date(2025, 6, 11)) is False  # Regular working Wednesday


def test_is_weekend():
    saturday = date(2025, 6, 14)
    sunday = date(2025, 6, 15)
    monday = date(2025, 6, 16)
    assert IndianSessionManager.is_weekend(saturday) is True
    assert IndianSessionManager.is_weekend(sunday) is True
    assert IndianSessionManager.is_weekend(monday) is False


def test_session_state_intraday():
    # Regular trading Wednesday at 10:30 AM IST
    dt = datetime(2025, 6, 11, 10, 30, 0, tzinfo=IST_TIMEZONE)
    state = IndianSessionManager.get_session_state(dt)
    assert state == SessionState.INTRADAY_REGULAR
    assert IndianSessionManager.is_market_open(dt) is True
    assert IndianSessionManager.is_valid_signal_window(dt) is True


def test_session_state_pre_market():
    # 09:05 AM IST
    dt = datetime(2025, 6, 11, 9, 5, 0, tzinfo=IST_TIMEZONE)
    state = IndianSessionManager.get_session_state(dt)
    assert state == SessionState.PRE_MARKET
    assert IndianSessionManager.is_market_open(dt) is False


def test_session_state_market_open():
    # 09:20 AM IST
    dt = datetime(2025, 6, 11, 9, 20, 0, tzinfo=IST_TIMEZONE)
    state = IndianSessionManager.get_session_state(dt)
    assert state == SessionState.MARKET_OPEN
    assert IndianSessionManager.is_market_open(dt) is True


def test_session_state_closing_and_post():
    # 15:20 IST -> Closing session
    dt_closing = datetime(2025, 6, 11, 15, 20, 0, tzinfo=IST_TIMEZONE)
    assert IndianSessionManager.get_session_state(dt_closing) == SessionState.MARKET_CLOSE

    # 15:45 IST -> Post-market
    dt_post = datetime(2025, 6, 11, 15, 45, 0, tzinfo=IST_TIMEZONE)
    assert IndianSessionManager.get_session_state(dt_post) == SessionState.POST_MARKET
    assert IndianSessionManager.is_market_open(dt_post) is False

    # 20:00 IST -> Closed
    dt_closed = datetime(2025, 6, 11, 20, 0, 0, tzinfo=IST_TIMEZONE)
    assert IndianSessionManager.get_session_state(dt_closed) == SessionState.CLOSED


def test_session_state_weekend_or_holiday():
    saturday_noon = datetime(2025, 6, 14, 11, 0, 0, tzinfo=IST_TIMEZONE)
    assert IndianSessionManager.get_session_state(saturday_noon) == SessionState.CLOSED
    assert IndianSessionManager.is_market_open(saturday_noon) is False

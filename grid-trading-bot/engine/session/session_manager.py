"""Indian Stock Market (NSE/BSE) Trading Session & IST Clock Manager.

Handles Indian Standard Time (IST = UTC+5:30), trading hours (09:15-15:30 IST),
pre-market, post-market, weekend, and NSE holiday calendar checks.
"""

from __future__ import annotations

from datetime import date, datetime, time as dtime, timedelta, timezone
from typing import Any

from config.constants import SessionState

# Indian Standard Time (UTC+05:30)
IST_TIMEZONE = timezone(timedelta(hours=5, minutes=30))

# Official NSE Holidays (2025 - 2027)
NSE_HOLIDAYS: set[str] = {
    # 2025
    "2025-01-26",  # Republic Day
    "2025-02-26",  # Mahashivratri
    "2025-03-14",  # Holi
    "2025-03-31",  # Id-Ul-Fitr
    "2025-04-10",  # Mahavir Jayanti
    "2025-04-14",  # Dr. Ambedkar Jayanti
    "2025-04-18",  # Good Friday
    "2025-05-01",  # Maharashtra Day
    "2025-06-07",  # Bakri Id
    "2025-07-06",  # Moharram
    "2025-08-15",  # Independence Day
    "2025-08-27",  # Ganesh Chaturthi
    "2025-10-02",  # Mahatma Gandhi Jayanti / Dussehra
    "2025-10-21",  # Diwali (Laxmi Pujan)
    "2025-10-22",  # Diwali Balipratipada
    "2025-11-05",  # Gurunanak Jayanti
    "2025-12-25",  # Christmas
    # 2026
    "2026-01-26",  # Republic Day
    "2026-02-17",  # Mahashivratri
    "2026-03-04",  # Holi
    "2026-03-20",  # Id-Ul-Fitr
    "2026-04-03",  # Good Friday
    "2026-04-14",  # Dr. Ambedkar Jayanti
    "2026-05-01",  # Maharashtra Day
    "2026-08-15",  # Independence Day
    "2026-10-02",  # Mahatma Gandhi Jayanti
    "2026-10-20",  # Dussehra
    "2026-11-08",  # Diwali
    "2026-11-24",  # Gurunanak Jayanti
    "2026-12-25",  # Christmas
}


class IndianSessionManager:
    """Evaluates the active Indian trading session state."""

    @staticmethod
    def now_ist() -> datetime:
        """Returns the current datetime in IST timezone."""
        return datetime.now(IST_TIMEZONE)

    @classmethod
    def is_holiday(cls, check_date: date | datetime | None = None) -> bool:
        """Checks if a given date is an official NSE market holiday."""
        if check_date is None:
            check_date = cls.now_ist().date()
        elif isinstance(check_date, datetime):
            check_date = check_date.date()
        date_str = check_date.strftime("%Y-%m-%d")
        return date_str in NSE_HOLIDAYS

    @classmethod
    def is_weekend(cls, check_date: date | datetime | None = None) -> bool:
        """Checks if the date falls on Saturday (5) or Sunday (6)."""
        if check_date is None:
            check_date = cls.now_ist().date()
        elif isinstance(check_date, datetime):
            check_date = check_date.date()
        return check_date.weekday() >= 5

    @classmethod
    def is_trading_day(cls, check_date: date | datetime | None = None) -> bool:
        """Returns True if the date is a regular weekday trading day (not weekend or holiday)."""
        return not cls.is_weekend(check_date) and not cls.is_holiday(check_date)

    @classmethod
    def get_session_state(cls, dt: datetime | None = None) -> SessionState:
        """Determines the current session state based on IST clock and NSE rules."""
        if dt is None:
            dt = cls.now_ist()
        elif dt.tzinfo is None:
            dt = dt.replace(tzinfo=IST_TIMEZONE)
        else:
            dt = dt.astimezone(IST_TIMEZONE)

        if not cls.is_trading_day(dt.date()):
            return SessionState.CLOSED

        t = dt.time()

        if dtime(9, 0) <= t < dtime(9, 15):
            return SessionState.PRE_MARKET
        elif dtime(9, 15) <= t < dtime(9, 30):
            return SessionState.MARKET_OPEN
        elif dtime(9, 30) <= t < dtime(15, 15):
            return SessionState.INTRADAY_REGULAR
        elif dtime(15, 15) <= t < dtime(15, 30):
            return SessionState.MARKET_CLOSE
        elif dtime(15, 30) <= t < dtime(16, 0):
            return SessionState.POST_MARKET
        else:
            return SessionState.CLOSED

    @classmethod
    def is_market_open(cls, dt: datetime | None = None) -> bool:
        """Returns True if regular market trading is active (09:15 - 15:30 IST)."""
        state = cls.get_session_state(dt)
        return state in (SessionState.MARKET_OPEN, SessionState.INTRADAY_REGULAR, SessionState.MARKET_CLOSE)

    @classmethod
    def is_valid_signal_window(cls, dt: datetime | None = None, allow_out_of_session: bool = False) -> bool:
        """Returns True if conditions are ideal for generating high-probability intraday signals.
        
        Prime signal window is 09:30 - 15:15 IST (filtering out opening whipsaws and closing noise).
        """
        if allow_out_of_session:
            return True
        state = cls.get_session_state(dt)
        return state in (SessionState.INTRADAY_REGULAR, SessionState.MARKET_OPEN)

    @classmethod
    def get_session_info(cls) -> dict[str, Any]:
        """Provides human-readable summary of the current market session."""
        now = cls.now_ist()
        state = cls.get_session_state(now)
        return {
            "current_time_ist": now.strftime("%Y-%m-%d %H:%M:%S IST"),
            "session_state": state.value,
            "is_market_open": cls.is_market_open(now),
            "is_trading_day": cls.is_trading_day(now.date()),
            "is_holiday": cls.is_holiday(now.date()),
            "is_weekend": cls.is_weekend(now.date()),
            "valid_signal_window": cls.is_valid_signal_window(now),
        }

"""Exchange-layer exceptions. All exchange clients raise these, never
raw httpx errors, so callers have one consistent contract to handle."""

from __future__ import annotations


class ExchangeError(Exception):
    """Base class for all exchange-layer failures."""


class ExchangeAuthError(ExchangeError):
    """Invalid or rejected API credentials."""


class ExchangeRateLimitError(ExchangeError):
    """Exchange responded with a rate-limit (429) error."""


class ExchangeTimeoutError(ExchangeError):
    """Request to the exchange timed out."""


class ExchangeConnectionError(ExchangeError):
    """Network-level failure reaching the exchange."""


class OrderRejectedError(ExchangeError):
    """Exchange explicitly rejected an order (e.g. insufficient balance)."""


class InsufficientBalanceError(ExchangeError):
    """Not enough wallet balance to place the requested order."""

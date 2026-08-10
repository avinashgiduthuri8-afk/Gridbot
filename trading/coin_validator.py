"""Coin and pair validation for the DCA grid bot.

Provides a single ``CoinValidator`` class that:
- Checks whether a trading pair exists and is active on the exchange.
- Validates that an investment amount meets the exchange's minimum-order rules.
- Computes the expected quantity (using Decimal arithmetic) and explains
  any rejection reason in plain language.
"""

from __future__ import annotations

from dataclasses import dataclass

from exchange.base import ExchangeClient, MarketInfo
from exchange.exceptions import (
    ExchangeAuthError,
    ExchangeConnectionError,
    ExchangeError,
    ExchangeRateLimitError,
    ExchangeTimeoutError,
)
from grid.dca_engine import validate_order
from utils.logger import get_logger

# Errors that indicate a transient exchange problem, NOT a bad symbol
_TRANSIENT_ERRORS = (
    ExchangeConnectionError,
    ExchangeTimeoutError,
    ExchangeRateLimitError,
)

log = get_logger("trading")


@dataclass
class ValidationResult:
    """Outcome of a single investment-amount validation."""

    valid: bool
    reason: str = ""
    quantity: float = 0.0          # rounded, ready-to-trade quantity
    raw_quantity: float = 0.0      # before step-size rounding
    notional: float = 0.0          # quantity * price — the actual order value
    min_quantity: float = 0.0      # exchange minimum quantity
    min_notional: float = 0.0      # exchange minimum order value
    min_investment_inr: float = 0.0  # INR amount needed to satisfy every rule
    step_size: float = 0.0
    quantity_precision: int | None = None
    price_precision: int | None = None
    market_price: float = 0.0
    investment_inr: float = 0.0


class CoinValidator:
    """Validates trading pairs and investment amounts against exchange rules.

    All results are derived from live exchange data — no caching is done here
    (the exchange client may cache market info internally).
    """

    def __init__(self, exchange: ExchangeClient) -> None:
        self._exchange = exchange

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def validate_pair(self, symbol: str) -> tuple[bool, str]:
        """Check that *symbol* is a known, active trading pair.

        Returns:
            (True, "")          when the pair is valid and active.
            (False, reason_str) when invalid or inactive.
        """
        symbol = symbol.upper()
        try:
            info = await self._exchange.get_market_info(symbol)
        except _TRANSIENT_ERRORS as exc:
            # Operational failure — the exchange is unreachable, rate-limiting, etc.
            # Do NOT classify this as "invalid pair"; return a retry-oriented message.
            return False, (
                f"⚠️ Could not reach the exchange to validate <b>{symbol}</b> "
                f"({type(exc).__name__}: {exc}). "
                "Please try again in a moment."
            )
        except ExchangeAuthError as exc:
            return False, (
                f"⚠️ Authentication failed while looking up <b>{symbol}</b>. "
                "Check your CoinDCX API key and secret in the bot settings."
            )
        except ExchangeError as exc:
            # Plain ExchangeError from get_market_info means the symbol was not found
            # in the market details cache after a successful API call.
            return False, (
                f"❌ <b>{symbol}</b> is not a recognised trading pair on CoinDCX.\n"
                f"Check the symbol and try again."
            )
        except Exception as exc:  # noqa: BLE001
            return False, (
                f"⚠️ Unexpected error while looking up <b>{symbol}</b>: {exc}"
            )

        if not info.is_active:
            return False, (
                f"❌ <b>{symbol}</b> exists but is not currently active "
                f"(status: <code>{info.status}</code>).  "
                "Choose a different pair."
            )

        return True, ""

    async def validate_investment(
        self,
        symbol: str,
        inr_amount: float,
        price: float,
    ) -> ValidationResult:
        """Validate that *inr_amount* at *price* produces a tradeable, exchange-legal order.

        Delegates all math and rule-checking to ``grid.dca_engine.validate_order``
        — the SAME function the Trading Engine's ``calculate_quantity_for_inr``
        uses. This is intentional: CoinValidator and the Trading Engine must
        never independently decide whether an order is valid, or they can
        drift apart (as previously happened with the minimum-notional check).
        """
        symbol = symbol.upper()
        if price <= 0:
            return ValidationResult(
                valid=False,
                reason="Market price must be positive.",
                investment_inr=inr_amount,
                market_price=price,
            )

        try:
            info: MarketInfo = await self._exchange.get_market_info(symbol)
        except ExchangeError as exc:
            return ValidationResult(
                valid=False,
                reason=f"Could not fetch market info for {symbol}: {exc}",
                investment_inr=inr_amount,
                market_price=price,
            )

        order = validate_order(
            inr_amount,
            price,
            info.step_size,
            info.min_quantity,
            min_notional=info.min_amount,
            quantity_precision=info.target_currency_precision,
            price_precision=info.base_currency_precision,
            unit_label=info.target_currency_short_name or "coins",
        )

        log.debug(
            "coin_validator qty_audit symbol=%s market_price=%.8f investment_inr=%.4f "
            "raw_quantity=%.10f step_size=%s rounded_quantity=%.10f notional=%.4f "
            "min_quantity=%.10f min_notional=%.4f min_investment_inr=%.4f result=%s",
            symbol, price, inr_amount, order.raw_quantity, order.step_size,
            order.quantity, order.notional, order.min_quantity, order.min_notional,
            order.min_investment_inr, "OK" if order.valid else "FAIL",
        )

        return ValidationResult(
            valid=order.valid,
            reason=order.reason,
            quantity=order.quantity,
            raw_quantity=order.raw_quantity,
            notional=order.notional,
            min_quantity=order.min_quantity,
            min_notional=order.min_notional,
            min_investment_inr=order.min_investment_inr,
            step_size=order.step_size,
            quantity_precision=order.quantity_precision,
            price_precision=order.price_precision,
            market_price=price,
            investment_inr=inr_amount,
        )

    async def validate_grid_params(
        self,
        symbol: str,
        base_investment: float,
        dip_buy_amount: float,
        profit_sell_amount: float,
        price: float,
    ) -> tuple[bool, str]:
        """Validate all three investment amounts for a new grid configuration.

        Returns (True, "") when every amount passes.  On failure returns
        (False, human-readable explanation) for the first failing amount.
        """
        valid, reason = await self.validate_pair(symbol)
        if not valid:
            return False, reason

        checks = [
            ("Base investment", base_investment),
            ("Dip buy amount", dip_buy_amount),
            ("Profit sell amount", profit_sell_amount),
        ]
        for label, amount in checks:
            result = await self.validate_investment(symbol, amount, price)
            if not result.valid:
                return False, (
                    f"<b>{label}</b> (₹{amount:,.2f}) does not meet exchange rules:\n"
                    f"{result.reason}"
                )

        return True, ""

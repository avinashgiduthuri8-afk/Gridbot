"""Coin and pair validation for the DCA grid bot.

Provides a single ``CoinValidator`` class that:
- Checks whether a trading pair exists and is active on the exchange.
- Validates that an investment amount meets the exchange's minimum-order rules.
- Computes the expected quantity (using Decimal arithmetic) and explains
  any rejection reason in plain language.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal, ROUND_DOWN

from exchange.base import ExchangeClient, MarketInfo
from exchange.exceptions import (
    ExchangeAuthError,
    ExchangeConnectionError,
    ExchangeError,
    ExchangeRateLimitError,
    ExchangeTimeoutError,
)
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
    min_quantity: float = 0.0      # exchange minimum
    min_investment_inr: float = 0.0  # INR amount needed to meet min_quantity
    step_size: float = 0.0
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
        """Validate that *inr_amount* at *price* produces a tradeable quantity.

        Uses the same Decimal arithmetic as ``calculate_quantity_for_inr`` in
        ``grid/dca_engine.py`` so the result matches what the engine will
        actually attempt to place.
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

        step = info.step_size
        min_qty = info.min_quantity
        min_amt = info.min_amount

        d_inr = Decimal(str(inr_amount))
        d_price = Decimal(str(price))
        d_step = Decimal(str(step)) if step > 0 else Decimal(0)

        raw_qty = d_inr / d_price
        if d_step > 0:
            n_steps = int(raw_qty / d_step)
            quantity = n_steps * d_step
        else:
            quantity = raw_qty

        qty_float = float(quantity)
        raw_float = float(raw_qty)

        # Minimum INR amount required to meet min_quantity at this price
        min_investment = float(Decimal(str(min_qty)) * d_price) if min_qty > 0 else 0.0
        # Also respect the exchange's own min_amount floor
        min_investment = max(min_investment, min_amt)

        log.debug(
            "coin_validator qty_audit symbol=%s price=%.4f inr=%.4f "
            "raw=%.8f rounded=%.8f step=%s min_qty=%.8f result=%s",
            symbol, price, inr_amount, raw_float, qty_float,
            step, min_qty, "OK" if qty_float >= min_qty else "FAIL",
        )

        base_result = ValidationResult(
            valid=False,
            quantity=qty_float,
            raw_quantity=raw_float,
            min_quantity=min_qty,
            min_investment_inr=min_investment,
            step_size=step,
            market_price=price,
            investment_inr=inr_amount,
        )

        if qty_float <= 0 and inr_amount > 0:
            base_result.reason = (
                f"₹{inr_amount:,.2f} at ₹{price:,.2f} yields 0 quantity after "
                f"rounding to step size {step}. "
                f"Minimum investment required: ₹{min_investment:,.2f}."
            )
            return base_result

        if min_qty > 0 and qty_float < min_qty:
            base_result.reason = (
                f"₹{inr_amount:,.2f} at ₹{price:,.2f} yields {qty_float:.8f} {info.base_currency_short_name or 'coins'}, "
                f"below the exchange minimum of {min_qty} {info.base_currency_short_name or 'coins'}. "
                f"Minimum investment required: ₹{min_investment:,.2f}."
            )
            return base_result

        if min_amt > 0 and inr_amount < min_amt:
            base_result.reason = (
                f"₹{inr_amount:,.2f} is below the exchange's minimum order value "
                f"of ₹{min_amt:,.2f}."
            )
            return base_result

        base_result.valid = True
        return base_result

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

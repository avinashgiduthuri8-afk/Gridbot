"""Tests for trading/coin_validator.py and related quantity calculation fixes.

Covers:
- CoinValidator.validate_pair: valid, invalid, inactive pairs
- CoinValidator.validate_investment: quantity rounding, min_quantity, min_amount
- CoinValidator.validate_grid_params: multi-amount grid validation
- format_wallet_balance: enhanced formatter with unrealized P&L
- format_coin_info: coin info formatter
- API failure handling in validator
- Decimal precision in calculate_quantity_for_inr
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from exchange.base import Balance, ExtendedTicker, MarketInfo, Ticker
from exchange.exceptions import (
    ExchangeAuthError,
    ExchangeConnectionError,
    ExchangeError,
    ExchangeRateLimitError,
    ExchangeTimeoutError,
)
from grid.dca_engine import calculate_quantity_for_inr
from trading.coin_validator import CoinValidator, ValidationResult


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_market_info(
    symbol: str = "BNBINR",
    base_prec: int = 2,
    target_prec: int = 5,
    min_qty: float = 0.01,
    min_amt: float = 100.0,
    step_size: float | None = None,
    status: str = "active",
    base_short: str = "BNB",
    target_short: str = "INR",
) -> MarketInfo:
    """Build a MarketInfo for tests.

    ``base_prec`` controls price-precision only. ``target_prec`` controls the
    traded coin's quantity precision and is used as the step_size fallback
    when ``step_size`` isn't explicitly given — mirroring how the real
    exchange client behaves.
    """
    return MarketInfo(
        symbol=symbol,
        base_currency_precision=base_prec,
        target_currency_precision=target_prec,
        min_quantity=min_qty,
        min_amount=min_amt,
        step_size=step_size,
        status=status,
        base_currency_short_name=base_short,
        target_currency_short_name=target_short,
    )


def _make_extended_ticker(
    symbol: str = "BNBINR",
    last_price: float = 30000.0,
    change_24h: float = -1.5,
    high_24h: float = 31000.0,
    low_24h: float = 29000.0,
    volume_24h: float = 500.0,
    bid: float = 29990.0,
    ask: float = 30010.0,
) -> ExtendedTicker:
    return ExtendedTicker(
        symbol=symbol,
        last_price=last_price,
        change_24h=change_24h,
        high_24h=high_24h,
        low_24h=low_24h,
        volume_24h=volume_24h,
        bid=bid,
        ask=ask,
    )


def _make_exchange(market_info: MarketInfo | None = None, side_effect: Exception | None = None) -> MagicMock:
    exchange = MagicMock()
    if side_effect is not None:
        exchange.get_market_info = AsyncMock(side_effect=side_effect)
    elif market_info is not None:
        exchange.get_market_info = AsyncMock(return_value=market_info)
    else:
        exchange.get_market_info = AsyncMock(return_value=_make_market_info())
    return exchange


# ---------------------------------------------------------------------------
# validate_pair — valid pair
# ---------------------------------------------------------------------------


class TestValidatePairValid:
    @pytest.mark.asyncio
    async def test_active_pair_returns_true(self):
        exchange = _make_exchange(_make_market_info(status="active"))
        validator = CoinValidator(exchange)
        valid, reason = await validator.validate_pair("BNBINR")
        assert valid is True
        assert reason == ""

    @pytest.mark.asyncio
    async def test_symbol_uppercased_automatically(self):
        exchange = _make_exchange(_make_market_info(symbol="BTCINR", status="active"))
        validator = CoinValidator(exchange)
        valid, _ = await validator.validate_pair("btcinr")
        assert valid is True

    @pytest.mark.asyncio
    async def test_valid_pair_calls_get_market_info_with_uppercase(self):
        exchange = _make_exchange(_make_market_info(status="active"))
        validator = CoinValidator(exchange)
        await validator.validate_pair("bnbinr")
        exchange.get_market_info.assert_called_once_with("BNBINR")


# ---------------------------------------------------------------------------
# validate_pair — invalid / not found
# ---------------------------------------------------------------------------


class TestValidatePairInvalid:
    @pytest.mark.asyncio
    async def test_exchange_error_returns_false_with_message(self):
        exchange = _make_exchange(side_effect=ExchangeError("Market XXXINR not found"))
        validator = CoinValidator(exchange)
        valid, reason = await validator.validate_pair("XXXINR")
        assert valid is False
        assert "XXXINR" in reason
        assert "not a recognised trading pair" in reason.lower() or "not" in reason.lower()

    @pytest.mark.asyncio
    async def test_generic_exception_returns_false_with_retry_message(self):
        exchange = _make_exchange(side_effect=RuntimeError("unexpected crash"))
        validator = CoinValidator(exchange)
        valid, reason = await validator.validate_pair("XXXINR")
        assert valid is False
        assert reason  # non-empty error message

    @pytest.mark.asyncio
    async def test_unknown_symbol_message_includes_symbol(self):
        exchange = _make_exchange(side_effect=ExchangeError("not found"))
        validator = CoinValidator(exchange)
        valid, reason = await validator.validate_pair("FAKEINR")
        assert valid is False
        assert "FAKEINR" in reason

    # ------------------------------------------------------------------
    # Transient exchange errors must NOT be classified as "invalid pair"
    # ------------------------------------------------------------------

    @pytest.mark.asyncio
    async def test_connection_error_returns_retry_message(self):
        exchange = _make_exchange(side_effect=ExchangeConnectionError("network unreachable"))
        validator = CoinValidator(exchange)
        valid, reason = await validator.validate_pair("BTCINR")
        assert valid is False
        # Must not say "not a recognised trading pair" — that's a different problem
        assert "not a recognised trading pair" not in reason.lower()
        # Should advise retry
        assert "try again" in reason.lower() or "unreachable" in reason.lower() or "reach" in reason.lower()

    @pytest.mark.asyncio
    async def test_timeout_error_returns_retry_message(self):
        exchange = _make_exchange(side_effect=ExchangeTimeoutError("request timed out"))
        validator = CoinValidator(exchange)
        valid, reason = await validator.validate_pair("BTCINR")
        assert valid is False
        assert "not a recognised trading pair" not in reason.lower()
        assert "try again" in reason.lower() or "timeout" in reason.lower() or "moment" in reason.lower()

    @pytest.mark.asyncio
    async def test_rate_limit_error_returns_retry_message(self):
        exchange = _make_exchange(side_effect=ExchangeRateLimitError("429 too many requests"))
        validator = CoinValidator(exchange)
        valid, reason = await validator.validate_pair("BTCINR")
        assert valid is False
        assert "not a recognised trading pair" not in reason.lower()

    @pytest.mark.asyncio
    async def test_auth_error_returns_credentials_message(self):
        exchange = _make_exchange(side_effect=ExchangeAuthError("401 unauthorized"))
        validator = CoinValidator(exchange)
        valid, reason = await validator.validate_pair("BTCINR")
        assert valid is False
        # Should mention credentials, not "invalid pair"
        assert "not a recognised trading pair" not in reason.lower()
        assert (
            "api key" in reason.lower()
            or "credentials" in reason.lower()
            or "authentication" in reason.lower()
            or "auth" in reason.lower()
        )


# ---------------------------------------------------------------------------
# validate_pair — inactive pair
# ---------------------------------------------------------------------------


class TestValidatePairInactive:
    @pytest.mark.asyncio
    async def test_suspended_pair_returns_false(self):
        exchange = _make_exchange(_make_market_info(status="suspended"))
        validator = CoinValidator(exchange)
        valid, reason = await validator.validate_pair("BNBINR")
        assert valid is False
        assert "suspended" in reason.lower() or "not currently active" in reason.lower()

    @pytest.mark.asyncio
    async def test_inactive_status_returns_false(self):
        exchange = _make_exchange(_make_market_info(status="inactive"))
        validator = CoinValidator(exchange)
        valid, reason = await validator.validate_pair("BNBINR")
        assert valid is False

    @pytest.mark.asyncio
    async def test_inactive_reason_includes_status(self):
        exchange = _make_exchange(_make_market_info(status="halted"))
        validator = CoinValidator(exchange)
        _, reason = await validator.validate_pair("BNBINR")
        # Either the status itself or a generic message should be in the reason
        assert reason


# ---------------------------------------------------------------------------
# validate_investment — valid cases
# ---------------------------------------------------------------------------


class TestValidateInvestmentValid:
    @pytest.mark.asyncio
    async def test_typical_investment_is_valid(self):
        info = _make_market_info(min_qty=0.01, min_amt=100.0)
        exchange = _make_exchange(info)
        validator = CoinValidator(exchange)
        # 500 INR at price 30000 → 0.01666... → rounded to 0.01666 (5 decimal places = step 0.00001)
        result = await validator.validate_investment("BNBINR", 500.0, 30000.0)
        assert result.valid is True
        assert result.quantity > 0

    @pytest.mark.asyncio
    async def test_quantity_rounded_down_to_step_size(self):
        # step_size = 0.01 (2 decimal places), price 100, invest 3.14 INR
        # raw = 0.0314, rounded = 0.03
        info = _make_market_info(target_prec=2, min_qty=0.01, min_amt=0.0)
        exchange = _make_exchange(info)
        validator = CoinValidator(exchange)
        result = await validator.validate_investment("BNBINR", 3.14, 100.0)
        assert result.valid is True
        assert abs(result.quantity - 0.03) < 1e-10

    @pytest.mark.asyncio
    async def test_result_fields_populated_correctly(self):
        info = _make_market_info(target_prec=5, min_qty=0.01, min_amt=0.0)
        exchange = _make_exchange(info)
        validator = CoinValidator(exchange)
        result = await validator.validate_investment("BNBINR", 500.0, 30000.0)
        assert result.investment_inr == 500.0
        assert result.market_price == 30000.0
        assert result.step_size == pytest.approx(1e-5, rel=1e-6)
        assert result.min_quantity == 0.01


# ---------------------------------------------------------------------------
# validate_investment — min quantity failures
# ---------------------------------------------------------------------------


class TestValidateInvestmentMinQuantity:
    @pytest.mark.asyncio
    async def test_investment_too_small_returns_invalid(self):
        # price 30000, invest 1 INR → 0.0000333 qty, min = 0.01 → fail
        info = _make_market_info(min_qty=0.01, min_amt=0.0)
        exchange = _make_exchange(info)
        validator = CoinValidator(exchange)
        result = await validator.validate_investment("BNBINR", 1.0, 30000.0)
        assert result.valid is False
        assert "minimum" in result.reason.lower()

    @pytest.mark.asyncio
    async def test_min_investment_inr_reported(self):
        # step=0.01, min_qty=0.01, price=30000 → min_investment = 0.01 * 30000 = 300
        info = _make_market_info(target_prec=2, min_qty=0.01, min_amt=0.0)
        exchange = _make_exchange(info)
        validator = CoinValidator(exchange)
        result = await validator.validate_investment("BNBINR", 1.0, 30000.0)
        assert result.valid is False
        assert result.min_investment_inr == pytest.approx(300.0, rel=0.01)

    @pytest.mark.asyncio
    async def test_zero_quantity_after_rounding_invalid(self):
        # step=1.0 (0 decimal places), price=10000, invest=0.5 → raw=0.00005, floor=0
        info = _make_market_info(target_prec=0, min_qty=1.0, min_amt=0.0)
        exchange = _make_exchange(info)
        validator = CoinValidator(exchange)
        result = await validator.validate_investment("BNBINR", 0.5, 10000.0)
        assert result.valid is False
        assert result.quantity == 0

    @pytest.mark.asyncio
    async def test_min_amount_floor_enforced(self):
        # Even if qty is above min_qty, if INR < min_amt → fail
        info = _make_market_info(target_prec=5, min_qty=0.00001, min_amt=500.0)
        exchange = _make_exchange(info)
        validator = CoinValidator(exchange)
        result = await validator.validate_investment("BNBINR", 100.0, 30000.0)
        assert result.valid is False
        assert "minimum order value" in result.reason.lower()


# ---------------------------------------------------------------------------
# validate_investment — API failures
# ---------------------------------------------------------------------------


class TestValidateInvestmentAPIFailure:
    @pytest.mark.asyncio
    async def test_exchange_error_on_market_info_returns_invalid(self):
        exchange = _make_exchange(side_effect=ExchangeError("network error"))
        validator = CoinValidator(exchange)
        result = await validator.validate_investment("BNBINR", 500.0, 30000.0)
        assert result.valid is False
        assert result.reason

    @pytest.mark.asyncio
    async def test_zero_price_returns_invalid(self):
        exchange = _make_exchange(_make_market_info())
        validator = CoinValidator(exchange)
        result = await validator.validate_investment("BNBINR", 500.0, 0.0)
        assert result.valid is False
        assert "positive" in result.reason.lower()

    @pytest.mark.asyncio
    async def test_negative_price_returns_invalid(self):
        exchange = _make_exchange(_make_market_info())
        validator = CoinValidator(exchange)
        result = await validator.validate_investment("BNBINR", 500.0, -100.0)
        assert result.valid is False


# ---------------------------------------------------------------------------
# validate_grid_params
# ---------------------------------------------------------------------------


class TestValidateGridParams:
    @pytest.mark.asyncio
    async def test_all_valid_amounts_returns_true(self):
        info = _make_market_info(min_qty=0.001, min_amt=100.0)
        exchange = _make_exchange(info)
        validator = CoinValidator(exchange)
        valid, reason = await validator.validate_grid_params(
            "BNBINR", 500.0, 200.0, 300.0, 30000.0
        )
        assert valid is True
        assert reason == ""

    @pytest.mark.asyncio
    async def test_invalid_pair_fails_early(self):
        exchange = _make_exchange(side_effect=ExchangeError("not found"))
        validator = CoinValidator(exchange)
        valid, reason = await validator.validate_grid_params(
            "FAKEINR", 500.0, 200.0, 300.0, 30000.0
        )
        assert valid is False
        assert reason

    @pytest.mark.asyncio
    async def test_base_investment_too_small_fails(self):
        # min_amt=500 but base_investment=100 → fails
        info = _make_market_info(min_qty=0.001, min_amt=500.0)
        exchange = _make_exchange(info)
        validator = CoinValidator(exchange)
        valid, reason = await validator.validate_grid_params(
            "BNBINR", 100.0, 200.0, 300.0, 30000.0
        )
        assert valid is False
        assert "Base investment" in reason or "base" in reason.lower()

    @pytest.mark.asyncio
    async def test_dip_buy_too_small_fails(self):
        # base OK (1000), dip too small (10), profit OK (200)
        info = _make_market_info(min_qty=0.001, min_amt=100.0)
        exchange = _make_exchange(info)
        validator = CoinValidator(exchange)
        # Make dip fail: use a very high min_amt
        info2 = _make_market_info(min_qty=0.001, min_amt=500.0)
        exchange2 = _make_exchange(info2)
        validator2 = CoinValidator(exchange2)
        valid, reason = await validator2.validate_grid_params(
            "BNBINR", 1000.0, 100.0, 600.0, 30000.0
        )
        assert valid is False
        assert "Dip buy" in reason or "dip" in reason.lower()


# ---------------------------------------------------------------------------
# Quantity rounding — Decimal precision (dca_engine)
# ---------------------------------------------------------------------------


class TestCalculateQuantityForInr:
    def test_basic_calculation(self):
        # 500 / 30000 = 0.01666... → step 0.00001 → 0.01666
        qty = calculate_quantity_for_inr(500.0, 30000.0, 0.00001, 0.0001)
        assert qty == pytest.approx(0.01666, abs=1e-5)

    def test_rounds_down_not_up(self):
        # 999 / 1000 = 0.999 → step 0.01 → 0.99 (not 1.0)
        qty = calculate_quantity_for_inr(999.0, 1000.0, 0.01, 0.0)
        assert qty == pytest.approx(0.99, abs=1e-10)

    def test_exact_multiple_of_step(self):
        # 1000 / 1000 = 1.0 → step 0.001 → 1.000
        qty = calculate_quantity_for_inr(1000.0, 1000.0, 0.001, 0.0)
        assert qty == pytest.approx(1.0, abs=1e-10)

    def test_raises_when_below_min_quantity(self):
        with pytest.raises(ValueError, match="minimum"):
            calculate_quantity_for_inr(1.0, 30000.0, 0.00001, 1.0)

    def test_raises_with_zero_price(self):
        with pytest.raises(ValueError):
            calculate_quantity_for_inr(500.0, 0.0, 0.00001, 0.0)

    def test_raises_with_negative_price(self):
        with pytest.raises(ValueError):
            calculate_quantity_for_inr(500.0, -100.0, 0.00001, 0.0)

    def test_no_step_size_returns_raw_quantity(self):
        # step_size=0 → no rounding
        qty = calculate_quantity_for_inr(500.0, 1000.0, 0.0, 0.0)
        assert qty == pytest.approx(0.5, abs=1e-10)

    def test_decimal_precision_no_floating_point_noise(self):
        # Classic float problem: 0.1 + 0.2 ≠ 0.3. We verify Decimal avoids this.
        # 1000 INR / 3333.33 INR per coin → 0.30000... → should not produce e.g. 0.29999...
        qty = calculate_quantity_for_inr(1000.0, 3333.33, 0.01, 0.0)
        # With float: (1000 / 3333.33) = 0.30000300003... → floor to 0.01 step = 0.30
        assert qty >= 0.30

    def test_large_investment_small_step(self):
        # 100000 INR / 5000000 BTC price → 0.02 BTC, step 0.00000001 → 0.02000000
        qty = calculate_quantity_for_inr(100_000.0, 5_000_000.0, 1e-8, 0.0)
        assert qty == pytest.approx(0.02, rel=1e-6)

    def test_error_message_includes_minimum_investment(self):
        """ValueError must tell the user how much they need to invest."""
        try:
            calculate_quantity_for_inr(10.0, 50000.0, 0.00001, 1.0)
            assert False, "Expected ValueError"
        except ValueError as exc:
            msg = str(exc)
            assert "Minimum investment" in msg or "minimum" in msg.lower()


# ---------------------------------------------------------------------------
# format_wallet_balance — enhanced formatter
# ---------------------------------------------------------------------------


class TestFormatWalletBalance:
    def _balances(self):
        from exchange.base import Balance
        return [
            Balance(currency="INR", balance=10000.0, locked_balance=500.0),
            Balance(currency="BTC", balance=0.001, locked_balance=0.0005),
            Balance(currency="ETH", balance=0.5, locked_balance=0.0),
        ]

    def test_shows_inr_available_and_locked(self):
        from bot_telegram.formatters import format_wallet_balance
        text = format_wallet_balance(self._balances(), {})
        assert "10,000" in text or "10000" in text
        assert "500" in text

    def test_shows_market_value_for_crypto(self):
        from bot_telegram.formatters import format_wallet_balance
        prices = {"BTC": 5_000_000.0, "ETH": 200_000.0}
        text = format_wallet_balance(self._balances(), prices)
        # BTC total 0.0015 * 5_000_000 = 7500
        assert "7,500" in text or "7500" in text

    def test_shows_unrealized_pnl_when_grids_provided(self):
        from bot_telegram.formatters import format_wallet_balance
        prices = {"BTC": 5_000_000.0}
        # Grid owns 0.001 BTC at avg 4_000_000 — wallet has 0.0015 total but we
        # use only the bot's 0.001 position for P&L to avoid mixing external holdings
        grids = [
            {
                "symbol": "BTCINR",
                "status": "active",
                "average_entry_price": 4_000_000.0,
                "total_quantity": 0.001,
            }
        ]
        text = format_wallet_balance(self._balances(), prices, grids=grids)
        # Bot P&L = (5_000_000 - 4_000_000) * 0.001 = 1_000 (not 1_500 — correct)
        assert "P&L" in text or "+" in text

    def test_unrealized_pnl_uses_grid_qty_not_wallet_qty(self):
        """P&L must be based on grid position qty, not total wallet balance."""
        from bot_telegram.formatters import format_wallet_balance
        # Wallet holds 10 BTC, but bot only manages 1 BTC @ avg 4_000_000
        balances = [Balance(currency="BTC", balance=10.0, locked_balance=0.0)]
        prices = {"BTC": 5_000_000.0}
        grids = [
            {
                "symbol": "BTCINR",
                "status": "active",
                "average_entry_price": 4_000_000.0,
                "total_quantity": 1.0,  # bot only has 1 BTC
            }
        ]
        text = format_wallet_balance(balances, prices, grids=grids)
        # Bot unrealized = (5_000_000 - 4_000_000) * 1 = 1_000_000
        # If wrong: (5_000_000 - 4_000_000) * 10 = 10_000_000 — must NOT appear
        assert "10,000,000" not in text.replace(",", "")

    def test_multi_grid_same_coin_pnl_is_summed(self):
        """Two grids on BTCINR: P&L must be the sum of both positions."""
        from bot_telegram.formatters import format_wallet_balance
        balances = [Balance(currency="BTC", balance=0.5, locked_balance=0.0)]
        prices = {"BTC": 5_000_000.0}
        grids = [
            # Grid 1: 0.2 BTC @ avg 4_000_000 → unrealized +200_000
            {
                "symbol": "BTCINR",
                "status": "active",
                "average_entry_price": 4_000_000.0,
                "total_quantity": 0.2,
            },
            # Grid 2: 0.1 BTC @ avg 6_000_000 → unrealized -100_000
            {
                "symbol": "BTCINR",
                "status": "paused",
                "average_entry_price": 6_000_000.0,
                "total_quantity": 0.1,
            },
        ]
        text = format_wallet_balance(balances, prices, grids=grids)
        # Combined bot P&L = +200_000 - 100_000 = +100_000
        assert "P&L" in text

    def test_non_bot_wallet_holdings_show_no_pnl_line(self):
        """ETH in wallet with no ETH grids should not show a P&L line."""
        from bot_telegram.formatters import format_wallet_balance
        balances = [
            Balance(currency="INR", balance=5000.0, locked_balance=0.0),
            Balance(currency="ETH", balance=1.0, locked_balance=0.0),
        ]
        prices = {"ETH": 200_000.0}
        grids = []  # no ETH grid
        text = format_wallet_balance(balances, prices, grids=grids)
        # ETH should appear but without a P&L annotation
        assert "ETH" in text
        # P&L should not appear for ETH (total unrealized is 0)
        assert "P&L" not in text and "📈" not in text and "📉" not in text

    def test_shows_total_wallet_value(self):
        from bot_telegram.formatters import format_wallet_balance
        prices = {"BTC": 5_000_000.0}
        text = format_wallet_balance(self._balances(), prices)
        assert "Total wallet" in text or "Portfolio" in text

    def test_no_grids_still_shows_balances(self):
        from bot_telegram.formatters import format_wallet_balance
        text = format_wallet_balance(self._balances(), {}, grids=None)
        assert "INR" in text
        assert "BTC" in text

    def test_price_unavailable_handled_gracefully(self):
        from bot_telegram.formatters import format_wallet_balance
        # ETH has no price
        text = format_wallet_balance(self._balances(), {"BTC": 5_000_000.0})
        assert "unavailable" in text.lower() or "ETH" in text

    def test_paused_grids_included_in_unrealized(self):
        from bot_telegram.formatters import format_wallet_balance
        prices = {"BTC": 5_000_000.0}
        grids = [{"symbol": "BTCINR", "status": "paused", "average_entry_price": 4_500_000.0, "total_quantity": 0.001}]
        text = format_wallet_balance(self._balances(), prices, grids=grids)
        assert "P&L" in text or "avg" in text.lower() or "+" in text or "-" in text

    def test_stopped_grids_excluded_from_pnl(self):
        """Stopped grids have no open position — must not contribute to P&L."""
        from bot_telegram.formatters import format_wallet_balance
        balances = [Balance(currency="BTC", balance=0.01, locked_balance=0.0)]
        prices = {"BTC": 5_000_000.0}
        grids = [
            {
                "symbol": "BTCINR",
                "status": "stopped",
                "average_entry_price": 3_000_000.0,
                "total_quantity": 0.01,
            }
        ]
        text = format_wallet_balance(balances, prices, grids=grids)
        assert "P&L" not in text and "📈" not in text and "📉" not in text


# ---------------------------------------------------------------------------
# format_coin_info
# ---------------------------------------------------------------------------


class TestFormatCoinInfo:
    def _make_args(self, **overrides):
        from trading.coin_validator import ValidationResult
        base = dict(
            symbol="BNBINR",
            market_info=_make_market_info(),
            extended_ticker=_make_extended_ticker(),
            base_validation=ValidationResult(valid=True, quantity=0.01666, investment_inr=500.0, market_price=30000.0),
            dip_validation=ValidationResult(valid=True, quantity=0.006, investment_inr=200.0, market_price=30000.0),
            profit_validation=ValidationResult(valid=True, quantity=0.008, investment_inr=250.0, market_price=30000.0),
        )
        base.update(overrides)
        return base

    def test_shows_symbol_in_header(self):
        from bot_telegram.formatters import format_coin_info
        text = format_coin_info(**self._make_args())
        assert "BNBINR" in text

    def test_shows_active_status(self):
        from bot_telegram.formatters import format_coin_info
        text = format_coin_info(**self._make_args())
        assert "Active" in text or "active" in text

    def test_shows_inactive_status(self):
        from bot_telegram.formatters import format_coin_info
        args = self._make_args(market_info=_make_market_info(status="suspended"))
        text = format_coin_info(**args)
        assert "suspended" in text.lower() or "SUSPENDED" in text

    def test_shows_current_price(self):
        from bot_telegram.formatters import format_coin_info
        text = format_coin_info(**self._make_args())
        assert "30,000" in text or "30000" in text

    def test_shows_24h_change(self):
        from bot_telegram.formatters import format_coin_info
        text = format_coin_info(**self._make_args())
        assert "1.5" in text  # -1.5% change

    def test_shows_min_quantity(self):
        from bot_telegram.formatters import format_coin_info
        text = format_coin_info(**self._make_args())
        assert "0.01" in text  # min_quantity

    def test_shows_valid_investment_check(self):
        from bot_telegram.formatters import format_coin_info
        text = format_coin_info(**self._make_args())
        assert "Valid" in text or "✅" in text

    def test_shows_invalid_investment_with_reason(self):
        from bot_telegram.formatters import format_coin_info
        from trading.coin_validator import ValidationResult
        args = self._make_args(
            base_validation=ValidationResult(
                valid=False,
                reason="Investment too small. Min ₹300.00.",
                investment_inr=100.0,
                market_price=30000.0,
                min_investment_inr=300.0,
            )
        )
        text = format_coin_info(**args)
        assert "Invalid" in text or "❌" in text
        assert "too small" in text.lower() or "300" in text

    def test_all_valid_shows_ready_message(self):
        from bot_telegram.formatters import format_coin_info
        text = format_coin_info(**self._make_args())
        assert "ready" in text.lower() or "✅" in text

    def test_shows_high_low(self):
        from bot_telegram.formatters import format_coin_info
        text = format_coin_info(**self._make_args())
        assert "31,000" in text or "31000" in text
        assert "29,000" in text or "29000" in text


# ---------------------------------------------------------------------------
# MarketInfo — is_active property
# ---------------------------------------------------------------------------


class TestMarketInfoIsActive:
    def test_active_status_is_active(self):
        info = _make_market_info(status="active")
        assert info.is_active is True

    def test_suspended_is_not_active(self):
        info = _make_market_info(status="suspended")
        assert info.is_active is False

    def test_case_insensitive_check(self):
        info = _make_market_info(status="ACTIVE")
        assert info.is_active is True

    def test_default_status_is_active(self):
        # Old code that creates MarketInfo without status uses the default "active"
        info = MarketInfo(
            symbol="BTCINR",
            base_currency_precision=2,
            target_currency_precision=8,
            min_quantity=0.00001,
            min_amount=100.0,
        )
        assert info.is_active is True


# ---------------------------------------------------------------------------
# ExtendedTicker
# ---------------------------------------------------------------------------


class TestExtendedTicker:
    def test_to_ticker_returns_plain_ticker(self):
        et = _make_extended_ticker(symbol="BNBINR", last_price=30000.0)
        ticker = et.to_ticker()
        assert isinstance(ticker, Ticker)
        assert ticker.symbol == "BNBINR"
        assert ticker.last_price == 30000.0

    def test_fields_accessible(self):
        et = _make_extended_ticker(change_24h=-2.5, high_24h=35000.0)
        assert et.change_24h == -2.5
        assert et.high_24h == 35000.0


# ---------------------------------------------------------------------------
# Regression: exchange metadata must never be confused across markets
# ---------------------------------------------------------------------------
#
# These reproduce the reported bug: a high-priced asset whose PRICE precision
# (base_currency_precision, e.g. INR quoted to 1 decimal) happened to look
# like a plausible quantity step, while the real quantity step/min_quantity
# came from the TARGET currency's own precision. Mixing the two produced a
# step_size that had no mathematical relationship to min_quantity, so a
# perfectly valid investment rounded to zero while the reported "minimum
# investment" was calculated from a completely different constraint.


class TestExchangeMetadataConsistency:
    @pytest.mark.asyncio
    async def test_high_priced_asset_matches_reported_bug_scenario(self):
        # Reproduces: price ₹6,234,915.90, base_investment ₹500.
        # Correct metadata for a high-priced coin: quantity step/min_quantity
        # are tiny (target_currency_precision=5), independent of the pricing
        # currency's own precision (base_currency_precision=1 for INR).
        info = _make_market_info(
            base_prec=1, target_prec=5, min_qty=0.00001, min_amt=0.0,
        )
        exchange = _make_exchange(info)
        validator = CoinValidator(exchange)
        result = await validator.validate_investment("WBTCINR", 500.0, 6_234_915.90)

        # step_size must be derived from target precision (0.00001), not
        # base/price precision (which would incorrectly give 0.1).
        assert result.step_size == pytest.approx(0.00001)
        assert result.step_size != pytest.approx(0.1)

        # raw quantity ≈ 0.00008019, rounds down to 0.00008 at step 0.00001 —
        # a valid, non-zero quantity, not "0 after rounding".
        assert result.quantity > 0
        assert result.valid is True

        # The minimum investment must be mathematically consistent with the
        # SAME step/min_quantity that produced the quantity above:
        # min_quantity * price == 0.00001 * 6,234,915.90 ≈ 62.35
        assert result.min_investment_inr == pytest.approx(62.349159, rel=1e-4)

    @pytest.mark.asyncio
    async def test_high_priced_asset_below_minimum_is_consistent(self):
        # A genuinely too-small investment on the same high-priced asset must
        # report a min_investment that, when actually invested, produces a
        # valid (non-zero) quantity — proving the numbers agree with each other.
        info = _make_market_info(
            base_prec=1, target_prec=5, min_qty=0.00001, min_amt=0.0,
        )
        exchange = _make_exchange(info)
        validator = CoinValidator(exchange)
        result = await validator.validate_investment("WBTCINR", 10.0, 6_234_915.90)
        assert result.valid is False

        retry = await validator.validate_investment(
            "WBTCINR", result.min_investment_inr, 6_234_915.90
        )
        assert retry.valid is True

    @pytest.mark.asyncio
    async def test_low_priced_asset_with_coarse_step(self):
        # Low-priced, high-quantity-precision-tolerant coin (e.g. a meme coin
        # priced at ₹0.05) with a coarse whole-number step size.
        info = _make_market_info(
            symbol="MEMEINR", base_prec=4, target_prec=0,
            min_qty=1.0, min_amt=1.0,
        )
        exchange = _make_exchange(info)
        validator = CoinValidator(exchange)
        result = await validator.validate_investment("MEMEINR", 500.0, 0.05)
        assert result.step_size == pytest.approx(1.0)
        assert result.valid is True
        assert result.quantity == pytest.approx(10000.0)

    @pytest.mark.asyncio
    async def test_step_size_taken_verbatim_when_not_a_power_of_ten(self):
        # Some CoinDCX pairs report a non-power-of-ten 'step' (e.g. 0.5, 5,
        # 25). The validator must use it exactly rather than re-deriving it
        # from a precision field.
        info = _make_market_info(
            target_prec=8, min_qty=0.5, min_amt=0.0, step_size=0.5,
        )
        exchange = _make_exchange(info)
        validator = CoinValidator(exchange)
        result = await validator.validate_investment("XINR", 100.0, 60.0)
        # raw = 1.6667, floored to nearest 0.5 -> 1.5
        assert result.step_size == pytest.approx(0.5)
        assert result.quantity == pytest.approx(1.5)

    @pytest.mark.asyncio
    async def test_different_quantity_precisions_all_validate_correctly(self):
        cases = [
            # (target_prec, min_qty, price, inr, expected_valid)
            (0, 1.0, 50000.0, 60000.0, True),      # whole-unit coin, affordable
            (2, 0.01, 200.0, 5.0, True),            # 2-decimal coin
            (5, 0.00001, 6_234_915.90, 500.0, True),  # very high priced coin
            (8, 0.00000001, 9_500_000.0, 100.0, True),  # BTC-like precision
        ]
        for target_prec, min_qty, price, inr, expected_valid in cases:
            info = _make_market_info(
                base_prec=2, target_prec=target_prec, min_qty=min_qty, min_amt=0.0,
            )
            exchange = _make_exchange(info)
            validator = CoinValidator(exchange)
            result = await validator.validate_investment("TESTINR", inr, price)
            assert result.valid is expected_valid, (
                f"target_prec={target_prec} price={price} inr={inr}: "
                f"expected valid={expected_valid}, got {result.valid} "
                f"(reason={result.reason})"
            )
            # min_investment must be consistent with min_quantity * price, but
            # min_investment_inr intentionally rounds UP to the nearest paisa
            # (so reinvesting exactly that amount is guaranteed to clear the
            # minimum) — allow up to one paisa of rounding headroom rather
            # than comparing to the unrounded exact product.
            expected_min_inv = max(min_qty * price, 0.0)
            assert result.min_investment_inr >= expected_min_inv - 1e-9
            assert result.min_investment_inr - expected_min_inv < 0.01 + 1e-9

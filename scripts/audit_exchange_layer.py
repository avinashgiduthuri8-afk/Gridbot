"""Final Exchange Layer validation audit — run this against the LIVE CoinDCX API.

This script does not use fixtures or mocks. It instantiates the real
CoinDCXClient and CoinValidator used in production and calls the live
public endpoints (get_market_info / get_ticker), so the report reflects
exactly what the running bot would see and do.

Usage (from the grid-trading-bot/ directory, in an environment WITH
internet access — e.g. your Replit shell):

    python scripts/audit_exchange_layer.py

No API key/secret is required: get_market_info() and get_ticker() only
call CoinDCX's public, unauthenticated endpoints. Dummy credentials are
passed to satisfy the client constructor, but they are never used for
these calls.

Exit code is 0 if no discrepancies were found, 1 otherwise — safe to
wire into CI.
"""

from __future__ import annotations

import asyncio
import sys
from decimal import Decimal

sys.path.insert(0, ".")

from exchange.coindcx import CoinDCXClient  # noqa: E402
from trading.coin_validator import CoinValidator  # noqa: E402
from grid.dca_engine import (  # noqa: E402
    calculate_quantity_for_inr,
    calculate_next_buy_price,
    calculate_profit_target,
    clamp_sell_quantity,
    update_position_after_buy,
    update_position_after_sell,
)
from config.constants import DEFAULT_DIP_PERCENTAGE, DEFAULT_PROFIT_PERCENTAGE  # noqa: E402

SYMBOLS = ["BTCINR", "ETHINR", "BNBINR", "SOLINR", "DOGEINR"]
INVESTMENT_AMOUNTS = [100.0, 500.0, 1000.0]

# Fixed simulation parameters for the DCA cycle test (per the audit spec)
SIM_BASE_INVESTMENT = 500.0
SIM_DIP_BUY_AMOUNT = 100.0
SIM_PROFIT_SELL_AMOUNT = 120.0

DIVIDER = "-" * 78


def fmt(x: float, prec: int = 8) -> str:
    return f"{x:,.{prec}f}".rstrip("0").rstrip(".") if x else "0"


async def main() -> int:
    client = CoinDCXClient(api_key="unused", api_secret="unused")
    validator = CoinValidator(client)

    discrepancies: list[str] = []
    report_lines: list[str] = []

    def log(line: str = "") -> None:
        report_lines.append(line)
        print(line)

    log("=" * 78)
    log("EXCHANGE LAYER — LIVE VALIDATION AUDIT (CoinDCX)")
    log("=" * 78)

    for symbol in SYMBOLS:
        log(f"\n{DIVIDER}\n{symbol}\n{DIVIDER}")

        # --- 1. Validate the pair and pull metadata straight from the exchange ---
        valid, reason = await validator.validate_pair(symbol)
        if not valid:
            log(f"  ❌ Pair validation FAILED: {reason}")
            discrepancies.append(f"{symbol}: pair validation failed — {reason}")
            continue

        try:
            info = await client.get_market_info(symbol)
            ticker = await client.get_ticker(symbol)
        except Exception as exc:  # noqa: BLE001
            log(f"  ❌ Could not fetch live data: {exc}")
            discrepancies.append(f"{symbol}: live data fetch failed — {exc}")
            continue

        price = ticker.last_price

        log(f"  Current Market Price:     ₹{price:,.4f}")
        log(f"  Trading Status:           {info.status} ({'ACTIVE' if info.is_active else 'INACTIVE'})")
        log(f"  Step Size:                {fmt(info.step_size)}")
        log(f"  Minimum Quantity:         {fmt(info.min_quantity)}")
        log(f"  Minimum Order Value:      ₹{info.min_amount:,.4f}  (min_notional)")
        log(f"  Quantity Precision:       {info.target_currency_precision} decimals")
        log(f"  Price Precision:          {info.base_currency_precision} decimals")

        # --- Consistency checks on the metadata itself ---
        # Flag (don't hard-fail on) cases where step_size numerically coincides
        # with 10^-base_currency_precision (the pricing currency's precision)
        # while differing from 10^-target_currency_precision. This is the exact
        # shape of the original bug, but it CAN happen legitimately by
        # coincidence for some coins — so it's a manual-review flag, not an
        # automatic discrepancy.
        price_derived_step = 10 ** (-info.base_currency_precision)
        target_derived_step = 10 ** (-info.target_currency_precision)
        if (
            info.base_currency_precision != info.target_currency_precision
            and abs(info.step_size - price_derived_step) < 1e-15
            and abs(info.step_size - target_derived_step) > 1e-15
        ):
            log(
                f"  ⚠ REVIEW: step_size ({info.step_size}) numerically coincides with "
                f"10^-base_currency_precision ({price_derived_step}) rather than "
                f"target_currency_precision ({info.target_currency_precision}). This matches "
                f"the shape of the original bug — confirm against CoinDCX's raw 'step' field "
                f"for {symbol} before trusting it, though it may be a legitimate coincidence."
            )

        if abs(info.step_size - target_derived_step) > 1e-12:
            log(
                f"  ℹ note: step_size ({fmt(info.step_size)}) is NOT a plain power-of-ten "
                f"of target_currency_precision ({target_derived_step}) — this is valid on "
                f"CoinDCX (non-uniform steps exist) as long as it matches the exchange's "
                f"own 'step' field verbatim."
            )

        if info.min_quantity > 0 and info.step_size > 0:
            # min_quantity should be a whole multiple of step_size (within float tolerance)
            ratio = Decimal(str(info.min_quantity)) / Decimal(str(info.step_size))
            if abs(ratio - round(ratio)) > Decimal("0.0001"):
                discrepancies.append(
                    f"{symbol}: min_quantity ({info.min_quantity}) is not a clean multiple "
                    f"of step_size ({info.step_size}) — possible metadata mismatch."
                )

        # --- 3. Confirm /coininfo renders the SAME values as the raw metadata ---
        try:
            from bot_telegram.formatters import format_coin_info
            from config.constants import (
                DEFAULT_BASE_INVESTMENT,
                DEFAULT_DIP_BUY_AMOUNT,
                DEFAULT_PROFIT_SELL_AMOUNT,
            )

            ext_ticker = await client.get_extended_ticker(symbol)
            base_val = await validator.validate_investment(symbol, DEFAULT_BASE_INVESTMENT, price)
            dip_val = await validator.validate_investment(symbol, DEFAULT_DIP_BUY_AMOUNT, price)
            profit_val = await validator.validate_investment(symbol, DEFAULT_PROFIT_SELL_AMOUNT, price)
            coininfo_text = format_coin_info(
                symbol, info, ext_ticker, base_val, dip_val, profit_val
            )

            checks = {
                "step_size": f"{info.step_size:.8g}" in coininfo_text,
                "min_quantity": f"{info.min_quantity:.8g}" in coininfo_text,
                "min_amount": f"{info.min_amount:,.2f}" in coininfo_text,
                "target_currency_precision": str(info.target_currency_precision) in coininfo_text,
                "base_currency_precision": str(info.base_currency_precision) in coininfo_text,
            }
            failed_checks = [k for k, ok in checks.items() if not ok]
            if failed_checks:
                discrepancies.append(
                    f"{symbol}: /coininfo output does not match raw exchange metadata for: "
                    f"{', '.join(failed_checks)}"
                )
            else:
                log("  ✅ /coininfo output matches raw exchange metadata")
        except Exception as exc:  # noqa: BLE001
            discrepancies.append(f"{symbol}: could not render /coininfo for cross-check — {exc}")

        # --- 4. Investment amount tests ---
        log(f"\n  Investment validation @ ₹{price:,.4f}:")
        for amt in INVESTMENT_AMOUNTS:
            result = await validator.validate_investment(symbol, amt, price)
            status = "✅ VALID" if result.valid else "❌ INVALID"
            log(f"    ₹{amt:>7,.2f} -> raw_qty={fmt(result.raw_quantity)}  "
                f"rounded_qty={fmt(result.quantity)}  {status}")
            if not result.valid:
                log(f"              min_investment_required=₹{result.min_investment_inr:,.2f}")

            # Zero-quantity-when-should-be-valid check: if raw_quantity clearly
            # exceeds min_quantity but rounds to exactly zero, that's the bug class
            # from before — flag it.
            if result.raw_quantity >= info.min_quantity and result.quantity == 0:
                discrepancies.append(
                    f"{symbol} @ ₹{amt}: raw_quantity ({result.raw_quantity}) >= min_quantity "
                    f"({info.min_quantity}) but rounded quantity is 0 — quantity incorrectly "
                    f"rounded to zero."
                )

            # Mathematical consistency of the reported minimum investment
            if not result.valid and result.min_investment_inr > 0:
                retry = await validator.validate_investment(
                    symbol, result.min_investment_inr, price
                )
                if not retry.valid:
                    discrepancies.append(
                        f"{symbol}: reported min_investment_inr (₹{result.min_investment_inr:,.2f}) "
                        f"does NOT itself validate — inconsistent minimum-investment calculation."
                    )

        # --- 5. Live Test Order Simulation ---
        # Uses grid/dca_engine.py's calculate_quantity_for_inr — the EXACT
        # function the Trading Engine calls when it actually places an order
        # (see DCAManager.start_grid / _execute_dip_buy / _execute_profit_sell).
        # No order is placed; no account state is touched; this only exercises
        # the pure calculation function against live price + live metadata.
        log(f"\n  Live Test Order Simulation @ ₹{price:,.4f} (production dca_engine math):")
        for amt in INVESTMENT_AMOUNTS:
            d_raw = Decimal(str(amt)) / Decimal(str(price))
            raw_qty = float(d_raw)
            try:
                rounded_qty = calculate_quantity_for_inr(
                    amt, price, info.step_size, info.min_quantity,
                    min_notional=info.min_amount,
                    quantity_precision=info.target_currency_precision,
                    price_precision=info.base_currency_precision,
                )
                notional = rounded_qty * price
                log(
                    f"    ₹{amt:>7,.2f} | raw_qty={fmt(raw_qty)} | rounded_qty={fmt(rounded_qty)} | "
                    f"step={fmt(info.step_size)} | min_qty={fmt(info.min_quantity)} | "
                    f"min_notional=₹{info.min_amount:,.2f} | ✅ PASS"
                )
            except ValueError as exc:
                log(
                    f"    ₹{amt:>7,.2f} | raw_qty={fmt(raw_qty)} | step={fmt(info.step_size)} | "
                    f"min_qty={fmt(info.min_quantity)} | min_notional=₹{info.min_amount:,.2f} | "
                    f"❌ FAIL"
                )
                log(f"              reason: {exc}")
                # Cross-check: if dca_engine says FAIL but CoinValidator said VALID
                # for the same amount, the two production code paths disagree —
                # that is a genuine discrepancy, not an expected rejection.
                cv_result = await validator.validate_investment(symbol, amt, price)
                if cv_result.valid:
                    discrepancies.append(
                        f"{symbol} @ ₹{amt}: dca_engine.calculate_quantity_for_inr() FAILS "
                        f"('{exc}') but CoinValidator.validate_investment() says VALID for the "
                        f"same amount/price — the two production code paths disagree."
                    )

        # --- 6. DCA cycle simulation: Base -> Dip -> Profit (pure math, no orders) ---
        log(
            f"\n  DCA Cycle Simulation "
            f"(Base=₹{SIM_BASE_INVESTMENT:,.0f}, Dip=₹{SIM_DIP_BUY_AMOUNT:,.0f}, "
            f"Profit=₹{SIM_PROFIT_SELL_AMOUNT:,.0f}, "
            f"dip%={DEFAULT_DIP_PERCENTAGE}, profit%={DEFAULT_PROFIT_PERCENTAGE}):"
        )
        try:
            entry_price = price

            # Base buy — mirrors DCAManager.start_grid()
            base_qty = calculate_quantity_for_inr(
                SIM_BASE_INVESTMENT, entry_price, info.step_size, info.min_quantity,
                min_notional=info.min_amount,
                quantity_precision=info.target_currency_precision,
                price_precision=info.base_currency_precision,
            )
            base_notional = base_qty * entry_price
            if info.min_amount > 0 and base_notional < info.min_amount:
                raise ValueError(
                    f"base buy notional ₹{base_notional:,.2f} is below "
                    f"min_notional ₹{info.min_amount:,.2f}"
                )
            total_inv, total_qty, avg_entry = update_position_after_buy(
                0.0, 0.0, base_notional, base_qty
            )
            log(f"    Base Buy:    qty={fmt(base_qty)} @ ₹{entry_price:,.2f} "
                f"→ avg_entry=₹{avg_entry:,.4f}")

            # Dip buy — mirrors DCAManager._execute_dip_buy()
            dip_price = calculate_next_buy_price(entry_price, DEFAULT_DIP_PERCENTAGE)
            dip_qty = calculate_quantity_for_inr(
                SIM_DIP_BUY_AMOUNT, dip_price, info.step_size, info.min_quantity,
                min_notional=info.min_amount,
                quantity_precision=info.target_currency_precision,
                price_precision=info.base_currency_precision,
            )
            dip_notional = dip_qty * dip_price
            if info.min_amount > 0 and dip_notional < info.min_amount:
                raise ValueError(
                    f"dip buy notional ₹{dip_notional:,.2f} is below "
                    f"min_notional ₹{info.min_amount:,.2f}"
                )
            total_inv, total_qty, avg_entry = update_position_after_buy(
                total_inv, total_qty, dip_notional, dip_qty
            )
            log(f"    Dip Buy:     qty={fmt(dip_qty)} @ ₹{dip_price:,.2f} "
                f"(-{DEFAULT_DIP_PERCENTAGE:.1f}%) → avg_entry=₹{avg_entry:,.4f}")

            log(f"    Quantity Purchased (total):     {fmt(total_qty)}")
            log(f"    Weighted Average Entry Price (simulation):   ₹{avg_entry:,.4f}")

            # Profit sell — mirrors DCAManager._execute_profit_sell()
            profit_price = calculate_profit_target(avg_entry, DEFAULT_PROFIT_PERCENTAGE)
            desired_sell_qty = calculate_quantity_for_inr(
                SIM_PROFIT_SELL_AMOUNT, profit_price, info.step_size, info.min_quantity,
                min_notional=info.min_amount,
                quantity_precision=info.target_currency_precision,
                price_precision=info.base_currency_precision,
            )
            sell_qty = clamp_sell_quantity(desired_sell_qty, total_qty, info.step_size)
            if sell_qty <= 0:
                raise ValueError(
                    f"profit sell quantity clamps to 0 against current position "
                    f"({fmt(total_qty)} available)"
                )
            remaining_inv, remaining_qty, pnl, _ = update_position_after_sell(
                total_inv, total_qty, avg_entry, sell_qty, profit_price
            )

            log(f"    Profit Sell: qty={fmt(sell_qty)} @ ₹{profit_price:,.2f} "
                f"(+{DEFAULT_PROFIT_PERCENTAGE:.1f}%) → realized PnL=₹{pnl:,.2f}")
            log(f"    Estimated Profit Sell Quantity: {fmt(sell_qty)}")
            log(f"    Estimated Remaining Position:   {fmt(remaining_qty)} "
                f"(₹{remaining_inv:,.2f} cost basis)")

            # Sanity check: remaining quantity must be non-negative and consistent
            if remaining_qty < 0 or remaining_inv < 0:
                discrepancies.append(
                    f"{symbol}: DCA cycle simulation produced a negative remaining position "
                    f"(qty={remaining_qty}, cost_basis={remaining_inv})."
                )
            log("    ✅ DCA cycle simulation PASS")
        except ValueError as exc:
            log(f"    ❌ DCA cycle simulation FAIL — {exc}")
            discrepancies.append(f"{symbol}: DCA cycle simulation failed — {exc}")

    log(f"\n{'=' * 78}")
    log("SUMMARY")
    log("=" * 78)
    if discrepancies:
        log(f"Found {len(discrepancies)} issue(s):\n")
        for i, d in enumerate(discrepancies, 1):
            log(f"  {i}. {d}")
        log("")
        log("❌ Exchange Validation Failed")
    else:
        log("All pairs, investment amounts, and grid-cycle simulations were")
        log("internally consistent with live exchange metadata.")
        log("")
        log("✅ Exchange Validation Passed")

    await client.close()
    return 1 if discrepancies else 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))

"""ConversationHandler implementing the guided /newgrid DCA setup flow.

Entry menu: Default Grid (coin only, saved defaults) vs Custom Grid (full
guided setup, unchanged from before).

Custom Grid steps:
  SELECT_COIN → ENTRY_PRICE → BASE_INVESTMENT → DIP_BUY_AMOUNT → DIP_PERCENTAGE
  → PROFIT_SELL_AMOUNT → PROFIT_PERCENTAGE → MAX_LEVELS → STOP_LOSS
  → SELECT_MODE → CONFIRM

Default Grid steps:
  DEFAULT_COIN → [SELECT_MODE if no saved mode yet] → CONFIRM
"""

from __future__ import annotations

import warnings

from telegram import Update
from telegram.ext import (
    CallbackQueryHandler,
    ContextTypes,
    ConversationHandler,
    MessageHandler,
    filters,
)

from bot_telegram.keyboards import (
    coin_selection_keyboard,
    confirm_keyboard,
    grid_mode_choice_keyboard,
    trailing_choice_keyboard,
    trading_mode_keyboard,
)
from config.constants import (
    DEFAULT_DIP_PERCENTAGE,
    DEFAULT_MAX_LEVELS,
    DEFAULT_PROFIT_PERCENTAGE,
    DEFAULT_STOP_LOSS_PERCENTAGE,
    QUICK_GRID_DEFAULTS_SEED,
)
from utils.logger import get_logger

log = get_logger("telegram")

(
    GRID_SETUP_MODE,
    SELECT_COIN,
    CUSTOM_COIN,
    DEFAULT_COIN,
    ENTRY_PRICE,
    BASE_INVESTMENT,
    DIP_BUY_AMOUNT,
    DIP_PERCENTAGE,
    PROFIT_SELL_AMOUNT,
    PROFIT_PERCENTAGE,
    MAX_LEVELS,
    STOP_LOSS,
    TRAILING_CHOICE,
    TRAILING_PERCENTAGE,
    SELECT_MODE,
    CONFIRM,
) = range(16)


def build_newgrid_conversation(app_context: "BotAppContext") -> ConversationHandler:  # noqa: F821

    # ------------------------------------------------------------------
    # Guard
    # ------------------------------------------------------------------

    def _is_authorized(user_id: int) -> bool:
        return app_context.is_authorized(user_id)

    # ------------------------------------------------------------------
    # Step 0 — entry
    # ------------------------------------------------------------------

    async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        if not _is_authorized(update.effective_user.id):
            await update.message.reply_text("You are not authorized to use this bot.")
            return ConversationHandler.END
        context.user_data.clear()
        await update.message.reply_text(
            "🆕 <b>Create New Grid</b>\n\n"
            "1️⃣ <b>Default Grid</b> — just pick a coin, everything else uses "
            "your saved defaults (see /defaults)\n"
            "2️⃣ <b>Custom Grid</b> — full guided setup, choose every parameter",
            parse_mode="HTML",
            reply_markup=grid_mode_choice_keyboard(),
        )
        return GRID_SETUP_MODE

    async def grid_setup_mode_chosen(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        query = update.callback_query
        await query.answer()
        _, choice = query.data.split(":", 1)

        if choice == "custom":
            context.user_data["_source"] = "custom"
            await query.edit_message_text(
                "🚀 <b>New DCA Grid Setup (Custom)</b>\n\n"
                "Step 1 of 11: Select a coin to trade, or type a custom symbol.",
                parse_mode="HTML",
                reply_markup=coin_selection_keyboard(),
            )
            return SELECT_COIN

        # Default Grid path
        context.user_data["_source"] = "default"
        await query.edit_message_text(
            "⚡ <b>Default Grid</b>\n\n"
            "Type the coin symbol to trade (e.g. BTCINR, SHIBINR). "
            "Every other setting will use your saved defaults — see /defaults "
            "to view or change them.",
            parse_mode="HTML",
        )
        return DEFAULT_COIN

    # ------------------------------------------------------------------
    # Shared symbol validation (used by both Custom and Default coin entry)
    # ------------------------------------------------------------------

    async def _validate_symbol(symbol: str) -> tuple[bool, str]:
        """Validate a typed symbol exists and is tradeable on the exchange.
        Shared by custom_coin_entered and default_coin_entered so the two
        entry points can never drift out of sync on validation rules.
        """
        from trading.coin_validator import CoinValidator
        try:
            validator = CoinValidator(app_context.exchange)
            return await validator.validate_pair(symbol)
        except Exception as exc:  # noqa: BLE001
            log.warning("Symbol validation error for %s: %s", symbol, exc)
            return False, f"Could not reach the exchange: {exc}"

    # ------------------------------------------------------------------
    # Default Grid — coin entry, then straight to mode/confirm
    # ------------------------------------------------------------------

    async def default_coin_entered(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        from config.constants import SYMBOL_PATTERN
        symbol = update.message.text.strip().upper()
        if not SYMBOL_PATTERN.match(symbol):
            await update.message.reply_text(
                "Symbol must be letters/numbers only and end with INR "
                "(e.g. BTCINR). Please try again:"
            )
            return DEFAULT_COIN

        checking_msg = await update.message.reply_text(
            f"⏳ Checking <b>{symbol}</b> on exchange…", parse_mode="HTML"
        )
        valid, reason = await _validate_symbol(symbol)
        if not valid:
            await checking_msg.edit_text(
                f"❌ {reason}\n\nPlease enter a valid trading symbol (e.g. BTCINR):"
            )
            return DEFAULT_COIN
        try:
            await checking_msg.delete()
        except Exception:  # noqa: BLE001
            pass

        defaults = await app_context.repos.grid_defaults.get_or_seed(QUICK_GRID_DEFAULTS_SEED)
        context.user_data.update({
            "symbol": symbol,
            "entry_price": 0.0,  # market price
            "base_investment": defaults["base_investment"],
            "dip_buy_amount": defaults["dip_buy_amount"],
            "dip_percentage": defaults["dip_percentage"],
            "profit_sell_amount": defaults["profit_sell_amount"],
            "profit_percentage": defaults["profit_percentage"],
            "max_levels": defaults["max_levels"],
            "stop_loss_percentage": defaults["stop_loss_percentage"],
            # Default Grid stays intentionally simple (per spec) — trailing
            # take-profit is a Custom Grid-only opt-in for now.
            "trailing_enabled": False,
            "trailing_percentage": None,
        })

        saved_mode = defaults.get("last_mode")
        if saved_mode in ("paper", "real"):
            context.user_data["mode"] = saved_mode
            await update.message.reply_text(
                f"✅ Coin: <b>{symbol}</b>\n"
                f"Using saved mode: {'🟢 Paper Trade' if saved_mode == 'paper' else '🔴 Real Trade'} "
                f"(change anytime via /defaults)",
                parse_mode="HTML",
            )
            summary = _build_summary(context.user_data)
            await update.message.reply_text(summary, parse_mode="HTML", reply_markup=confirm_keyboard())
            return CONFIRM

        await update.message.reply_text(
            f"✅ Coin: <b>{symbol}</b>\n\n"
            "Choose your <b>trading mode</b>.\n\n"
            "🟢 <b>Paper Trade</b> — simulate orders with no real money.\n"
            "🔴 <b>Real Trade</b> — execute actual orders on CoinDCX.",
            parse_mode="HTML",
            reply_markup=trading_mode_keyboard(),
        )
        return SELECT_MODE

    # ------------------------------------------------------------------
    # Step 1 — coin (Custom Grid path)
    # ------------------------------------------------------------------

    async def coin_chosen(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        query = update.callback_query
        await query.answer()
        _, coin = query.data.split(":", 1)
        if coin == "custom":
            await query.edit_message_text(
                "Type the trading symbol (e.g. BTCINR, SHIBINR):"
            )
            return CUSTOM_COIN
        context.user_data["symbol"] = coin
        await query.edit_message_text(
            f"✅ Coin: <b>{coin}</b>\n\n"
            "Step 2 of 11: Enter the <b>entry price</b> in ₹.\n"
            "Type <code>0</code> or <code>market</code> to use the current market price.",
            parse_mode="HTML",
        )
        return ENTRY_PRICE

    async def custom_coin_entered(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        from config.constants import SYMBOL_PATTERN
        symbol = update.message.text.strip().upper()
        if not SYMBOL_PATTERN.match(symbol):
            await update.message.reply_text(
                "Symbol must be letters/numbers only and end with INR "
                "(e.g. BTCINR). Please try again:"
            )
            return CUSTOM_COIN

        # Validate the symbol exists on the exchange before accepting it so the
        # user learns immediately — not after filling in 8 more steps.
        from trading.coin_validator import CoinValidator
        checking_msg = await update.message.reply_text(
            f"⏳ Checking <b>{symbol}</b> on exchange…", parse_mode="HTML"
        )
        try:
            validator = CoinValidator(app_context.exchange)
            valid, reason = await validator.validate_pair(symbol)
        except Exception as exc:  # noqa: BLE001
            log.warning("Symbol validation error for %s: %s", symbol, exc)
            valid, reason = False, f"Could not reach the exchange: {exc}"

        if not valid:
            await checking_msg.edit_text(
                f"❌ {reason}\n\nPlease enter a valid trading symbol (e.g. BTCINR):"
            )
            return CUSTOM_COIN

        try:
            await checking_msg.delete()
        except Exception:  # noqa: BLE001
            pass  # message may have already been deleted or Telegram timed out
        context.user_data["symbol"] = symbol
        await update.message.reply_text(
            f"✅ Coin: <b>{symbol}</b>\n\n"
            "Step 2 of 11: Enter the <b>entry price</b> in ₹.\n"
            "Type <code>0</code> or <code>market</code> to use the current market price.",
            parse_mode="HTML",
        )
        return ENTRY_PRICE

    # ------------------------------------------------------------------
    # Step 2 — entry price
    # ------------------------------------------------------------------

    async def entry_price_entered(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        text = update.message.text.strip().lower().replace(",", "")
        if text in ("0", "market", "skip", "m"):
            context.user_data["entry_price"] = 0.0
            price_label = "market price"
        else:
            try:
                price = float(text)
                if price <= 0:
                    raise ValueError
                context.user_data["entry_price"] = price
                price_label = f"₹{price:,.2f}"
            except ValueError:
                await update.message.reply_text(
                    "Please enter a valid price (e.g. 54000), or type 0 for market price."
                )
                return ENTRY_PRICE
        await update.message.reply_text(
            f"✅ Entry price: <b>{price_label}</b>\n\n"
            "Step 3 of 11: Enter the <b>base investment</b> (INR) — "
            "the amount used for the <i>first</i> buy only.\n"
            "Example: <code>500</code>",
            parse_mode="HTML",
        )
        return BASE_INVESTMENT

    # ------------------------------------------------------------------
    # Step 3 — base investment
    # ------------------------------------------------------------------

    async def base_investment_entered(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        try:
            amount = float(update.message.text.strip().replace(",", ""))
            if amount <= 0:
                raise ValueError
            context.user_data["base_investment"] = amount
        except ValueError:
            await update.message.reply_text("Please enter a positive number. Example: 500")
            return BASE_INVESTMENT
        await update.message.reply_text(
            f"✅ Base investment: <b>₹{amount:,.2f}</b>\n\n"
            "Step 4 of 11: Enter the <b>dip buy amount</b> (INR) — "
            "used for every additional buy after a dip.\n"
            "Example: <code>100</code>",
            parse_mode="HTML",
        )
        return DIP_BUY_AMOUNT

    # ------------------------------------------------------------------
    # Step 4 — dip buy amount
    # ------------------------------------------------------------------

    async def dip_buy_amount_entered(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        try:
            amount = float(update.message.text.strip().replace(",", ""))
            if amount <= 0:
                raise ValueError
            context.user_data["dip_buy_amount"] = amount
        except ValueError:
            await update.message.reply_text("Please enter a positive number. Example: 100")
            return DIP_BUY_AMOUNT
        await update.message.reply_text(
            f"✅ Dip buy amount: <b>₹{amount:,.2f}</b>\n\n"
            "Step 5 of 11: Enter the <b>dip percentage</b> — how far the price must "
            "fall from the previous buy before triggering the next buy.\n"
            f"Example: <code>{DEFAULT_DIP_PERCENTAGE}</code> (means 5%)",
            parse_mode="HTML",
        )
        return DIP_PERCENTAGE

    # ------------------------------------------------------------------
    # Step 5 — dip percentage
    # ------------------------------------------------------------------

    async def dip_percentage_entered(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        try:
            pct = float(update.message.text.strip().replace("%", ""))
            if not (0.1 <= pct <= 50):
                raise ValueError
            context.user_data["dip_percentage"] = pct
        except ValueError:
            await update.message.reply_text("Please enter a percentage between 0.1 and 50. Example: 5")
            return DIP_PERCENTAGE
        await update.message.reply_text(
            f"✅ Dip %: <b>{pct}%</b>\n\n"
            "Step 6 of 11: Enter the <b>profit sell amount</b> (INR) — "
            "how much to sell each time the profit target is hit.\n"
            "Example: <code>150</code>",
            parse_mode="HTML",
        )
        return PROFIT_SELL_AMOUNT

    # ------------------------------------------------------------------
    # Step 6 — profit sell amount
    # ------------------------------------------------------------------

    async def profit_sell_amount_entered(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        try:
            amount = float(update.message.text.strip().replace(",", ""))
            if amount <= 0:
                raise ValueError
            context.user_data["profit_sell_amount"] = amount
        except ValueError:
            await update.message.reply_text("Please enter a positive number. Example: 150")
            return PROFIT_SELL_AMOUNT
        await update.message.reply_text(
            f"✅ Profit sell amount: <b>₹{amount:,.2f}</b>\n\n"
            "Step 7 of 11: Enter the <b>profit percentage</b> — "
            "sell when the price reaches (average entry + this %).\n"
            f"Example: <code>{DEFAULT_PROFIT_PERCENTAGE}</code> (means 7%)",
            parse_mode="HTML",
        )
        return PROFIT_PERCENTAGE

    # ------------------------------------------------------------------
    # Step 7 — profit percentage
    # ------------------------------------------------------------------

    async def profit_percentage_entered(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        try:
            pct = float(update.message.text.strip().replace("%", ""))
            if not (0.1 <= pct <= 100):
                raise ValueError
            context.user_data["profit_percentage"] = pct
        except ValueError:
            await update.message.reply_text("Please enter a percentage between 0.1 and 100. Example: 7")
            return PROFIT_PERCENTAGE
        await update.message.reply_text(
            f"✅ Profit %: <b>{pct}%</b>\n\n"
            "Step 8 of 11: Enter the <b>maximum grid levels</b> — "
            "the bot will not buy more than this many times.\n"
            f"Example: <code>{DEFAULT_MAX_LEVELS}</code>",
            parse_mode="HTML",
        )
        return MAX_LEVELS

    # ------------------------------------------------------------------
    # Step 8 — max levels
    # ------------------------------------------------------------------

    async def max_levels_entered(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        try:
            levels = int(update.message.text.strip())
            if not (1 <= levels <= 100):
                raise ValueError
            context.user_data["max_levels"] = levels
        except ValueError:
            await update.message.reply_text("Please enter a whole number between 1 and 100. Example: 10")
            return MAX_LEVELS
        await update.message.reply_text(
            f"✅ Max levels: <b>{levels}</b>\n\n"
            "Step 9 of 11: Enter the <b>stop loss percentage</b> — "
            "close the position if the price falls this far below the average entry.\n"
            f"Example: <code>{DEFAULT_STOP_LOSS_PERCENTAGE}</code> (means 50%)",
            parse_mode="HTML",
        )
        return STOP_LOSS

    # ------------------------------------------------------------------
    # Step 9 — stop loss
    # ------------------------------------------------------------------

    async def stop_loss_entered(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        try:
            pct = float(update.message.text.strip().replace("%", ""))
            if not (1 <= pct <= 99):
                raise ValueError
            context.user_data["stop_loss_percentage"] = pct
        except ValueError:
            await update.message.reply_text(
                "Please enter a stop loss between 1 and 99. Example: 50"
            )
            return STOP_LOSS

        await update.message.reply_text(
            "Step 10 of 11: <b>Trailing take-profit</b> (optional)\n\n"
            "Instead of selling a fixed amount the instant your profit target "
            "is hit, trailing keeps tracking the price upward and only sells "
            "once it pulls back a set % from the highest point reached — "
            "captures more of a strong upward move.\n\n"
            "Skip this to use your fixed profit percentage as-is.",
            parse_mode="HTML",
            reply_markup=trailing_choice_keyboard(),
        )
        return TRAILING_CHOICE

    # ------------------------------------------------------------------
    # Step 10 — trailing take-profit (optional)
    # ------------------------------------------------------------------

    async def trailing_choice_selected(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        query = update.callback_query
        await query.answer()
        _, choice = query.data.split(":", 1)

        if choice == "no":
            context.user_data["trailing_enabled"] = False
            context.user_data["trailing_percentage"] = None
            await query.edit_message_text(
                "Step 11 of 11: Choose your <b>trading mode</b>.\n\n"
                "🟢 <b>Paper Trade</b> — simulate orders with no real money. "
                "Great for testing your strategy safely.\n\n"
                "🔴 <b>Real Trade</b> — execute actual orders on CoinDCX.",
                parse_mode="HTML",
                reply_markup=trading_mode_keyboard(),
            )
            return SELECT_MODE

        await query.edit_message_text(
            "Enter the trailing pullback percentage (1-50).\n"
            "Example: <code>2</code> means sell once price drops 2% from its peak "
            "after your profit target was first reached.",
            parse_mode="HTML",
        )
        return TRAILING_PERCENTAGE

    async def trailing_percentage_entered(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        try:
            pct = float(update.message.text.strip().replace("%", ""))
            if not (0 < pct <= 50):
                raise ValueError
            context.user_data["trailing_enabled"] = True
            context.user_data["trailing_percentage"] = pct
        except ValueError:
            await update.message.reply_text(
                "Please enter a trailing percentage between 0 and 50. Example: 2"
            )
            return TRAILING_PERCENTAGE

        await update.message.reply_text(
            "Step 11 of 11: Choose your <b>trading mode</b>.\n\n"
            "🟢 <b>Paper Trade</b> — simulate orders with no real money. "
            "Great for testing your strategy safely.\n\n"
            "🔴 <b>Real Trade</b> — execute actual orders on CoinDCX.",
            parse_mode="HTML",
            reply_markup=trading_mode_keyboard(),
        )
        return SELECT_MODE

    # ------------------------------------------------------------------
    # Step 10 — mode selection
    # ------------------------------------------------------------------

    def _build_summary(d: dict) -> str:
        """Shared by mode_selected (Custom Grid) and default_coin_entered
        (Default Grid, when a saved mode already exists) so both paths
        produce an identical confirmation screen from the same user_data
        shape."""
        mode_label = "🟢 Paper Trade" if d.get("mode") == "paper" else "🔴 Real Trade"
        price_label = f"₹{d['entry_price']:,.2f}" if d["entry_price"] > 0 else "market price"
        total_possible = d["base_investment"] + d["dip_buy_amount"] * (d["max_levels"] - 1)
        trailing_line = (
            f"Trailing take-profit: {d['trailing_percentage']}% pullback\n"
            if d.get("trailing_enabled") else ""
        )
        return (
            "<b>📋 DCA Grid Summary</b>\n\n"
            f"Coin: <b>{d['symbol']}</b>\n"
            f"Entry price: {price_label}\n"
            f"Mode: {mode_label}\n"
            f"─────────────────────\n"
            f"Base investment:    ₹{d['base_investment']:,.2f}\n"
            f"Dip buy amount:     ₹{d['dip_buy_amount']:,.2f}\n"
            f"Dip percentage:     {d['dip_percentage']}%\n"
            f"─────────────────────\n"
            f"Profit sell amount: ₹{d['profit_sell_amount']:,.2f}\n"
            f"Profit percentage:  {d['profit_percentage']}%\n"
            f"{trailing_line}"
            f"─────────────────────\n"
            f"Max grid levels:    {d['max_levels']}\n"
            f"Stop loss:          {d['stop_loss_percentage']}%\n"
            f"─────────────────────\n"
            f"Max possible capital: ₹{total_possible:,.2f}\n\n"
            "Confirm to start this DCA grid?"
        )

    async def mode_selected(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        query = update.callback_query
        await query.answer()
        _, mode = query.data.split(":", 1)
        context.user_data["mode"] = mode
        summary = _build_summary(context.user_data)
        await query.edit_message_text(summary, parse_mode="HTML", reply_markup=confirm_keyboard())
        return CONFIRM

    # ------------------------------------------------------------------
    # Confirm
    # ------------------------------------------------------------------

    async def confirm(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        query = update.callback_query
        await query.answer()
        _, choice = query.data.split(":", 1)
        if choice == "no":
            await query.edit_message_text("❌ Grid creation cancelled.")
            return ConversationHandler.END

        d = context.user_data
        symbol: str = d.get("symbol", "")

        # ------------------------------------------------------------------
        # Pre-flight validation: pair + investment amounts
        # ------------------------------------------------------------------
        await query.edit_message_text("⏳ Validating pair and investment rules…")

        from trading.coin_validator import CoinValidator
        from exchange.exceptions import ExchangeError

        validator = CoinValidator(app_context.exchange)

        # 1. Pair validation
        try:
            valid_pair, pair_reason = await validator.validate_pair(symbol)
        except Exception as exc:  # noqa: BLE001
            log.warning("Pair validation error for %s: %s", symbol, exc)
            valid_pair, pair_reason = False, f"Could not validate pair {symbol}: {exc}"

        if not valid_pair:
            await query.edit_message_text(
                f"{pair_reason}\n\nUse /newgrid to start over.",
                parse_mode="HTML",
            )
            return ConversationHandler.END

        # 2. Resolve the price we'll validate against
        entry_price: float = float(d.get("entry_price", 0))
        if entry_price <= 0:
            try:
                ticker = await app_context.exchange.get_ticker(symbol)
                entry_price = ticker.last_price
            except ExchangeError as exc:
                await query.edit_message_text(
                    f"❌ Could not fetch current price for {symbol}: {exc}\n\nUse /newgrid to try again."
                )
                return ConversationHandler.END

        # 3. Investment amount validation
        checks = [
            ("Base investment", float(d.get("base_investment", 0))),
            ("Dip buy amount", float(d.get("dip_buy_amount", 0))),
            ("Profit sell amount", float(d.get("profit_sell_amount", 0))),
        ]
        for label, amount in checks:
            try:
                result = await validator.validate_investment(symbol, amount, entry_price)
            except Exception as exc:  # noqa: BLE001
                await query.edit_message_text(
                    f"❌ Could not validate {label}: {exc}\n\nUse /newgrid to start over."
                )
                return ConversationHandler.END

            if not result.valid:
                is_default = d.get("_source") == "default"
                hint = (
                    "\n\nUse /defaults to update your saved default amounts, "
                    "then try /newgrid again."
                    if is_default else
                    "\n\nUse /newgrid to start over with a larger amount."
                )
                await query.edit_message_text(
                    f"❌ <b>{label}</b> (₹{amount:,.2f}) does not meet exchange rules:\n\n"
                    f"{result.reason}"
                    f"{hint}",
                    parse_mode="HTML",
                )
                return ConversationHandler.END

        # ------------------------------------------------------------------
        # All checks passed — start the grid
        # ------------------------------------------------------------------
        await query.edit_message_text("⏳ Starting grid… please wait.")
        try:
            grid_id = await app_context.dca_manager.start_grid(context.user_data)
        except Exception as exc:  # noqa: BLE001
            log.exception("Error starting DCA grid")
            await query.edit_message_text(f"❌ Could not start grid: {exc}")
            return ConversationHandler.END

        # Grid created — persist mode choice for Default Grid before replying
        # (failure here is non-fatal and must not produce a false error message)
        if d.get("_source") == "default":
            try:
                await app_context.repos.grid_defaults.update(last_mode=d.get("mode"))
            except Exception:  # noqa: BLE001
                log.warning("Could not persist last_mode after grid start", exc_info=True)

        await query.edit_message_text(
            f"✅ <b>DCA Grid Started!</b>\n\n"
            f"Coin: <b>{symbol}</b>\n"
            f"Grid ID: <code>{grid_id}</code>\n\n"
            "Initial buy order placed. The bot will monitor price and execute "
            "dip buys and profit sells automatically.\n\n"
            "Use /grids to see status, or /stopgrid to stop.",
            parse_mode="HTML",
        )
        return ConversationHandler.END


    # ------------------------------------------------------------------
    # Cancel
    # ------------------------------------------------------------------

    async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        await update.message.reply_text("❌ Grid setup cancelled.")
        return ConversationHandler.END

    # ------------------------------------------------------------------
    # Build handler
    # ------------------------------------------------------------------

    # Suppress PTB's informational warning about per_message=False.
    # per_message=False is correct here: this conversation mixes
    # MessageHandler (entry_points, fallbacks, text-input states) with
    # CallbackQueryHandler (inline-button states).  Setting per_message=True
    # would require ALL handlers to be CallbackQueryHandler, which would
    # break the flow.
    with warnings.catch_warnings():
        warnings.filterwarnings(
            "ignore",
            message="If 'per_message=False'",
            category=UserWarning,
        )
        return ConversationHandler(
            entry_points=[MessageHandler(filters.Regex(r"^/newgrid$"), start)],
            states={
                GRID_SETUP_MODE: [CallbackQueryHandler(grid_setup_mode_chosen, pattern="^grid_setup_mode:")],
                DEFAULT_COIN: [MessageHandler(filters.TEXT & ~filters.COMMAND, default_coin_entered)],
                SELECT_COIN: [CallbackQueryHandler(coin_chosen, pattern="^pick_coin:")],
                CUSTOM_COIN: [MessageHandler(filters.TEXT & ~filters.COMMAND, custom_coin_entered)],
                ENTRY_PRICE: [MessageHandler(filters.TEXT & ~filters.COMMAND, entry_price_entered)],
                BASE_INVESTMENT: [MessageHandler(filters.TEXT & ~filters.COMMAND, base_investment_entered)],
                DIP_BUY_AMOUNT: [MessageHandler(filters.TEXT & ~filters.COMMAND, dip_buy_amount_entered)],
                DIP_PERCENTAGE: [MessageHandler(filters.TEXT & ~filters.COMMAND, dip_percentage_entered)],
                PROFIT_SELL_AMOUNT: [MessageHandler(filters.TEXT & ~filters.COMMAND, profit_sell_amount_entered)],
                PROFIT_PERCENTAGE: [MessageHandler(filters.TEXT & ~filters.COMMAND, profit_percentage_entered)],
                MAX_LEVELS: [MessageHandler(filters.TEXT & ~filters.COMMAND, max_levels_entered)],
                STOP_LOSS: [MessageHandler(filters.TEXT & ~filters.COMMAND, stop_loss_entered)],
                TRAILING_CHOICE: [CallbackQueryHandler(trailing_choice_selected, pattern="^trailing_choice:")],
                TRAILING_PERCENTAGE: [MessageHandler(filters.TEXT & ~filters.COMMAND, trailing_percentage_entered)],
                SELECT_MODE: [CallbackQueryHandler(mode_selected, pattern="^pick_mode:")],
                CONFIRM: [CallbackQueryHandler(confirm, pattern="^confirm_grid:")],
            },
            fallbacks=[MessageHandler(filters.Regex(r"^/cancel$"), cancel)],
            name="newgrid_conversation",
            persistent=False,
        )

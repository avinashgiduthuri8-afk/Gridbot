---
name: Coin Validator & MarketInfo
description: Architecture of the coin/pair validation layer and MarketInfo extensions added in Prompt 3.
---

## Rule
`CoinValidator` is the single place for pair validation and investment validation. It is imported lazily (inside handler/conversation functions) to avoid circular imports at module load time.

**Why:** This keeps the bot_telegram layer free of exchange-level details, and lets validators be tested in pure Python without Telegram deps.

## MarketInfo extensions
`MarketInfo` gained three optional fields with defaults so old code creating it without them still works:
- `status: str = "active"` — populated from CoinDCX markets_details response
- `base_currency_short_name: str = ""`
- `target_currency_short_name: str = ""`
- `is_active: bool` — property: `status.lower() == "active"`

**How to apply:** Any code that creates MarketInfo manually (tests, mocks) can omit the new fields safely. CoinDCXClient._load_market_details now populates all three.

## Decimal quantity calculation
`calculate_quantity_for_inr` in `grid/dca_engine.py` uses `Decimal(str(value))` for all arithmetic, avoiding floating-point rounding that could truncate valid quantities to zero.

The ValueError message now includes "Minimum investment required: ₹X.XX" so the UI can display it directly.

## format_wallet_balance signature change
`format_wallet_balance(balances, prices, grids=None)` — new optional `grids` parameter.
When grids are passed, unrealized P&L is computed per currency from the weighted average entry prices in active/paused grids.

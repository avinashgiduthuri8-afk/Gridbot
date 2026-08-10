---
name: Grid Validation Flow
description: How /newgrid validates pair and investment amounts before creating a grid.
---

## Rule
`conversations.py confirm()` runs a pre-flight check before calling `dca_manager.start_grid()`:
1. Validate the trading pair (CoinValidator.validate_pair)
2. Resolve the current market price if entry_price == 0
3. Validate base_investment, dip_buy_amount, profit_sell_amount at that price

If any check fails, the conversation ends with a clear error message and the grid is NOT created.

**Why:** start_grid() would also raise on invalid params, but the error messages are less user-friendly and the grid record may already be persisted when the order fails.

## How to apply
When adding new grid parameters (e.g. a second profit target), add them to the checks list in confirm(). The pattern is: `("Label", float(d.get("param", 0)))`.

# Task 3 Validation Regression Report

**Date:** 2026-07-09  
**Scope:** Shared-validation integration across all DCA buy/sell paths  
**Result:** ✅ PASS — 335 / 335 tests pass (35 new + 300 pre-existing)

---

## 1. Validation Coverage Audit

All implemented order paths were audited against the shared validator in `grid/dca_engine.py`.

| Path | Validated via | Validator location |
|---|---|---|
| Base buy (`start_grid`) | `calculate_quantity_for_inr()` with full params | Before `place_dca_order` |
| Dip buy (`_execute_dip_buy`) | `calculate_quantity_for_inr()` with full params | Before `place_dca_order` |
| Profit sell (`_execute_profit_sell`) | `calculate_quantity_for_inr()` → `clamp_sell_quantity()` → `validate_quantity()` | After clamp, before `place_dca_order` |
| Stop-loss sell (`_execute_stop_loss`) | `clamp_sell_quantity()` → `validate_quantity()` | After clamp; dust → write-off + notification |

**Conclusion:** No order reaches `OrderManager.place_dca_order()` without passing the shared rule engine. The shared `_check_exchange_rules()` function is the single decision point for both buy-path (`validate_order`) and sell-path (`validate_quantity`), so buys and sells can never disagree about what is exchange-legal.

---

## 2. New Regression Test File

**File:** `tests/test_validation_regression.py`  
**Tests added:** 35 (in 8 test classes)

### Class breakdown

| Class | Tests | What is covered |
|---|---|---|
| `TestBaseBuyValidation` | 3 | Valid 500 INR buy; qty < min_quantity raises, no order; notional < min_amount raises, no order |
| `TestDipBuyValidation` | 3 | Valid dip buy placed; 1 INR (qty too small) caught, no order; grid stays ACTIVE on failure |
| `TestProfitSellValidation` | 5 | Valid sell placed; step_size respected; dust blocks with order_failed; min-notional blocks after clamp; large desired qty clamped to holding |
| `TestStopLossValidation` | 8 | Valid sell placed; dust: no order, STOPPED, error notif, holdings zeroed; min-notional breach: no order, STOPPED, error notif; success: stop_loss_triggered notif, holdings zeroed |
| `TestClampedBelowMinimum` | 3 | Profit sell: large desired→dust after clamp; stop-loss: dust; profit sell: clamp to min-notional failure |
| `TestFullPositionExit` | 3 | Multi-level: one sell placed; sell qty ≤ total_qty; DB zeroed and STOPPED |
| `TestPaperModeValidationParity` | 7 | Paper valid buy; paper invalid buy (ValueError); paper dust stop-loss write-off; paper valid stop-loss; paper profit sell dust; paper valid dip buy; paper invalid dip buy |
| `TestRecoveryDoesNotPlaceOrders` | 3 | Offline fill reconciled, no new order; PENDING with no exchange_id → FAILED, no order; 3-grid multi-fill recovery, no orders |

### Key invariants tested

1. **Gate invariant**: `len(mock_exchange.orders_placed)` is compared before and after each failure path — always unchanged.
2. **Notification correctness**: `order_failed` vs `error` vs `stop_loss_triggered` are tested to fire only in the right cases.
3. **DB state correctness**: `total_quantity`, `total_investment`, and `status` are checked post-trigger.
4. **Step-size alignment**: One test asserts the placed quantity is an exact multiple of `step_size`.
5. **Clamp ceiling**: One test asserts the placed quantity never exceeds `total_quantity`.

---

## 3. conftest.py Patch

Added `market_info_override: MarketInfo | None = None` to `MockExchange.__init__` and an early-return in `get_market_info()`. This allows per-test override of exchange rules (e.g., custom `min_amount`, `min_quantity`) without touching other tests (default behavior unchanged when the attribute is `None`).

---

## 4. Concrete Numeric Scenarios Verified

All calculations use `MockExchange` defaults unless noted.

| Scenario | Setup | Validation result |
|---|---|---|
| Valid base buy | 500 INR @ 54000, step=1e-5, min_qty=0.001, min_amt=10 | qty=0.00925, notional=499.5 → ✓ PASS |
| Buy qty < min_quantity | 5 INR @ 54000 | qty=0.00009 < 0.001 → ✗ FAIL (ValueError) |
| Buy notional < min_amount | 30 INR @ 10, min_amt=50 | qty=3 ≥ min_qty=1, notional=30 < 50 → ✗ FAIL |
| Profit sell dust | total_qty=0.0005, clamped=0.0005 | 0.0005 < 0.001 → ✗ FAIL (order_failed) |
| Profit sell min-notional | total_qty=0.001, price=8002 | notional=8.002 < 10 → ✗ FAIL (order_failed) |
| Stop-loss dust | total_qty=0.0005, price=26000 | 0.0005 < 0.001 → ✗ FAIL (error + write-off) |
| Stop-loss min-notional | total_qty=0.001, price=7600, avg=8000, sl=5% | notional=7.6 < 10 → ✗ FAIL (error + write-off) |
| Stop-loss success | total_qty=0.00925, price=26000, avg=54000, sl=50% | qty=0.00925, notional=240.5 → ✓ PASS |
| Paper mode dust SL | mode="paper", same dust scenario | Identical validation path → ✗ FAIL (write-off) |
| Recovery offline fill | OPEN order → FILLED on exchange | No new orders placed, fill_recovered=1 |

---

## 5. Full Suite Results

```
335 passed in 1.26s
```

- **Pre-existing tests:** 300 (unchanged, no regressions from conftest patch)
- **New regression tests:** 35
- **Failed:** 0

---

## 6. Code Review

Architect code review verdict: **PASS**

> "The new suite materially covers the required execution paths in DCAManager: base buy, dip buy, profit sell, stop loss, paper-mode behavior, and recovery. Assertions are generally tight and regression-resistant. The conftest.py patch is minimal and non-breaking."

One gap identified (paper-mode dip-buy parity) was resolved by adding two additional tests before finalising.

---
name: Uncertain order resolution
description: When to mark a SUBMITTED-without-exchange_id order as FAILED vs leaving it for retry.
---

**Rule:** When resolving a SUBMITTED order with no exchange_order_id, only mark FAILED if the exchange query *succeeded* but returned no matching open order. If the exchange query itself fails (ExchangeError), leave the order as SUBMITTED and return without marking FAILED.

**Why:** An order placement timeout/crash can leave the order as SUBMITTED with no exchange_order_id. During recovery or mid-session sync, we try to find the order in the exchange's open-orders list. If the exchange is momentarily down, incorrectly marking FAILED causes state drift — the bot re-enters the position while the exchange still has the original order sitting open.

**How to apply:** OrderManager.resolve_uncertain_submitted() catches ExchangeError from get_open_orders and returns False (leaving status SUBMITTED). The caller (order_monitor._sync_with_exchange) will retry on the next sync cycle. Only zero-or-ambiguous matches after a *successful* query result in FAILED status.

**Files:** trading/order_manager.py — resolve_uncertain_submitted(); trading/order_monitor.py — _sync_with_exchange().

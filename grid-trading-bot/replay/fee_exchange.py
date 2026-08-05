"""Fee-simulating exchange wrapper for replay.

Reuses exchange.paper_exchange.PaperExchangeClient — the SAME order
simulation (slippage, latency, partial fills) already used by real paper
trading — and adds only what that class deliberately doesn't do: charging
a trading fee on fills, and (optionally) tracking a real, depleting INR
balance. This keeps all order-simulation logic in exactly one place
(PaperExchangeClient) and confines replay-specific behavior to this one
small subclass, isolated from live/paper trading.
"""
from __future__ import annotations

from exchange.base import Balance, ExchangeOrder
from exchange.paper_exchange import PaperExchangeClient


class FeeSimulatingPaperExchange(PaperExchangeClient):
    """PaperExchangeClient plus a configurable percentage trading fee,
    applied to the filled notional value once an order reaches FILLED or
    PARTIALLY_FILLED, matching how a real exchange reports `fee_amount`
    alongside a fill.

    Optionally also tracks a real, depleting INR balance (debited on buy
    fills, credited on sell fills) instead of PaperExchangeClient's fixed
    PAPER_INITIAL_BALANCE constant — enabled only when `initial_balance_inr`
    is given. This is what lets a replay grid running in mode="real" (see
    replay/cli.py's --wallet-balance) actually exercise RiskManager's
    capital-constraint checks (max_capital_per_coin, min_wallet_balance),
    which DCAManager bypasses entirely for mode="paper" grids by design.

    Existing behavior is unchanged when initial_balance_inr is omitted:
    get_balance()/get_balances() delegate to PaperExchangeClient exactly as
    before.
    """

    def __init__(
        self, *args, fee_rate: float = 0.001,
        initial_balance_inr: float | None = None, **kwargs,
    ) -> None:
        """fee_rate is a fraction, e.g. 0.001 = 0.1% (CoinDCX's typical
        taker fee). initial_balance_inr, if given, enables capital
        tracking starting from that balance."""
        super().__init__(*args, **kwargs)
        self._fee_rate = fee_rate
        self._track_capital = initial_balance_inr is not None
        self._tracked_balance_inr = initial_balance_inr if initial_balance_inr is not None else 0.0
        # Tracks the filled_quantity last seen per exchange_order_id, so a
        # partially-filled order polled multiple times only has its NEW
        # increment applied to the tracked balance each time, not the full
        # cumulative amount again.
        self._last_seen_filled_qty: dict[str, float] = {}

    def _with_fee(self, order: ExchangeOrder) -> ExchangeOrder:
        if order.filled_quantity > 0:
            notional = order.filled_quantity * (order.filled_price or order.price)
            order.fee = round(notional * self._fee_rate, 8)
            if self._track_capital:
                self._apply_capital_delta(order)
        return order

    def _apply_capital_delta(self, order: ExchangeOrder) -> None:
        eid = order.exchange_order_id
        previous_qty = self._last_seen_filled_qty.get(eid, 0.0)
        delta_qty = order.filled_quantity - previous_qty
        if delta_qty <= 0:
            return  # already accounted for (or a stale/duplicate status read)
        self._last_seen_filled_qty[eid] = order.filled_quantity

        price = order.filled_price or order.price
        delta_notional = delta_qty * price
        delta_fee = round(delta_notional * self._fee_rate, 8)
        if order.side == "buy":
            self._tracked_balance_inr -= (delta_notional + delta_fee)
        else:
            self._tracked_balance_inr += (delta_notional - delta_fee)

    async def get_balance(self, currency: str) -> Balance:
        if self._track_capital and currency.upper() == "INR":
            return Balance(currency="INR", balance=self._tracked_balance_inr, locked_balance=0.0)
        return await super().get_balance(currency)

    async def get_balances(self) -> list[Balance]:
        if self._track_capital:
            return [Balance(currency="INR", balance=self._tracked_balance_inr, locked_balance=0.0)]
        return await super().get_balances()

    async def place_order(self, *args, **kwargs) -> ExchangeOrder:
        order = await super().place_order(*args, **kwargs)
        return self._with_fee(order)

    async def get_order_status(self, exchange_order_id: str) -> ExchangeOrder:
        order = await super().get_order_status(exchange_order_id)
        return self._with_fee(order)

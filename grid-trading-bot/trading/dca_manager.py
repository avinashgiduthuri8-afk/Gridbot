"""DCA Manager: orchestrates the full DCA grid trading lifecycle.

Responsibilities:
  - Starting, pausing, resuming, and stopping grids.
  - Checking price triggers (dip buys, profit sells, stop loss) on demand.
  - Updating in-memory grid state after every order fill.
  - Delegating exchange calls to OrderManager and persistence to Repositories.
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone

from config.constants import GridStatus, OrderStatus
from exchange.base import ExchangeClient
from exchange.exceptions import ExchangeError
from grid.dca_engine import (
    calculate_next_buy_price,
    calculate_profit_target,
    calculate_quantity_for_inr,
    calculate_stop_loss_price,
    clamp_sell_quantity,
    is_dip_triggered,
    is_profit_triggered,
    is_stop_loss_triggered,
    update_position_after_buy,
    update_position_after_sell,
    validate_quantity,
)
from notifications.notifier import Notifier
from risk.risk_manager import RiskManager
from storage.models import DCAGridRecord, TradeHistoryRecord
from storage.repositories import Repositories
from trading.order_manager import OrderManager
from utils.helpers import new_id, now_iso
from utils.logger import get_logger

log = get_logger("trading")


class DCAManager:
    def __init__(
        self,
        exchange: ExchangeClient,
        repos: Repositories,
        order_manager: OrderManager,
        notifier: Notifier,
        risk: RiskManager,
    ) -> None:
        self._exchange = exchange
        self._repos = repos
        self._order_manager = order_manager
        self._notifier = notifier
        self._risk = risk
        # Per-grid locks prevent concurrent Telegram commands and monitor callbacks
        # from racing on the same grid's state.
        self._grid_locks: dict[str, asyncio.Lock] = {}

    def _grid_lock(self, grid_id: str) -> asyncio.Lock:
        """Return (creating if necessary) the asyncio.Lock for a single grid."""
        if grid_id not in self._grid_locks:
            self._grid_locks[grid_id] = asyncio.Lock()
        return self._grid_locks[grid_id]

    async def _get_wallet_balance(self, mode: str) -> float:
        """Return the INR balance to risk-check against for this grid's mode.

        Shared by start_grid and every subsequent buy so paper and real grids
        are evaluated against the same balance figure every time — previously
        start_grid used a hardcoded paper balance while no other call site
        checked balance at all.
        """
        if mode == "paper":
            return 1_000_000.0
        wallet = await self._exchange.get_balance("INR")
        return wallet.balance

    # ------------------------------------------------------------------
    # Grid lifecycle
    # ------------------------------------------------------------------

    async def start_grid(self, params: dict) -> str:
        """Create and start a new DCA grid.

        params keys: symbol, entry_price (0 = market), base_investment,
        dip_buy_amount, dip_percentage, profit_sell_amount, profit_percentage,
        max_levels, stop_loss_percentage.

        Returns the new grid_id.
        Raises ValueError on risk/exchange validation failures.
        """
        symbol: str = params["symbol"].upper()
        entry_price: float = float(params.get("entry_price", 0))
        base_investment: float = float(params["base_investment"])
        dip_buy_amount: float = float(params["dip_buy_amount"])
        dip_pct: float = float(params["dip_percentage"])
        profit_sell_amount: float = float(params["profit_sell_amount"])
        profit_pct: float = float(params["profit_percentage"])
        max_levels: int = int(params["max_levels"])
        stop_loss_pct: float = float(params["stop_loss_percentage"])
        mode: str = str(params.get("mode", "real"))
        trailing_enabled: bool = bool(params.get("trailing_enabled", False))
        trailing_pct: float | None = None
        if trailing_enabled:
            trailing_pct = float(params.get("trailing_percentage") or 0)
            if not (0 < trailing_pct < 100):
                raise ValueError(
                    f"trailing_percentage must be between 0 and 100, got {trailing_pct}"
                )

        wallet_balance = await self._get_wallet_balance(mode)
        # Pass the full DCA ladder commitment so the risk manager can correctly
        # assess whether total capital limits would be breached across all grids.
        full_ladder_commitment = base_investment + dip_buy_amount * (max_levels - 1)
        risk_result = await self._risk.check_can_start_grid(
            symbol, full_ladder_commitment, wallet_balance
        )
        if not risk_result.allowed:
            raise ValueError(risk_result.reason)

        market_info = await self._exchange.get_market_info(symbol)

        if entry_price <= 0:
            ticker = await self._exchange.get_ticker(symbol)
            entry_price = ticker.last_price
            log.info("Using market price %.4f for %s initial entry", entry_price, symbol)

        grid_id = new_id("grd")
        now = now_iso()

        grid = DCAGridRecord(
            grid_id=grid_id,
            symbol=symbol,
            status=GridStatus.ACTIVE.value,
            mode=mode,
            entry_price=entry_price,
            base_investment=base_investment,
            dip_buy_amount=dip_buy_amount,
            dip_percentage=dip_pct,
            profit_sell_amount=profit_sell_amount,
            profit_percentage=profit_pct,
            max_levels=max_levels,
            stop_loss_percentage=stop_loss_pct,
            trailing_enabled=trailing_enabled,
            trailing_percentage=trailing_pct,
            trailing_peak_price=None,
            current_level=0,
            total_quantity=0.0,
            total_investment=0.0,
            average_entry_price=0.0,
            last_buy_price=entry_price,
            next_buy_price=0.0,
            next_sell_price=0.0,
            realized_profit=0.0,
            completed_cycles=0,
            created_at=now,
            updated_at=now,
        )
        await self._repos.grids.create(grid)
        log.info("Created DCA grid %s for %s (entry ₹%.2f)", grid_id, symbol, entry_price)

        initial_qty = calculate_quantity_for_inr(
            base_investment, entry_price,
            market_info.step_size, market_info.min_quantity,
            min_notional=market_info.min_amount,
            quantity_precision=market_info.target_currency_precision,
            price_precision=market_info.base_currency_precision,
        )
        try:
            await self._order_manager.place_dca_order(
                grid_id=grid_id,
                symbol=symbol,
                side="buy",
                price=entry_price,
                quantity=initial_qty,
                order_type="market_order",
                mode=mode,
            )
        except Exception as exc:
            # Roll back the grid row entirely — a zombie ACTIVE/STOPPED record with
            # no orders is more confusing than a clean failure the user can retry.
            try:
                # Orders that reference this grid must be removed first to satisfy
                # the FK constraint, then the grid row itself can be deleted.
                await self._repos.orders.delete_for_grid(grid_id)
                await self._repos.grids.delete(grid_id)
                log.warning("Rolled back grid %s after order failure: %s", grid_id, exc)
            except Exception:
                log.exception("Could not roll back grid %s; it may need manual cleanup", grid_id)
            if isinstance(exc, ExchangeError):
                raise ValueError(f"Exchange rejected initial buy: {exc}") from exc
            raise

        approx_next_sell = calculate_profit_target(entry_price, profit_pct)
        await self._notifier.grid_started(
            symbol=symbol,
            grid_id=grid_id,
            entry_price=entry_price,
            base_investment=base_investment,
            dip_pct=dip_pct,
            profit_pct=profit_pct,
            max_levels=max_levels,
            next_sell_price=approx_next_sell,
        )
        return grid_id

    async def pause_grid(self, grid_id: str) -> None:
        async with self._grid_lock(grid_id):
            grid = await self._repos.grids.get(grid_id)
            if not grid or grid["status"] != GridStatus.ACTIVE.value:
                raise ValueError(f"Grid {grid_id} is not active.")
            await self._repos.grids.update_status(grid_id, GridStatus.PAUSED.value)
            log.info("Grid %s paused", grid_id)
            await self._notifier.grid_paused(grid["symbol"], grid_id)

    async def resume_grid(self, grid_id: str) -> None:
        async with self._grid_lock(grid_id):
            grid = await self._repos.grids.get(grid_id)
            if not grid or grid["status"] != GridStatus.PAUSED.value:
                raise ValueError(f"Grid {grid_id} is not paused.")
            await self._repos.grids.update_status(grid_id, GridStatus.ACTIVE.value)
            log.info("Grid %s resumed", grid_id)
            await self._notifier.grid_resumed(grid["symbol"], grid_id)

    async def stop_grid(self, grid_id: str, reason: str = "manual") -> None:
        """Stop a grid, selling all remaining holdings if stop-loss is the reason."""
        async with self._grid_lock(grid_id):
            grid = await self._repos.grids.get(grid_id)
            if not grid:
                raise ValueError(f"Grid {grid_id} not found.")
            if grid["status"] in (GridStatus.STOPPED.value, GridStatus.COMPLETED.value):
                return

            pending = await self._repos.orders.list_pending_for_grid(grid_id)
            for order in pending:
                try:
                    await self._order_manager.cancel_order(order["order_id"])
                except ExchangeError as exc:
                    log.warning(
                        "Could not cancel %s order %s during stop: %s",
                        order["side"], order["order_id"], exc,
                    )

            await self._repos.grids.update_status(grid_id, GridStatus.STOPPED.value)
            log.info("Grid %s stopped (reason: %s)", grid_id, reason)
            await self._notifier.grid_stopped(grid["symbol"], grid_id, reason)

    # ------------------------------------------------------------------
    # Manual buy / sell (user-initiated, outside the automatic dip/profit/
    # stop-loss triggers — /buy and /sell Telegram commands)
    # ------------------------------------------------------------------

    async def manual_buy(self, grid_id: str, inr_amount: float):
        """Place a manual buy on an active grid for a specific INR amount.

        Goes through the exact same exchange-rule validation and risk gate
        as an automatic dip-buy (calculate_quantity_for_inr, then
        check_can_place_order) — a manual action must not be a way to
        bypass emergency-stop or the daily loss limit. Unlike a dip-buy,
        it is NOT gated on is_dip_triggered() or max_levels: this is a
        deliberate, explicit user action, not the automatic ladder.

        The resulting fill is processed by the same handle_order_filled
        path as every other buy, so current_level/average_entry_price
        update consistently regardless of what triggered the buy.

        Raises ValueError with a clear reason on any validation/risk
        failure; the caller (Telegram handler) is responsible for
        reporting that to the user.
        """
        if inr_amount <= 0:
            raise ValueError("Buy amount must be greater than zero.")

        async with self._grid_lock(grid_id):
            grid = await self._repos.grids.get(grid_id)
            if not grid:
                raise ValueError(f"Grid {grid_id} not found.")
            if grid["status"] != GridStatus.ACTIVE.value:
                raise ValueError(
                    f"Grid {grid_id} is {grid['status']}, not active — cannot buy."
                )

            symbol: str = grid["symbol"]
            mode: str = grid.get("mode", "real")

            ticker = await self._exchange.get_ticker(symbol)
            current_price = ticker.last_price

            market_info = await self._exchange.get_market_info(symbol)
            qty = calculate_quantity_for_inr(
                inr_amount, current_price,
                market_info.step_size, market_info.min_quantity,
                min_notional=market_info.min_amount,
                quantity_precision=market_info.target_currency_precision,
                price_precision=market_info.base_currency_precision,
            )

            order_value_inr = qty * current_price
            wallet_balance = await self._get_wallet_balance(mode)
            risk_result = await self._risk.check_can_place_order(order_value_inr, wallet_balance)
            if not risk_result.allowed:
                raise ValueError(risk_result.reason)

            order = await self._order_manager.place_dca_order(
                grid_id=grid_id, symbol=symbol, side="buy",
                price=current_price, quantity=qty,
                order_type="market_order", mode=mode,
            )
            log.info(
                "Manual buy placed: grid=%s order=%s qty=%.8f @ ₹%.2f mode=%s",
                grid_id, order.order_id, qty, current_price, mode,
            )
            await self._notifier.order_submitted(
                symbol=symbol, grid_id=grid_id, order_id=order.order_id,
                side="buy", quantity=qty, price=current_price, mode=mode,
            )
            return order

    async def manual_sell(self, grid_id: str, inr_amount: float | None):
        """Place a manual sell on an active grid.

        ``inr_amount=None`` sells the entire remaining position (full
        close); otherwise sells that INR amount, clamped to the available
        quantity exactly like an automatic profit-sell. Deliberately NOT
        gated on is_profit_triggered() — this is an explicit user decision
        to sell now regardless of current P&L.

        Sells are not risk-gated (see _execute_dip_buy's docstring on why
        buys and sells are treated asymmetrically): reducing a position
        must never be blocked, including under emergency stop.

        Raises ValueError with a clear reason on any validation failure.
        """
        async with self._grid_lock(grid_id):
            grid = await self._repos.grids.get(grid_id)
            if not grid:
                raise ValueError(f"Grid {grid_id} not found.")
            if grid["status"] != GridStatus.ACTIVE.value:
                raise ValueError(
                    f"Grid {grid_id} is {grid['status']}, not active — cannot sell."
                )
            total_qty: float = grid["total_quantity"]
            if total_qty <= 0:
                raise ValueError(f"Grid {grid_id} has no position to sell.")
            if await self._repos.orders.count_pending_side(grid_id, "sell") > 0:
                raise ValueError(
                    f"Grid {grid_id} already has a sell order pending — wait for it to resolve."
                )

            symbol: str = grid["symbol"]
            mode: str = grid.get("mode", "real")
            ticker = await self._exchange.get_ticker(symbol)
            current_price = ticker.last_price
            market_info = await self._exchange.get_market_info(symbol)

            if inr_amount is None:
                desired_qty = total_qty
            else:
                if inr_amount <= 0:
                    raise ValueError("Sell amount must be greater than zero.")
                desired_qty = calculate_quantity_for_inr(
                    inr_amount, current_price,
                    market_info.step_size, market_info.min_quantity,
                    min_notional=market_info.min_amount,
                    quantity_precision=market_info.target_currency_precision,
                    price_precision=market_info.base_currency_precision,
                )

            sell_qty = clamp_sell_quantity(desired_qty, total_qty, market_info.step_size)
            check = validate_quantity(
                sell_qty, current_price,
                market_info.min_quantity,
                step_size=market_info.step_size,
                min_notional=market_info.min_amount,
                quantity_precision=market_info.target_currency_precision,
                price_precision=market_info.base_currency_precision,
                unit_label=market_info.target_currency_short_name or "coins",
            )
            if not check.valid:
                raise ValueError(check.reason)

            order = await self._order_manager.place_dca_order(
                grid_id=grid_id, symbol=symbol, side="sell",
                price=current_price, quantity=sell_qty,
                order_type="market_order", mode=mode,
            )
            log.info(
                "Manual sell placed: grid=%s order=%s qty=%.8f @ ₹%.2f mode=%s",
                grid_id, order.order_id, sell_qty, current_price, mode,
            )
            await self._notifier.order_submitted(
                symbol=symbol, grid_id=grid_id, order_id=order.order_id,
                side="sell", quantity=sell_qty, price=current_price, mode=mode,
            )
            return order

    # A closed allow-list, not user input, drives which literal keyword is
    # passed to update_state() below — see the safety note on
    # DCAGridRepository.update_state for why this must never be **field-as-key.
    ADJUSTABLE_GRID_FIELDS = frozenset({
        "dip_buy_amount", "dip_percentage", "profit_sell_amount",
        "profit_percentage", "max_levels", "stop_loss_percentage",
        "trailing_enabled", "trailing_percentage",
    })

    async def adjust_grid(self, grid_id: str, field: str, value) -> dict:
        """Adjust a single parameter of an existing active/paused grid
        without stopping and recreating it.

        dip_percentage and profit_percentage require special handling:
        next_buy_price/next_sell_price are pre-computed and cached on the
        grid record (see is_dip_triggered/is_profit_triggered in
        dca_engine.py, which read the cached value rather than recomputing
        from the percentage on every tick) — so simply updating the
        percentage field alone would silently have NO effect until the next
        buy/sell fill recomputed those prices naturally. Both are
        recalculated and persisted here so the change takes effect on the
        very next price tick, not the next fill.

        max_levels and stop_loss_percentage are read fresh from the grid
        record on every trigger check, so they need no special handling.
        """
        if field not in self.ADJUSTABLE_GRID_FIELDS:
            raise ValueError(f"'{field}' cannot be adjusted this way.")

        async with self._grid_lock(grid_id):
            grid = await self._repos.grids.get(grid_id)
            if not grid:
                raise ValueError(f"Grid {grid_id} not found.")
            if grid["status"] not in (GridStatus.ACTIVE.value, GridStatus.PAUSED.value):
                raise ValueError(
                    f"Grid {grid_id} is {grid['status']} — only active or paused grids can be adjusted."
                )

            if field == "dip_percentage":
                last_buy_price = grid.get("last_buy_price") or 0.0
                new_next_buy = (
                    calculate_next_buy_price(last_buy_price, value) if last_buy_price > 0 else 0.0
                )
                await self._repos.grids.update_state(
                    grid_id, dip_percentage=value, next_buy_price=new_next_buy,
                )
            elif field == "profit_percentage":
                avg_entry = grid.get("average_entry_price") or 0.0
                new_next_sell = (
                    calculate_profit_target(avg_entry, value) if avg_entry > 0 else 0.0
                )
                await self._repos.grids.update_state(
                    grid_id, profit_percentage=value, next_sell_price=new_next_sell,
                )
            elif field == "dip_buy_amount":
                await self._repos.grids.update_state(grid_id, dip_buy_amount=value)
            elif field == "profit_sell_amount":
                await self._repos.grids.update_state(grid_id, profit_sell_amount=value)
            elif field == "max_levels":
                await self._repos.grids.update_state(grid_id, max_levels=int(value))
            elif field == "stop_loss_percentage":
                await self._repos.grids.update_state(grid_id, stop_loss_percentage=value)
            elif field == "trailing_enabled":
                await self._repos.grids.update_state(grid_id, trailing_enabled=bool(value))
            elif field == "trailing_percentage":
                await self._repos.grids.update_state(grid_id, trailing_percentage=value)

            updated_grid = await self._repos.grids.get(grid_id)
            log.info("Grid %s adjusted: %s -> %s", grid_id, field, value)
            return updated_grid

    # ------------------------------------------------------------------
    # Price trigger checks (called by the price-monitor loop in main.py)
    # ------------------------------------------------------------------

    async def check_grid_triggers(self, grid_id: str, current_price: float) -> None:
        """Check dip-buy, profit-sell, and stop-loss triggers for one grid.

        Safe to call on every price tick — guard conditions prevent duplicate
        orders and respect paused / stopped state.
        """
        async with self._grid_lock(grid_id):
            await self._check_grid_triggers_locked(grid_id, current_price)

    async def _check_grid_triggers_locked(self, grid_id: str, current_price: float) -> None:
        """Inner implementation — must be called while holding _grid_lock(grid_id)."""
        grid = await self._repos.grids.get(grid_id)
        if not grid or grid["status"] != GridStatus.ACTIVE.value:
            return
        if grid["current_level"] == 0:
            return

        symbol: str = grid["symbol"]
        avg_entry: float = grid["average_entry_price"]
        total_qty: float = grid["total_quantity"]

        if total_qty <= 0:
            return

        # 1. Stop loss — highest priority
        if is_stop_loss_triggered(current_price, avg_entry, grid["stop_loss_percentage"]):
            log.warning(
                "Stop loss triggered on %s (price ₹%.2f, avg_entry ₹%.2f)",
                symbol, current_price, avg_entry,
            )
            await self._execute_stop_loss(grid, current_price)
            return

        # 2. Profit sell / trailing take-profit — only if no pending sell already in flight
        if grid["trailing_peak_price"] is not None:
            # Trailing is already active for this profit cycle: track the peak
            # and check for the trail-stop on every tick, independent of
            # next_sell_price — once trailing has started, price falling back
            # below next_sell_price must NOT stop us tracking the trail, or
            # a fast reversal could skip the trailing-stop check entirely.
            if await self._repos.orders.count_pending_side(grid_id, "sell") == 0:
                await self._handle_trailing_tick(grid, current_price)
            return
        if (
            is_profit_triggered(current_price, grid["next_sell_price"])
            and await self._repos.orders.count_pending_side(grid_id, "sell") == 0
        ):
            if grid["trailing_enabled"]:
                await self._repos.grids.update_state(grid_id, trailing_peak_price=current_price)
                log.info(
                    "Trailing take-profit activated for %s at ₹%.2f (trail %.2f%%)",
                    grid_id, current_price, grid["trailing_percentage"],
                )
                await self._notifier.trailing_activated(
                    symbol=symbol, grid_id=grid_id, peak_price=current_price,
                    trailing_percentage=grid["trailing_percentage"],
                )
            else:
                await self._execute_profit_sell(grid, current_price)
            return

        # 3. Dip buy — only if below max levels and no buy in flight
        if (
            is_dip_triggered(current_price, grid["next_buy_price"])
            and grid["current_level"] < grid["max_levels"]
            and await self._repos.orders.count_pending_side(grid_id, "buy") == 0
        ):
            await self._execute_dip_buy(grid, current_price)

    # ------------------------------------------------------------------
    # Order fill handler (called by OrderMonitor on confirmed fill)
    # ------------------------------------------------------------------

    async def handle_order_filled(
        self, order_id: str, fill_price: float, fill_qty: float
    ) -> None:
        """Update DCA grid state after an order has been confirmed as filled.

        Idempotency guard: checks trade_history for an existing record for this
        order_id before applying mutations.  Safe to call from both OrderMonitor
        and RecoveryManager without risk of double-applying a fill.
        """
        order = await self._repos.orders.get(order_id)
        if not order:
            log.warning("handle_order_filled called for unknown order %s", order_id)
            return

        grid_id: str = order["grid_id"]

        async with self._grid_lock(grid_id):
            # Idempotency check must live inside the lock so that two concurrent
            # callers cannot both pass the guard and then each apply the fill.
            existing_trade = await self._repos.trade_history.get_by_order_id(order_id)
            if existing_trade:
                log.info(
                    "handle_order_filled: fill for order %s already recorded "
                    "(trade %s) — skipping to prevent double-apply",
                    order_id, existing_trade["trade_id"],
                )
                return

            grid = await self._repos.grids.get(grid_id)
            if not grid:
                log.warning("Order %s belongs to missing grid %s", order_id, grid_id)
                return

            actual_price = fill_price if fill_price > 0 else order["price"]
            actual_qty = fill_qty if fill_qty > 0 else order["quantity"]

            if order["side"] == "buy":
                await self._on_buy_filled(grid, order, order_id, actual_price, actual_qty)
            else:
                await self._on_sell_filled(grid, order, order_id, actual_price, actual_qty)

    # ------------------------------------------------------------------
    # Private: order execution helpers
    # ------------------------------------------------------------------

    async def _resolve_fill_fee(self, order: dict) -> float:
        fee = float(order.get("fee") or 0.0)
        if fee > 0:
            return fee

        exchange_order_id = order.get("exchange_order_id")
        if not exchange_order_id:
            return 0.0

        try:
            trades = await self._exchange.get_trade_history(
                symbol=order["symbol"],
                limit=500,
                order_id=exchange_order_id,
            )
        except ExchangeError as exc:
            log.warning(
                "Could not resolve fee for order %s via trade history: %s",
                order["order_id"], exc,
            )
            return 0.0

        resolved = sum(float(t.fee or 0.0) for t in trades if t.exchange_order_id == exchange_order_id)
        if resolved > 0:
            await self._repos.orders.update_status(
                order["order_id"],
                order["status"],
                fee=resolved,
            )
        return resolved if resolved > 0 else 0.0

    async def _execute_dip_buy(self, grid: dict, current_price: float) -> None:
        grid_id: str = grid["grid_id"]
        symbol: str = grid["symbol"]
        mode: str = grid.get("mode", "real")
        try:
            market_info = await self._exchange.get_market_info(symbol)
            qty = calculate_quantity_for_inr(
                grid["dip_buy_amount"], current_price,
                market_info.step_size, market_info.min_quantity,
                min_notional=market_info.min_amount,
                quantity_precision=market_info.target_currency_precision,
                price_precision=market_info.base_currency_precision,
            )
        except (ExchangeError, ValueError) as exc:
            # Previously this only logged, with no Telegram notification —
            # a ValueError here means dip_buy_amount is configured too small
            # for the current price and this grid will silently fail this
            # same computation on every future trigger with zero visibility.
            # Notify the same way every other failed-attempt branch in this
            # method does, so a persistent misconfiguration is actually seen.
            log.error("Cannot compute dip buy qty for %s: %s", grid_id, exc)
            await self._notifier.order_failed(
                symbol=symbol, grid_id=grid_id, order_id="(not placed)",
                side="buy", reason=str(exc), mode=mode,
            )
            return

        # Risk gate: a dip buy commits *new* capital, exactly like starting a
        # grid does, so it must pass through the same emergency-stop / daily-
        # loss-limit / balance checks as check_can_start_grid — previously
        # this check only ran once, at grid creation, and every subsequent
        # dip buy bypassed it entirely (emergency stop had no effect on
        # already-running grids). Profit-sells and stop-loss sells are
        # deliberately NOT gated here: they reduce risk, and blocking an exit
        # during an emergency stop or daily-loss halt would trap capital in a
        # losing position instead of protecting it.
        order_value_inr = qty * current_price
        try:
            wallet_balance = await self._get_wallet_balance(mode)
            risk_result = await self._risk.check_can_place_order(order_value_inr, wallet_balance)
        except Exception as exc:
            # Fail-safe: if we can't even determine whether the risk gate
            # allows this buy (exchange balance call failed, DB error reading
            # daily stats, etc.), do NOT place the order. Previously an
            # exception here would only be caught by price_monitor's generic
            # per-grid handler, logged, and never surfaced to the user —
            # this grid would then silently stop progressing with no visible
            # explanation. Now it's reported the same way an order failure is.
            log.error("Risk gate check errored for dip buy on %s: %s", grid_id, exc)
            await self._notifier.order_failed(
                symbol=symbol, grid_id=grid_id, order_id="(blocked)",
                side="buy", reason=f"Risk check failed: {exc}", mode=mode,
            )
            return
        if not risk_result.allowed:
            log.warning("Dip buy for %s blocked by risk gate: %s", grid_id, risk_result.reason)
            await self._notifier.order_failed(
                symbol=symbol, grid_id=grid_id, order_id="(blocked)",
                side="buy", reason=risk_result.reason, mode=mode,
            )
            return

        try:
            order = await self._order_manager.place_dca_order(
                grid_id=grid_id,
                symbol=symbol,
                side="buy",
                price=current_price,
                quantity=qty,
                order_type="market_order",
                mode=mode,
            )
            log.info(
                "Dip buy placed: grid=%s order=%s qty=%.8f @ ₹%.2f mode=%s",
                grid_id, order.order_id, qty, current_price, mode,
            )
            await self._notifier.order_submitted(
                symbol=symbol, grid_id=grid_id, order_id=order.order_id,
                side="buy", quantity=qty, price=current_price, mode=mode,
            )
        except ExchangeError as exc:
            log.error("Dip buy failed for %s: %s", grid_id, exc)
            await self._notifier.order_failed(
                symbol=symbol, grid_id=grid_id, order_id="(pending)",
                side="buy", reason=str(exc), mode=mode,
            )

    async def _handle_trailing_tick(self, grid: dict, current_price: float) -> None:
        """Update the trailing peak, or execute the sell once price has
        pulled back trailing_percentage from that peak.

        Precondition: grid["trailing_peak_price"] is not None (trailing is
        active for this profit cycle) and there's no sell already pending.
        """
        grid_id: str = grid["grid_id"]
        peak: float = grid["trailing_peak_price"]
        trailing_pct: float = grid["trailing_percentage"]

        if current_price > peak:
            await self._repos.grids.update_state(grid_id, trailing_peak_price=current_price)
            return

        drop_pct = (peak - current_price) / peak * 100 if peak > 0 else 0.0
        if drop_pct < trailing_pct:
            return  # still within the trailing band, keep waiting

        log.info(
            "Trailing take-profit stop hit for %s: peak ₹%.2f, current ₹%.2f (%.2f%% pullback)",
            grid_id, peak, current_price, drop_pct,
        )
        await self._execute_profit_sell(grid, current_price)
        # Reset regardless of outcome (success, dust write-off, or a
        # retryable failure) — a fresh trailing cycle will re-activate
        # cleanly from whatever price prevails on the next trigger, rather
        # than risk resuming from a stale peak.
        await self._repos.grids.update_state(grid_id, trailing_peak_price=None)

    async def _execute_profit_sell(self, grid: dict, current_price: float) -> None:
        grid_id: str = grid["grid_id"]
        symbol: str = grid["symbol"]
        mode: str = grid.get("mode", "real")
        try:
            market_info = await self._exchange.get_market_info(symbol)
            desired_qty = calculate_quantity_for_inr(
                grid["profit_sell_amount"], current_price,
                market_info.step_size, market_info.min_quantity,
                min_notional=market_info.min_amount,
                quantity_precision=market_info.target_currency_precision,
                price_precision=market_info.base_currency_precision,
            )
        except (ExchangeError, ValueError) as exc:
            # Same fix as _execute_dip_buy above: a persistent
            # misconfiguration (profit_sell_amount too small for current
            # price) must not fail silently forever with only a log line.
            log.error("Cannot compute profit sell qty for %s: %s", grid_id, exc)
            await self._notifier.order_failed(
                symbol=symbol, grid_id=grid_id, order_id="(not placed)",
                side="sell", reason=str(exc), mode=mode,
            )
            return

        sell_qty = clamp_sell_quantity(desired_qty, grid["total_quantity"], market_info.step_size)

        # Clamping to the available balance can push a previously-valid
        # quantity down to zero or back below min_quantity/min_notional
        # (e.g. a "dust" remainder) — revalidate through the SAME rule
        # engine as buys before this quantity is allowed to reach
        # OrderManager. validate_quantity() treats qty<=0 as a min_quantity
        # failure, so this is the ONE path for every clamp-shrinks-it-away
        # outcome, with a proper user-facing notification every time.
        check = validate_quantity(
            sell_qty, current_price,
            market_info.min_quantity,
            step_size=market_info.step_size,
            min_notional=market_info.min_amount,
            quantity_precision=market_info.target_currency_precision,
            price_precision=market_info.base_currency_precision,
            unit_label=market_info.target_currency_short_name or "coins",
        )
        if not check.valid:
            # If this sell was clamped down to (essentially) the entire
            # remaining position, there is no future price movement that
            # will change the outcome — total_quantity itself is the
            # unsellable dust amount, and the grid would otherwise sit
            # ACTIVE forever, re-attempting and re-failing this same sell on
            # every future profit trigger. This mirrors the stop-loss dust
            # write-off below. A genuine *partial* sell that fails (sell_qty
            # meaningfully less than total_quantity) is left to retry later,
            # since there's still a real position that a future trigger
            # could act on differently.
            if sell_qty >= grid["total_quantity"]:
                log.warning(
                    "Profit sell for %s: remaining position %.8f cannot be sold "
                    "(%s) and this was the full remaining quantity — writing "
                    "off as dust and closing grid.",
                    grid_id, sell_qty, check.reason,
                )
                await self._repos.grids.update_state(
                    grid_id,
                    status=GridStatus.STOPPED.value,
                    total_quantity=0.0,
                    total_investment=0.0,
                )
                await self._notifier.error(
                    f"Profit sell {symbol}",
                    f"Grid closed, but {sell_qty:.8f} {market_info.target_currency_short_name or 'coins'} "
                    f"(the entire remaining position) could not be sold "
                    f"({check.reason}) and was written off as dust.",
                )
                return

            log.warning(
                "Profit sell for %s rejected after clamping: %s", grid_id, check.reason,
            )
            await self._notifier.order_failed(
                symbol=symbol, grid_id=grid_id, order_id="(pending)",
                side="sell", reason=check.reason, mode=mode,
            )
            return

        try:
            order = await self._order_manager.place_dca_order(
                grid_id=grid_id,
                symbol=symbol,
                side="sell",
                price=current_price,
                quantity=sell_qty,
                order_type="market_order",
                mode=mode,
            )
            log.info(
                "Profit sell placed: grid=%s order=%s qty=%.8f @ ₹%.2f mode=%s",
                grid_id, order.order_id, sell_qty, current_price, mode,
            )
            await self._notifier.order_submitted(
                symbol=symbol, grid_id=grid_id, order_id=order.order_id,
                side="sell", quantity=sell_qty, price=current_price, mode=mode,
            )
        except ExchangeError as exc:
            log.error("Profit sell failed for %s: %s", grid_id, exc)
            await self._notifier.order_failed(
                symbol=symbol, grid_id=grid_id, order_id="(pending)",
                side="sell", reason=str(exc), mode=mode,
            )

    async def _execute_stop_loss(self, grid: dict, current_price: float) -> None:
        grid_id: str = grid["grid_id"]
        symbol: str = grid["symbol"]
        total_qty: float = grid["total_quantity"]
        avg_entry: float = grid["average_entry_price"]
        mode: str = grid.get("mode", "real")

        if total_qty <= 0:
            await self._repos.grids.update_status(grid_id, GridStatus.STOPPED.value)
            return

        try:
            market_info = await self._exchange.get_market_info(symbol)
            sell_qty = clamp_sell_quantity(total_qty, total_qty, market_info.step_size)
        except ExchangeError:
            sell_qty = total_qty
            market_info = None

        pnl = (current_price - avg_entry) * sell_qty

        # A stop-loss is always a FINAL, full-position exit — unlike a
        # partial profit sell (which can retry a later, smaller clamp on a
        # future trigger if there's real quantity left), there's no "try
        # again later" for a stop-loss. If the clamped remainder fails the
        # shared rule check (e.g. it's an unsellable "dust" amount below
        # min_quantity/min_notional), we cannot leave the grid open forever
        # waiting for a sell that will never clear — write the position off
        # as dust, notify, and close the grid. (Profit-sell has the same
        # write-off for the equivalent case — see _execute_profit_sell —
        # when its clamp also reduces to the entire remaining position.)
        if market_info is not None:
            check = validate_quantity(
                sell_qty, current_price,
                market_info.min_quantity,
                step_size=market_info.step_size,
                min_notional=market_info.min_amount,
                quantity_precision=market_info.target_currency_precision,
                price_precision=market_info.base_currency_precision,
                unit_label=market_info.target_currency_short_name or "coins",
            )
            if not check.valid:
                log.warning(
                    "Stop loss for %s: remaining %.8f cannot be sold (%s) — "
                    "writing off as dust and closing grid.",
                    grid_id, sell_qty, check.reason,
                )
                await self._repos.grids.update_state(
                    grid_id,
                    status=GridStatus.STOPPED.value,
                    total_quantity=0.0,
                    total_investment=0.0,
                )
                await self._notifier.error(
                    f"Stop loss {symbol}",
                    f"Grid closed, but {sell_qty:.8f} {market_info.target_currency_short_name or 'coins'} "
                    f"could not be sold ({check.reason}) and was written off as dust.",
                )
                return

        try:
            await self._order_manager.place_dca_order(
                grid_id=grid_id,
                symbol=symbol,
                side="sell",
                price=current_price,
                quantity=sell_qty,
                order_type="market_order",
                mode=mode,
            )
        except ExchangeError as exc:
            log.error("Stop loss sell failed for %s: %s", grid_id, exc)
            await self._notifier.error(f"Stop loss {symbol}", str(exc))
            return

        await self._repos.grids.update_state(
            grid_id,
            status=GridStatus.STOPPED.value,
            total_quantity=0.0,
            total_investment=0.0,
        )
        await self._notifier.stop_loss_triggered(
            symbol=symbol,
            grid_id=grid_id,
            sell_price=current_price,
            avg_entry_price=avg_entry,
            quantity=sell_qty,
            pnl=pnl,
        )
        log.warning("Stop loss executed for %s, sold %.8f @ ₹%.2f", grid_id, sell_qty, current_price)

    # ------------------------------------------------------------------
    # Private: fill event handlers
    # ------------------------------------------------------------------

    async def _on_buy_filled(
        self, grid: dict, order: dict, order_id: str, fill_price: float, fill_qty: float
    ) -> None:
        grid_id = grid["grid_id"]
        symbol = grid["symbol"]
        fee = await self._resolve_fill_fee(order)
        investment_inr = fill_qty * fill_price
        total_buy_cost = investment_inr + fee

        new_total_inv, new_total_qty, new_avg = update_position_after_buy(
            grid["total_investment"], grid["total_quantity"], total_buy_cost, fill_qty
        )
        new_level = grid["current_level"] + 1
        new_next_buy = calculate_next_buy_price(fill_price, grid["dip_percentage"])
        new_next_sell = calculate_profit_target(new_avg, grid["profit_percentage"])

        await self._repos.grids.update_state(
            grid_id,
            current_level=new_level,
            total_investment=new_total_inv,
            total_quantity=new_total_qty,
            average_entry_price=new_avg,
            last_buy_price=fill_price,
            next_buy_price=new_next_buy,
            next_sell_price=new_next_sell,
        )
        await self._repos.orders.update_status(
            order_id,
            order["status"],
            fee=fee,
        )

        trade_id = new_id("trd")
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        await self._repos.trade_history.record(
            TradeHistoryRecord(
                trade_id=trade_id,
                grid_id=grid_id,
                order_id=order_id,
                symbol=symbol,
                side="buy",
                price=fill_price,
                quantity=fill_qty,
                investment_inr=total_buy_cost,
                fee=fee,
                pnl=0.0,
                executed_at=now_iso(),
            )
        )
        await self._repos.daily_stats.add_trade(today, 0.0)

        log.info(
            "Buy filled %s: qty %.8f @ ₹%.2f → avg ₹%.2f level %d",
            grid_id, fill_qty, fill_price, new_avg, new_level,
        )

        if new_level == 1:
            await self._notifier.avg_entry_updated(
                symbol, grid_id, new_avg, new_total_qty, new_total_inv
            )
        else:
            await self._notifier.dip_buy_executed(
                symbol=symbol,
                grid_id=grid_id,
                level=new_level,
                quantity=fill_qty,
                buy_price=fill_price,
                investment_inr=total_buy_cost,
                avg_entry_price=new_avg,
                next_buy_price=new_next_buy,
                next_sell_price=new_next_sell,
            )

    async def _on_sell_filled(
        self, grid: dict, order: dict, order_id: str, fill_price: float, fill_qty: float
    ) -> None:
        grid_id = grid["grid_id"]
        symbol = grid["symbol"]
        fee = await self._resolve_fill_fee(order)

        new_total_inv, new_total_qty, pnl, avg_entry = update_position_after_sell(
            grid["total_investment"],
            grid["total_quantity"],
            grid["average_entry_price"],
            fill_qty,
            fill_price,
        )
        net_pnl = pnl - fee
        new_realized = grid["realized_profit"] + net_pnl
        new_cycles = grid["completed_cycles"] + 1
        proceeds_inr = fill_qty * fill_price

        if new_total_qty <= 0:
            new_next_sell = 0.0
            new_status = GridStatus.COMPLETED.value
        else:
            new_next_sell = calculate_profit_target(avg_entry, grid["profit_percentage"])
            new_status = grid["status"]

        await self._repos.grids.update_state(
            grid_id,
            status=new_status,
            total_investment=new_total_inv,
            total_quantity=new_total_qty,
            average_entry_price=avg_entry,
            realized_profit=new_realized,
            completed_cycles=new_cycles,
            next_sell_price=new_next_sell,
        )
        await self._repos.orders.update_status(
            order_id,
            order["status"],
            fee=fee,
        )

        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        await self._repos.trade_history.record(
            TradeHistoryRecord(
                trade_id=new_id("trd"),
                grid_id=grid_id,
                order_id=order_id,
                symbol=symbol,
                side="sell",
                price=fill_price,
                quantity=fill_qty,
                investment_inr=max(0.0, proceeds_inr - fee),
                fee=fee,
                pnl=net_pnl,
                executed_at=now_iso(),
            )
        )
        await self._repos.daily_stats.add_trade(today, net_pnl)

        log.info(
            "Sell filled %s: qty %.8f @ ₹%.2f pnl ₹%.2f fee ₹%.2f (net ₹%.2f total realized ₹%.2f)",
            grid_id, fill_qty, fill_price, pnl, fee, net_pnl, new_realized,
        )

        await self._notifier.profit_sell_executed(
            symbol=symbol,
            grid_id=grid_id,
            quantity=fill_qty,
            sell_price=fill_price,
            avg_entry_price=avg_entry,
            pnl=net_pnl,
            total_realized=new_realized,
            cycles=new_cycles,
            next_sell_price=new_next_sell,
        )

        if new_status == GridStatus.COMPLETED.value:
            await self._notifier.grid_completed(symbol, grid_id, new_cycles, new_realized)
            log.info("Grid %s completed after %d sell cycles", grid_id, new_cycles)

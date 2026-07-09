"""DCA Manager: orchestrates the full DCA grid trading lifecycle.

Responsibilities:
  - Starting, pausing, resuming, and stopping grids.
  - Checking price triggers (dip buys, profit sells, stop loss) on demand.
  - Updating in-memory grid state after every order fill.
  - Delegating exchange calls to OrderManager and persistence to Repositories.
"""

from __future__ import annotations

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

        if mode == "paper":
            wallet_balance = 1_000_000.0
        else:
            wallet = await self._exchange.get_balance("INR")
            wallet_balance = wallet.balance
        risk_result = await self._risk.check_can_start_grid(
            symbol, base_investment, wallet_balance
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
            )
        except ExchangeError as exc:
            await self._repos.grids.update_status(grid_id, GridStatus.STOPPED.value)
            raise ValueError(f"Exchange rejected initial buy: {exc}") from exc

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
        grid = await self._repos.grids.get(grid_id)
        if not grid or grid["status"] != GridStatus.ACTIVE.value:
            raise ValueError(f"Grid {grid_id} is not active.")
        await self._repos.grids.update_status(grid_id, GridStatus.PAUSED.value)
        log.info("Grid %s paused", grid_id)
        await self._notifier.grid_paused(grid["symbol"], grid_id)

    async def resume_grid(self, grid_id: str) -> None:
        grid = await self._repos.grids.get(grid_id)
        if not grid or grid["status"] != GridStatus.PAUSED.value:
            raise ValueError(f"Grid {grid_id} is not paused.")
        await self._repos.grids.update_status(grid_id, GridStatus.ACTIVE.value)
        log.info("Grid %s resumed", grid_id)
        await self._notifier.grid_resumed(grid["symbol"], grid_id)

    async def stop_grid(self, grid_id: str, reason: str = "manual") -> None:
        """Stop a grid, selling all remaining holdings if stop-loss is the reason."""
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
    # Price trigger checks (called by the price-monitor loop in main.py)
    # ------------------------------------------------------------------

    async def check_grid_triggers(self, grid_id: str, current_price: float) -> None:
        """Check dip-buy, profit-sell, and stop-loss triggers for one grid.

        Safe to call on every price tick — guard conditions prevent duplicate
        orders and respect paused / stopped state.
        """
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

        # 2. Profit sell — only if no pending sell already in flight
        if (
            is_profit_triggered(current_price, grid["next_sell_price"])
            and await self._repos.orders.count_pending_side(grid_id, "sell") == 0
        ):
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

        # Idempotency: if a trade record already exists for this order, the fill
        # was already processed (e.g. by a previous recovery run or poll cycle).
        existing_trade = await self._repos.trade_history.get_by_order_id(order_id)
        if existing_trade:
            log.info(
                "handle_order_filled: fill for order %s already recorded "
                "(trade %s) — skipping to prevent double-apply",
                order_id, existing_trade["trade_id"],
            )
            return

        grid_id: str = order["grid_id"]
        grid = await self._repos.grids.get(grid_id)
        if not grid:
            log.warning("Order %s belongs to missing grid %s", order_id, grid_id)
            return

        actual_price = fill_price if fill_price > 0 else order["price"]
        actual_qty = fill_qty if fill_qty > 0 else order["quantity"]

        if order["side"] == "buy":
            await self._on_buy_filled(grid, order_id, actual_price, actual_qty)
        else:
            await self._on_sell_filled(grid, order_id, actual_price, actual_qty)

    # ------------------------------------------------------------------
    # Private: order execution helpers
    # ------------------------------------------------------------------

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
            log.error("Cannot compute dip buy qty for %s: %s", grid_id, exc)
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
            log.error("Cannot compute profit sell qty for %s: %s", grid_id, exc)
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

        # Unlike a profit sell (where the grid stays open and can simply
        # retry later), a stop-loss is a FINAL exit. If the clamped
        # remainder fails the shared rule check (e.g. it's an unsellable
        # "dust" amount below min_quantity/min_notional), we cannot leave
        # the grid open forever waiting for a sell that will never clear —
        # write the position off as dust, notify, and close the grid.
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
        self, grid: dict, order_id: str, fill_price: float, fill_qty: float
    ) -> None:
        grid_id = grid["grid_id"]
        symbol = grid["symbol"]
        investment_inr = fill_qty * fill_price

        new_total_inv, new_total_qty, new_avg = update_position_after_buy(
            grid["total_investment"], grid["total_quantity"], investment_inr, fill_qty
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
                investment_inr=investment_inr,
                fee=0.0,
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
                investment_inr=investment_inr,
                avg_entry_price=new_avg,
                next_buy_price=new_next_buy,
                next_sell_price=new_next_sell,
            )

    async def _on_sell_filled(
        self, grid: dict, order_id: str, fill_price: float, fill_qty: float
    ) -> None:
        grid_id = grid["grid_id"]
        symbol = grid["symbol"]

        new_total_inv, new_total_qty, pnl, avg_entry = update_position_after_sell(
            grid["total_investment"],
            grid["total_quantity"],
            grid["average_entry_price"],
            fill_qty,
            fill_price,
        )
        new_realized = grid["realized_profit"] + pnl
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
                investment_inr=proceeds_inr,
                fee=0.0,
                pnl=pnl,
                executed_at=now_iso(),
            )
        )
        await self._repos.daily_stats.add_trade(today, pnl)

        log.info(
            "Sell filled %s: qty %.8f @ ₹%.2f pnl ₹%.2f (total realized ₹%.2f)",
            grid_id, fill_qty, fill_price, pnl, new_realized,
        )

        await self._notifier.profit_sell_executed(
            symbol=symbol,
            grid_id=grid_id,
            quantity=fill_qty,
            sell_price=fill_price,
            avg_entry_price=avg_entry,
            pnl=pnl,
            total_realized=new_realized,
            cycles=new_cycles,
            next_sell_price=new_next_sell,
        )

        if new_status == GridStatus.COMPLETED.value:
            await self._notifier.grid_completed(symbol, grid_id, new_cycles, new_realized)
            log.info("Grid %s completed after %d sell cycles", grid_id, new_cycles)

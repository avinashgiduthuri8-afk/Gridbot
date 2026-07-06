"""Grid Lifecycle Manager: the central orchestrator that ties together the
grid generator, order manager, position manager, risk manager and
notifier to run a single grid's full lifecycle end-to-end.

One `GridManager` instance is shared across all active grids; each grid
is identified purely by its `grid_id` and all state lives in SQLite, so
grids survive process restarts without any special-casing here.
"""

from __future__ import annotations

from config.constants import GridStatus, GridType, OrderSide
from exchange.base import ExchangeClient
from grid.generator import build_grid_plan
from grid.lifecycle import compute_sell_price_for_level, is_price_out_of_range
from notifications.notifier import Notifier
from risk.risk_manager import RiskManager
from storage.models import GridLevelRecord, GridRecord
from storage.repositories import Repositories
from trading.order_manager import OrderManager
from trading.position_manager import PositionManager
from utils.helpers import new_id, now_iso, quantize, to_decimal
from utils.logger import get_logger

log = get_logger("grid")


class GridManagerError(Exception):
    pass


class GridManager:
    def __init__(
        self,
        exchange: ExchangeClient,
        repos: Repositories,
        order_manager: OrderManager,
        position_manager: PositionManager,
        risk_manager: RiskManager,
        notifier: Notifier,
    ) -> None:
        self._exchange = exchange
        self._repos = repos
        self._orders = order_manager
        self._positions = position_manager
        self._risk = risk_manager
        self._notifier = notifier

    async def start_grid(
        self,
        symbol: str,
        upper_price: float,
        lower_price: float,
        grid_levels: int,
        investment_per_grid: float,
        grid_type: GridType = GridType.ARITHMETIC,
    ) -> GridRecord:
        plan = build_grid_plan(
            symbol=symbol,
            grid_type=grid_type,
            upper_price=upper_price,
            lower_price=lower_price,
            grid_levels=grid_levels,
            investment_per_grid=investment_per_grid,
        )

        inr_balance = await self._exchange.get_balance("INR")
        risk_check = await self._risk.check_can_start_grid(
            symbol, plan.total_investment, inr_balance.balance
        )
        if not risk_check.allowed:
            raise GridManagerError(risk_check.reason)

        grid_id = new_id("grid")
        record = GridRecord(
            grid_id=grid_id,
            symbol=symbol,
            grid_type=grid_type.value,
            status=GridStatus.ACTIVE.value,
            upper_price=upper_price,
            lower_price=lower_price,
            grid_levels=grid_levels,
            investment_per_grid=investment_per_grid,
            created_at=now_iso(),
            updated_at=now_iso(),
        )
        await self._repos.grids.create(record)

        level_records = [
            GridLevelRecord(
                id=None, grid_id=grid_id, level_index=lv.level_index, price=lv.price,
                side="buy", is_filled=False,
            )
            for lv in plan.levels
        ]
        await self._repos.grid_levels.bulk_create(level_records)

        await self._repos.coin_configs.upsert(
            symbol=symbol, grid_levels=grid_levels, investment_per_grid=investment_per_grid,
            upper_price=upper_price, lower_price=lower_price, grid_type=grid_type.value,
        )

        ticker = await self._exchange.get_ticker(symbol)
        await self._place_initial_buy_ladder(grid_id, plan, ticker.last_price)

        await self._notifier.grid_started(symbol, grid_id, grid_levels, investment_per_grid)
        log.info("Started grid %s for %s (%s, %d levels)", grid_id, symbol, grid_type.value, grid_levels)
        return record

    async def _place_initial_buy_ladder(self, grid_id: str, plan, current_price: float) -> None:
        """Place a resting buy order at every grid level below the current
        market price. Levels above current price stay unarmed until price
        falls to them naturally (progression handles that on each tick)."""
        levels = await self._repos.grid_levels.list_for_grid(grid_id)
        for level in levels:
            if level["price"] >= current_price:
                continue
            quantity = quantize(
                to_decimal(plan.investment_per_grid / level["price"]) if level["price"] > 0 else to_decimal(0),
                8,
            )
            if quantity <= 0:
                continue
            try:
                order = await self._orders.place_grid_order(
                    grid_id=grid_id, symbol=plan.symbol, side=OrderSide.BUY.value,
                    price=level["price"], quantity=float(quantity), level_index=level["level_index"],
                )
                await self._repos.grid_levels.mark_filled(
                    grid_id, level["level_index"], "buy", order.order_id
                )
            except Exception as exc:  # noqa: BLE001 - keep placing remaining levels
                log.error("Failed to place initial buy at level %s: %s", level["level_index"], exc)

    async def on_buy_filled(self, grid_id: str, order: dict, plan_levels: list[dict]) -> None:
        """Called by the order monitor when a grid buy order fills:
        opens a position, then places the matching sell one level up."""
        grid = await self._repos.grids.get(grid_id)
        if grid is None:
            return

        position = await self._positions.open_position(
            grid_id=grid_id, symbol=order["symbol"], entry_order_id=order["order_id"],
            entry_price=order["price"], quantity=order["quantity"],
        )

        next_level = next(
            (lv for lv in plan_levels if lv["level_index"] == order["level_index"] + 1), None
        )
        if next_level is None:
            log.warning("No level above %s for grid %s; holding position without sell target",
                        order["level_index"], grid_id)
            return

        sell_price = compute_sell_price_for_level(order["price"], next_level["price"])
        sell_order = await self._orders.place_grid_order(
            grid_id=grid_id, symbol=order["symbol"], side=OrderSide.SELL.value,
            price=sell_price, quantity=order["quantity"], level_index=next_level["level_index"],
        )
        await self._repos.grid_levels.mark_filled(
            grid_id, next_level["level_index"], "sell", sell_order.order_id
        )
        await self._notifier.buy_executed(order["symbol"], order["price"], order["quantity"], grid_id)

    async def on_sell_filled(self, grid_id: str, order: dict) -> None:
        """Called when a grid sell fills: closes the matching position,
        realizes profit, and re-arms the level for another buy cycle."""
        open_positions = await self._repos.positions.list_open_for_grid(grid_id)
        if not open_positions:
            log.warning("Sell filled for grid %s but no open position found", grid_id)
            return

        position = min(open_positions, key=lambda p: p["entry_price"])
        profit = await self._positions.close_position(position, order["order_id"], order["price"])

        grid = await self._repos.grids.get(grid_id)
        if grid:
            new_total_invested = grid["total_invested"]
            new_profit = grid["realized_profit"] + profit
            new_cycles = grid["completed_cycles"] + 1
            await self._repos.grids.update_financials(grid_id, new_total_invested, new_profit, new_cycles)

        await self._repos.grid_levels.reset_level(grid_id, order["level_index"] - 1, "buy")
        await self._notifier.sell_executed(order["symbol"], order["price"], order["quantity"], profit, grid_id)

        # Re-place a buy order one level below the sell to keep the grid cycling.
        levels = await self._repos.grid_levels.list_for_grid(grid_id)
        buy_level = next((lv for lv in levels if lv["level_index"] == order["level_index"] - 1), None)
        if buy_level and grid and grid["status"] == GridStatus.ACTIVE.value:
            quantity = quantize(to_decimal(grid["investment_per_grid"] / buy_level["price"]), 8)
            if quantity > 0:
                new_order = await self._orders.place_grid_order(
                    grid_id=grid_id, symbol=order["symbol"], side=OrderSide.BUY.value,
                    price=buy_level["price"], quantity=float(quantity), level_index=buy_level["level_index"],
                )
                await self._repos.grid_levels.mark_filled(
                    grid_id, buy_level["level_index"], "buy", new_order.order_id
                )

    async def pause_grid(self, grid_id: str) -> None:
        grid = await self._repos.grids.get(grid_id)
        if not grid:
            raise GridManagerError("Grid not found.")
        for order in await self._repos.orders.list_for_grid(grid_id):
            if order["status"] in ("open", "pending", "partially_filled"):
                await self._orders.cancel_order(order["order_id"])
        await self._repos.grids.update_status(grid_id, GridStatus.PAUSED.value)
        await self._notifier.grid_paused(grid["symbol"], grid_id)

    async def resume_grid(self, grid_id: str) -> None:
        grid = await self._repos.grids.get(grid_id)
        if not grid:
            raise GridManagerError("Grid not found.")
        inr_balance = await self._exchange.get_balance("INR")
        risk_check = await self._risk.check_can_place_order(grid["investment_per_grid"], inr_balance.balance)
        if not risk_check.allowed:
            raise GridManagerError(risk_check.reason)

        await self._repos.grids.update_status(grid_id, GridStatus.ACTIVE.value)
        ticker = await self._exchange.get_ticker(grid["symbol"])
        from grid.generator import build_grid_plan

        plan = build_grid_plan(
            symbol=grid["symbol"], grid_type=GridType(grid["grid_type"]),
            upper_price=grid["upper_price"], lower_price=grid["lower_price"],
            grid_levels=grid["grid_levels"], investment_per_grid=grid["investment_per_grid"],
        )
        await self._place_initial_buy_ladder(grid_id, plan, ticker.last_price)
        await self._notifier.grid_resumed(grid["symbol"], grid_id)

    async def stop_grid(self, grid_id: str, reason: str = "Manually stopped by user") -> None:
        grid = await self._repos.grids.get(grid_id)
        if not grid:
            raise GridManagerError("Grid not found.")
        for order in await self._repos.orders.list_for_grid(grid_id):
            if order["status"] in ("open", "pending", "partially_filled"):
                await self._orders.cancel_order(order["order_id"])
        await self._repos.grids.update_status(grid_id, GridStatus.STOPPED.value, reason)
        await self._notifier.grid_stopped(grid["symbol"], grid_id, reason)

    async def check_range_breach(self, grid_id: str) -> None:
        """Auto-pause a grid whose price has moved entirely outside its
        configured band, to avoid endlessly resting orders no one will fill."""
        grid = await self._repos.grids.get(grid_id)
        if not grid or grid["status"] != GridStatus.ACTIVE.value:
            return
        ticker = await self._exchange.get_ticker(grid["symbol"])
        breach = is_price_out_of_range(ticker.last_price, grid["upper_price"], grid["lower_price"])
        if breach:
            await self.pause_grid(grid_id)
            await self._notifier.error(
                "Grid Range Breach",
                f"{grid['symbol']} price moved {breach} the configured grid range. Grid auto-paused.",
            )

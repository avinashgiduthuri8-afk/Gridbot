"""Position Manager: tracks open inventory acquired by filled grid buys
until it is closed out by the matching sell.
"""

from __future__ import annotations

from grid.lifecycle import compute_step_profit
from storage.models import PositionRecord, TradeHistoryRecord
from storage.repositories import Repositories
from utils.helpers import new_id, now_iso
from utils.logger import get_logger

log = get_logger("trading")


class PositionManager:
    def __init__(self, repos: Repositories) -> None:
        self._repos = repos

    async def open_position(
        self, grid_id: str, symbol: str, entry_order_id: str, entry_price: float, quantity: float
    ) -> PositionRecord:
        position = PositionRecord(
            position_id=new_id("pos"),
            grid_id=grid_id,
            symbol=symbol,
            entry_order_id=entry_order_id,
            entry_price=entry_price,
            quantity=quantity,
            status="open",
            created_at=now_iso(),
        )
        await self._repos.positions.create(position)
        log.info("Opened position %s for %s: %.8f @ %.8f", position.position_id, symbol, quantity, entry_price)
        return position

    async def close_position(
        self, position: dict, exit_order_id: str, exit_price: float, fee_rate: float = 0.001
    ) -> float:
        step = compute_step_profit(
            buy_price=position["entry_price"],
            sell_price=exit_price,
            quantity=position["quantity"],
            fee_rate=fee_rate,
        )
        await self._repos.positions.close(
            position["position_id"], exit_order_id, exit_price, step.net_profit
        )
        await self._repos.trade_history.record(
            TradeHistoryRecord(
                trade_id=new_id("trd"),
                grid_id=position["grid_id"],
                order_id=exit_order_id,
                symbol=position["symbol"],
                side="sell",
                price=exit_price,
                quantity=position["quantity"],
                fee=step.fee,
                pnl=step.net_profit,
                executed_at=now_iso(),
            )
        )
        today = now_iso()[:10]
        await self._repos.daily_stats.add_trade(today, step.net_profit)
        log.info(
            "Closed position %s: buy %.8f -> sell %.8f, net profit ₹%.2f",
            position["position_id"], position["entry_price"], exit_price, step.net_profit,
        )
        return step.net_profit

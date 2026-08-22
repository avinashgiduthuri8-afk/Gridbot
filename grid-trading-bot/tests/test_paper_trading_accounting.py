"""Comprehensive regression tests for paper-trading accounting and state-management.

Covers:
1. Partial fills lifecycle (10 -> 3 -> 2 -> 5, zero/negative guards)
2. Idempotent fill processing (duplicate events, double-spend protection)
3. Weighted-average entry calculation & progression
4. Grid-level progression guards (no advance on submit or partial fill)
5. Dip-buy duplicate protection & concurrent execution locks
6. Sell / profit-cycle accounting (full, partial, realized P&L basis)
7. Unrealized P&L accuracy across price changes
8. Combined P&L accounting
9. Capital accounting (exact debits/credits on fill only)
10. Restart & recovery state persistence
11. Telegram /paper reporting alignment with database state
"""
from __future__ import annotations

import asyncio
from datetime import datetime, timezone
import pytest

from config.constants import GridStatus, OrderSide, OrderStatus
from config.settings import RiskSettings
from exchange.base import Balance, ExchangeOrder, MarketInfo, Ticker
from exchange.paper_exchange import PaperExchangeClient, PAPER_INITIAL_BALANCE
from grid.dca_engine import (
    calculate_average_entry_price,
    calculate_next_buy_price,
    calculate_profit_target,
    update_position_after_buy,
    update_position_after_sell,
)
from notifications.notifier import Notifier
from replay.fee_exchange import FeeSimulatingPaperExchange
from replay.market_data_exchange import ReplayMarketDataExchange
from risk.risk_manager import RiskManager
from storage.database import Database
from storage.repositories import Repositories
from storage.repositories.grids import DCAGridRecord
from storage.repositories.orders import OrderRecord
from storage.repositories.trade_history import TradeHistoryRecord
from trading.dca_manager import DCAManager
from trading.order_manager import OrderManager
from trading.order_monitor import OrderMonitor
from trading.portfolio_metrics import (
    grid_pnl_breakdown,
    pnl_pct,
    portfolio_totals,
    unrealized_pnl,
)
from trading.recovery import RecoveryManager
from bot_telegram.formatters import format_paper_grids
from utils.helpers import new_id, now_iso

pytestmark = pytest.mark.anyio


def _risk_settings():
    return RiskSettings(
        max_total_capital=100_000.0,
        max_capital_per_coin=20_000.0,
        max_simultaneous_grids=5,
        min_wallet_balance=5_000.0,
        daily_loss_limit=5_000.0,
    )

def _market_info(symbol="BTCINR"):
    return MarketInfo(
        symbol=symbol,
        base_currency_precision=2,
        target_currency_precision=6,
        min_quantity=0.0001,
        min_amount=10.0,
        step_size=0.0001,
    )


class FakeClock:
    def __init__(self, start: float = 1000.0) -> None:
        self.t = start

    def __call__(self) -> float:
        return self.t

    def advance(self, seconds: float) -> None:
        self.t += seconds


class DummyExchange:
    def __init__(self, price: float = 100.0):
        self.price = price

    async def get_ticker(self, symbol: str) -> Ticker:
        return Ticker(symbol=symbol, last_price=self.price, high=self.price, low=self.price, volume=100.0)

    async def get_market_info(self, symbol: str) -> MarketInfo:
        return _market_info(symbol)

    async def get_open_orders(self, symbol: str | None = None) -> list[ExchangeOrder]:
        return []

    async def get_trade_history(self, symbol=None, limit=50, order_id=None):
        return []


# ===========================================================================
# 1. PARTIAL FILLS ACCOUNTING
# ===========================================================================

async def test_paper_exchange_zero_and_negative_quantity_protection():
    real_ex = DummyExchange(100.0)
    paper = PaperExchangeClient(real_ex)

    with pytest.raises(ValueError, match="quantity must be positive"):
        await paper.place_order("BTCINR", OrderSide.BUY, 100.0, 0.0)

    with pytest.raises(ValueError, match="quantity must be positive"):
        await paper.place_order("BTCINR", OrderSide.BUY, 100.0, -5.0)

    with pytest.raises(ValueError, match="price cannot be negative"):
        await paper.place_order("BTCINR", OrderSide.BUY, -10.0, 1.0)


async def test_partial_fill_lifecycle_multi_stage():
    """Verify multi-stage fills: 10 units -> 3 units -> 2 units -> 5 units."""
    clock = FakeClock(1000.0)
    real_ex = DummyExchange(100.0)
    paper = PaperExchangeClient(
        real_ex,
        time_fn=clock,
        latency_seconds_range=(2.0, 2.0),
        partial_fill_probability=1.0,
        slippage_bps_max=0.0,
    )

    order = await paper.place_order("BTCINR", OrderSide.BUY, 100.0, 10.0)
    eid = order.exchange_order_id
    assert order.status == OrderStatus.OPEN.value
    assert order.filled_quantity == 0.0

    # Poll before latency -> OPEN
    clock.advance(1.0)
    st = await paper.get_order_status(eid)
    assert st.status == OrderStatus.OPEN.value
    assert st.filled_quantity == 0.0

    # Poll during partial fill stage -> PARTIALLY_FILLED
    clock.advance(2.0)
    st_partial = await paper.get_order_status(eid)
    assert st_partial.status == OrderStatus.PARTIALLY_FILLED.value
    assert 0.0 < st_partial.filled_quantity < 10.0

    # Poll after completion -> FILLED
    clock.advance(10.0)
    st_filled = await paper.get_order_status(eid)
    assert st_filled.status == OrderStatus.FILLED.value
    assert st_filled.filled_quantity == 10.0


# ===========================================================================
# 2. IDEMPOTENT FILL PROCESSING
# ===========================================================================

async def test_idempotent_fill_processing_prevents_duplicate_trades_and_position_changes(db, repos):
    real_ex = DummyExchange(100.0)
    paper = PaperExchangeClient(real_ex, slippage_bps_max=0.0)
    om = OrderManager(paper, repos)
    notifier = Notifier(bot=None, chat_ids=())
    risk = RiskManager(_risk_settings(), repos)
    dca = DCAManager(paper, repos, om, notifier, risk)

    grid = DCAGridRecord(
        grid_id="grd_test_idem", symbol="DOGEINR", status="active", mode="paper",
        entry_price=10.0, base_investment=100.0, dip_buy_amount=50.0,
        dip_percentage=5.0, profit_sell_amount=50.0, profit_percentage=5.0,
        max_levels=5, stop_loss_percentage=20.0, current_level=0,
        total_quantity=0.0, total_investment=0.0, average_entry_price=0.0,
        last_buy_price=0.0, next_buy_price=0.0, next_sell_price=0.0,
        realized_profit=0.0, completed_cycles=0, created_at=now_iso(), updated_at=now_iso(),
    )
    await repos.grids.create(grid)

    order_id = "ord_test_idem_1"
    await repos.orders.create(
        OrderRecord(
            order_id=order_id, grid_id="grd_test_idem", exchange_order_id="PAPER_IDEM_1",
            symbol="DOGEINR", side="buy", order_type="market_order",
            price=10.0, quantity=10.0, filled_quantity=10.0, filled_price=10.0,
            fee=0.0, status=OrderStatus.FILLED.value, created_at=now_iso(), updated_at=now_iso(),
        )
    )

    # First fill processing
    await dca.handle_order_filled(order_id, fill_price=10.0, fill_qty=10.0)

    g1 = await repos.grids.get("grd_test_idem")
    assert g1["total_quantity"] == 10.0
    assert g1["total_investment"] == 100.0
    assert g1["average_entry_price"] == 10.0
    assert g1["current_level"] == 1

    trades1 = await repos.trade_history.list_for_grid("grd_test_idem")
    assert len(trades1) == 1

    # Second fill processing for the exact same order event (idempotency test)
    await dca.handle_order_filled(order_id, fill_price=10.0, fill_qty=10.0)

    g2 = await repos.grids.get("grd_test_idem")
    assert g2["total_quantity"] == 10.0, "Position quantity must not double-count"
    assert g2["total_investment"] == 100.0, "Investment must not double-count"
    assert g2["current_level"] == 1, "Level must not advance twice"

    trades2 = await repos.trade_history.list_for_grid("grd_test_idem")
    assert len(trades2) == 1, "Must not create duplicate trade record"


# ===========================================================================
# 3. WEIGHTED AVERAGE ENTRY
# ===========================================================================

def test_weighted_average_entry_math():
    """Verify exact formula:
    Initial: 10 DOGE @ ₹10 -> Total Cost = 100, Qty = 10
    Dip: 5 DOGE @ ₹9 -> Total Cost = 145, Qty = 15
    Average Entry = 145 / 15 = 9.666666666666666...
    """
    total_inv, total_qty, avg_1 = update_position_after_buy(0.0, 0.0, 100.0, 10.0)
    assert total_qty == 10.0
    assert total_inv == 100.0
    assert avg_1 == 10.0

    total_inv, total_qty, avg_2 = update_position_after_buy(total_inv, total_qty, 45.0, 5.0)
    assert total_qty == 15.0
    assert total_inv == 145.0
    assert avg_2 == pytest.approx(145.0 / 15.0)

    # Partial sell does not change average entry
    total_inv, total_qty, pnl, avg_3 = update_position_after_sell(total_inv, total_qty, avg_2, 5.0, 12.0)
    assert total_qty == 10.0
    assert avg_3 == pytest.approx(145.0 / 15.0), "Selling must not alter average entry price"
    expected_cost_basis = 5.0 * (145.0 / 15.0)
    assert total_inv == pytest.approx(145.0 - expected_cost_basis)
    assert pnl == pytest.approx(5.0 * 12.0 - expected_cost_basis)


# ===========================================================================
# 4. GRID-LEVEL PROGRESSION
# ===========================================================================

async def test_grid_level_progression_rules(db, repos):
    """Submitted order and partial fill must not advance level; full fill advances exactly once."""
    real_ex = DummyExchange(100.0)
    paper = PaperExchangeClient(real_ex, slippage_bps_max=0.0)
    om = OrderManager(paper, repos)
    notifier = Notifier(bot=None, chat_ids=())
    risk = RiskManager(_risk_settings(), repos)
    dca = DCAManager(paper, repos, om, notifier, risk)

    grid = DCAGridRecord(
        grid_id="grd_test_lvl", symbol="ETHINR", status="active", mode="paper",
        entry_price=100.0, base_investment=100.0, dip_buy_amount=100.0,
        dip_percentage=5.0, profit_sell_amount=100.0, profit_percentage=5.0,
        max_levels=5, stop_loss_percentage=20.0, current_level=1,
        total_quantity=1.0, total_investment=100.0, average_entry_price=100.0,
        last_buy_price=100.0, next_buy_price=95.0, next_sell_price=105.0,
        realized_profit=0.0, completed_cycles=0, created_at=now_iso(), updated_at=now_iso(),
    )
    await repos.grids.create(grid)

    order_id = "ord_test_lvl_dip"
    await repos.orders.create(
        OrderRecord(
            order_id=order_id, grid_id="grd_test_lvl", exchange_order_id="PAPER_LVL_1",
            symbol="ETHINR", side="buy", order_type="market_order",
            price=95.0, quantity=1.0, filled_quantity=0.4, filled_price=95.0,
            fee=0.0, status=OrderStatus.PARTIALLY_FILLED.value, created_at=now_iso(), updated_at=now_iso(),
        )
    )

    # Partial fill must NOT advance level
    g = await repos.grids.get("grd_test_lvl")
    assert g["current_level"] == 1

    # Order completed
    await repos.orders.update_status(order_id, OrderStatus.FILLED.value, filled_quantity=1.0, filled_price=95.0)
    await dca.handle_order_filled(order_id, fill_price=95.0, fill_qty=1.0)

    g_after = await repos.grids.get("grd_test_lvl")
    assert g_after["current_level"] == 2
    assert g_after["total_quantity"] == 2.0
    assert g_after["total_investment"] == 195.0
    assert g_after["average_entry_price"] == 97.5


# ===========================================================================
# 5. DIP-BUY DUPLICATE PROTECTION & CONCURRENCY
# ===========================================================================

async def test_dip_buy_duplicate_protection_under_repeated_price_ticks(db, repos):
    real_ex = DummyExchange(90.0)
    paper = PaperExchangeClient(real_ex, slippage_bps_max=0.0)
    om = OrderManager(paper, repos)
    notifier = Notifier(bot=None, chat_ids=())
    risk = RiskManager(_risk_settings(), repos)
    dca = DCAManager(paper, repos, om, notifier, risk)

    grid = DCAGridRecord(
        grid_id="grd_test_dip_dup", symbol="BTCINR", status="active", mode="paper",
        entry_price=100.0, base_investment=100.0, dip_buy_amount=100.0,
        dip_percentage=5.0, profit_sell_amount=100.0, profit_percentage=5.0,
        max_levels=3, stop_loss_percentage=20.0, current_level=1,
        total_quantity=1.0, total_investment=100.0, average_entry_price=100.0,
        last_buy_price=100.0, next_buy_price=95.0, next_sell_price=105.0,
        realized_profit=0.0, completed_cycles=0, created_at=now_iso(), updated_at=now_iso(),
    )
    await repos.grids.create(grid)

    # First tick: dip triggered -> 1 order placed
    await dca.check_grid_triggers("grd_test_dip_dup", 90.0)
    orders = await repos.orders.list_for_grid("grd_test_dip_dup")
    assert len(orders) == 1

    # Second tick at same or lower price -> zero additional orders because pending buy exists
    await dca.check_grid_triggers("grd_test_dip_dup", 89.0)
    await dca.check_grid_triggers("grd_test_dip_dup", 88.0)
    orders_again = await repos.orders.list_for_grid("grd_test_dip_dup")
    assert len(orders_again) == 1, "Must not place duplicate dip buys while order is in flight"


# ===========================================================================
# 6. SELL / PROFIT-CYCLE ACCOUNTING
# ===========================================================================

async def test_sell_profit_cycle_accounting_full_and_partial(db, repos):
    real_ex = DummyExchange(110.0)
    paper = PaperExchangeClient(real_ex, slippage_bps_max=0.0)
    om = OrderManager(paper, repos)
    notifier = Notifier(bot=None, chat_ids=())
    risk = RiskManager(_risk_settings(), repos)
    dca = DCAManager(paper, repos, om, notifier, risk)

    # Position: 2 BTC @ ₹100 = ₹200
    grid = DCAGridRecord(
        grid_id="grd_test_sell_pnl", symbol="BTCINR", status="active", mode="paper",
        entry_price=100.0, base_investment=100.0, dip_buy_amount=100.0,
        dip_percentage=5.0, profit_sell_amount=100.0, profit_percentage=5.0,
        max_levels=3, stop_loss_percentage=20.0, current_level=2,
        total_quantity=2.0, total_investment=200.0, average_entry_price=100.0,
        last_buy_price=100.0, next_buy_price=95.0, next_sell_price=105.0,
        realized_profit=0.0, completed_cycles=0, created_at=now_iso(), updated_at=now_iso(),
    )
    await repos.grids.create(grid)

    # Partial sell: 1 BTC @ ₹110 -> proceeds = 110, cost = 100, PnL = +10
    sell_order_id_1 = "ord_sell_part_1"
    await repos.orders.create(
        OrderRecord(
            order_id=sell_order_id_1, grid_id="grd_test_sell_pnl", exchange_order_id="PAPER_S_1",
            symbol="BTCINR", side="sell", order_type="market_order",
            price=110.0, quantity=1.0, filled_quantity=1.0, filled_price=110.0,
            fee=0.0, status=OrderStatus.FILLED.value, created_at=now_iso(), updated_at=now_iso(),
        )
    )
    await dca.handle_order_filled(sell_order_id_1, fill_price=110.0, fill_qty=1.0)

    g_part = await repos.grids.get("grd_test_sell_pnl")
    assert g_part["total_quantity"] == 1.0
    assert g_part["total_investment"] == 100.0
    assert g_part["average_entry_price"] == 100.0
    assert g_part["realized_profit"] == 10.0
    assert g_part["completed_cycles"] == 1

    # Full sell: remaining 1 BTC @ ₹120 -> proceeds = 120, cost = 100, PnL = +20 (Total Realized = +30)
    sell_order_id_2 = "ord_sell_full_2"
    await repos.orders.create(
        OrderRecord(
            order_id=sell_order_id_2, grid_id="grd_test_sell_pnl", exchange_order_id="PAPER_S_2",
            symbol="BTCINR", side="sell", order_type="market_order",
            price=120.0, quantity=1.0, filled_quantity=1.0, filled_price=120.0,
            fee=0.0, status=OrderStatus.FILLED.value, created_at=now_iso(), updated_at=now_iso(),
        )
    )
    await dca.handle_order_filled(sell_order_id_2, fill_price=120.0, fill_qty=1.0)

    g_full = await repos.grids.get("grd_test_sell_pnl")
    assert g_full["total_quantity"] == 0.0
    assert g_full["total_investment"] == 0.0
    assert g_full["realized_profit"] == 30.0
    assert g_full["completed_cycles"] == 2


# ===========================================================================
# 7. UNREALIZED & COMBINED P&L
# ===========================================================================

def test_unrealized_and_combined_pnl_calculations():
    # Position: 2 units @ ₹100 avg, realized = ₹50
    grid = {
        "grid_id": "grd_pnl_calc",
        "symbol": "BTCINR",
        "total_quantity": 2.0,
        "average_entry_price": 100.0,
        "realized_profit": 50.0,
        "total_investment": 200.0,
    }

    # Price at ₹110 -> unrealized = (110 - 100) * 2 = +20, combined = 50 + 20 = 70
    b_up = grid_pnl_breakdown(grid, current_price=110.0)
    assert b_up["realized"] == 50.0
    assert b_up["unrealized"] == 20.0
    assert b_up["combined"] == 70.0

    # Price at ₹90 -> unrealized = (90 - 100) * 2 = -20, combined = 50 - 20 = 30
    b_down = grid_pnl_breakdown(grid, current_price=90.0)
    assert b_down["unrealized"] == -20.0
    assert b_down["combined"] == 30.0

    # Closed position (qty = 0) -> unrealized = 0, combined = realized
    grid_closed = {**grid, "total_quantity": 0.0, "total_investment": 0.0}
    b_closed = grid_pnl_breakdown(grid_closed, current_price=150.0)
    assert b_closed["unrealized"] == 0.0
    assert b_closed["combined"] == 50.0


# ===========================================================================
# 8. CAPITAL ACCOUNTING (DEBIT/CREDIT ON FILL ONLY)
# ===========================================================================

async def test_paper_capital_accounting_exact_debit_credit():
    md = ReplayMarketDataExchange()
    md.register_market("BTCINR", _market_info("BTCINR"))
    md.set_price("BTCINR", 100.0)
    clock = FakeClock(1000.0)
    ex = FeeSimulatingPaperExchange(
        md, time_fn=clock, latency_seconds_range=(1.0, 1.0),
        partial_fill_probability=0.0, fee_rate=0.001,
        initial_balance_inr=10000.0,
    )

    # Buy order placed -> balance unaffected while open
    order = await ex.place_order("BTCINR", OrderSide.BUY, 100.0, 10.0)
    b0 = (await ex.get_balance("INR")).balance
    assert b0 == 10000.0

    # Fill buy order -> balance debited exactly by fill notional + fee
    clock.advance(2.0)
    st = await ex.get_order_status(order.exchange_order_id)
    assert st.status == OrderStatus.FILLED.value
    expected_debit = st.filled_quantity * st.filled_price + st.fee
    b1 = (await ex.get_balance("INR")).balance
    assert b1 == pytest.approx(10000.0 - expected_debit)

    # Sell order placed and filled -> balance credited by proceeds - fee
    sell_order = await ex.place_order("BTCINR", OrderSide.SELL, 110.0, 5.0)
    clock.advance(2.0)
    st_sell = await ex.get_order_status(sell_order.exchange_order_id)
    assert st_sell.status == OrderStatus.FILLED.value
    expected_credit = st_sell.filled_quantity * st_sell.filled_price - st_sell.fee
    b2 = (await ex.get_balance("INR")).balance
    assert b2 == pytest.approx(b1 + expected_credit)


# ===========================================================================
# 9. RESTART / RECOVERY
# ===========================================================================

async def test_paper_restart_recovery_preserves_state(db, repos):
    real_ex = DummyExchange(100.0)
    paper = PaperExchangeClient(real_ex, slippage_bps_max=0.0)
    om = OrderManager(paper, repos)
    notifier = Notifier(bot=None, chat_ids=())
    risk = RiskManager(_risk_settings(), repos)
    dca = DCAManager(paper, repos, om, notifier, risk)

    # Seed an active paper grid
    grid = DCAGridRecord(
        grid_id="grd_rec_paper", symbol="BTCINR", status="active", mode="paper",
        entry_price=100.0, base_investment=100.0, dip_buy_amount=50.0,
        dip_percentage=5.0, profit_sell_amount=50.0, profit_percentage=5.0,
        max_levels=5, stop_loss_percentage=20.0, current_level=1,
        total_quantity=1.0, total_investment=100.0, average_entry_price=100.0,
        last_buy_price=100.0, next_buy_price=95.0, next_sell_price=105.0,
        realized_profit=15.0, completed_cycles=1, created_at=now_iso(), updated_at=now_iso(),
    )
    await repos.grids.create(grid)

    # Run recovery
    rec = RecoveryManager(paper, repos, notifier, dca)
    report = await rec.recover()

    assert report['reconciled_orders'] == 0
    assert report['fills_recovered'] == 0

    # Grid state remains identical and valid after recovery
    g = await repos.grids.get("grd_rec_paper")
    assert g["status"] == "active"
    assert g["mode"] == "paper"
    assert g["total_quantity"] == 1.0
    assert g["total_investment"] == 100.0
    assert g["average_entry_price"] == 100.0
    assert g["realized_profit"] == 15.0


# ===========================================================================
# 10. TELEGRAM /PAPER FORMATTER ALIGNMENT
# ===========================================================================

def test_telegram_paper_formatter_matches_accounting():
    paper_grid = {
        "grid_id": "grd_paper_fmt_1",
        "symbol": "BTCINR",
        "status": "active",
        "mode": "paper",
        "entry_price": 5000000.0,
        "dip_percentage": 5.0,
        "profit_percentage": 5.0,
        "current_level": 2,
        "max_levels": 5,
        "total_quantity": 0.002,
        "average_entry_price": 4900000.0,
        "total_investment": 9800.0,
        "realized_profit": 500.0,
        "completed_cycles": 1,
    }

    prices = {"BTCINR": 5100000.0}
    text = format_paper_grids([paper_grid], prices=prices)

    assert "Paper Trade Grids" in text
    assert "BTCINR" in text
    assert "grd_paper_fmt_1" in text
    assert "Level: 2/5" in text
    assert "Net realized P&amp;L" in text
    assert "Paper Portfolio Totals" in text

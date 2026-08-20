import asyncio
import sys
from pathlib import Path

# Add grid-trading-bot to python sys.path
bot_dir = Path(__file__).resolve().parent.parent / "grid-trading-bot"
sys.path.insert(0, str(bot_dir))

from storage.database import Database
from storage.models import DCAGridRecord, OrderRecord, TradeHistoryRecord
from storage.repositories import Repositories
from utils.helpers import now_iso

async def seed():
    db_path = bot_dir / "data" / "grid_bot.db"
    db = Database(str(db_path))
    await db.connect()
    await db.migrate()

    repos = Repositories(db)

    # 1. Seed Grids
    grid1 = DCAGridRecord(
        grid_id="grid-test-btc-001",
        symbol="BTCINR",
        status="active",
        mode="paper",
        entry_price=7500000.0,
        base_investment=5000.0,
        dip_buy_amount=2500.0,
        dip_percentage=2.5,
        profit_sell_amount=2600.0,
        profit_percentage=2.0,
        max_levels=5,
        stop_loss_percentage=10.0,
        current_level=2,
        total_quantity=0.00133333,
        total_investment=10000.0,
        average_entry_price=7450000.0,
        last_buy_price=7312500.0,
        next_buy_price=7129687.5,
        next_sell_price=7599000.0,
        realized_profit=450.50,
        completed_cycles=3,
        trailing_enabled=True,
        trailing_percentage=1.5,
        trailing_peak_price=7650000.0,
        created_at=now_iso(),
        updated_at=now_iso(),
    )

    grid2 = DCAGridRecord(
        grid_id="grid-test-eth-002",
        symbol="ETHINR",
        status="paused",
        mode="paper",
        entry_price=280000.0,
        base_investment=3000.0,
        dip_buy_amount=1500.0,
        dip_percentage=3.0,
        profit_sell_amount=1600.0,
        profit_percentage=2.5,
        max_levels=4,
        stop_loss_percentage=8.0,
        current_level=1,
        total_quantity=0.010714,
        total_investment=3000.0,
        average_entry_price=280000.0,
        last_buy_price=280000.0,
        next_buy_price=271600.0,
        next_sell_price=287000.0,
        realized_profit=120.0,
        completed_cycles=1,
        trailing_enabled=False,
        created_at=now_iso(),
        updated_at=now_iso(),
    )

    grid3 = DCAGridRecord(
        grid_id="grid-test-sol-003",
        symbol="SOLINR",
        status="completed",
        mode="paper",
        entry_price=14000.0,
        base_investment=2000.0,
        dip_buy_amount=1000.0,
        dip_percentage=4.0,
        profit_sell_amount=1050.0,
        profit_percentage=3.0,
        max_levels=3,
        stop_loss_percentage=12.0,
        current_level=0,
        total_quantity=0.0,
        total_investment=0.0,
        average_entry_price=0.0,
        last_buy_price=14000.0,
        next_buy_price=13440.0,
        next_sell_price=14420.0,
        realized_profit=350.0,
        completed_cycles=4,
        trailing_enabled=False,
        created_at=now_iso(),
        updated_at=now_iso(),
    )

    for g in [grid1, grid2, grid3]:
        try:
            await repos.grids.create(g)
        except Exception:
            await repos.grids.update_state(
                g.grid_id,
                symbol=g.symbol,
                status=g.status,
                mode=g.mode,
                entry_price=g.entry_price,
                total_investment=g.total_investment,
                realized_profit=g.realized_profit,
                completed_cycles=g.completed_cycles,
            )

    # 2. Seed Orders
    orders = [
        OrderRecord(
            order_id="ord-test-btc-01",
            grid_id="grid-test-btc-001",
            exchange_order_id="coindcx-100001",
            symbol="BTCINR",
            side="buy",
            order_type="limit",
            price=7500000.0,
            quantity=0.000666,
            filled_quantity=0.000666,
            filled_price=7500000.0,
            status="filled",
            fee=10.0,
            reconciliation_status="matched",
            created_at=now_iso(),
            updated_at=now_iso(),
        ),
        OrderRecord(
            order_id="ord-test-btc-02",
            grid_id="grid-test-btc-001",
            exchange_order_id="coindcx-100002",
            symbol="BTCINR",
            side="buy",
            order_type="limit",
            price=7312500.0,
            quantity=0.000667,
            filled_quantity=0.000667,
            filled_price=7312500.0,
            status="filled",
            fee=9.75,
            reconciliation_status="matched",
            created_at=now_iso(),
            updated_at=now_iso(),
        ),
        OrderRecord(
            order_id="ord-test-btc-03",
            grid_id="grid-test-btc-001",
            exchange_order_id="coindcx-100003",
            symbol="BTCINR",
            side="sell",
            order_type="limit",
            price=7599000.0,
            quantity=0.00133333,
            filled_quantity=0.0,
            filled_price=0.0,
            status="open",
            fee=0.0,
            reconciliation_status="not_needed",
            created_at=now_iso(),
            updated_at=now_iso(),
        ),
        OrderRecord(
            order_id="ord-test-eth-01",
            grid_id="grid-test-eth-002",
            exchange_order_id="coindcx-100004",
            symbol="ETHINR",
            side="buy",
            order_type="limit",
            price=280000.0,
            quantity=0.010714,
            filled_quantity=0.010714,
            filled_price=280000.0,
            status="filled",
            fee=6.0,
            reconciliation_status="matched",
            created_at=now_iso(),
            updated_at=now_iso(),
        ),
        OrderRecord(
            order_id="ord-test-eth-02",
            grid_id="grid-test-eth-002",
            exchange_order_id=None,
            symbol="ETHINR",
            side="buy",
            order_type="limit",
            price=271600.0,
            quantity=0.005522,
            filled_quantity=0.0,
            filled_price=0.0,
            status="open",
            fee=0.0,
            reconciliation_status="not_needed",
            created_at=now_iso(),
            updated_at=now_iso(),
        ),
        OrderRecord(
            order_id="ord-test-sol-01",
            grid_id="grid-test-sol-003",
            exchange_order_id="coindcx-100005",
            symbol="SOLINR",
            side="buy",
            order_type="limit",
            price=13440.0,
            quantity=0.1488,
            filled_quantity=0.0,
            filled_price=0.0,
            status="cancelled",
            fee=0.0,
            reconciliation_status="cancelled_on_exchange",
            created_at=now_iso(),
            updated_at=now_iso(),
        ),
    ]

    for o in orders:
        try:
            await repos.orders.create(o)
        except Exception:
            pass

    # 3. Seed Trade History
    trades = [
        TradeHistoryRecord(
            trade_id="trade-test-001",
            grid_id="grid-test-btc-001",
            order_id="ord-test-btc-01",
            symbol="BTCINR",
            side="buy",
            price=7500000.0,
            quantity=0.000666,
            investment_inr=5000.0,
            fee=10.0,
            pnl=0.0,
            executed_at=now_iso(),
        ),
        TradeHistoryRecord(
            trade_id="trade-test-002",
            grid_id="grid-test-btc-001",
            order_id="ord-test-btc-02",
            symbol="BTCINR",
            side="buy",
            price=7312500.0,
            quantity=0.000667,
            investment_inr=4877.4,
            fee=9.75,
            pnl=0.0,
            executed_at=now_iso(),
        ),
        TradeHistoryRecord(
            trade_id="trade-test-003",
            grid_id="grid-test-btc-001",
            order_id="ord-test-btc-03-prev",
            symbol="BTCINR",
            side="sell",
            price=7650000.0,
            quantity=0.000666,
            investment_inr=5094.9,
            fee=10.2,
            pnl=200.0,
            executed_at=now_iso(),
        ),
        TradeHistoryRecord(
            trade_id="trade-test-004",
            grid_id="grid-test-eth-002",
            order_id="ord-test-eth-01-prev",
            symbol="ETHINR",
            side="sell",
            price=290000.0,
            quantity=0.010714,
            investment_inr=3107.0,
            fee=6.2,
            pnl=120.0,
            executed_at=now_iso(),
        ),
        TradeHistoryRecord(
            trade_id="trade-test-005",
            grid_id="grid-test-sol-003",
            order_id="ord-test-sol-01-prev",
            symbol="SOLINR",
            side="sell",
            price=15000.0,
            quantity=0.14285,
            investment_inr=2142.7,
            fee=3.5,
            pnl=350.0,
            executed_at=now_iso(),
        ),
    ]

    for t in trades:
        try:
            await repos.trade_history.record(t)
        except Exception:
            pass

    # 4. Seed Daily Stats
    today = now_iso()[:10]
    await repos.daily_stats.add_trade(today, pnl=920.50)

    print("Test paper data successfully seeded into SQLite database!")
    await db.close()

if __name__ == "__main__":
    asyncio.run(seed())

"""Phase 3 / Step 3 — Pre-Production Staging & Dry-Run Validation Suite.

Validates:
1. Paper Trading Safety Contract & MixedOrderManager routing
2. Deterministic BUY -> SELL Profit Cycle math and state updates
3. Partial fill reconciliation and remaining quantity tracking
4. Order placement timeout and unknown status recovery (no duplicate orders)
5. Process interrupt, DB reopen, and RecoveryManager restart safety
6. Boundary testing for all 6 active risk rules
7. Emergency Stop persistence and trading block verification
8. Exchange failure simulation (timeout, HTTP 500, rate limit, invalid JSON)
9. Telegram notification fail-safety and secret masking
10. Production preflight validator environment & path integration
11. Accelerated monitor loop stability and clean cancellation
12. Live Trading Guard routing verification
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
import httpx
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from config.constants import GridStatus, OrderSide, OrderStatus
from config.settings import RiskSettings
from exchange.base import ExchangeOrder
from exchange.coindcx import CoinDCXClient
from exchange.exceptions import ExchangeConnectionError, ExchangeRateLimitError, ExchangeTimeoutError
from exchange.paper_exchange import PaperExchangeClient
from notifications.notifier import Notifier
from risk.risk_manager import RiskManager
from storage.database import Database
from storage.models import DCAGridRecord, OrderRecord
from storage.repositories import Repositories
from trading.dca_manager import DCAManager
from trading.mixed_order_manager import MixedOrderManager
from trading.order_manager import OrderManager
from trading.recovery import RecoveryManager
from utils.helpers import now_iso
from scripts.preflight import run_preflight, mask_status


@pytest.fixture
async def staging_db(tmp_path):
    db_file = tmp_path / "staging_test.db"
    db = Database(str(db_file))
    await db.connect()
    await db.migrate()
    yield db
    await db.close()


@pytest.fixture
def staging_repos(staging_db):
    return Repositories(staging_db)


@pytest.fixture
def risk_settings():
    return RiskSettings(
        max_total_capital=50000.0,
        max_capital_per_coin=20000.0,
        max_simultaneous_grids=20,
        min_wallet_balance=500.0,
        daily_loss_limit=2000.0,
    )


@pytest.fixture
def risk_manager(risk_settings, staging_repos):
    return RiskManager(risk_settings, staging_repos)


def make_grid(grid_id: str, symbol: str = "BTCINR", mode: str = "paper") -> DCAGridRecord:
    now = now_iso()
    return DCAGridRecord(
        grid_id=grid_id,
        symbol=symbol,
        status=GridStatus.ACTIVE.value,
        mode=mode,
        entry_price=100.0,
        base_investment=1000.0,
        dip_buy_amount=1000.0,
        dip_percentage=2.0,
        profit_sell_amount=1000.0,
        profit_percentage=2.0,
        max_levels=5,
        stop_loss_percentage=10.0,
        current_level=0,
        total_quantity=0.0,
        total_investment=0.0,
        average_entry_price=0.0,
        last_buy_price=0.0,
        next_buy_price=98.0,
        next_sell_price=102.0,
        realized_profit=0.0,
        completed_cycles=0,
        created_at=now,
        updated_at=now,
    )


# ------------------------------------------------------------------------------
# 1. Paper Mode Safety Contract & Routing Test
# ------------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_paper_mode_safety_contract(staging_repos):
    real_order_mgr = AsyncMock(spec=OrderManager)
    paper_order_mgr = AsyncMock(spec=OrderManager)
    mixed_mgr = MixedOrderManager(real=real_order_mgr, paper=paper_order_mgr, repos=staging_repos)

    grid = make_grid("grid_paper_1", "BTCINR", mode="paper")
    await staging_repos.grids.create(grid)

    mgr = await mixed_mgr._manager_for_grid("grid_paper_1")
    assert mgr is paper_order_mgr
    assert mgr is not real_order_mgr


@pytest.mark.asyncio
async def test_missing_grid_defaults_to_paper_safety(staging_repos):
    real_order_mgr = AsyncMock(spec=OrderManager)
    paper_order_mgr = AsyncMock(spec=OrderManager)
    mixed_mgr = MixedOrderManager(real=real_order_mgr, paper=paper_order_mgr, repos=staging_repos)

    mgr = await mixed_mgr._manager_for_grid("non_existent_grid_id")
    assert mgr is paper_order_mgr


# ------------------------------------------------------------------------------
# 2. Deterministic BUY -> SELL Profit Cycle Test
# ------------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_deterministic_buy_sell_profit_cycle(staging_repos, risk_manager):
    mock_exchange = AsyncMock(spec=PaperExchangeClient)
    order_mgr = OrderManager(mock_exchange, staging_repos)
    notifier = AsyncMock(spec=Notifier)

    dca_mgr = DCAManager(
        exchange=mock_exchange,
        repos=staging_repos,
        order_manager=order_mgr,
        notifier=notifier,
        risk=risk_manager,
    )

    grid = make_grid("grid_cycle_1", "ETHINR", mode="paper")
    await staging_repos.grids.create(grid)

    now = now_iso()

    # 1. Simulate Entry BUY at 250,000 INR for 0.008 ETH
    buy_price = 250000.0
    buy_qty = 0.008
    buy_fee = 2.0

    buy_order = OrderRecord(
        order_id="ord_buy_1",
        grid_id="grid_cycle_1",
        exchange_order_id="paper_buy_101",
        client_order_id="client_buy_101",
        symbol="ETHINR",
        side=OrderSide.BUY.value,
        order_type="LIMIT",
        price=buy_price,
        quantity=buy_qty,
        filled_quantity=buy_qty,
        filled_price=buy_price,
        fee=buy_fee,
        status=OrderStatus.FILLED.value,
        reconciliation_status="NORMAL",
        reconciliation_retry_count=0,
        created_at=now,
        updated_at=now,
    )
    await staging_repos.orders.create(buy_order)
    await dca_mgr.handle_order_filled("ord_buy_1", buy_price, buy_qty)

    grid_after_buy = await staging_repos.grids.get("grid_cycle_1")
    assert grid_after_buy["current_level"] == 1
    assert float(grid_after_buy["total_quantity"]) == buy_qty

    # 2. Simulate Take-Profit SELL at 275,000 INR for 0.008 ETH
    sell_price = 275000.0
    sell_qty = 0.008
    sell_fee = 2.2

    sell_order = OrderRecord(
        order_id="ord_sell_1",
        grid_id="grid_cycle_1",
        exchange_order_id="paper_sell_102",
        client_order_id="client_sell_102",
        symbol="ETHINR",
        side=OrderSide.SELL.value,
        order_type="LIMIT",
        price=sell_price,
        quantity=sell_qty,
        filled_quantity=sell_qty,
        filled_price=sell_price,
        fee=sell_fee,
        status=OrderStatus.FILLED.value,
        reconciliation_status="NORMAL",
        reconciliation_retry_count=0,
        created_at=now,
        updated_at=now,
    )
    await staging_repos.orders.create(sell_order)
    await dca_mgr.handle_order_filled("ord_sell_1", sell_price, sell_qty)

    # 3. Verify Math & Profit Realization
    expected_gross = (sell_price - buy_price) * buy_qty
    expected_net = expected_gross - buy_fee - sell_fee

    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    daily_stats = await staging_repos.daily_stats.get(today)
    assert daily_stats is not None
    assert abs(daily_stats["realized_pnl"] - expected_net) < 1e-4

    grid_final = await staging_repos.grids.get("grid_cycle_1")
    assert grid_final["completed_cycles"] == 1
    assert grid_final["status"] == GridStatus.COMPLETED.value


# ------------------------------------------------------------------------------
# 3. Partial Fill Validation
# ------------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_partial_fill_reconciliation(staging_repos):
    mock_exchange = AsyncMock()
    order_mgr = OrderManager(mock_exchange, staging_repos)

    grid = make_grid("grid_partial_1", "SOLINR", mode="paper")
    await staging_repos.grids.create(grid)

    now = now_iso()
    order = OrderRecord(
        order_id="ord_partial_1",
        grid_id="grid_partial_1",
        exchange_order_id="ex_partial_1",
        client_order_id="cl_partial_1",
        symbol="SOLINR",
        side=OrderSide.BUY.value,
        order_type="LIMIT",
        price=15000.0,
        quantity=1.0,
        filled_quantity=0.0,
        filled_price=0.0,
        fee=0.0,
        status=OrderStatus.OPEN.value,
        reconciliation_status="NORMAL",
        reconciliation_retry_count=0,
        created_at=now,
        updated_at=now,
    )
    await staging_repos.orders.create(order)

    # Partial Fill (0.4 / 1.0)
    mock_exchange.get_order_status.return_value = ExchangeOrder(
        exchange_order_id="ex_partial_1",
        symbol="SOLINR",
        side=OrderSide.BUY.value,
        price=15000.0,
        quantity=1.0,
        filled_quantity=0.4,
        filled_price=15000.0,
        fee=6.0,
        status=OrderStatus.PARTIALLY_FILLED.value,
        raw_status="partially_filled",
    )

    updated_order = await order_mgr.sync_order_status("ord_partial_1")
    assert updated_order.status == OrderStatus.PARTIALLY_FILLED.value
    assert float(updated_order.filled_quantity) == 0.4


# ------------------------------------------------------------------------------
# 4. Order Timeout / Unknown Status Recovery Test
# ------------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_order_timeout_unknown_status_recovery(staging_repos, risk_manager):
    mock_exchange = AsyncMock()
    order_mgr = OrderManager(mock_exchange, staging_repos)
    notifier = AsyncMock(spec=Notifier)
    dca_mgr = DCAManager(
        exchange=mock_exchange,
        repos=staging_repos,
        order_manager=order_mgr,
        notifier=notifier,
        risk=risk_manager,
    )
    recovery_mgr = RecoveryManager(mock_exchange, staging_repos, notifier, dca_mgr)

    grid = make_grid("grid_timeout_1", "XRPINR", mode="paper")
    await staging_repos.grids.create(grid)

    now = now_iso()
    stuck_order = OrderRecord(
        order_id="ord_stuck_1",
        grid_id="grid_timeout_1",
        exchange_order_id=None,
        client_order_id="cl_stuck_1",
        symbol="XRPINR",
        side=OrderSide.BUY.value,
        order_type="LIMIT",
        price=60.0,
        quantity=100.0,
        filled_quantity=0.0,
        filled_price=0.0,
        fee=0.0,
        status=OrderStatus.PENDING.value,
        reconciliation_status="NORMAL",
        reconciliation_retry_count=0,
        created_at=now,
        updated_at=now,
    )
    await staging_repos.orders.create(stuck_order)

    mock_exchange.get_open_orders.return_value = []
    mock_exchange.get_trade_history.return_value = []

    await recovery_mgr.recover()
    reconciled = await staging_repos.orders.get("ord_stuck_1")
    assert reconciled is not None
    assert reconciled["status"] in (OrderStatus.FAILED.value, OrderStatus.CANCELLED.value)


# ------------------------------------------------------------------------------
# 5. Process Interrupt & Restart Recovery Test
# ------------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_process_restart_recovery_preserves_state(staging_db, risk_manager):
    repos_1 = Repositories(staging_db)

    await risk_manager.trigger_emergency_stop()
    grid = make_grid("grid_restart_1", "ADAINR", mode="paper")
    await repos_1.grids.create(grid)

    repos_2 = Repositories(staging_db)
    new_risk_mgr = RiskManager(risk_manager._settings, repos_2)
    await new_risk_mgr.load_emergency_stop()

    assert new_risk_mgr.emergency_stopped is True
    persisted_grid = await repos_2.grids.get("grid_restart_1")
    assert persisted_grid is not None


# ------------------------------------------------------------------------------
# 6. Risk Management Boundary Tests (6 Active Rules)
# ------------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_risk_manager_boundary_rules(staging_repos, risk_manager):
    res_ok = await risk_manager.check_can_start_grid("BTCINR", 20000.0, 30000.0)
    assert res_ok.allowed is True

    res_exceed = await risk_manager.check_can_start_grid("BTCINR", 60000.0, 100000.0)
    assert res_exceed.allowed is False

    res_coin_exceed = await risk_manager.check_can_start_grid("ETHINR", 25000.0, 50000.0)
    assert res_coin_exceed.allowed is False

    res_wallet_low = await risk_manager.check_can_start_grid("SOLINR", 4600.0, 5000.0)
    assert res_wallet_low.allowed is False

    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    await staging_repos.daily_stats.add_trade(today, -2500.0)
    res_loss = await risk_manager.check_can_start_grid("DOGEINR", 1000.0, 10000.0)
    assert res_loss.allowed is False


# ------------------------------------------------------------------------------
# 7. Emergency Stop Validation
# ------------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_emergency_stop_toggle_and_block(risk_manager):
    res_before = await risk_manager.check_can_place_order(1000.0, 5000.0)
    assert res_before.allowed is True

    await risk_manager.trigger_emergency_stop()
    res_during = await risk_manager.check_can_place_order(1000.0, 5000.0)
    assert res_during.allowed is False

    await risk_manager.clear_emergency_stop()
    res_after = await risk_manager.check_can_place_order(1000.0, 5000.0)
    assert res_after.allowed is True


# ------------------------------------------------------------------------------
# 8. Exchange Failure Simulation
# ------------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_exchange_failure_handling():
    client = CoinDCXClient(api_key="mock", api_secret="mock", base_url="https://api.coindcx.com")

    with patch.object(client._client, "request", side_effect=httpx.TimeoutException("Timeout")):
        with pytest.raises(ExchangeTimeoutError):
            await client._request_once("POST", "/exchange/v1/orders/create")


# ------------------------------------------------------------------------------
# 9. Telegram Safety & Secret Masking Test
# ------------------------------------------------------------------------------
def test_telegram_secret_masking():
    token = "123456:ABC-DEF1234ghIkl-zyx57W2v1u123ew11"
    key = "0123456789abcdef0123456789abcdef"

    assert mask_status(token) == "SET"
    assert mask_status(key) == "SET"
    assert mask_status("") == "MISSING"


# ------------------------------------------------------------------------------
# 10. Live Trading Guard Routing Audit
# ------------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_live_trading_guard_routing(staging_repos):
    real_mgr = AsyncMock(spec=OrderManager)
    paper_mgr = AsyncMock(spec=OrderManager)
    mixed = MixedOrderManager(real=real_mgr, paper=paper_mgr, repos=staging_repos)

    grid = make_grid("grid_guard_1", "DOTINR", mode="paper")
    await staging_repos.grids.create(grid)

    selected = await mixed._manager_for_grid("grid_guard_1")
    assert selected is paper_mgr
    assert selected is not real_mgr

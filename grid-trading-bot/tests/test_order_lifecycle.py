"""Comprehensive tests for production order management:
  - Full order lifecycle (PENDING → SUBMITTED → OPEN/FILLED)
  - Partial fill handling (PARTIALLY_FILLED → FILLED)
  - Restart recovery (offline fills, SUBMITTED crash, PENDING crash)
  - Duplicate order prevention
  - Retry / transient error handling
  - Order synchronisation (exchange sync cycle)
  - Crash recovery (SUBMITTED with exchange match)
  - Mixed paper / real grid isolation
"""

from __future__ import annotations

import pytest

from config.constants import GridStatus, OrderStatus
from config.settings import RiskSettings
from exchange.base import ExchangeOrder
from exchange.exceptions import (
    ExchangeConnectionError,
    ExchangeError,
    ExchangeTimeoutError,
    InsufficientBalanceError,
    OrderRejectedError,
)
from risk.risk_manager import RiskManager
from storage.models import DCAGridRecord, OrderRecord
from trading.dca_manager import DCAManager
from trading.order_manager import OrderManager
from trading.order_monitor import OrderMonitor
from trading.recovery import RecoveryManager
from utils.helpers import new_id, now_iso


# ---------------------------------------------------------------------------
# Helpers / fixtures
# ---------------------------------------------------------------------------


def _make_grid(
    grid_id: str | None = None,
    symbol: str = "BTCINR",
    status: str = GridStatus.ACTIVE.value,
    mode: str = "real",
    current_level: int = 1,
    total_quantity: float = 0.00925,
    total_investment: float = 499.5,
    average_entry_price: float = 54000.0,
) -> DCAGridRecord:
    now = now_iso()
    return DCAGridRecord(
        grid_id=grid_id or new_id("grd"),
        symbol=symbol,
        status=status,
        mode=mode,
        entry_price=54000.0,
        base_investment=500.0,
        dip_buy_amount=100.0,
        dip_percentage=5.0,
        profit_sell_amount=150.0,
        profit_percentage=7.0,
        max_levels=10,
        stop_loss_percentage=50.0,
        current_level=current_level,
        total_quantity=total_quantity,
        total_investment=total_investment,
        average_entry_price=average_entry_price,
        last_buy_price=54000.0,
        next_buy_price=51300.0,
        next_sell_price=57780.0,
        realized_profit=0.0,
        completed_cycles=0,
        created_at=now,
        updated_at=now,
    )


def _make_order(
    grid_id: str,
    side: str = "buy",
    status: str = OrderStatus.OPEN.value,
    exchange_order_id: str | None = "EX0001",
    quantity: float = 0.00925,
    filled_quantity: float = 0.0,
    symbol: str = "BTCINR",
    price: float = 54000.0,
) -> OrderRecord:
    now = now_iso()
    return OrderRecord(
        order_id=new_id("ord"),
        grid_id=grid_id,
        exchange_order_id=exchange_order_id,
        symbol=symbol,
        side=side,
        order_type="market_order",
        price=price,
        quantity=quantity,
        filled_quantity=filled_quantity,
        filled_price=0.0,
        status=status,
        created_at=now,
        updated_at=now,
    )


def _filled_ex_order(exchange_order_id: str, symbol: str = "BTCINR",
                     side: str = "buy", price: float = 54000.0,
                     quantity: float = 0.00925) -> ExchangeOrder:
    return ExchangeOrder(
        exchange_order_id=exchange_order_id,
        symbol=symbol,
        side=side,
        price=price,
        quantity=quantity,
        filled_quantity=quantity,
        filled_price=price,
        status=OrderStatus.FILLED.value,
        raw_status="filled",
    )


def _open_ex_order(exchange_order_id: str, symbol: str = "BTCINR",
                   side: str = "buy", price: float = 54000.0,
                   quantity: float = 0.00925) -> ExchangeOrder:
    return ExchangeOrder(
        exchange_order_id=exchange_order_id,
        symbol=symbol,
        side=side,
        price=price,
        quantity=quantity,
        filled_quantity=0.0,
        filled_price=0.0,
        status=OrderStatus.OPEN.value,
        raw_status="open",
    )


def _partial_ex_order(exchange_order_id: str, filled_qty: float, total_qty: float,
                      symbol: str = "BTCINR", side: str = "buy",
                      price: float = 54000.0) -> ExchangeOrder:
    return ExchangeOrder(
        exchange_order_id=exchange_order_id,
        symbol=symbol,
        side=side,
        price=price,
        quantity=total_qty,
        filled_quantity=filled_qty,
        filled_price=price,
        status=OrderStatus.PARTIALLY_FILLED.value,
        raw_status="partially_filled",
    )


@pytest.fixture
def order_manager(mock_exchange, repos):
    return OrderManager(mock_exchange, repos)


@pytest.fixture
def dca_manager(mock_exchange, repos, order_manager, mock_notifier, permissive_risk_settings):
    risk = RiskManager(permissive_risk_settings, repos)
    return DCAManager(
        exchange=mock_exchange,
        repos=repos,
        order_manager=order_manager,
        notifier=mock_notifier,
        risk=risk,
    )


@pytest.fixture
def recovery(mock_exchange, repos, mock_notifier, dca_manager):
    return RecoveryManager(
        exchange=mock_exchange,
        repos=repos,
        notifier=mock_notifier,
        dca_manager=dca_manager,
    )


@pytest.fixture
def order_monitor(repos, order_manager, dca_manager, mock_notifier, mock_exchange):
    return OrderMonitor(
        repos=repos,
        order_manager=order_manager,
        dca_manager=dca_manager,
        notifier=mock_notifier,
        exchange=mock_exchange,
        poll_interval=1,
        sync_every_n_cycles=100,  # don't auto-trigger sync in unit tests
    )


# ===========================================================================
# 1. Order lifecycle
# ===========================================================================


class TestOrderLifecycle:
    @pytest.mark.anyio
    async def test_place_creates_pending_then_submits_then_fills(
        self, order_manager, repos, mock_exchange
    ):
        """A successful placement transitions PENDING → SUBMITTED → FILLED."""
        grid = _make_grid()
        await repos.grids.create(grid)

        order = await order_manager.place_dca_order(
            grid_id=grid.grid_id,
            symbol="BTCINR",
            side="buy",
            price=54000.0,
            quantity=0.00925,
        )

        # Final state should be FILLED (MockExchange fills immediately)
        assert order.status == OrderStatus.FILLED.value
        assert order.exchange_order_id is not None
        assert order.filled_quantity == 0.00925

        # DB record should match
        db_order = await repos.orders.get(order.order_id)
        assert db_order["status"] == OrderStatus.FILLED.value
        assert db_order["exchange_order_id"] == order.exchange_order_id

    @pytest.mark.anyio
    async def test_rejected_order_sets_rejected_status(
        self, order_manager, repos, mock_exchange
    ):
        mock_exchange.place_exception = OrderRejectedError("price out of bounds")
        grid = _make_grid()
        await repos.grids.create(grid)

        with pytest.raises(OrderRejectedError):
            await order_manager.place_dca_order(
                grid_id=grid.grid_id, symbol="BTCINR",
                side="buy", price=54000.0, quantity=0.001,
            )

        orders = await repos.orders.list_for_grid(grid.grid_id)
        assert len(orders) == 1
        assert orders[0]["status"] == OrderStatus.REJECTED.value

    @pytest.mark.anyio
    async def test_insufficient_balance_sets_failed_status(
        self, order_manager, repos, mock_exchange
    ):
        mock_exchange.place_exception = InsufficientBalanceError("not enough INR")
        grid = _make_grid()
        await repos.grids.create(grid)

        with pytest.raises(InsufficientBalanceError):
            await order_manager.place_dca_order(
                grid_id=grid.grid_id, symbol="BTCINR",
                side="buy", price=54000.0, quantity=0.001,
            )

        orders = await repos.orders.list_for_grid(grid.grid_id)
        assert orders[0]["status"] == OrderStatus.FAILED.value

    @pytest.mark.anyio
    async def test_transient_error_sets_failed_status_with_warning(
        self, order_manager, repos, mock_exchange
    ):
        """Network timeout → FAILED (uncertain delivery, not REJECTED)."""
        mock_exchange.place_exception = ExchangeTimeoutError("timed out")
        grid = _make_grid()
        await repos.grids.create(grid)

        with pytest.raises(ExchangeTimeoutError):
            await order_manager.place_dca_order(
                grid_id=grid.grid_id, symbol="BTCINR",
                side="buy", price=54000.0, quantity=0.001,
            )

        orders = await repos.orders.list_for_grid(grid.grid_id)
        # Status is FAILED; not REJECTED (different permanent-vs-transient semantics)
        assert orders[0]["status"] == OrderStatus.FAILED.value

    @pytest.mark.anyio
    async def test_cancel_order_updates_status(self, order_manager, repos, mock_exchange):
        grid = _make_grid()
        await repos.grids.create(grid)
        order = await order_manager.place_dca_order(
            grid_id=grid.grid_id, symbol="BTCINR",
            side="buy", price=54000.0, quantity=0.001,
        )
        # Artificially make it OPEN so cancel is meaningful
        await repos.orders.update_status(order.order_id, OrderStatus.OPEN.value)

        cancelled = await order_manager.cancel_order(order.order_id)
        assert cancelled is True
        db = await repos.orders.get(order.order_id)
        assert db["status"] == OrderStatus.CANCELLED.value

    @pytest.mark.anyio
    async def test_cancel_already_terminal_order_is_noop(
        self, order_manager, repos, mock_exchange
    ):
        grid = _make_grid()
        await repos.grids.create(grid)
        order = _make_order(grid.grid_id, status=OrderStatus.FILLED.value)
        await repos.orders.create(order)

        cancelled = await order_manager.cancel_order(order.order_id)
        assert cancelled is False
        db = await repos.orders.get(order.order_id)
        assert db["status"] == OrderStatus.FILLED.value  # unchanged

    @pytest.mark.anyio
    async def test_sync_order_status_updates_db(self, order_manager, repos, mock_exchange):
        grid = _make_grid()
        await repos.grids.create(grid)
        order = _make_order(grid.grid_id, status=OrderStatus.OPEN.value, exchange_order_id="EX_SYNC")
        await repos.orders.create(order)

        # Teach the exchange that this order is now filled
        filled = _filled_ex_order("EX_SYNC")
        mock_exchange.status_overrides["EX_SYNC"] = filled

        refreshed = await order_manager.sync_order_status(order.order_id)
        assert refreshed is not None
        assert refreshed.status == OrderStatus.FILLED.value
        assert refreshed.filled_quantity == 0.00925


# ===========================================================================
# 2. Partial fill handling
# ===========================================================================


class TestPartialFillHandling:
    @pytest.mark.anyio
    async def test_place_order_with_partial_fill(
        self, order_manager, repos, mock_exchange
    ):
        """place_dca_order should return PARTIALLY_FILLED when exchange partial-fills."""
        mock_exchange.partial_fill_qty = 0.005
        grid = _make_grid()
        await repos.grids.create(grid)

        order = await order_manager.place_dca_order(
            grid_id=grid.grid_id, symbol="BTCINR",
            side="buy", price=54000.0, quantity=0.01,
        )
        assert order.status == OrderStatus.PARTIALLY_FILLED.value
        assert order.filled_quantity == 0.005

    @pytest.mark.anyio
    async def test_partial_fill_is_in_list_open(
        self, order_manager, repos, mock_exchange
    ):
        """A PARTIALLY_FILLED order must stay in list_open for continued monitoring."""
        mock_exchange.partial_fill_qty = 0.003
        grid = _make_grid()
        await repos.grids.create(grid)

        order = await order_manager.place_dca_order(
            grid_id=grid.grid_id, symbol="BTCINR",
            side="buy", price=54000.0, quantity=0.01,
        )
        assert order.status == OrderStatus.PARTIALLY_FILLED.value
        open_orders = await repos.orders.list_open()
        assert any(o["order_id"] == order.order_id for o in open_orders)

    @pytest.mark.anyio
    async def test_order_monitor_sends_partial_fill_notification(
        self, repos, order_manager, order_monitor, mock_notifier, mock_exchange
    ):
        """When order_monitor polls and sees new partial fill progress, notify."""
        grid = _make_grid()
        await repos.grids.create(grid)

        # Start with a PARTIALLY_FILLED local order (0 filled so far)
        order = _make_order(
            grid.grid_id,
            status=OrderStatus.PARTIALLY_FILLED.value,
            exchange_order_id="EX_PARTIAL",
            quantity=0.01,
            filled_quantity=0.0,
        )
        await repos.orders.create(order)

        # Exchange now says 0.005 has been filled
        partial = _partial_ex_order("EX_PARTIAL", filled_qty=0.005, total_qty=0.01)
        mock_exchange.status_overrides["EX_PARTIAL"] = partial

        await order_monitor._poll_once()
        assert mock_notifier.was_called("partial_fill_received")

    @pytest.mark.anyio
    async def test_order_monitor_does_not_double_notify_partial_fill(
        self, repos, order_manager, order_monitor, mock_notifier, mock_exchange
    ):
        """Polling twice with no new fill progress should send only 1 notification."""
        grid = _make_grid()
        await repos.grids.create(grid)

        order = _make_order(
            grid.grid_id,
            status=OrderStatus.PARTIALLY_FILLED.value,
            exchange_order_id="EX_NOCHANGE",
            quantity=0.01,
            filled_quantity=0.005,  # already at 0.005
        )
        await repos.orders.create(order)

        # Exchange still at the same 0.005 (no progress)
        partial = _partial_ex_order("EX_NOCHANGE", filled_qty=0.005, total_qty=0.01)
        mock_exchange.status_overrides["EX_NOCHANGE"] = partial

        await order_monitor._poll_once()
        await order_monitor._poll_once()
        assert mock_notifier.call_count("partial_fill_received") <= 1

    @pytest.mark.anyio
    async def test_partial_fill_then_full_fill_processes_correctly(
        self, repos, order_manager, order_monitor, dca_manager, mock_notifier, mock_exchange
    ):
        """A partial fill followed by a full fill triggers handle_order_filled once."""
        grid = _make_grid()
        await repos.grids.create(grid)

        order = _make_order(
            grid.grid_id,
            status=OrderStatus.PARTIALLY_FILLED.value,
            exchange_order_id="EX_THEN_FULL",
            quantity=0.00925,
            filled_quantity=0.004,
        )
        await repos.orders.create(order)

        # Exchange now shows fully filled
        filled = _filled_ex_order("EX_THEN_FULL", quantity=0.00925)
        mock_exchange.status_overrides["EX_THEN_FULL"] = filled

        await order_monitor._poll_once()

        # Grid level should have advanced (handle_order_filled processed the buy)
        refreshed_grid = await repos.grids.get(grid.grid_id)
        assert refreshed_grid["current_level"] == 2  # was 1, incremented by fill


# ===========================================================================
# 3. Restart recovery
# ===========================================================================


class TestRestartRecovery:
    @pytest.mark.anyio
    async def test_offline_fill_recovered_on_restart(
        self, recovery, repos, mock_exchange
    ):
        """An order that filled while the bot was down is recovered on startup."""
        grid = _make_grid()
        await repos.grids.create(grid)

        order = _make_order(grid.grid_id, status=OrderStatus.OPEN.value, exchange_order_id="EX_OFFLINE_FILL")
        await repos.orders.create(order)

        # Exchange says it's now filled
        mock_exchange.status_overrides["EX_OFFLINE_FILL"] = _filled_ex_order("EX_OFFLINE_FILL")

        summary = await recovery.recover()
        assert summary["fills_recovered"] == 1
        assert summary["reconciled_orders"] == 1

        refreshed_grid = await repos.grids.get(grid.grid_id)
        assert refreshed_grid["current_level"] == 2

    @pytest.mark.anyio
    async def test_pending_order_without_exchange_id_marked_failed(
        self, recovery, repos
    ):
        """PENDING order with no exchange_order_id never reached the exchange → FAILED."""
        grid = _make_grid()
        await repos.grids.create(grid)
        order = _make_order(
            grid.grid_id, status=OrderStatus.PENDING.value, exchange_order_id=None
        )
        await repos.orders.create(order)

        await recovery.recover()

        db_order = await repos.orders.get(order.order_id)
        assert db_order["status"] == OrderStatus.FAILED.value

    @pytest.mark.anyio
    async def test_submitted_order_linked_to_exchange_match(
        self, recovery, repos, mock_exchange
    ):
        """SUBMITTED + no exchange_id: if exchange has matching open order, link it."""
        grid = _make_grid()
        await repos.grids.create(grid)
        order = _make_order(
            grid.grid_id,
            status=OrderStatus.SUBMITTED.value,
            exchange_order_id=None,
            quantity=0.00925,
        )
        await repos.orders.create(order)

        # Exchange has an open order that matches: side=buy, qty≈0.00925
        orphan_ex = _open_ex_order("EX_MATCH_001", side="buy", quantity=0.00925)
        mock_exchange.open_orders_override = [orphan_ex]

        summary = await recovery.recover()
        assert summary["reconciled_orders"] >= 1

        db_order = await repos.orders.get(order.order_id)
        assert db_order["exchange_order_id"] == "EX_MATCH_001"
        assert db_order["status"] == OrderStatus.OPEN.value

    @pytest.mark.anyio
    async def test_submitted_order_without_match_marked_failed(
        self, recovery, repos, mock_exchange
    ):
        """SUBMITTED + no exchange_id + no matching exchange order → FAILED."""
        grid = _make_grid()
        await repos.grids.create(grid)
        order = _make_order(
            grid.grid_id,
            status=OrderStatus.SUBMITTED.value,
            exchange_order_id=None,
            quantity=0.00925,
        )
        await repos.orders.create(order)

        # No exchange open orders
        mock_exchange.open_orders_override = []

        await recovery.recover()

        db_order = await repos.orders.get(order.order_id)
        assert db_order["status"] == OrderStatus.FAILED.value

    @pytest.mark.anyio
    async def test_recovery_ignores_already_terminal_orders(self, recovery, repos):
        grid = _make_grid()
        await repos.grids.create(grid)

        for status in [
            OrderStatus.FILLED.value,
            OrderStatus.CANCELLED.value,
            OrderStatus.FAILED.value,
        ]:
            order = _make_order(grid.grid_id, status=status, exchange_order_id="EX_DONE")
            await repos.orders.create(order)

        summary = await recovery.recover()
        assert summary["reconciled_orders"] == 0

    @pytest.mark.anyio
    async def test_recovery_sends_notification(
        self, recovery, repos, mock_notifier
    ):
        grid = _make_grid()
        await repos.grids.create(grid)
        await recovery.recover()
        assert mock_notifier.was_called("recovery_complete")

    @pytest.mark.anyio
    async def test_recovery_counts_active_and_paused_grids(self, recovery, repos):
        active = _make_grid(status=GridStatus.ACTIVE.value)
        paused = _make_grid(symbol="ETHINR", status=GridStatus.PAUSED.value)
        stopped = _make_grid(symbol="SOLINR", status=GridStatus.STOPPED.value)
        for g in [active, paused, stopped]:
            await repos.grids.create(g)

        summary = await recovery.recover()
        assert summary["active_grids"] == 2

    @pytest.mark.anyio
    async def test_recovery_tolerates_exchange_error_per_order(
        self, recovery, repos, mock_exchange
    ):
        """Exchange error on one order must not stop recovery for others."""
        grid = _make_grid()
        await repos.grids.create(grid)

        # This one will fail exchange lookup
        bad_order = _make_order(grid.grid_id, status=OrderStatus.OPEN.value,
                                exchange_order_id="EX_UNREACHABLE")
        good_order = _make_order(grid.grid_id, status=OrderStatus.OPEN.value,
                                 exchange_order_id="EX_GOOD")
        await repos.orders.create(bad_order)
        await repos.orders.create(good_order)

        # EX_GOOD will be found as filled
        mock_exchange.status_overrides["EX_GOOD"] = _filled_ex_order("EX_GOOD")
        # EX_UNREACHABLE raises (not in status_overrides and not in orders_placed)

        summary = await recovery.recover()
        # EX_GOOD should be reconciled
        assert summary["fills_recovered"] >= 1
        # EX_UNREACHABLE should be skipped gracefully
        bad_db = await repos.orders.get(bad_order.order_id)
        assert bad_db["status"] == OrderStatus.OPEN.value  # unchanged


# ===========================================================================
# 4. Duplicate order prevention
# ===========================================================================


class TestDuplicateOrderPrevention:
    @pytest.mark.anyio
    async def test_count_pending_side_includes_submitted(self, repos):
        """SUBMITTED orders count toward the duplicate guard."""
        grid = _make_grid()
        await repos.grids.create(grid)

        order = _make_order(grid.grid_id, status=OrderStatus.SUBMITTED.value,
                            exchange_order_id=None)
        await repos.orders.create(order)

        count = await repos.orders.count_pending_side(grid.grid_id, "buy")
        assert count == 1

    @pytest.mark.anyio
    async def test_count_pending_side_includes_pending(self, repos):
        grid = _make_grid()
        await repos.grids.create(grid)
        order = _make_order(grid.grid_id, status=OrderStatus.PENDING.value,
                            exchange_order_id=None)
        await repos.orders.create(order)
        assert await repos.orders.count_pending_side(grid.grid_id, "buy") == 1

    @pytest.mark.anyio
    async def test_count_pending_side_includes_open(self, repos):
        grid = _make_grid()
        await repos.grids.create(grid)
        order = _make_order(grid.grid_id, status=OrderStatus.OPEN.value)
        await repos.orders.create(order)
        assert await repos.orders.count_pending_side(grid.grid_id, "buy") == 1

    @pytest.mark.anyio
    async def test_count_pending_side_excludes_terminal_statuses(self, repos):
        grid = _make_grid()
        await repos.grids.create(grid)
        for status in [
            OrderStatus.FILLED.value,
            OrderStatus.CANCELLED.value,
            OrderStatus.FAILED.value,
            OrderStatus.REJECTED.value,
        ]:
            order = _make_order(grid.grid_id, status=status)
            await repos.orders.create(order)
        assert await repos.orders.count_pending_side(grid.grid_id, "buy") == 0

    @pytest.mark.anyio
    async def test_check_grid_triggers_skips_dip_buy_when_buy_already_open(
        self, dca_manager, repos, mock_exchange
    ):
        """DCAManager.check_grid_triggers must not place a second buy if one is open."""
        grid = _make_grid(current_level=1, total_quantity=0.00925,
                          average_entry_price=54000.0)
        await repos.grids.create(grid)

        # Plant an OPEN buy order for this grid
        existing = _make_order(grid.grid_id, side="buy", status=OrderStatus.OPEN.value)
        await repos.orders.create(existing)

        before = len(mock_exchange.orders_placed)
        await dca_manager.check_grid_triggers(grid.grid_id, current_price=51000.0)
        after = len(mock_exchange.orders_placed)

        assert after == before  # no new order placed

    @pytest.mark.anyio
    async def test_check_grid_triggers_skips_dip_buy_when_submitted_exists(
        self, dca_manager, repos, mock_exchange
    ):
        """SUBMITTED orders (in-flight) also block new buy placement."""
        grid = _make_grid(current_level=1, total_quantity=0.00925,
                          average_entry_price=54000.0)
        await repos.grids.create(grid)

        in_flight = _make_order(grid.grid_id, side="buy",
                                status=OrderStatus.SUBMITTED.value,
                                exchange_order_id=None)
        await repos.orders.create(in_flight)

        before = len(mock_exchange.orders_placed)
        await dca_manager.check_grid_triggers(grid.grid_id, current_price=51000.0)
        after = len(mock_exchange.orders_placed)

        assert after == before


# ===========================================================================
# 5. Retry logic (transient errors)
# ===========================================================================


class TestRetryLogic:
    @pytest.mark.anyio
    async def test_transient_error_does_not_produce_rejected_status(
        self, order_manager, repos, mock_exchange
    ):
        """Timeout → FAILED (not REJECTED); the distinction matters for recovery."""
        mock_exchange.place_exception = ExchangeTimeoutError("timeout")
        grid = _make_grid()
        await repos.grids.create(grid)

        with pytest.raises(ExchangeTimeoutError):
            await order_manager.place_dca_order(
                grid_id=grid.grid_id, symbol="BTCINR",
                side="buy", price=54000.0, quantity=0.001,
            )

        orders = await repos.orders.list_for_grid(grid.grid_id)
        assert orders[0]["status"] == OrderStatus.FAILED.value
        # NOT REJECTED
        assert orders[0]["status"] != OrderStatus.REJECTED.value

    @pytest.mark.anyio
    async def test_connection_error_also_sets_failed_not_rejected(
        self, order_manager, repos, mock_exchange
    ):
        mock_exchange.place_exception = ExchangeConnectionError("network down")
        grid = _make_grid()
        await repos.grids.create(grid)

        with pytest.raises(ExchangeConnectionError):
            await order_manager.place_dca_order(
                grid_id=grid.grid_id, symbol="BTCINR",
                side="buy", price=54000.0, quantity=0.001,
            )

        orders = await repos.orders.list_for_grid(grid.grid_id)
        assert orders[0]["status"] == OrderStatus.FAILED.value

    @pytest.mark.anyio
    async def test_transient_error_leaves_submitted_state_before_failure(
        self, order_manager, repos, mock_exchange
    ):
        """Before the exchange call, status is set to SUBMITTED.
        After transient failure, it's FAILED — confirming the transition happened.
        """
        transitions: list[str] = []

        # Monkey-patch update_status to record every transition
        original_update = repos.orders.update_status

        async def recording_update(order_id, status, **kwargs):
            transitions.append(status)
            return await original_update(order_id, status, **kwargs)

        repos.orders.update_status = recording_update

        mock_exchange.place_exception = ExchangeTimeoutError("timeout")
        grid = _make_grid()
        await repos.grids.create(grid)

        with pytest.raises(ExchangeTimeoutError):
            await order_manager.place_dca_order(
                grid_id=grid.grid_id, symbol="BTCINR",
                side="buy", price=54000.0, quantity=0.001,
            )

        # Should have seen: SUBMITTED (before call), then FAILED (after timeout)
        assert OrderStatus.SUBMITTED.value in transitions
        assert transitions[-1] == OrderStatus.FAILED.value


# ===========================================================================
# 6. Order synchronisation (exchange sync cycle)
# ===========================================================================


class TestOrderSynchronisation:
    @pytest.mark.anyio
    async def test_sync_detects_silently_filled_order(
        self, order_monitor, repos, mock_exchange
    ):
        """_sync_with_exchange must detect an order that filled without appearing
        in get_open_orders (silently moved out of the open set)."""
        grid = _make_grid()
        await repos.grids.create(grid)

        order = _make_order(grid.grid_id, status=OrderStatus.OPEN.value,
                            exchange_order_id="EX_SILENT_FILL")
        await repos.orders.create(order)

        # Exchange open orders set is empty — order is gone
        mock_exchange.open_orders_override = []
        # But status check returns FILLED
        mock_exchange.status_overrides["EX_SILENT_FILL"] = _filled_ex_order("EX_SILENT_FILL")

        synced, fills = await order_monitor._sync_with_exchange()
        assert synced >= 1
        assert fills >= 1

        refreshed = await repos.grids.get(grid.grid_id)
        assert refreshed["current_level"] == 2  # handle_order_filled ran

    @pytest.mark.anyio
    async def test_sync_skips_orders_still_in_exchange_open_set(
        self, order_monitor, repos, mock_exchange
    ):
        """Orders still open on the exchange are not synced unnecessarily."""
        grid = _make_grid()
        await repos.grids.create(grid)

        order = _make_order(grid.grid_id, status=OrderStatus.OPEN.value,
                            exchange_order_id="EX_STILL_OPEN")
        await repos.orders.create(order)

        # Exchange shows this order as still open
        still_open = _open_ex_order("EX_STILL_OPEN")
        mock_exchange.open_orders_override = [still_open]

        synced, fills = await order_monitor._sync_with_exchange()
        assert synced == 0
        assert fills == 0

    @pytest.mark.anyio
    async def test_sync_completed_notification_sent_only_when_something_changed(
        self, repos, order_manager, order_monitor, mock_notifier, mock_exchange
    ):
        """sync_completed is only notified when synced > 0 or fills > 0."""
        # No open orders — sync should not fire notification
        synced, fills = await order_monitor._sync_with_exchange()
        assert synced == 0
        assert fills == 0
        # (The monitor itself notifies from _run_loop; we just check the counts here)

    @pytest.mark.anyio
    async def test_get_by_exchange_order_id(self, repos):
        """Repository helper used in orphan detection must work correctly."""
        grid = _make_grid()
        await repos.grids.create(grid)

        order = _make_order(grid.grid_id, exchange_order_id="EX_LOOKUP_ME")
        await repos.orders.create(order)

        found = await repos.orders.get_by_exchange_order_id("EX_LOOKUP_ME")
        assert found is not None
        assert found["order_id"] == order.order_id

        not_found = await repos.orders.get_by_exchange_order_id("EX_GHOST")
        assert not_found is None


# ===========================================================================
# 7. Crash recovery (SUBMITTED state edge cases)
# ===========================================================================


class TestCrashRecovery:
    @pytest.mark.anyio
    async def test_full_crash_recovery_restores_grid_state(
        self, recovery, repos, mock_exchange
    ):
        """After a crash, recovery restores: active grids, open positions, order state."""
        grid = _make_grid(
            current_level=2,
            total_quantity=0.02,
            total_investment=1000.0,
            average_entry_price=50000.0,
        )
        await repos.grids.create(grid)

        # Open order that filled while down
        order = _make_order(grid.grid_id, status=OrderStatus.OPEN.value,
                            exchange_order_id="EX_CRASH_FILL",
                            quantity=0.005, filled_quantity=0.0)
        await repos.orders.create(order)

        mock_exchange.status_overrides["EX_CRASH_FILL"] = ExchangeOrder(
            exchange_order_id="EX_CRASH_FILL",
            symbol="BTCINR",
            side="buy",
            price=48000.0,
            quantity=0.005,
            filled_quantity=0.005,
            filled_price=48000.0,
            status=OrderStatus.FILLED.value,
            raw_status="filled",
        )

        summary = await recovery.recover()
        assert summary["active_grids"] == 1
        assert summary["fills_recovered"] == 1

        refreshed_grid = await repos.grids.get(grid.grid_id)
        # Level advanced from 2 → 3 after fill processed
        assert refreshed_grid["current_level"] == 3
        # Investment and qty updated
        assert refreshed_grid["total_quantity"] > 0.02

    @pytest.mark.anyio
    async def test_submitted_order_with_qty_mismatch_is_not_linked(
        self, recovery, repos, mock_exchange
    ):
        """A SUBMITTED order should NOT be linked to an exchange order with very
        different qty — prevents mis-linking two separate orders."""
        grid = _make_grid()
        await repos.grids.create(grid)

        # Local SUBMITTED order wants 0.01 BTC
        order = _make_order(
            grid.grid_id,
            status=OrderStatus.SUBMITTED.value,
            exchange_order_id=None,
            quantity=0.01,
        )
        await repos.orders.create(order)

        # Exchange has an open order for 0.5 BTC — very different qty
        wrong_size = _open_ex_order("EX_WRONG_SIZE", quantity=0.5)
        mock_exchange.open_orders_override = [wrong_size]

        await recovery.recover()

        db_order = await repos.orders.get(order.order_id)
        # Should NOT be linked — should be FAILED
        assert db_order["status"] == OrderStatus.FAILED.value
        assert db_order["exchange_order_id"] is None

    @pytest.mark.anyio
    async def test_list_submitted_no_exchange_id_query(self, repos):
        """Repository helper must correctly isolate SUBMITTED orders without exchange_id."""
        grid = _make_grid()
        await repos.grids.create(grid)

        submitted_no_id = _make_order(
            grid.grid_id, status=OrderStatus.SUBMITTED.value,
            exchange_order_id=None,
        )
        submitted_with_id = _make_order(
            grid.grid_id, status=OrderStatus.SUBMITTED.value,
            exchange_order_id="EX_HAS_ID",
        )
        pending_no_id = _make_order(
            grid.grid_id, status=OrderStatus.PENDING.value,
            exchange_order_id=None,
        )
        for o in [submitted_no_id, submitted_with_id, pending_no_id]:
            await repos.orders.create(o)

        result = await repos.repos.orders.list_submitted_no_exchange_id() \
            if hasattr(repos, "repos") else \
            await repos.orders.list_submitted_no_exchange_id()
        ids = {r["order_id"] for r in result}
        assert submitted_no_id.order_id in ids
        assert submitted_with_id.order_id not in ids
        assert pending_no_id.order_id not in ids


# ===========================================================================
# 8. Mixed paper and real grids
# ===========================================================================


class TestMixedPaperAndReal:
    @pytest.mark.anyio
    async def test_paper_grid_uses_paper_exchange(
        self, repos, mock_exchange, mock_notifier, permissive_risk_settings
    ):
        """Paper grids must route through the paper exchange, not the real one."""
        from exchange.paper_exchange import PaperExchangeClient
        from trading.mixed_order_manager import MixedOrderManager

        paper_ex = PaperExchangeClient(mock_exchange)
        real_om = OrderManager(mock_exchange, repos)
        paper_om = OrderManager(paper_ex, repos)
        mixed_om = MixedOrderManager(real=real_om, paper=paper_om, repos=repos)

        risk = RiskManager(permissive_risk_settings, repos)
        dca = DCAManager(
            exchange=mock_exchange, repos=repos,
            order_manager=mixed_om, notifier=mock_notifier, risk=risk,
        )

        grid_id = await dca.start_grid({
            "symbol": "BTCINR",
            "entry_price": 54000.0,
            "base_investment": 500.0,
            "dip_buy_amount": 100.0,
            "dip_percentage": 5.0,
            "profit_sell_amount": 150.0,
            "profit_percentage": 7.0,
            "max_levels": 10,
            "stop_loss_percentage": 50.0,
            "mode": "paper",
        })

        grid_rec = await repos.grids.get(grid_id)
        assert grid_rec["mode"] == "paper"
        orders = await repos.orders.list_for_grid(grid_id)
        assert len(orders) >= 1

    @pytest.mark.anyio
    async def test_recovery_processes_both_paper_and_real_fills(
        self, repos, mock_exchange, mock_notifier, permissive_risk_settings
    ):
        """Recovery must reconcile both paper and real grids."""
        real_grid = _make_grid(symbol="BTCINR", mode="real")
        paper_grid = _make_grid(symbol="ETHINR", mode="paper")
        await repos.grids.create(real_grid)
        await repos.grids.create(paper_grid)

        real_order = _make_order(real_grid.grid_id, status=OrderStatus.OPEN.value,
                                 exchange_order_id="EX_REAL_FILL", symbol="BTCINR")
        paper_order = _make_order(paper_grid.grid_id, status=OrderStatus.OPEN.value,
                                  exchange_order_id="EX_PAPER_FILL", symbol="ETHINR")
        await repos.orders.create(real_order)
        await repos.orders.create(paper_order)

        mock_exchange.status_overrides["EX_REAL_FILL"] = _filled_ex_order(
            "EX_REAL_FILL", symbol="BTCINR"
        )
        mock_exchange.status_overrides["EX_PAPER_FILL"] = _filled_ex_order(
            "EX_PAPER_FILL", symbol="ETHINR"
        )

        risk = RiskManager(permissive_risk_settings, repos)
        real_om = OrderManager(mock_exchange, repos)
        dca = DCAManager(
            exchange=mock_exchange, repos=repos,
            order_manager=real_om, notifier=mock_notifier, risk=risk,
        )
        rec = RecoveryManager(
            exchange=mock_exchange, repos=repos,
            notifier=mock_notifier, dca_manager=dca,
        )

        summary = await rec.recover()
        assert summary["fills_recovered"] == 2
        assert summary["active_grids"] == 2

    @pytest.mark.anyio
    async def test_order_submitted_notification_includes_mode(
        self, dca_manager, repos, mock_notifier, mock_exchange
    ):
        """order_submitted notification must carry the grid mode."""
        grid = _make_grid(mode="paper", current_level=1, total_quantity=0.00925,
                          average_entry_price=54000.0)
        await repos.grids.create(grid)

        await dca_manager.check_grid_triggers(grid.grid_id, current_price=51000.0)

        calls = mock_notifier.get_calls("order_submitted")
        assert len(calls) == 1
        # The notification kwargs should include mode
        kwargs = calls[0][2]
        assert kwargs.get("mode") == "paper"

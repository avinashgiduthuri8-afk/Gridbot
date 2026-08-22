"""Failure-sequence tests for exactly-once CoinDCX order submission."""

from __future__ import annotations

import pytest

from config.constants import OrderStatus
from exchange.base import ExchangeOrder
from exchange.coindcx import CoinDCXClient
from exchange.exceptions import ExchangeTimeoutError
from storage.models import OrderRecord
from trading.order_manager import OrderManager
from trading.recovery import RecoveryManager
from utils.helpers import new_id, now_iso

from tests.conftest import MockExchange
from tests.test_order_lifecycle import _make_grid


class TimeoutAfterAcceptedExchange(MockExchange):
    """The exchange accepted the order but the HTTP response was lost."""

    async def place_order(self, *args, client_order_id=None, **kwargs):
        order = await super().place_order(*args, client_order_id=client_order_id, **kwargs)
        self.orders_placed[-1] = ExchangeOrder(
            **{**order.__dict__, "status": OrderStatus.OPEN.value, "filled_quantity": 0.0}
        )
        raise ExchangeTimeoutError("response lost after acceptance")


class TimeoutBeforeAcceptedExchange(MockExchange):
    """The transport failed before CoinDCX received the create request."""

    async def place_order(self, *args, client_order_id=None, **kwargs):
        raise ExchangeTimeoutError("connection lost before delivery")


def _submitted_record(grid_id: str, client_order_id: str) -> OrderRecord:
    now = now_iso()
    return OrderRecord(
        order_id=client_order_id, grid_id=grid_id, exchange_order_id=None,
        client_order_id=client_order_id, symbol="BTCINR", side="buy",
        order_type="market_order", price=54000.0, quantity=0.01,
        filled_quantity=0.0, filled_price=0.0, status=OrderStatus.SUBMITTED.value,
        reconciliation_status="submitted", reconciliation_retry_count=0,
        created_at=now, updated_at=now,
    )


@pytest.mark.anyio
async def test_timeout_after_acceptance_reconciles_same_client_id_without_resubmit(repos):
    grid = _make_grid()
    await repos.grids.create(grid)
    exchange = TimeoutAfterAcceptedExchange()
    manager = OrderManager(exchange, repos)

    with pytest.raises(ExchangeTimeoutError):
        await manager.place_dca_order(grid.grid_id, "BTCINR", "buy", 54000.0, 0.01)

    orders = await repos.orders.list_for_grid(grid.grid_id)
    assert len(exchange.orders_placed) == 1
    assert len(orders) == 1
    assert orders[0]["client_order_id"] == orders[0]["order_id"]
    assert orders[0]["exchange_order_id"] == exchange.orders_placed[0].exchange_order_id
    assert orders[0]["status"] == OrderStatus.OPEN.value
    assert orders[0]["reconciliation_status"] == "resolved"


@pytest.mark.anyio
async def test_timeout_before_acceptance_stays_unknown_and_never_creates_replacement(repos):
    grid = _make_grid()
    await repos.grids.create(grid)
    exchange = TimeoutBeforeAcceptedExchange()
    manager = OrderManager(exchange, repos)

    with pytest.raises(ExchangeTimeoutError):
        await manager.place_dca_order(grid.grid_id, "BTCINR", "buy", 54000.0, 0.01)

    order = (await repos.orders.list_for_grid(grid.grid_id))[0]
    assert exchange.orders_placed == []
    assert order["status"] == OrderStatus.UNKNOWN.value
    assert order["client_order_id"] == order["order_id"]
    await manager.resolve_uncertain_submitted(order["order_id"])
    assert exchange.orders_placed == []
    assert (await repos.orders.get(order["order_id"]))["status"] == OrderStatus.UNKNOWN.value


@pytest.mark.anyio
async def test_restart_recovery_links_delayed_order_by_client_id_only(repos, mock_notifier):
    grid = _make_grid()
    await repos.grids.create(grid)
    client_id = new_id("ord")
    await repos.orders.create(_submitted_record(grid.grid_id, client_id))
    exchange = MockExchange()
    exchange.orders_placed.append(ExchangeOrder(
        exchange_order_id="EX_DELAYED", symbol="BTCINR", side="buy", price=54000.0,
        quantity=0.01, filled_quantity=0.0, filled_price=0.0,
        status=OrderStatus.OPEN.value, raw_status="open", client_order_id=client_id,
    ))
    recovery = RecoveryManager(exchange, repos, mock_notifier, object())
    summary = await recovery.recover()
    recovered = await repos.orders.get(client_id)
    assert summary["reconciled_orders"] >= 1
    assert recovered["exchange_order_id"] == "EX_DELAYED"
    assert recovered["status"] == OrderStatus.OPEN.value
    assert len(exchange.orders_placed) == 1


@pytest.mark.anyio
async def test_startup_recovery_never_fuzzy_matches_or_resubmits_unknown_order(repos, mock_notifier):
    grid = _make_grid()
    await repos.grids.create(grid)
    client_id = new_id("ord")
    await repos.orders.create(_submitted_record(grid.grid_id, client_id))
    exchange = MockExchange()
    # Same symbol/side/quantity but a different client id must not be linked.
    exchange.orders_placed.append(ExchangeOrder(
        exchange_order_id="EX_OTHER", symbol="BTCINR", side="buy", price=54000.0,
        quantity=0.01, filled_quantity=0.0, filled_price=0.0,
        status=OrderStatus.OPEN.value, raw_status="open", client_order_id="other-order",
    ))
    manager = OrderManager(exchange, repos)
    dca = type("Dca", (), {"handle_order_filled": staticmethod(lambda **_: None)})()
    recovery = RecoveryManager(exchange, repos, mock_notifier, dca)

    await recovery.recover()
    order = await repos.orders.get(client_id)
    assert order["status"] == OrderStatus.UNKNOWN.value
    assert order["exchange_order_id"] is None
    assert len(exchange.orders_placed) == 1


@pytest.mark.anyio
async def test_coindcx_create_sends_client_id_and_explicitly_disables_retry(monkeypatch):
    client = CoinDCXClient("key", "secret")
    captured = {}

    async def fake_post(path, body=None, *, retry=True):
        captured.update(path=path, body=body, retry=retry)
        return {"orders": [{"id": "EX1", "market": "BTCINR", "side": "buy", "status": "open"}]}

    monkeypatch.setattr(client, "_post_private", fake_post)
    try:
        await client.place_order("BTCINR", type("Side", (), {"value": "buy"})(), 0, 0.01,
                                 "market_order", client_order_id="ord_immutable")
    finally:
        await client.close()
    assert captured["path"] == "/exchange/v1/orders/create"
    assert captured["retry"] is False
    assert captured["body"]["client_order_id"] == "ord_immutable"

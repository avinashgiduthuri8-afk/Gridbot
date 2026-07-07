"""Tests for CoinDCXClient: parsing, HMAC signing, and error mapping."""

from __future__ import annotations

import hashlib
import hmac
import json

import pytest

from config.constants import OrderStatus
from exchange.coindcx import CoinDCXClient, _STATUS_MAP
from exchange.base import MarketInfo
from exchange.exceptions import ExchangeError


@pytest.fixture
def client():
    return CoinDCXClient(api_key="testkey", api_secret="testsecret")


# ---------------------------------------------------------------------------
# _parse_order  (static, no I/O)
# ---------------------------------------------------------------------------


def test_parse_order_filled():
    raw = {
        "id": "abc123",
        "market": "BTCINR",
        "side": "buy",
        "status": "filled",
        "price_per_unit": 54000.0,
        "total_quantity": 0.01,
        "filled_quantity": 0.01,
        "avg_price": 54050.0,
    }
    order = CoinDCXClient._parse_order(raw)
    assert order.exchange_order_id == "abc123"
    assert order.symbol == "BTCINR"
    assert order.side == "buy"
    assert order.status == OrderStatus.FILLED.value
    assert order.filled_quantity == pytest.approx(0.01)
    assert order.filled_price == pytest.approx(54050.0)


def test_parse_order_open():
    raw = {"id": "x1", "market": "ETHINR", "side": "sell", "status": "open",
           "price_per_unit": 3000.0, "total_quantity": 1.0,
           "filled_quantity": 0.0, "avg_price": 0.0}
    order = CoinDCXClient._parse_order(raw)
    assert order.status == OrderStatus.OPEN.value


def test_parse_order_partially_filled():
    raw = {"id": "x2", "market": "BTCINR", "side": "buy", "status": "partially_filled",
           "price_per_unit": 54000.0, "total_quantity": 0.01,
           "filled_quantity": 0.005, "avg_price": 54010.0}
    order = CoinDCXClient._parse_order(raw)
    assert order.status == OrderStatus.PARTIALLY_FILLED.value
    assert order.filled_quantity == pytest.approx(0.005)


def test_parse_order_cancelled():
    raw = {"id": "x3", "market": "BTCINR", "side": "buy", "status": "cancelled",
           "price_per_unit": 54000.0, "total_quantity": 0.01,
           "filled_quantity": 0.0, "avg_price": 0.0}
    order = CoinDCXClient._parse_order(raw)
    assert order.status == OrderStatus.CANCELLED.value


def test_parse_order_init_maps_to_pending():
    raw = {"id": "x4", "market": "BTCINR", "side": "buy", "status": "init",
           "price_per_unit": 54000.0, "total_quantity": 0.01,
           "filled_quantity": 0.0, "avg_price": 0.0}
    order = CoinDCXClient._parse_order(raw)
    assert order.status == OrderStatus.PENDING.value


def test_parse_order_unknown_status_defaults_to_open():
    raw = {"id": "x5", "market": "BTCINR", "side": "buy", "status": "unknown_state",
           "price_per_unit": 54000.0, "total_quantity": 0.01,
           "filled_quantity": 0.0, "avg_price": 0.0}
    order = CoinDCXClient._parse_order(raw)
    assert order.status == OrderStatus.OPEN.value


def test_parse_order_uses_price_per_unit_when_avg_price_zero():
    raw = {"id": "x6", "market": "BTCINR", "side": "buy", "status": "filled",
           "price_per_unit": 54000.0, "total_quantity": 0.01,
           "filled_quantity": 0.01, "avg_price": 0.0}
    order = CoinDCXClient._parse_order(raw)
    assert order.filled_price == pytest.approx(54000.0)


def test_parse_order_missing_fields_do_not_crash():
    order = CoinDCXClient._parse_order({})
    assert order.exchange_order_id == ""
    assert order.status == OrderStatus.OPEN.value


# ---------------------------------------------------------------------------
# _sign (HMAC correctness)
# ---------------------------------------------------------------------------


def test_sign_produces_valid_hmac(client):
    body = {"market": "BTCINR", "side": "buy", "total_quantity": 0.01}
    payload, signature = client._sign(body)
    expected = hmac.new(
        b"testsecret",
        payload.encode(),
        hashlib.sha256,
    ).hexdigest()
    assert signature == expected


def test_sign_payload_is_compact_json(client):
    body = {"a": 1, "b": 2}
    payload, _ = client._sign(body)
    parsed = json.loads(payload)
    assert parsed == body
    assert " " not in payload


def test_sign_different_secrets_produce_different_sigs():
    c1 = CoinDCXClient(api_key="k", api_secret="secret1")
    c2 = CoinDCXClient(api_key="k", api_secret="secret2")
    body = {"x": 1}
    _, sig1 = c1._sign(body)
    _, sig2 = c2._sign(body)
    assert sig1 != sig2


# ---------------------------------------------------------------------------
# MarketInfo step_size derivation
# ---------------------------------------------------------------------------


def test_market_info_step_size_precision_5():
    info = MarketInfo(symbol="BTCINR", base_currency_precision=5,
                      quote_currency_precision=2, min_quantity=0.001, min_amount=10.0)
    assert info.step_size == pytest.approx(1e-5)


def test_market_info_step_size_precision_8():
    info = MarketInfo(symbol="BTCINR", base_currency_precision=8,
                      quote_currency_precision=2, min_quantity=0.00000001, min_amount=10.0)
    assert info.step_size == pytest.approx(1e-8)


# ---------------------------------------------------------------------------
# Status map completeness
# ---------------------------------------------------------------------------


def test_status_map_covers_all_known_states():
    expected = {"init", "open", "partially_filled", "filled", "cancelled", "rejected"}
    assert expected.issubset(set(_STATUS_MAP.keys()))

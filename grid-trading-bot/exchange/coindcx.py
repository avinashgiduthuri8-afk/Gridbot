"""CoinDCX REST API client.

Implements authenticated and public CoinDCX endpoints behind the shared
ExchangeClient interface, with automatic retry, rate-limit backoff, and
timeout handling so the trading engine never deals with raw HTTP concerns.

CoinDCX auth scheme: every private request body must include a millisecond
`timestamp`, signed with HMAC-SHA256(secret, json_body) sent as the
`X-AUTH-SIGNATURE` header alongside `X-AUTH-APIKEY`.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import time
from typing import Any

import httpx
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from config.constants import OrderSide, OrderStatus
from exchange.base import Balance, ExchangeClient, ExchangeOrder, MarketInfo, Ticker, Trade
from exchange.exceptions import (
    ExchangeAuthError,
    ExchangeConnectionError,
    ExchangeError,
    ExchangeRateLimitError,
    ExchangeTimeoutError,
    InsufficientBalanceError,
    OrderRejectedError,
)
from utils.logger import get_logger

log = get_logger("exchange")

_RETRYABLE = (ExchangeRateLimitError, ExchangeTimeoutError, ExchangeConnectionError)

_STATUS_MAP = {
    "init": OrderStatus.PENDING.value,
    "open": OrderStatus.OPEN.value,
    "partially_filled": OrderStatus.PARTIALLY_FILLED.value,
    "filled": OrderStatus.FILLED.value,
    "cancelled": OrderStatus.CANCELLED.value,
    "rejected": OrderStatus.REJECTED.value,
}


def _retry_policy():
    return retry(
        retry=retry_if_exception_type(_RETRYABLE),
        stop=stop_after_attempt(4),
        wait=wait_exponential(multiplier=0.75, min=0.75, max=8),
        reraise=True,
    )


class CoinDCXClient(ExchangeClient):
    def __init__(self, api_key: str, api_secret: str, base_url: str = "https://api.coindcx.com") -> None:
        self._api_key = api_key
        self._api_secret = api_secret.encode()
        self._base_url = base_url.rstrip("/")
        self._client = httpx.AsyncClient(base_url=self._base_url, timeout=15.0)
        self._market_cache: dict[str, MarketInfo] = {}

    async def close(self) -> None:
        await self._client.aclose()

    # ------------------------------------------------------------------
    # Low-level request helpers
    # ------------------------------------------------------------------

    def _sign(self, body: dict[str, Any]) -> tuple[str, str]:
        payload = json.dumps(body, separators=(",", ":"))
        signature = hmac.new(self._api_secret, payload.encode(), hashlib.sha256).hexdigest()
        return payload, signature

    async def _post_private(self, path: str, body: dict[str, Any] | None = None) -> Any:
        body = dict(body or {})
        body["timestamp"] = int(time.time() * 1000)
        payload, signature = self._sign(body)
        headers = {
            "Content-Type": "application/json",
            "X-AUTH-APIKEY": self._api_key,
            "X-AUTH-SIGNATURE": signature,
        }
        return await self._request("POST", path, content=payload, headers=headers)

    async def _get_public(self, path: str, params: dict[str, Any] | None = None) -> Any:
        return await self._request("GET", path, params=params)

    @_retry_policy()
    async def _request(self, method: str, path: str, **kwargs: Any) -> Any:
        try:
            response = await self._client.request(method, path, **kwargs)
        except httpx.TimeoutException as exc:
            log.warning("Timeout calling %s %s: %s", method, path, exc)
            raise ExchangeTimeoutError(f"Timeout calling {path}") from exc
        except httpx.ConnectError as exc:
            log.warning("Connection error calling %s %s: %s", method, path, exc)
            raise ExchangeConnectionError(f"Connection error calling {path}") from exc

        if response.status_code in (401, 403):
            log.error("Auth rejected on %s: %s", path, response.text[:300])
            raise ExchangeAuthError(f"CoinDCX rejected credentials on {path}: {response.text[:200]}")
        if response.status_code == 429:
            log.warning("Rate limited on %s, backing off", path)
            raise ExchangeRateLimitError(f"Rate limited on {path}")
        if response.status_code >= 500:
            log.warning("Server error %s on %s", response.status_code, path)
            raise ExchangeConnectionError(f"CoinDCX server error {response.status_code} on {path}")
        if response.status_code >= 400:
            message = response.text[:300]
            log.error("Request rejected on %s: %s", path, message)
            if "insufficient" in message.lower():
                raise InsufficientBalanceError(message)
            raise OrderRejectedError(f"CoinDCX rejected request on {path}: {message}")

        if not response.content:
            return None
        return response.json()

    # ------------------------------------------------------------------
    # Public data
    # ------------------------------------------------------------------

    async def get_ticker(self, symbol: str) -> Ticker:
        data = await self._get_public("/exchange/ticker")
        for entry in data:
            if entry.get("market") == symbol:
                return Ticker(symbol=symbol, last_price=float(entry["last_price"]))
        raise ExchangeError(f"Symbol {symbol} not found in ticker response")

    async def get_tickers_batch(self, symbols: set[str]) -> dict[str, "Ticker"]:
        """Fetch all tickers in one request and return only the requested symbols.

        CoinDCX /exchange/ticker always returns the full market list; we filter
        client-side so callers never pay more than one HTTP round-trip regardless
        of how many symbols are monitored.
        """
        if not symbols:
            return {}
        try:
            data = await self._get_public("/exchange/ticker")
        except Exception as exc:
            log.warning("Batch ticker fetch failed: %s", exc)
            return {}
        result: dict[str, Ticker] = {}
        for entry in data:
            market = entry.get("market", "")
            if market in symbols:
                try:
                    result[market] = Ticker(symbol=market, last_price=float(entry["last_price"]))
                except (KeyError, ValueError, TypeError) as exc:
                    log.warning("Bad ticker entry for %s: %s", market, exc)
        return result

    async def get_market_info(self, symbol: str) -> MarketInfo:
        """Return precision and minimum-size rules for *symbol*.

        Results are cached after the first fetch so subsequent calls
        within the same process lifetime are free.
        """
        if symbol in self._market_cache:
            return self._market_cache[symbol]
        await self._load_market_details()
        if symbol not in self._market_cache:
            raise ExchangeError(f"Market {symbol} not found in CoinDCX market details")
        return self._market_cache[symbol]

    async def _load_market_details(self) -> None:
        """Fetch all market details and populate the in-memory cache."""
        data: list[dict[str, Any]] = await self._get_public("/exchange/v1/markets_details")
        for item in data:
            sym = item.get("coindcx_name", "")
            if not sym:
                continue
            base_prec = int(item.get("base_currency_precision", 8))
            quote_prec = int(item.get("quote_currency_precision", 2))
            min_qty = float(item.get("min_quantity", 0) or 0)
            min_amt = float(item.get("min_amount", 0) or 0)
            self._market_cache[sym] = MarketInfo(
                symbol=sym,
                base_currency_precision=base_prec,
                quote_currency_precision=quote_prec,
                min_quantity=min_qty,
                min_amount=min_amt,
            )
        log.info("Loaded market details for %d symbols", len(self._market_cache))

    # ------------------------------------------------------------------
    # Wallet
    # ------------------------------------------------------------------

    async def get_balances(self) -> list[Balance]:
        data = await self._post_private("/exchange/v1/users/balances")
        return [
            Balance(
                currency=item["currency"],
                balance=float(item["balance"]),
                locked_balance=float(item.get("locked_balance", 0) or 0),
            )
            for item in data
        ]

    async def get_balance(self, currency: str) -> Balance:
        balances = await self.get_balances()
        for balance in balances:
            if balance.currency.upper() == currency.upper():
                return balance
        return Balance(currency=currency, balance=0.0, locked_balance=0.0)

    # ------------------------------------------------------------------
    # Orders
    # ------------------------------------------------------------------

    async def place_order(
        self,
        symbol: str,
        side: OrderSide,
        price: float,
        quantity: float,
        order_type: str = "limit_order",
    ) -> ExchangeOrder:
        body: dict[str, Any] = {
            "side": side.value,
            "order_type": order_type,
            "market": symbol,
            "total_quantity": quantity,
        }
        if order_type == "limit_order":
            body["price_per_unit"] = price
        data = await self._post_private("/exchange/v1/orders/create", body)
        orders = data.get("orders", [data]) if isinstance(data, dict) else data
        order = orders[0] if orders else data
        return self._parse_order(order)

    async def cancel_order(self, exchange_order_id: str) -> bool:
        try:
            await self._post_private("/exchange/v1/orders/cancel", {"id": exchange_order_id})
            return True
        except OrderRejectedError as exc:
            log.info("Cancel for %s rejected (likely already closed): %s", exchange_order_id, exc)
            return False

    async def get_order_status(self, exchange_order_id: str) -> ExchangeOrder:
        data = await self._post_private("/exchange/v1/orders/status", {"id": exchange_order_id})
        order = data.get("orders", [data])[0] if isinstance(data, dict) and "orders" in data else data
        return self._parse_order(order)

    async def get_open_orders(self, symbol: str | None = None) -> list[ExchangeOrder]:
        body: dict[str, Any] = {}
        if symbol:
            body["market"] = symbol
        data = await self._post_private("/exchange/v1/orders/active_orders", body)
        orders = data.get("orders", []) if isinstance(data, dict) else data
        return [self._parse_order(o) for o in orders]

    async def get_trade_history(self, symbol: str | None = None, limit: int = 50) -> list[Trade]:
        body: dict[str, Any] = {"limit": limit}
        if symbol:
            body["market"] = symbol
        data = await self._post_private("/exchange/v1/orders/trade_history", body)
        trades = data if isinstance(data, list) else data.get("trades", [])
        result: list[Trade] = []
        for t in trades:
            result.append(
                Trade(
                    exchange_order_id=str(t.get("order_id", "")),
                    symbol=t.get("market", symbol or ""),
                    side=t.get("side", ""),
                    price=float(t.get("price", 0)),
                    quantity=float(t.get("quantity", 0)),
                    fee=float(t.get("fee_amount", 0) or 0),
                    executed_at=str(t.get("timestamp", "")),
                )
            )
        return result

    @staticmethod
    def _parse_order(order: dict[str, Any]) -> ExchangeOrder:
        raw_status = str(order.get("status", "open")).lower()
        return ExchangeOrder(
            exchange_order_id=str(order.get("id", "")),
            symbol=order.get("market", ""),
            side=order.get("side", ""),
            price=float(order.get("price_per_unit", 0) or 0),
            quantity=float(order.get("total_quantity", 0) or 0),
            filled_quantity=float(order.get("filled_quantity", 0) or 0),
            filled_price=float(order.get("avg_price", 0) or order.get("price_per_unit", 0) or 0),
            status=_STATUS_MAP.get(raw_status, OrderStatus.OPEN.value),
            raw_status=raw_status,
        )

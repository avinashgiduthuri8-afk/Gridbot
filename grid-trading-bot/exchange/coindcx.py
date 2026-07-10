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

import asyncio as _asyncio
import time as _time_mod

import httpx
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from config.constants import OrderSide, OrderStatus
from exchange.base import Balance, ExchangeClient, ExchangeOrder, ExtendedTicker, MarketInfo, Ticker, Trade
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
    def __init__(
        self,
        api_key: str,
        api_secret: str,
        base_url: str = "https://api.coindcx.com",
        ticker_cache_ttl: float = 1.5,
    ) -> None:
        """Create a CoinDCX client.

        Args:
            ticker_cache_ttl: How long (seconds) to cache the full ticker list
                from /exchange/ticker.  Set to slightly less than the shortest
                price-monitor interval you intend to use so consecutive calls
                within the same poll cycle share one network round-trip without
                reusing data from the *previous* cycle.  Default 1.5s is safe
                down to the minimum supported 2s monitor interval.
        """
        self._api_key = api_key
        self._api_secret = api_secret.encode()
        self._base_url = base_url.rstrip("/")
        self._client = httpx.AsyncClient(base_url=self._base_url, timeout=15.0)
        self._market_cache: dict[str, MarketInfo] = {}
        self._ticker_cache_ttl: float = ticker_cache_ttl
        self._ticker_cache: list[dict] = []
        self._ticker_cache_ts: float = 0.0
        # Single-flight lock: prevents concurrent cache misses from issuing
        # multiple parallel /exchange/ticker requests.
        self._ticker_refresh_lock: _asyncio.Lock = _asyncio.Lock()

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

    async def _get_tickers_cached(self) -> list[dict]:
        """Return the full raw ticker list, refreshing only when the TTL has expired.

        CoinDCX's /exchange/ticker returns the complete market list (~100+ entries)
        every call.  With multiple active grids and a 5-10s poll interval, hitting
        this endpoint on every price tick wastes bandwidth and burns the rate limit.

        TTL is set to 1.5s by default (safe down to the 2s minimum poll interval):
        multiple symbols within the same poll cycle share one network round-trip
        without reusing stale prices from the previous cycle.

        A single-flight asyncio.Lock prevents concurrent cache misses from issuing
        multiple parallel requests — only one refresh fires at a time, and all
        waiters reuse its result.
        """
        now = _time_mod.monotonic()
        if self._ticker_cache and (now - self._ticker_cache_ts) < self._ticker_cache_ttl:
            log.debug("Ticker cache HIT (age=%.2fs)", now - self._ticker_cache_ts)
            return self._ticker_cache

        async with self._ticker_refresh_lock:
            # Re-check inside the lock: another coroutine may have refreshed
            # while we were waiting to acquire it.
            now = _time_mod.monotonic()
            if self._ticker_cache and (now - self._ticker_cache_ts) < self._ticker_cache_ttl:
                log.debug("Ticker cache HIT (post-lock, age=%.2fs)", now - self._ticker_cache_ts)
                return self._ticker_cache
            data: list[dict] = await self._get_public("/exchange/ticker")
            self._ticker_cache = data
            self._ticker_cache_ts = _time_mod.monotonic()
            log.debug("Ticker cache refreshed — %d entries", len(data))
            return data

    async def get_ticker(self, symbol: str) -> Ticker:
        data = await self._get_tickers_cached()
        for entry in data:
            if entry.get("market") == symbol:
                return Ticker(symbol=symbol, last_price=float(entry["last_price"]))
        raise ExchangeError(f"Symbol {symbol} not found in ticker response")

    async def get_tickers_batch(self, symbols: set[str]) -> dict[str, "Ticker"]:
        """Fetch all tickers in one request and return only the requested symbols.

        CoinDCX /exchange/ticker always returns the full market list; we filter
        client-side so callers never pay more than one HTTP round-trip regardless
        of how many symbols are monitored.  The shared TTL cache means this and
        get_ticker() share the same underlying data for the same poll cycle.
        """
        if not symbols:
            return {}
        try:
            data = await self._get_tickers_cached()
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
        """Fetch all market details and populate the in-memory cache.

        Field mapping is taken verbatim from CoinDCX's own
        ``/exchange/v1/markets_details`` schema. CoinDCX's naming is the
        reverse of the usual base/quote convention:

        - ``base_currency_precision``   -> decimals of the PRICING currency (price precision)
        - ``target_currency_precision`` -> decimals of the TRADED coin (quantity precision)
        - ``step``                      -> the authoritative quantity increment (NOT derived)
        - ``min_quantity``               -> minimum tradeable quantity of the traded coin
        - ``min_notional``               -> minimum order value in the pricing currency

        Every one of these must be read per-symbol from this response —
        never assumed, and never reused from another market's entry.
        """
        data: list[dict[str, Any]] = await self._get_public("/exchange/v1/markets_details")
        for item in data:
            sym = item.get("coindcx_name", "")
            if not sym:
                continue
            base_prec = int(item.get("base_currency_precision", 8))
            target_prec = int(item.get("target_currency_precision", 8))
            min_qty = float(item.get("min_quantity", 0) or 0)
            min_notional = float(item.get("min_notional", 0) or 0)
            raw_step = item.get("step")
            try:
                step = float(raw_step) if raw_step is not None else None
            except (TypeError, ValueError):
                step = None
            status = str(item.get("status", "active")).lower()
            base_short = str(item.get("base_currency_short_name", ""))
            target_short = str(item.get("target_currency_short_name", ""))

            if step is None:
                log.warning(
                    "market_details: %s has no 'step' field from CoinDCX — "
                    "falling back to target_currency_precision=%d (10^-%d)",
                    sym, target_prec, target_prec,
                )

            self._market_cache[sym] = MarketInfo(
                symbol=sym,
                base_currency_precision=base_prec,
                target_currency_precision=target_prec,
                min_quantity=min_qty,
                min_amount=min_notional,
                step_size=step,
                status=status,
                base_currency_short_name=base_short,
                target_currency_short_name=target_short,
            )
            log.debug(
                "market_details loaded symbol=%s base_prec=%d target_prec=%d "
                "step=%s min_quantity=%s min_notional=%s status=%s",
                sym, base_prec, target_prec, step, min_qty, min_notional, status,
            )
        log.info("Loaded market details for %d symbols", len(self._market_cache))

    async def get_extended_ticker(self, symbol: str) -> "ExtendedTicker":
        """Fetch full 24-hour market data for *symbol* in a single API call.

        Uses the TTL cache so a /coininfo call immediately after a price check
        doesn't hit the exchange twice.
        """
        data = await self._get_tickers_cached()
        for entry in data:
            if entry.get("market") != symbol:
                continue
            try:
                return ExtendedTicker(
                    symbol=symbol,
                    last_price=float(entry.get("last_price", 0) or 0),
                    change_24h=float(entry.get("change_24_hour", 0) or 0),
                    high_24h=float(entry.get("high", 0) or 0),
                    low_24h=float(entry.get("low", 0) or 0),
                    volume_24h=float(entry.get("volume", 0) or 0),
                    bid=float(entry.get("bid", 0) or 0),
                    ask=float(entry.get("ask", 0) or 0),
                    timestamp=int(entry.get("timestamp", 0) or 0),
                )
            except (KeyError, ValueError, TypeError) as exc:
                log.warning("Bad extended ticker entry for %s: %s", symbol, exc)
        raise ExchangeError(f"Symbol {symbol} not found in ticker response")

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

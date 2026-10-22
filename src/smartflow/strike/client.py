"""Strike Finance REST client: only endpoints present in the official OpenAPI (snapshot 2026-10-19,
``docs/sources/strike_openapi_merged_2026-10-19.json``), plus ``GET /v2/markets`` (used by the official
strike-builder-reference and verified live).

Bases: trading/account ``https://api.strikefinance.org`` (testnet ``https://api-v2-testnet.strikefinance.org``),
market data under ``/price``, statistics under ``/stat``.

Builder fee: ``X-Builder-Fee-Bps`` is attached to order-creating requests only, and only when a builder fee is
configured. It must be <= the fee the user approved at builder-connect AND <= the builder's registered fee share,
otherwise Strike rejects the order with 400 (docs: api/builder-codes "Fee rules").
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Callable

from ..net import HttpError, request_json
from .auth import ApiWalletSigner, serialize_body
from .models import (AccountState, Order, Position, Transfer, parse_account, parse_fee_tiers, parse_fills, parse_market,
                     parse_order, parse_positions, parse_premium, parse_transfers)

MAINNET = "https://api.strikefinance.org"
TESTNET = "https://api-v2-testnet.strikefinance.org"
ORDER_PATHS = {"/v2/order", "/v2/order/strategy", "/v2/orders/batch", "/v2/order/replace", "/v2/order/replace-batch",
               "/v2/orders/replace"}


@dataclass(frozen=True)
class BuilderFee:
    code: str
    fee_bps: int
    approved_bps: int | None = None   # what the user approved at connect (verify-signature response)
    registered_bps: int | None = None  # the builder's configured fee share (dashboard)

    def validate(self) -> None:
        if not 0 <= self.fee_bps <= 100:
            raise ValueError("builder fee must be 0..100 bps")
        for cap, name in ((self.approved_bps, "user-approved"), (self.registered_bps, "registered")):
            if cap is not None and self.fee_bps > cap:
                raise ValueError(f"builder fee {self.fee_bps} bps exceeds the {name} cap of {cap} bps")


class StrikeClient:
    def __init__(self, base: str = MAINNET, signer: ApiWalletSigner | None = None,
                 builder: BuilderFee | None = None, timeout: float = 15.0, sub_account_id: str | None = None):
        self.base = base.rstrip("/")
        self.signer = signer
        self.builder = builder
        if builder:
            builder.validate()
        self.timeout = timeout
        self.sub_account_id = sub_account_id
        self.clock_offset_s = 0.0
        # audit hook: called with every signed request that changes something (and every signed read that fails),
        # as sent and as answered; the signing headers are never included. It must not raise.
        self.trace: Callable[[dict], None] | None = None

    # ------------------------------------------------------------------ transport
    def _public(self, path: str, params: dict | None = None):
        status, data, _ = request_json("GET", self.base + path, params=params, timeout=self.timeout)
        return data

    def _signed(self, method: str, path: str, params: dict | None = None, body: dict | None = None):
        if self.signer is None:
            raise RuntimeError("this call needs an API wallet (signer)")
        query = ""
        clean = {k: v for k, v in (params or {}).items() if v is not None}
        if clean:  # never sign a dangling "?": the server verifies the path without it (verified 2026-10-19)
            from urllib.parse import urlencode
            query = "?" + urlencode(clean)
        body_s = serialize_body(body) if method != "GET" else ""
        ts = int(time.time() + self.clock_offset_s)
        headers = self.signer.headers(method, path + query, body_s, timestamp=ts)
        if body is not None:
            headers["Content-Type"] = "application/json"
        if self.builder and self.builder.fee_bps > 0 and method == "POST" and path in ORDER_PATHS:
            headers["X-Builder-Fee-Bps"] = str(self.builder.fee_bps)
        t0 = time.monotonic()
        try:
            status, data, _ = request_json(method, self.base + path + query, body=body_s.encode() if body_s else None,
                                           headers=headers, timeout=self.timeout)
        except Exception as e:
            self._trace(method, path + query, body, headers, t0, error=e)
            raise
        if method != "GET":
            self._trace(method, path + query, body, headers, t0, status=status, response=data)
        return data

    def _trace(self, method: str, path: str, body: dict | None, headers: dict, t0: float, status: int | None = None,
               response=None, error: Exception | None = None) -> None:
        if self.trace is None:
            return
        rec = {"method": method, "url": self.base + path, "body": body,
               "builder_fee_bps": int(headers["X-Builder-Fee-Bps"]) if "X-Builder-Fee-Bps" in headers else None,
               "ms": round((time.monotonic() - t0) * 1000)}
        if error is None:
            rec.update(status=status, response=response)
        elif isinstance(error, HttpError):
            rec.update(status=error.status, error=error.body[:4000])
        else:   # timeout or connection error: the request may or may not have reached Strike
            rec.update(status=None, error=repr(error)[:1000])
        try:
            self.trace(rec)
        except Exception:
            pass

    def sync_clock(self) -> float:
        """Server time drift guard: signatures must be within 3 minutes of server time."""
        t0 = time.time()
        server = self.time()
        self.clock_offset_s = server / 1000 - (t0 + time.time()) / 2
        return self.clock_offset_s

    # ------------------------------------------------------------------ public (no auth)
    def ping(self) -> bool:
        return self._public("/v2/ping") is not None

    def time(self) -> int:
        return int(self._public("/v2/time")["serverTime"])

    def markets(self) -> dict:
        return {s: parse_market(m) for s, m in self._public("/v2/markets")["markets"].items()}

    def exchange_info(self) -> dict:
        return self._public("/price/v2/exchangeInfo")

    def fee_tiers(self):
        return parse_fee_tiers(self._public("/v2/fee-tiers"))

    def klines(self, symbol: str, interval: str, start_ms: int | None = None, end_ms: int | None = None,
               limit: int = 1500, price_type: str = "last") -> list[list]:
        params = {"symbol": symbol, "interval": interval, "limit": limit, "priceType": price_type}
        if start_ms is not None:
            params["startTime"] = start_ms
        if end_ms is not None:
            params["endTime"] = end_ms
        return self._public("/price/v2/klines", params)

    def depth(self, symbol: str, limit: int = 100) -> dict:
        return self._public("/price/v2/depth", {"symbol": symbol, "limit": limit})

    def book_ticker(self, symbol: str) -> dict:
        d = self._public("/price/v2/ticker/bookTicker", {"symbol": symbol})
        return d[0] if isinstance(d, list) else d

    def premium(self, symbol: str) -> dict:
        return parse_premium(self._public("/price/v2/premiumIndex", {"symbol": symbol}), symbol)

    # ------------------------------------------------------------------ account (API wallet)
    def _scope(self, params: dict | None = None) -> dict:
        p = dict(params or {})
        if self.sub_account_id:
            p["sub_account_id"] = self.sub_account_id
        return p

    def account(self) -> AccountState:
        return parse_account(self._signed("GET", "/v2/account", self._scope()))

    def positions(self, symbol: str | None = None) -> list[Position]:
        return parse_positions(self._signed("GET", "/v2/positions", self._scope({"symbol": symbol})))

    def open_orders(self, symbol: str | None = None) -> list[Order]:
        d = self._signed("GET", "/v2/openOrders", self._scope({"symbol": symbol}))
        return [parse_order(o) for o in ((d or {}).get("orders") or [])]

    def order(self, symbol: str, order_id: int | None = None, client_order_id: str | None = None) -> Order | None:
        try:
            d = self._signed("GET", "/v2/order", self._scope({"symbol": symbol, "order_id": order_id,
                                                               "client_order_id": client_order_id}))
        except HttpError as e:
            if e.status == 404:
                return None
            raise
        return parse_order(d.get("data", d) if isinstance(d, dict) else d)

    def fills(self, symbol: str | None = None, since_trade_id: int | None = None, limit: int = 500):
        return parse_fills(self._signed("GET", "/v2/history/fill", self._scope(
            {"symbol": symbol, "since_trade_id": since_trade_id, "limit": limit})))

    def transfers(self, start_ms: int | None = None, limit: int = 200) -> list[Transfer]:
        """Deposits, withdrawals and transfers of the account, newest first (GET /v2/history/transaction)."""
        return parse_transfers(self._signed("GET", "/v2/history/transaction", self._scope(
            {"type": "1,2,10", "startTime": start_ms, "limit": limit})))

    def funding_history(self, symbol: str | None = None, start_ms: int | None = None, limit: int = 500) -> dict:
        return self._signed("GET", "/v2/history/funding", self._scope({"symbol": symbol, "startTime": start_ms,
                                                                        "limit": limit}))

    # ------------------------------------------------------------------ trading (API wallet)
    def _with_scope(self, body: dict) -> dict:
        if self.sub_account_id:
            body = {**body, "sub_account_id": self.sub_account_id}
        return body

    def set_leverage(self, symbol: str, leverage: int) -> dict:
        return self._signed("POST", "/v2/leverage", body=self._with_scope({"symbol": symbol, "leverage": int(leverage)}))

    def set_margin_mode(self, symbol: str, mode: str) -> dict:
        return self._signed("POST", "/v2/marginMode", body=self._with_scope({"symbol": symbol, "marginMode": mode}))

    def create_order(self, body: dict) -> dict:
        """POST /v2/order. The response has no order id (the engine is asynchronous): reconcile with
        ``order(symbol, client_order_id=...)``."""
        return self._signed("POST", "/v2/order", body=self._with_scope(body))

    def create_strategy_order(self, body: dict) -> dict:
        """POST /v2/order/strategy (bracket / OTOCO): primary + ``tp_order`` and/or ``sl_order``; the legs are
        placed when the primary fills and are reduce-only."""
        return self._signed("POST", "/v2/order/strategy", body=self._with_scope(body))

    def cancel_order(self, symbol: str, order_id: int) -> dict:
        return self._signed("DELETE", "/v2/order/cancel", body=self._with_scope({"order_id": int(order_id),
                                                                                 "symbol": symbol}))

    def cancel_all(self, symbol: str | None = None) -> dict:
        return self._signed("DELETE", "/v2/order/cancel-all", body=self._with_scope({"symbol": symbol} if symbol else {}))

    # ------------------------------------------------------------------ copy trading (API wallet)
    def copy_subscribe(self, body: dict) -> dict:
        """POST /v2/copy/subscribe: `active` (201) or, for a managed copy (its own sub-account), `creating_account`,
        `funding`, `refunding` (202) until done; repeat the same body (same `request_id`) to poll."""
        return self._signed("POST", "/v2/copy/subscribe", body=body) or {}

    def copy_update(self, subscription_id: str, body: dict) -> None:
        self._signed("PATCH", f"/v2/copy/subscribe/{subscription_id}", body=body)

    def copy_stop(self, subscription_id: str, sub_account_id: str | None = None) -> None:
        """Stops the copy and closes its copied positions (Strike pays a Strike lead its share of the profit)."""
        self._signed("DELETE", f"/v2/copy/subscribe/{subscription_id}", {"sub_account_id": sub_account_id})

    def copy_subscriptions(self, status: str | None = None) -> list[dict]:
        """Every copy of the master account and its sub-accounts (each row with its `account_id`)."""
        d = self._signed("GET", "/v2/copy/subscriptions", {"scope": "all", "status": status}) or {}
        return list(d.get("subscriptions") or [])

    def account_of(self, sub_account_id: str | None) -> dict:
        """The raw account reading of the master account or of one of its sub-accounts."""
        return self._signed("GET", "/v2/account", {"sub_account_id": sub_account_id}) or {}

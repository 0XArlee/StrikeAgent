"""Execution adapters with one interface: ``StrikeExecution`` (real orders through the official API) and
``PaperExecution`` (same decisions, simulated fills against Strike's live public order book).

Entry = bracket order (``POST /v2/order/strategy``): primary LIMIT IOC at a protective price (bounded slippage; an
unfilled IOC cancels the whole strategy) + reduce-only stop leg (+ optional take-profit leg). Strike places the legs
when the primary fills; the agent then *confirms* the stop leg is resting before calling the position protected,
and falls back to a standalone reduce-only stop if it is not.

Exit = market reduce-only order (``POST /v2/order``) for the position size, then cancel leftover strategy legs.

Client order ids are deterministic per (trade, purpose) so a retry after a timeout can be reconciled with
``GET /v2/order?client_order_id=`` instead of being sent twice.
"""

from __future__ import annotations

import hashlib
import math
import time
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Protocol

from ..strike.client import StrikeClient
from ..strike.models import AccountState, MarketSpec, Order, Position


def client_id(trade_id: str, purpose: str) -> str:
    return "sf-" + hashlib.sha256(f"{trade_id}:{purpose}".encode()).hexdigest()[:20] + "-" + purpose[:2]


@dataclass(frozen=True)
class Quote:
    bid: float
    ask: float
    mark: float
    index: float
    funding_rate: float
    ts: float

    @property
    def mid(self) -> float:
        return (self.bid + self.ask) / 2


@dataclass(frozen=True)
class EntryPlan:
    trade_id: str
    symbol: str
    dir: int
    qty: Decimal
    limit_price: Decimal      # protective IOC price
    stop: Decimal
    take_profit: Decimal | None
    leverage: int

    def side(self) -> str:
        return "buy" if self.dir == 1 else "sell"


@dataclass
class Ack:
    ok: bool
    client_order_id: str
    response: dict = field(default_factory=dict)
    error: str = ""
    uncertain: bool = False   # timeout / 5xx: the order MAY have reached the engine -> reconcile, never resend


UNCERTAIN_STATUS = {0, 408, 425, 429, 500, 502, 503, 504}


def _fail(cid: str, e: Exception) -> Ack:
    """Verified on testnet 2026-10-19: a duplicate client_order_id is NOT rejected (a second order is created), so a
    failed request whose outcome is unknown must be reconciled by client_order_id, not retried."""
    from ..net import HttpError
    status = getattr(e, "status", None)
    uncertain = isinstance(e, HttpError) and status in UNCERTAIN_STATUS
    return Ack(False, cid, error=str(e), uncertain=uncertain or not isinstance(e, HttpError))


class ExecutionAdapter(Protocol):
    name: str
    live: bool

    def market_spec(self, symbol: str) -> MarketSpec: ...
    def quote(self, symbol: str) -> Quote: ...
    def impact_bps(self, symbol: str, side: int, qty: float) -> float: ...
    def account(self) -> AccountState: ...
    def position(self, symbol: str) -> Position | None: ...
    def all_positions(self) -> dict[str, Position]: ...
    def open_orders(self, symbol: str) -> list[Order]: ...
    def find_order(self, symbol: str, client_order_id: str) -> Order | None: ...
    def submit_entry(self, plan: EntryPlan) -> Ack: ...
    def submit_stop(self, trade_id: str, symbol: str, dir: int, qty: Decimal, stop: Decimal, purpose: str = "stop2") -> Ack: ...
    def submit_exit(self, trade_id: str, symbol: str, dir: int, qty: Decimal, reason: str) -> Ack: ...
    def cancel(self, symbol: str, order_id: int) -> None: ...
    def tick(self) -> list[dict]: ...


def walk_book(levels: list[list], qty: float) -> float:
    """Average fill price of ``qty`` walking ``[[price, size], ...]``; nan if the book is too thin."""
    got, cost = 0.0, 0.0
    for p, q in levels:
        p, q = float(p), float(q)
        take = min(q, qty - got)
        got += take
        cost += take * p
        if got >= qty - 1e-15:
            return cost / got
    return math.nan


class _StrikeMarketData:
    def __init__(self, public: StrikeClient):
        self.public = public
        self._specs: dict[str, MarketSpec] = {}
        self._specs_t = 0.0

    def market_spec(self, symbol: str) -> MarketSpec:
        if not self._specs or time.time() - self._specs_t > 900:
            self._specs = self.public.markets()
            self._specs_t = time.time()
        return self._specs[symbol]

    def quote(self, symbol: str) -> Quote:
        bt = self.public.book_ticker(symbol)
        pr = self.public.premium(symbol)
        return Quote(float(bt["bidPrice"]), float(bt["askPrice"]), pr["mark"], pr["index"], pr["funding_rate"],
                     time.time())

    def impact_bps(self, symbol: str, side: int, qty: float) -> float:
        d = self.public.depth(symbol, 200)
        bid, ask = float(d["bids"][0][0]), float(d["asks"][0][0])
        mid = (bid + ask) / 2
        px = walk_book(d["asks"] if side == 1 else d["bids"], qty)
        return math.inf if math.isnan(px) else abs(px - mid) / mid * 1e4


class StrikeExecution(_StrikeMarketData):
    name = "strike"
    live = True

    def __init__(self, client: StrikeClient):
        super().__init__(client)
        self.c = client

    def account(self) -> AccountState:
        return self.c.account()

    def position(self, symbol: str) -> Position | None:
        ps = [p for p in self.c.positions(symbol) if p.symbol == symbol and p.size != 0]
        return ps[0] if ps else None

    def all_positions(self) -> dict[str, Position]:
        """Every open position of the account in one call (reconcile reads them all at once)."""
        return {p.symbol: p for p in self.c.positions() if p.size != 0}

    def open_orders(self, symbol: str) -> list[Order]:
        return self.c.open_orders(symbol)

    def find_order(self, symbol: str, client_order_id: str) -> Order | None:
        return self.c.order(symbol, client_order_id=client_order_id)

    def submit_entry(self, plan: EntryPlan) -> Ack:
        cid = client_id(plan.trade_id, "entry")
        if self.find_order(plan.symbol, cid):          # idempotency: already reached the engine
            return Ack(True, cid, {"note": "already submitted"})
        try:
            self.c.set_leverage(plan.symbol, plan.leverage)
        except Exception as e:  # leverage is a cap; failing to lower it must stop the entry
            return Ack(False, cid, error=f"set_leverage failed: {e}")
        exit_side = "sell" if plan.dir == 1 else "buy"
        body = {
            "strategy_id": "sf-" + plan.trade_id[:40], "client_order_id": cid, "symbol": plan.symbol,
            "side": plan.side(), "type": "limit", "time_in_force": "IOC", "size": str(plan.qty),
            "price": str(plan.limit_price),
            "sl_order": {"client_order_id": client_id(plan.trade_id, "stop"), "type": "stop", "size": str(plan.qty),
                         "stop_price": str(plan.stop), "working_type": "mark_price"},
        }
        if plan.take_profit is not None:
            body["tp_order"] = {"client_order_id": client_id(plan.trade_id, "target"), "type": "take_profit",
                                "size": str(plan.qty), "stop_price": str(plan.take_profit),
                                "working_type": "mark_price"}
        _ = exit_side
        try:
            return Ack(True, cid, self.c.create_strategy_order(body))
        except Exception as e:
            return _fail(cid, e)

    def submit_stop(self, trade_id: str, symbol: str, dir: int, qty: Decimal, stop: Decimal, purpose: str = "stop2") -> Ack:
        cid = client_id(trade_id, purpose)
        if self.find_order(symbol, cid):
            return Ack(True, cid, {"note": "already submitted"})
        body = {"client_order_id": cid, "symbol": symbol, "side": "sell" if dir == 1 else "buy", "type": "stop",
                "size": str(qty), "stop_price": str(stop), "reduce_only": True, "working_type": "mark_price"}
        try:
            return Ack(True, cid, self.c.create_order(body))
        except Exception as e:
            return _fail(cid, e)

    def submit_exit(self, trade_id: str, symbol: str, dir: int, qty: Decimal, reason: str) -> Ack:
        cid = client_id(trade_id, "exit")
        if self.find_order(symbol, cid):
            return Ack(True, cid, {"note": "already submitted"})
        body = {"client_order_id": cid, "symbol": symbol, "side": "sell" if dir == 1 else "buy", "type": "market",
                "size": str(qty), "reduce_only": True, "slippage": "0.01"}
        try:
            return Ack(True, cid, self.c.create_order(body))
        except Exception as e:
            return _fail(cid, e)

    def cancel(self, symbol: str, order_id: int) -> None:
        self.c.cancel_order(symbol, order_id)

    def tick(self) -> list[dict]:
        return []


@dataclass
class _PaperPos:
    trade_id: str
    dir: int
    qty: float
    entry: float
    stop: float
    tp: float | None
    opened: float
    fees: float


def _trade_cids(trade_id: str) -> set[str]:
    """The orders that belong to one trade (entry, its stop legs, target, exit)."""
    return {client_id(trade_id, k) for k in ("entry", "stop", "stop2", "stop3", "stop4", "stop5", "target", "exit")}


class PaperExecution(_StrikeMarketData):
    """Simulated account on top of Strike's real public prices. Fills: IOC entry at the book-walk price if within
    the protective limit; exits at the book-walk price; stops trigger on the mark price (Strike's default working
    type) and fill at the bid/ask then (plus the book walk). Fees: taker + builder on every fill.

    A market can hold several trades in the same direction (the pyramid policy): like Strike, the position is their
    net sum, while each trade keeps its own lot, stop and exit."""

    name = "paper"
    live = False

    def __init__(self, public: StrikeClient, equity: float = 10_000.0, taker_fee: float = 0.0005,
                 builder_fee_bps: float = 0.0):
        super().__init__(public)
        self.equity0 = equity
        self.cash = equity
        self.taker_fee = taker_fee
        self.builder = builder_fee_bps / 1e4
        self.pos: dict[str, list[_PaperPos]] = {}
        self.orders: dict[str, Order] = {}
        self.legs: dict[str, set[str]] = {}   # every stop a trade had (a moved stop replaces the previous one)
        self.events: list[dict] = []

    def _fee(self, notional: float) -> float:
        return notional * (self.taker_fee + self.builder)

    def snapshot(self) -> dict:
        return {"cash": self.cash, "equity0": self.equity0,
                "lots": {s: [p.__dict__ for p in lots] for s, lots in self.pos.items()}, "events": self.events[-500:]}

    def restore(self, d: dict) -> None:
        if not d:
            return
        self.cash, self.equity0 = d.get("cash", self.cash), d.get("equity0", self.equity0)
        if "lots" in d:
            self.pos = {s: [_PaperPos(**p) for p in lots] for s, lots in d["lots"].items() if lots}
        else:   # state written before stacked trades: one lot per market
            self.pos = {s: [_PaperPos(**p)] for s, p in d.get("pos", {}).items()}
        self.events = d.get("events", [])
        for s, lots in self.pos.items():   # the resting paper stops survive the restart
            for p in lots:
                self._record(client_id(p.trade_id, "stop"), s, "sell" if p.dir == 1 else "buy", "stop", "untriggered",
                             p.qty, math.nan, p.stop, True)

    def account(self) -> AccountState:
        upnl = 0.0
        for s, lots in self.pos.items():
            q = self.quote(s)
            upnl += sum((q.mark - p.entry) * p.dir * p.qty for p in lots)
        eq = self.cash + upnl
        used = sum(p.qty * p.entry for lots in self.pos.values() for p in lots) / 5
        return AccountState("paper", self.cash, eq - used, eq, upnl, 0.0, {})

    def all_positions(self) -> dict[str, Position]:
        return {s: p for s in list(self.pos) if (p := self.position(s)) is not None}

    def position(self, symbol: str) -> Position | None:
        lots = self.pos.get(symbol)
        if not lots:
            return None
        qty = sum(p.qty for p in lots)
        entry = sum(p.qty * p.entry for p in lots) / qty
        return Position(symbol, qty * lots[0].dir, entry, 1, "cross", math.nan, 0.0, 0.0, 0, {})

    def open_orders(self, symbol: str) -> list[Order]:
        return [o for o in self.orders.values() if o.symbol == symbol and not o.is_terminal]

    def find_order(self, symbol: str, client_order_id: str) -> Order | None:
        return self.orders.get(client_order_id)

    def _record(self, cid, symbol, side, typ, status, qty, px, stop=math.nan, reduce=False) -> Order:
        o = Order(0, cid, symbol, side, typ, status, qty, qty if status == "filled" else 0.0, px, stop, reduce,
                  None, "paper", int(self.builder * 1e4), {})
        self.orders[cid] = o
        return o

    def _set_status(self, cid: str, status: str) -> None:
        o = self.orders.get(cid)
        if o is not None and not o.is_terminal:
            self.orders[cid] = Order(o.order_id, o.client_order_id, o.symbol, o.side, o.type, status, o.size,
                                     o.size if status == "filled" else o.filled, o.price, o.stop_price, o.reduce_only,
                                     o.strategy_id, o.builder_code, o.builder_fee_bps, {})

    def submit_entry(self, plan: EntryPlan) -> Ack:
        cid = client_id(plan.trade_id, "entry")
        if cid in self.orders:
            return Ack(True, cid, {"note": "already submitted"})
        lots = self.pos.get(plan.symbol, [])
        if lots and lots[0].dir != plan.dir:   # a netted account cannot hold both sides
            self._record(cid, plan.symbol, plan.side(), "limit", "rejected", float(plan.qty), float(plan.limit_price))
            return Ack(False, cid, error="opposite position open")
        d = self.public.depth(plan.symbol, 200)
        px = walk_book(d["asks"] if plan.dir == 1 else d["bids"], float(plan.qty))
        lim = float(plan.limit_price)
        if math.isnan(px) or (plan.dir == 1 and px > lim) or (plan.dir == -1 and px < lim):
            self._record(cid, plan.symbol, plan.side(), "limit", "canceled", float(plan.qty), lim)
            return Ack(True, cid, {"status": "canceled", "reason": "IOC not filled within protective price"})
        fee = self._fee(px * float(plan.qty))
        self.cash -= fee
        self.pos.setdefault(plan.symbol, []).append(
            _PaperPos(plan.trade_id, plan.dir, float(plan.qty), px, float(plan.stop),
                      float(plan.take_profit) if plan.take_profit is not None else None, time.time(), fee))
        self._record(cid, plan.symbol, plan.side(), "limit", "filled", float(plan.qty), px)
        self._record(client_id(plan.trade_id, "stop"), plan.symbol, "sell" if plan.dir == 1 else "buy", "stop",
                     "untriggered", float(plan.qty), math.nan, float(plan.stop), True)
        self.events.append({"event": "entry", "symbol": plan.symbol, "price": px, "qty": float(plan.qty), "fee": fee,
                            "trade_id": plan.trade_id})
        return Ack(True, cid, {"status": "filled", "avg_price": px, "fee": fee})

    def submit_stop(self, trade_id, symbol, dir, qty, stop, purpose="stop2") -> Ack:
        cid = client_id(trade_id, purpose)
        for old in self.legs.get(trade_id, set()) | {client_id(trade_id, "stop")}:   # one paper stop per lot
            if old != cid:
                self._set_status(old, "canceled")
        self.legs.setdefault(trade_id, set()).add(cid)
        self._record(cid, symbol, "sell" if dir == 1 else "buy", "stop", "untriggered", float(qty), math.nan,
                     float(stop), True)
        for p in self.pos.get(symbol, []):
            if p.trade_id == trade_id:
                p.stop = float(stop)
        return Ack(True, cid, {"status": "untriggered"})

    def _close(self, symbol: str, lot: _PaperPos, px: float, reason: str) -> dict:
        self.pos[symbol].remove(lot)
        if not self.pos[symbol]:
            del self.pos[symbol]
        fee = self._fee(px * lot.qty)
        pnl = (px - lot.entry) * lot.dir * lot.qty
        self.cash += pnl - fee
        if reason in ("stop", "target"):   # the leg that fired is filled, the trade's other legs are cancelled
            self._set_status(client_id(lot.trade_id, "stop" if reason == "stop" else "target"), "filled")
        for cid in _trade_cids(lot.trade_id) | self.legs.pop(lot.trade_id, set()):
            self._set_status(cid, "canceled")
        ev = {"event": "exit", "symbol": symbol, "reason": reason, "price": px, "qty": lot.qty, "pnl": pnl,
              "fees": lot.fees + fee, "trade_id": lot.trade_id}
        self.events.append(ev)
        return ev

    def submit_exit(self, trade_id, symbol, dir, qty, reason) -> Ack:
        cid = client_id(trade_id, "exit")
        lots = self.pos.get(symbol, [])
        lot = next((p for p in lots if p.trade_id == trade_id), lots[0] if len(lots) == 1 else None)
        if lot is None:
            return Ack(False, cid, error="no paper position for this trade")
        d = self.public.depth(symbol, 200)
        px = walk_book(d["bids"] if dir == 1 else d["asks"], lot.qty)
        ev = self._close(symbol, lot, px, reason)
        self._record(cid, symbol, "sell" if dir == 1 else "buy", "market", "filled", lot.qty, px, reduce=True)
        return Ack(True, cid, ev)

    def cancel(self, symbol, order_id) -> None:
        return None

    def tick(self) -> list[dict]:
        """Check every lot's paper stop/target against the current mark price; returns exit events."""
        out = []
        for s in list(self.pos):
            q = self.quote(s)
            for p in list(self.pos.get(s, [])):
                hit_stop = (q.mark <= p.stop) if p.dir == 1 else (q.mark >= p.stop)
                hit_tp = p.tp is not None and ((q.mark >= p.tp) if p.dir == 1 else (q.mark <= p.tp))
                if hit_stop or hit_tp:
                    d = self.public.depth(s, 200)
                    px = walk_book(d["bids"] if p.dir == 1 else d["asks"], p.qty)
                    out.append(self._close(s, p, px, "stop" if hit_stop else "target"))
        return out

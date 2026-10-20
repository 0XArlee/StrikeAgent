"""Tolerant parsing of Strike responses.

The live API does not always match the published OpenAPI (verified 2026-10-19): ``/v2/fee-tiers`` returns PascalCase
keys, ``/price/v2/premiumIndex`` returns a list with ``fundingRate`` instead of an object with ``lastFundingRate``,
``/v2/order`` returns PascalCase order objects while ``/v2/history/order`` uses snake_case. Every parser here accepts
the documented and the observed spellings and keeps the raw payload.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from decimal import ROUND_DOWN, Decimal


def pick(d: dict, *names, default=None):
    for n in names:
        if n in d and d[n] is not None:
            return d[n]
    lower = {k.lower(): v for k, v in d.items()}
    for n in names:
        v = lower.get(n.lower())
        if v is not None:
            return v
    return default


def fnum(x, default: float = math.nan) -> float:
    try:
        return float(x)
    except (TypeError, ValueError):
        return default


@dataclass(frozen=True)
class MarginTier:
    max_notional: float
    max_leverage: int
    mmr: float
    maintenance_amount: float


@dataclass(frozen=True)
class MarketSpec:
    symbol: str
    status: str
    tick: Decimal
    step: Decimal
    min_qty: Decimal
    max_market_qty: Decimal
    min_notional: float
    market_price_bound: float      # max deviation of a market fill from mark (e.g. 0.05)
    tiers: tuple[MarginTier, ...]
    default_leverage: int
    reduce_only_mode: bool         # market accepts only reduce-only orders
    raw: dict = field(default_factory=dict, compare=False, repr=False)

    @property
    def tradable(self) -> bool:
        return self.status.lower() == "trading" and not self.reduce_only_mode

    def round_qty(self, q: float) -> Decimal:
        return (Decimal(repr(q)) / self.step).to_integral_value(ROUND_DOWN) * self.step

    def round_price(self, p: float, side_up: bool | None = None) -> Decimal:
        """Round to tick; ``side_up`` True rounds up, False down, None to nearest."""
        x = Decimal(repr(p)) / self.tick
        if side_up is None:
            x = x.quantize(Decimal(1))
        else:
            x = x.to_integral_value("ROUND_CEILING" if side_up else "ROUND_FLOOR")
        return x * self.tick

    def tier_for(self, notional: float) -> MarginTier:
        for t in self.tiers:
            if notional <= t.max_notional:
                return t
        return self.tiers[-1]


def parse_market(m: dict) -> MarketSpec:
    tiers = tuple(sorted((MarginTier(fnum(t.get("max_notional")), int(fnum(t.get("max_leverage"), 1)),
                                     fnum(t.get("maintenance_margin_rate")), fnum(t.get("maintenance_amount"), 0.0))
                          for t in m.get("margin_tiers", [])), key=lambda t: t.max_notional))
    return MarketSpec(
        symbol=m["symbol"], status=str(m.get("status", "")),
        tick=Decimal(str(pick(m, "order_tick_price", default="0.01"))),
        step=Decimal(str(pick(m, "order_market_step_size", "order_limit_step_size", default="0.001"))),
        min_qty=Decimal(str(pick(m, "order_market_min_size", "order_limit_min_size", default="0"))),
        max_market_qty=Decimal(str(pick(m, "order_market_max_size", default="1e18"))),
        min_notional=fnum(pick(m, "order_min_notional", default=0)),
        market_price_bound=fnum(pick(m, "order_market_price_bound", default=0.05)),
        tiers=tiers or (MarginTier(math.inf, int(fnum(m.get("default_leverage"), 10)), 0.01, 0.0),),
        default_leverage=int(fnum(m.get("default_leverage"), 10)),
        reduce_only_mode=bool(m.get("reduce_only", False)), raw=m,
    )


@dataclass(frozen=True)
class FeeTier:
    tier: int
    min_volume: float
    taker: float
    maker: float


def parse_fee_tiers(payload) -> list[FeeTier]:
    rows = (payload.get("feeTiers") or payload.get("fee_tiers") if isinstance(payload, dict) else payload) or []
    return [FeeTier(int(fnum(pick(r, "tier", "Tier"), 0)), fnum(pick(r, "minVolume", "MinVolume")),
                    fnum(pick(r, "takerRate", "TakerRate")), fnum(pick(r, "makerRate", "MakerRate"))) for r in rows]


@dataclass(frozen=True)
class Position:
    symbol: str
    size: float              # signed: + long, - short
    entry_price: float
    leverage: int
    margin_mode: str
    liquidation_price: float
    upnl: float
    funding_fees: float
    position_id: int
    raw: dict = field(default_factory=dict, compare=False, repr=False)

    @property
    def side(self) -> int:
        return 1 if self.size > 0 else -1 if self.size < 0 else 0


def parse_positions(payload) -> list[Position]:
    rows = (payload.get("positions") if isinstance(payload, dict) else payload) or []
    out = []
    for p in rows:
        out.append(Position(symbol=pick(p, "symbol", "Symbol"), size=fnum(pick(p, "size", "Size"), 0.0),
                            entry_price=fnum(pick(p, "entry_price", "EntryPrice")),
                            leverage=int(fnum(pick(p, "leverage", "Leverage"), 0)),
                            margin_mode=str(pick(p, "margin_mode", "MarginMode", default="")),
                            liquidation_price=fnum(pick(p, "liquidation_price", "LiquidationPrice")),
                            upnl=fnum(pick(p, "upnl", "unrealized_pnl"), 0.0),
                            funding_fees=fnum(pick(p, "accumulated_funding_fees"), 0.0),
                            position_id=int(fnum(pick(p, "id", "ID"), 0)), raw=p))
    return out


@dataclass(frozen=True)
class Order:
    order_id: int
    client_order_id: str
    symbol: str
    side: str
    type: str
    status: str
    size: float
    filled: float
    price: float
    stop_price: float
    reduce_only: bool
    strategy_id: str | None
    builder_code: str | None
    builder_fee_bps: int | None
    raw: dict = field(default_factory=dict, compare=False, repr=False)

    @property
    def is_terminal(self) -> bool:
        return self.status in ("filled", "canceled", "rejected", "expired")


def parse_order(o: dict) -> Order:
    strat = pick(o, "Strategy", "strategy")
    builder = pick(o, "Builder", "builder")
    return Order(
        order_id=int(fnum(pick(o, "ID", "id", "order_id"), 0)),
        client_order_id=str(pick(o, "ClientOrderID", "client_order_id", default="")),
        symbol=str(pick(o, "Symbol", "symbol", default="")),
        side=str(pick(o, "Side", "side", default="")).lower(),
        type=str(pick(o, "Type", "type", default="")).lower(),
        status=str(pick(o, "Status", "status", default="")).lower(),
        size=fnum(pick(o, "Size", "size"), 0.0), filled=fnum(pick(o, "Filled", "filled"), 0.0),
        price=fnum(pick(o, "Price", "price")), stop_price=fnum(pick(o, "StopPrice", "stop_price")),
        reduce_only=bool(pick(o, "ReduceOnly", "reduce_only", default=False)),
        strategy_id=(pick(strat, "ID", "id") if isinstance(strat, dict) else pick(o, "strategy_id")),
        builder_code=(pick(builder, "Code", "code") if isinstance(builder, dict) else None),
        builder_fee_bps=(int(fnum(pick(builder, "FeeBps", "fee_bps"), 0)) if isinstance(builder, dict) else None),
        raw=o,
    )


@dataclass(frozen=True)
class Fill:
    trade_id: int
    order_id: int
    symbol: str
    side: str
    role: str
    price: float
    size: float
    fee: float
    realized_pnl: float
    timestamp: int
    raw: dict = field(default_factory=dict, compare=False, repr=False)


def parse_fills(payload) -> list[Fill]:
    rows = (payload.get("fills") if isinstance(payload, dict) else payload) or []  # live API sends null when empty
    return [Fill(int(fnum(r.get("trade_id"), 0)), int(fnum(r.get("order_id"), 0)), r.get("symbol", ""),
                 r.get("side", ""), r.get("role", ""), fnum(r.get("price")), fnum(r.get("size")), fnum(r.get("fee"), 0),
                 fnum(r.get("realized_pnl"), 0), int(fnum(r.get("timestamp"), 0)), r) for r in rows]


# money that enters or leaves the account without being a trade's result (GET /v2/history/transaction): the
# account's result since the agent started leaves these out, so a deposit never looks like a gain
FLOW_TYPES = {"deposit", "withdraw", "transfer"}
TX_TYPES = {1: "deposit", 2: "withdraw", 3: "fee", 4: "realized_pnl", 5: "liquidation", 6: "funding", 7: "reward_grant",
            8: "reward_reclaim", 9: "credit", 10: "transfer"}
TX_DONE = {"completed", "settled"}   # what the balance already holds (pending ones are not credited yet)


@dataclass(frozen=True)
class Transfer:
    id: int
    type: str
    amount: float        # signed: + into the account, - out of it
    status: str
    timestamp: int


def parse_transfers(payload) -> list[Transfer]:
    rows = (payload.get("transactions") if isinstance(payload, dict) else payload) or []   # null when empty
    out = []
    for r in rows:
        kind = r.get("type")
        kind = TX_TYPES.get(int(kind), str(kind)) if isinstance(kind, (int, float)) or str(kind).isdigit() else str(kind or "")
        amt = fnum(r.get("amount"), 0.0)
        if kind == "withdraw":
            amt = -abs(amt)   # always out, whichever sign the API uses
        elif kind == "deposit":
            amt = abs(amt)
        out.append(Transfer(int(fnum(r.get("id"), 0)), kind, amt, str(r.get("status") or "").lower(),
                            int(fnum(r.get("timestamp"), 0))))
    return out


@dataclass(frozen=True)
class AccountState:
    account_id: str
    wallet_balance: float
    available_balance: float
    margin_balance: float
    unrealized_pnl: float
    maintenance_margin: float
    raw: dict = field(default_factory=dict, compare=False, repr=False)


def parse_account(a: dict) -> AccountState:
    return AccountState(str(pick(a, "account_id", default="")), fnum(pick(a, "wallet_balance"), 0.0),
                        fnum(pick(a, "available_balance"), 0.0), fnum(pick(a, "margin_balance"), 0.0),
                        fnum(pick(a, "unrealized_pnl"), 0.0), fnum(pick(a, "maintenance_margin"), 0.0), a)


def parse_premium(payload, symbol: str) -> dict:
    rows = payload if isinstance(payload, list) else [payload]
    for r in rows:
        if r.get("symbol") == symbol:
            return {"mark": fnum(r.get("markPrice")), "index": fnum(r.get("indexPrice")),
                    "funding_rate": fnum(pick(r, "fundingRate", "lastFundingRate")),
                    "next_funding_time": int(fnum(r.get("nextFundingTime"), 0)), "time": int(fnum(r.get("time"), 0))}
    raise KeyError(symbol)

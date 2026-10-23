"""Risk engine: every order the agent could send passes through ``RiskEngine.evaluate`` first.

Execution is subordinate to it. A rejection always carries its reasons; an acceptance carries the size, notional,
leverage, margin and an estimated liquidation price. The builder fee is an input cost only: it can make a trade
*less* attractive (or rejected), never larger or more frequent.

The 1.5 ATR stop is a reference level, not a loss guarantee: gaps, slippage, liquidity and failures can lose more,
so sizing keeps a margin of safety (``loss_buffer``) and leverage is capped well below liquidation distance.
"""

from __future__ import annotations

import math
import os
from dataclasses import dataclass, field
from decimal import Decimal
from pathlib import Path

from ..strike.models import MarketSpec


@dataclass(frozen=True)
class RiskConfig:
    risk_per_trade: float = 0.005        # fraction of equity lost if the stop fills exactly
    loss_buffer: float = 1.25            # size so that 1.25x the stop distance (slippage/gap) stays within budget
    max_leverage: float = 5.0            # effective notional / equity per position
    max_total_leverage: float = 10.0     # across all open positions
    max_open_positions: int = 3
    max_daily_loss: float = 0.02         # realised + open loss today (fraction of start-of-day equity, as in the backtest)
    max_weekly_loss: float = 0.05
    max_spread_bps: float = 10.0
    max_impact_bps: float = 15.0         # estimated slippage of our size on the book
    max_data_age_s: float = 180.0        # signal candle must be this fresh at decision time
    max_basis_bps: float = 60.0          # |Strike mark - signal feed close|
    min_stop_bps: float = 15.0           # stops tighter than this are noise for the fee/slippage budget
    liq_safety: float = 2.0              # liquidation must be >= this many stop distances away
    max_cost_r: float = 0.35             # expected round-trip costs (fees+builder+spread) in R
    kill_switch_file: str = "KILL_SWITCH"


@dataclass(frozen=True)
class Proposal:
    symbol: str
    dir: int
    ref_price: float          # expected fill (ask for buys, bid for sells)
    stop: float
    take_profit: float | None
    signal_close: float       # signal feed close (Binance)
    signal_age_s: float


@dataclass(frozen=True)
class MarketContext:
    spec: MarketSpec
    bid: float
    ask: float
    mark: float
    impact_bps: float         # estimated for the proposed size (computed by the caller from depth)
    taker_fee: float          # e.g. 0.0005
    builder_fee_bps: float


@dataclass(frozen=True)
class AccountContext:
    equity: float
    available: float
    open_positions: int
    open_notional: float
    day_pnl: float            # realised + unrealised since 00:00 UTC
    week_pnl: float
    has_position_in_symbol: bool
    pending_orders_in_symbol: int


@dataclass
class Decision:
    accepted: bool
    reasons: list[str] = field(default_factory=list)
    qty: Decimal = Decimal(0)
    notional: float = 0.0
    leverage: float = 0.0
    margin: float = 0.0
    risk_usd: float = 0.0
    est_liq_price: float = math.nan
    expected_cost_r: float = math.nan
    stop_bps: float = math.nan

    def summary(self) -> str:
        if not self.accepted:
            return "REJECTED: " + "; ".join(self.reasons)
        return (f"ACCEPTED qty={self.qty} notional=${self.notional:,.2f} lev={self.leverage:.2f}x "
                f"risk=${self.risk_usd:,.2f} liq~{self.est_liq_price:,.4f} cost={self.expected_cost_r:.3f}R")


def est_liquidation(entry: float, dir: int, leverage: float, mmr: float) -> float:
    """Isolated-margin approximation: price where (1/lev) margin is consumed down to the maintenance rate."""
    return entry * (1 - dir * (1 / leverage - mmr)) if leverage > 0 else math.nan


class RiskEngine:
    def __init__(self, cfg: RiskConfig, root: Path = Path(".")):
        self.cfg = cfg
        self.root = root

    def kill_switch_on(self) -> bool:
        return (self.root / self.cfg.kill_switch_file).exists() or os.environ.get("SMARTFLOW_KILL") == "1"

    def evaluate(self, p: Proposal, m: MarketContext, a: AccountContext) -> Decision:
        c = self.cfg
        d = Decision(False)
        r = d.reasons
        if self.kill_switch_on():
            r.append("kill switch engaged")
        if not m.spec.tradable:
            r.append(f"market {p.symbol} not tradable (status {m.spec.status}, reduce-only {m.spec.reduce_only_mode})")
        if p.signal_age_s > c.max_data_age_s:
            r.append(f"signal data stale ({p.signal_age_s:.0f}s > {c.max_data_age_s:.0f}s)")
        if a.has_position_in_symbol:
            r.append("a position is already open in this market (Strike nets positions per market)")
        if a.pending_orders_in_symbol:
            r.append(f"{a.pending_orders_in_symbol} unreconciled order(s) in this market")
        if a.open_positions >= c.max_open_positions:
            r.append(f"max open positions reached ({a.open_positions})")
        if a.equity <= 0:
            # an empty account: the loss limits below are fractions of the equity and would all "trip" at 0, which
            # would tell the owner they lost money when they have only not deposited yet
            r.append("no equity: the account has no balance")
            return d
        if a.day_pnl <= -c.max_daily_loss * (a.equity - a.day_pnl):     # the equity at 00:00 UTC
            r.append(f"daily loss limit hit ({a.day_pnl:,.2f})")
        if a.week_pnl <= -c.max_weekly_loss * (a.equity - a.week_pnl):  # and on Monday at 00:00 UTC
            r.append(f"weekly loss limit hit ({a.week_pnl:,.2f})")
        mid = (m.bid + m.ask) / 2 if m.bid > 0 and m.ask > 0 else m.mark
        spread_bps = (m.ask - m.bid) / mid * 1e4 if m.bid > 0 and m.ask > 0 else math.inf
        if spread_bps > c.max_spread_bps:
            r.append(f"spread {spread_bps:.1f}bps > {c.max_spread_bps}")
        if m.impact_bps > c.max_impact_bps:
            r.append(f"estimated impact {m.impact_bps:.1f}bps > {c.max_impact_bps}")
        basis = abs(m.mark - p.signal_close) / p.signal_close * 1e4 if p.signal_close else math.inf
        if basis > c.max_basis_bps:
            r.append(f"Strike mark differs {basis:.0f}bps from the signal feed")
        dist = (p.ref_price - p.stop) * p.dir
        if dist <= 0:
            r.append("price already at/through the stop")
        else:
            d.stop_bps = dist / p.ref_price * 1e4
            if d.stop_bps < c.min_stop_bps:
                r.append(f"stop distance {d.stop_bps:.1f}bps below minimum {c.min_stop_bps}")
        if p.take_profit is not None and (p.take_profit - p.ref_price) * p.dir <= 0:
            r.append("take profit on the wrong side")
        if r or dist <= 0:
            return d

        risk_usd = c.risk_per_trade * a.equity
        qty_f = risk_usd / (dist * c.loss_buffer)
        qty = m.spec.round_qty(qty_f)
        notional = float(qty) * p.ref_price
        lev_cap = min(c.max_leverage, m.spec.tier_for(notional).max_leverage)
        if notional > lev_cap * a.equity:
            qty = m.spec.round_qty(lev_cap * a.equity / p.ref_price)
            notional = float(qty) * p.ref_price
            r.append(f"note: size capped by leverage {lev_cap:g}x")  # informative, not a rejection by itself
        if qty <= 0 or qty < m.spec.min_qty:
            return Decision(False, [f"size {qty} below market minimum {m.spec.min_qty}"])
        if notional < m.spec.min_notional:
            return Decision(False, [f"notional ${notional:.2f} below market minimum ${m.spec.min_notional:g}"])
        if qty > m.spec.max_market_qty:
            return Decision(False, [f"size {qty} above max market order {m.spec.max_market_qty}"])
        if a.open_notional + notional > c.max_total_leverage * a.equity:
            return Decision(False, [f"total exposure would exceed {c.max_total_leverage:g}x equity"])
        # the lowest leverage whose initial margin fits in 90 % of the available balance, up to the cap. On Strike's
        # cross margin the leverage only sets the initial margin (notional / leverage); maintenance margin and so the
        # liquidation depend on the notional, which the stop already sizes. The lowest one (1x) would leave no room
        # for a second or third position at 1-2 % risk and skip trades the strategy takes (docs/STRATEGY.md "Risk levels")
        low = max(1, math.ceil(notional / a.equity))
        leverage = next((float(x) for x in range(low, int(lev_cap) + 1) if notional / x <= a.available * 0.9), None)
        if leverage is None:
            return Decision(False, [f"margin ${notional / max(low, lev_cap):,.2f} exceeds 90% of available ${a.available:,.2f}"])
        margin = notional / leverage
        tier = m.spec.tier_for(notional)
        liq = est_liquidation(p.ref_price, p.dir, leverage, tier.mmr)
        if (p.ref_price - liq) * p.dir < c.liq_safety * dist:
            return Decision(False, [f"estimated liquidation {liq:,.4f} closer than {c.liq_safety}x the stop distance"])
        cost_r = ((m.taker_fee * 2 + 2 * m.builder_fee_bps / 1e4) * p.ref_price + spread_bps / 1e4 * mid) / dist
        if cost_r > c.max_cost_r:
            return Decision(False, [f"expected costs {cost_r:.2f}R exceed {c.max_cost_r}R (stop too tight for fees)"])
        return Decision(True, [x for x in r if x.startswith("note:")], qty, notional, leverage, margin,
                        float(qty) * dist, liq, cost_r, d.stop_bps)

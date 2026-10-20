"""Execution-realistic simulation of Smart Flow signals (one market).

Differences with the reference model (``core.reference_trades``), all configurable so each effect can be measured:

* **Entry** at the next bar's open plus slippage (a market order sent right after the signal candle closes),
  instead of exactly at the signal close.
* **Position policy**: Strike nets positions per market (``/v2/positions`` returns one signed size), so overlapping
  trades cannot coexist the way the script tracks them. ``single`` ignores signals while a position is open,
  ``reverse`` flips on an opposite signal, ``overlap`` keeps the script's independent trades (not executable on one
  account; kept as a bridge to the reference numbers). ``pyramid`` stacks up to ``max_stack`` trades in the SAME
  direction, each with its own stop and exit (executable on a netted account: one reduce-only stop per trade), and
  ignores opposite signals while any is open; ``pyramid_rev`` closes them on an opposite signal and enters it.
* **Stops** fill at the stop minus stop slippage, or at the open when the bar gaps through it.
* **Close-based exits** (trailing channel, money-flow cross, candle limit) fill at the next open plus slippage.
* **Costs** per fill on notional: taker fee + builder fee (``X-Builder-Fee-Bps``), and funding while open.

R is measured against the risk actually taken: ``|entry fill - stop|`` per unit, so 1 R is what the stop would lose.
"""

from __future__ import annotations

import bisect
import math
from dataclasses import dataclass, field

from ..core.config import Params
from ..core.exits import close_exit
from ..core.engine import BarState
from ..core.pine import ge, isna, le
from ..core.types import Candle


@dataclass(frozen=True)
class CostModel:
    taker_fee_bps: float = 5.0        # Strike tier 0 taker (0.050 %), GET /v2/fee-tiers, 2026-10-19
    builder_fee_bps: float = 0.0      # per fill, entry and exit; 0..100 (docs: max 100 bps)
    slippage_bps: float = 2.0         # market entries / close-based exits beyond the reference price
    stop_slippage_bps: float = 5.0    # stop-market fills beyond the stop
    funding: bool = True

    def label(self) -> str:
        return (f"taker {self.taker_fee_bps:g}bp + builder {self.builder_fee_bps:g}bp per fill, slip "
                f"{self.slippage_bps:g}/{self.stop_slippage_bps:g}bp, funding {'on' if self.funding else 'off'}")


REFERENCE_COSTS = CostModel(taker_fee_bps=5.0, builder_fee_bps=0.0, slippage_bps=0.0, stop_slippage_bps=0.0,
                            funding=False)


@dataclass(frozen=True)
class ExecModel:
    entry: str = "next_open"          # "close" | "next_open"
    exit_fill: str = "next_open"      # close-based exits: "close" | "next_open"
    stop_gap: bool = True
    policy: str = "single"            # "single" | "reverse" | "overlap" | "pyramid" | "pyramid_rev"
    max_stack: int = 3                # pyramid: open trades per market at most (same direction)

    def label(self) -> str:
        stack = f" x{self.max_stack}" if self.policy.startswith("pyramid") else ""
        return f"entry {self.entry}, exits {self.exit_fill}, gap-aware stops {self.stop_gap}, policy {self.policy}{stack}"


@dataclass(slots=True)
class SimTrade:
    symbol: str
    dir: int
    signal_bar: int
    signal_time: int
    ref_entry: float          # signal close (the script's entry)
    sl: float
    tp: float
    entry_bar: int = -1
    entry_time: int = 0
    entry: float = math.nan
    exit_bar: int = -1
    exit_time: int = 0
    exit: float = math.nan
    reason: str = ""
    r_gross: float = 0.0
    r_fees: float = 0.0
    r_builder: float = 0.0
    r_funding: float = 0.0    # positive = paid
    r_slip: float = 0.0       # cost of slippage vs reference prices, in R (informative; already inside r_gross)
    pending_exit: str = ""    # close-based exit decided, to fill on next open
    best: float = math.nan    # best extreme since the entry (chandelier)
    trail: float = math.nan   # the stop after the chandelier moved it (1 R stays |entry - sl|)

    @property
    def risk(self) -> float:
        return abs(self.entry - self.sl)

    @property
    def r(self) -> float:
        return self.r_gross - self.r_fees - self.r_builder - self.r_funding

    @property
    def open(self) -> bool:
        return self.exit_bar < 0


@dataclass
class SimResult:
    symbol: str
    trades: list[SimTrade] = field(default_factory=list)
    skipped: dict[str, int] = field(default_factory=dict)
    bars: int = 0
    bars_in_market: int = 0


class FundingTable:
    """Funding settlements ``(time_ms, rate)``; positive rate = longs pay."""

    def __init__(self, events: list[tuple[int, float]]):
        self.t = [e[0] for e in events]
        self.r = [e[1] for e in events]

    def between(self, t0: int, t1: int) -> list[tuple[int, float]]:
        i, j = bisect.bisect_right(self.t, t0), bisect.bisect_right(self.t, t1)
        return list(zip(self.t[i:j], self.r[i:j]))


def simulate(symbol: str, candles: list[Candle], states: list[BarState], p: Params, cost: CostModel,
             exe: ExecModel, funding: FundingTable | None = None, start_ms: int | None = None,
             end_ms: int | None = None) -> SimResult:
    """Signals are taken only when the signal bar opens inside [start_ms, end_ms); open trades run to their exit."""
    assert len(candles) == len(states)
    res = SimResult(symbol)
    open_trades: list[SimTrade] = []
    pending: list[SimTrade] = []   # signals waiting for next-open entry
    closes = [c.close for c in candles]
    times = [c.open_time for c in candles]
    slip, sslip = cost.slippage_bps / 1e4, cost.stop_slippage_bps / 1e4
    fee = cost.taker_fee_bps / 1e4
    bfee = cost.builder_fee_bps / 1e4

    def price_at(t: int) -> float:
        k = bisect.bisect_right(times, t) - 1
        return closes[max(0, k)]

    def finish(t: SimTrade, i: int, px: float, reason: str, ref_px: float) -> None:
        t.exit_bar, t.exit_time, t.exit, t.reason = i, times[i], px, reason
        risk = t.risk
        t.r_gross = (px - t.entry) * t.dir / risk
        t.r_fees = fee * (t.entry + px) / risk
        t.r_builder = bfee * (t.entry + px) / risk
        t.r_slip = (abs(t.entry - t.ref_entry) + abs(px - ref_px)) / risk  # shortfall vs the script's prices
        if cost.funding and funding is not None:
            paid = sum(rate * price_at(ft) * t.dir for ft, rate in funding.between(t.entry_time, t.exit_time))
            t.r_funding = paid / risk
        res.trades.append(t)

    def try_enter(t: SimTrade, i: int, px: float) -> bool:
        """Fill an entry at ``px``; reject if the price is already at/through the stop (no valid risk)."""
        if (t.dir == 1 and px <= t.sl) or (t.dir == -1 and px >= t.sl) or abs(px - t.sl) < 1e-12:
            res.skipped["entry beyond stop"] = res.skipped.get("entry beyond stop", 0) + 1
            return False
        t.entry_bar, t.entry_time, t.entry = i, times[i], px
        open_trades.append(t)
        return True

    for i, (c, s) in enumerate(zip(candles, states)):
        res.bars += 1
        # 1. fills at this bar's open: pending exits, then pending entries
        for t in list(open_trades):
            if t.pending_exit:
                px = c.open * (1 - slip * t.dir)
                finish(t, i, px, t.pending_exit, c.open)
                open_trades.remove(t)
        for t in pending:
            if exe.policy == "single" and any(o.open for o in open_trades):
                res.skipped["position already open"] = res.skipped.get("position already open", 0) + 1
                continue
            if exe.policy.startswith("pyramid"):
                held = [o for o in open_trades if o.open]
                if any(o.dir != t.dir for o in held) or len(held) >= exe.max_stack:
                    res.skipped["stack full or opposite"] = res.skipped.get("stack full or opposite", 0) + 1
                    continue
            try_enter(t, i, c.open * (1 + slip * t.dir))
        pending = []

        # 2. intrabar stop / target on positions already entered (entry bar included: the stop is live from the fill)
        for t in list(open_trades):
            if t.entry_bar > i:
                continue
            stop = t.sl if isna(t.trail) else t.trail
            hit_sl = le(c.low, stop) if t.dir == 1 else ge(c.high, stop)
            hit_tp = not isna(t.tp) and (ge(c.high, t.tp) if t.dir == 1 else le(c.low, t.tp))
            if t.entry_bar == i and exe.entry == "close":
                hit_sl = hit_tp = False   # reference timing: an entry at the close cannot be stopped on that bar
            if hit_sl:
                gapped = exe.stop_gap and ((t.dir == 1 and c.open < stop) or (t.dir == -1 and c.open > stop))
                base = c.open if gapped and t.entry_bar < i else stop
                label = "stop" if isna(t.trail) else "chandelier stop"
                finish(t, i, base * (1 - sslip * t.dir), label + (" (gap)" if gapped and t.entry_bar < i else ""), stop)
                open_trades.remove(t)
            elif hit_tp:
                gapped = (t.dir == 1 and c.open > t.tp) or (t.dir == -1 and c.open < t.tp)
                base = c.open if gapped and t.entry_bar < i else t.tp
                finish(t, i, base * (1 - slip * t.dir), "target", t.tp)
                open_trades.remove(t)

        # 3. close-based exits decided on this bar's close (signal-bar arithmetic as in the script)
        for t in open_trades:
            if t.pending_exit or i <= t.signal_bar:
                continue
            reason = close_exit(s, t.dir, i - t.signal_bar, p)
            if reason:
                if exe.exit_fill == "close":
                    finish(t, i, s.close * (1 - slip * t.dir), reason, s.close)
                else:
                    t.pending_exit = reason
            elif p.chand_atr > 0 and t.entry_bar <= i:
                # chandelier: the stop on the exchange rises to the best extreme since the entry - chand_atr ATR
                t.best = (max(t.entry if isna(t.best) else t.best, c.high) if t.dir == 1
                          else min(t.entry if isna(t.best) else t.best, c.low))
                lvl = t.best - t.dir * p.chand_atr * s.atr
                cur = t.sl if isna(t.trail) else t.trail
                if (t.dir == 1 and lvl > cur) or (t.dir == -1 and lvl < cur):
                    t.trail = lvl
        open_trades = [t for t in open_trades if t.open]
        if open_trades:
            res.bars_in_market += 1

        # 4. new signal
        in_window = (start_ms is None or c.open_time >= start_ms) and (end_ms is None or c.open_time < end_ms)
        if s.sig_dir != 0 and in_window and not isna(s.atr):
            risk = p.stop_atr * s.atr
            t = SimTrade(symbol, s.sig_dir, i, c.open_time, s.close, s.close - s.sig_dir * risk,
                         s.close + s.sig_dir * p.tp_r * risk if p.tp_r > 0 else math.nan)
            live = [o for o in open_trades if o.open and not o.pending_exit]
            if exe.policy == "reverse" and live and live[0].dir == -t.dir:
                for o in live:   # flip: close the opposite position with the same market order as the entry
                    o.pending_exit = "reversed"
                live = []
            if exe.policy == "pyramid_rev" and live and live[0].dir == -t.dir:
                for o in live:
                    o.pending_exit = "reversed"
                live = []
            if exe.policy.startswith("pyramid") and live and (live[0].dir != t.dir or len(live) >= exe.max_stack):
                res.skipped["stack full or opposite"] = res.skipped.get("stack full or opposite", 0) + 1
            elif exe.policy in ("single", "reverse") and live:
                res.skipped["position already open"] = res.skipped.get("position already open", 0) + 1
            elif exe.entry == "close":
                try_enter(t, i, s.close * (1 + slip * t.dir))
            else:
                pending.append(t)
    return res

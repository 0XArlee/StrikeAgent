"""Trend daily backtest with the costs a Smart Flow user pays on Strike, on the markets Strike lists.

Decision at each daily close (data <= that close), execution at the next open, held to the following open, as the
original's model_daily_return. Costs per unit of turnover: taker fee + builder fee + slippage; funding paid by longs
(received by shorts). Every series is computed once (all its steps are causal), and a self-check compares the fast
path with the model's own functions on sample days.

Variants are judged out of sample, with the rule fixed before looking: a variant replaces the validated specification
only if it beats it in 2021-2023 (selection years) and does not do worse in 2024 onwards (test years).

    python -m smartflow.trend.backtest [--root data] [--builder-bps 20] [--taker-bps 5] [--slip-bps 2]
"""

from __future__ import annotations

import argparse
import math
import time
from bisect import bisect_right
from dataclasses import dataclass, replace
from pathlib import Path
from statistics import median

from ..data.binance import kline_path, load_funding
from ..data.store import read_rows
from .model import PRESETS, TrendParams, apply_rebalance_threshold, asset_weight, select_universe, target_weights

SYMBOLS = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "XRPUSDT", "BNBUSDT", "ADAUSDT", "NEARUSDT", "ZECUSDT"]
DAY = 86_400_000
SPLIT = 19723   # 2024-01-01 (days since epoch): selection years before, test years after


@dataclass
class Result:
    days: int
    cagr: float
    sharpe: float
    max_dd: float
    turnover_year: float
    entries: int
    exposure: float
    cost_year: float
    builder_year: float
    funding_year: float
    years: dict[int, float]

    def row(self) -> str:
        return (f"CAGR {100 * self.cagr:6.1f} % · Sharpe {self.sharpe:5.2f} · maxDD {100 * self.max_dd:5.1f} % · "
                f"turnover {self.turnover_year:4.1f}x/yr · entries {self.entries:3d} · exposure {100 * self.exposure:3.0f} % · "
                f"costs {100 * self.cost_year:4.2f} %/yr (Smart Flow fee {100 * self.builder_year:4.2f}) · funding {100 * self.funding_year:+5.2f} %/yr")


@dataclass
class Data:
    days: list[int]
    hist: dict[str, list[tuple[int, float, float]]]
    opens: dict[str, dict[int, float]]
    funding: dict[str, tuple[list[int], list[float]]]


def load(root: Path) -> Data:
    hist, opens, funding = {}, {}, {}
    for sym in SYMBOLS:
        rows = read_rows(kline_path(root, sym, "D"))
        hist[sym] = [(int(r[0]) // DAY, float(r[4]), float(r[6]) if r[6] != "" else math.nan) for r in rows]
        opens[sym] = {int(r[0]) // DAY: float(r[1]) for r in rows}
        f = load_funding(root, sym)
        funding[sym] = ([t for t, _ in f], [r for _, r in f])
    days = sorted({d for rows in hist.values() for d, _, _ in rows})
    return Data(days, hist, opens, funding)


def _funding_day(fund: tuple[list[int], list[float]], day: int) -> float:
    ts, rs = fund
    a, b = bisect_right(ts, day * DAY - 1), bisect_right(ts, (day + 1) * DAY - 1)
    return sum(rs[a:b])


class Fast:
    """Per-symbol series computed once: weights, 30-day median dollar volume, index of each day."""

    def __init__(self, data: Data, p: TrendParams):
        self.p, self.data = p, data
        self.day_idx, self.w, self.med = {}, {}, {}
        for s, rows in data.hist.items():
            ds = [r[0] for r in rows]
            self.day_idx[s] = ds
            self.w[s] = asset_weight([r[1] for r in rows], p)
            q = [r[2] for r in rows]
            self.med[s] = [median([x for x in q[max(0, i - 29):i + 1] if not math.isnan(x)] or [math.nan]) for i in range(len(q))]

    def _i(self, s: str, day: int) -> int:
        return bisect_right(self.day_idx[s], day) - 1   # last row <= day

    def universe(self, day: int, current: list[str]) -> list[str]:
        p, scores = self.p, {}
        for s, ds in self.day_idx.items():
            i = self._i(s, day)
            if i + 1 < 30 or day - ds[0] < p.min_listing_days:
                continue
            if not math.isnan(self.med[s][i]):
                scores[s] = self.med[s][i]
        ok = [s for s, v in scores.items() if v >= p.liq_enter_usd]
        ranked = sorted(ok, key=lambda s: scores[s], reverse=True)
        keep = [s for s in current if s in scores and scores[s] >= p.liq_exit_usd and s in ok]
        for s in ranked:
            if len(keep) >= p.n_assets:
                break
            if s not in keep:
                keep.append(s)
        return keep[:p.n_assets]

    def targets(self, day: int, universe: list[str]) -> dict[str, float]:
        if not universe:
            return {}
        share, out = 1.0 / len(universe), {}
        for s in universe:
            i = self._i(s, day)
            w = 0.0 if i + 1 < self.p.min_history_days else self.w[s][i]
            out[s] = (w if self.p.allow_shorts else max(0.0, w)) * share
        return out


def self_check(data: Data, p: TrendParams, n: int = 8) -> bool:
    """The fast path against the model's own functions on sample days (universe and weights)."""
    f, cur_f, cur_m, ok = Fast(data, p), [], [], True
    for day in data.days[len(data.days) // 2::max(1, len(data.days) // (2 * n))][:n]:
        u_f, u_m = f.universe(day, cur_f), select_universe(data.hist, day, p, cur_m)
        cut = {s: [c for d, c, _ in data.hist[s] if d <= day] for s in u_m}
        t_f, t_m = f.targets(day, u_f), target_weights(cut, u_m, p)
        ok &= u_f == u_m and all(abs(t_f.get(s, 0) - t_m.get(s, 0)) < 1e-12 for s in set(t_f) | set(t_m))
        cur_f, cur_m = u_f, u_m
    return ok


def run(data: Data, p: TrendParams, cost_bps: float, builder_bps: float, start_day: int | None = None,
        end_day: int | None = None, fast: Fast | None = None) -> Result:
    f = fast or Fast(data, p)
    days = data.days
    w_prev: dict[str, float] = {}
    universe: list[str] = []
    eq, peak, max_dd = 1.0, 1.0, 0.0
    rets, turnover, entries, exposure, cost, builder, fund = [], 0.0, 0, 0.0, 0.0, 0.0, 0.0
    years: dict[int, float] = {}
    for k, day in enumerate(days[:-2]):
        if end_day is not None and day >= end_day:
            break
        universe = f.universe(day, universe)
        w = apply_rebalance_threshold(f.targets(day, universe), w_prev, p.rebalance_threshold)
        w = {s: v for s, v in w.items() if v}
        t1, t2 = days[k + 1], days[k + 2]
        tov = sum(abs(w.get(s, 0.0) - w_prev.get(s, 0.0)) for s in set(w) | set(w_prev))
        gross = 0.0
        for s, x in w.items():
            o1, o2 = data.opens[s].get(t1), data.opens[s].get(t2)
            if o1 and o2:
                gross += x * (o2 / o1 - 1.0)
        fu = sum(x * _funding_day(data.funding[s], t1) for s, x in w.items())
        r = gross - tov * cost_bps / 1e4 - fu
        if start_day is None or day >= start_day:
            entries += sum(1 for s in w if not w_prev.get(s))
            turnover += tov
            exposure += sum(abs(v) for v in w.values())
            cost += tov * cost_bps / 1e4
            builder += tov * builder_bps / 1e4
            fund += fu
            eq *= 1 + r
            peak = max(peak, eq)
            max_dd = max(max_dd, 1 - eq / peak)
            rets.append(r)
            y = time.gmtime(t1 * 86400).tm_year
            years[y] = (1 + years.get(y, 0.0)) * (1 + r) - 1
        w_prev = w
    # the book is flat until the first market has a year of listing and 92 days of history: count from there
    first = next((i for i, x in enumerate(rets) if x != 0.0), len(rets))
    live = rets[first:]
    n = max(1, len(live))
    yrs = n / 365
    mean = sum(live) / n if live else 0.0
    sd = math.sqrt(sum((x - mean) ** 2 for x in live) / max(1, n - 1)) if live else 0.0
    return Result(n, eq ** (1 / yrs) - 1 if yrs > 0 else 0.0, mean / sd * math.sqrt(365) if sd else 0.0,
                  max_dd, turnover / yrs, entries, exposure / max(1, len(rets)), cost / yrs, builder / yrs, fund / yrs, years)


VARIANTS = {
    "validated spec (3 assets, 20 % threshold)": {},
    "resize threshold 35 %": {"rebalance_threshold": 0.35},
    "resize threshold 50 %": {"rebalance_threshold": 0.50},
    "2 assets": {"n_assets": 2},
    "4 assets": {"n_assets": 4},
    "shorts at half size": {"allow_shorts": True},
}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="smartflow.trend.backtest")
    ap.add_argument("--root", default="data")
    ap.add_argument("--builder-bps", type=float, default=20.0)
    ap.add_argument("--taker-bps", type=float, default=5.0)
    ap.add_argument("--slip-bps", type=float, default=2.0)
    a = ap.parse_args(argv)
    data = load(Path(a.root))
    cost = a.taker_bps + a.slip_bps
    fmt = lambda d: time.strftime("%Y-%m-%d", time.gmtime(d * 86400))
    print(f"Trend daily on {len(SYMBOLS)} Strike markets, Binance daily data {fmt(data.days[0])} → {fmt(data.days[-1])}; "
          f"taker {a.taker_bps:g} + slippage {a.slip_bps:g} bps per unit of turnover, Smart Flow fee {a.builder_bps:g} bps")
    base = PRESETS["standard"]
    print("self-check fast path vs model functions:", "OK" if self_check(data, base) else "FAILED")
    print("\n== validated spec, standard risk: the cost of the Smart Flow fee")
    fb = Fast(data, base)
    for label, b in (("without Smart Flow fee", 0.0), ("with Smart Flow fee", a.builder_bps)):
        print(f"  {label:24s} {run(data, base, cost + b, b, fast=fb).row()}")
    print("\n== variants (standard risk, with the fee): selection 2021-2023 | test 2024+")
    chosen, best = "validated spec (3 assets, 20 % threshold)", None
    res = {}
    for name, ch in VARIANTS.items():
        p = replace(base, **ch)
        fp = Fast(data, p)
        sel = run(data, p, cost + a.builder_bps, a.builder_bps, end_day=SPLIT, fast=fp)
        test = run(data, p, cost + a.builder_bps, a.builder_bps, start_day=SPLIT, fast=fp)
        res[name] = (sel, test)
        print(f"  {name:42s} sel: Sharpe {sel.sharpe:5.2f} CAGR {100 * sel.cagr:5.1f} % DD {100 * sel.max_dd:4.1f} % | "
              f"test: Sharpe {test.sharpe:5.2f} CAGR {100 * test.cagr:5.1f} % DD {100 * test.max_dd:4.1f} % | turnover {sel.turnover_year:4.1f}x/yr")
    b_sel, b_test = res[chosen]
    for name, (sel, test) in res.items():
        if sel.sharpe >= b_sel.sharpe + 0.10 and test.sharpe >= b_test.sharpe and (best is None or sel.sharpe > best):
            chosen, best = name, sel.sharpe
    print(f"\nrule (fixed beforehand): a variant wins only with +0.10 Sharpe in selection AND no worse in test -> {chosen}")
    pick = replace(base, **VARIANTS[chosen])
    print("\n== chosen configuration at each risk level, with the fee, whole period")
    for name, p0 in PRESETS.items():
        p = replace(p0, **VARIANTS[chosen])
        r = run(data, p, cost + a.builder_bps, a.builder_bps)
        print(f"  {name:12s} {r.row()}")
        print(f"  {'':12s} per year: " + " · ".join(f"{y} {100 * v:+.1f} %" for y, v in sorted(r.years.items())))
    _ = pick
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

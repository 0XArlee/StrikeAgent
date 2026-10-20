"""Trend daily: the daily trend book of Edgar's BotStrike (strategies/trend_daily_model.py there), ported line by line
to pure Python so it runs in this agent without numpy/pandas. Parity with the original is checked on the same data
(smartflow.trend.parity). Specification, as validated in BotStrike (research_r2_trend_evidence.md §11.2):

* six Donchian sub-strategies (5, 10, 20, 30, 60, 90 days), long-only: a close at the n-day high enters, the stop
  starts at the channel mid and never falls, a close at or below it exits;
* each asset's weight = mean over the six of (vol scalar × position), vol scalar = target vol / realised 90-day vol,
  capped; the book holds the 3 most liquid markets (30-day median dollar volume, listed 365+ days), 1/3 each;
* resizes only when the weight drifts more than 20 % (entries and exits always execute).

Everything uses data at or before the decision bar: callers pass series already cut there.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from statistics import median

ANNUALIZATION = 365   # crypto: one daily bar per calendar day


@dataclass(frozen=True)
class TrendParams:
    lookbacks: tuple[int, ...] = (5, 10, 20, 30, 60, 90)
    target_vol: float = 0.20
    vol_window: int = 90
    leverage_cap: float = 2.0
    n_assets: int = 3
    rebalance_threshold: float = 0.20
    min_listing_days: int = 365
    liq_enter_usd: float = 2_000_000.0
    liq_exit_usd: float = 1_000_000.0
    allow_shorts: bool = False   # the original's mirror side at short_size (off in the validated spec)
    short_size: float = 0.5

    @property
    def min_history_days(self) -> int:
        return max(max(self.lookbacks), self.vol_window) + 2


# risk levels a user picks; "standard" is the validated specification
PRESETS = {
    "conservative": TrendParams(target_vol=0.10, leverage_cap=2.0),
    "standard": TrendParams(target_vol=0.20, leverage_cap=2.0),
    "assertive": TrendParams(target_vol=0.45, leverage_cap=3.0),
}

NAN = math.nan


def _rolling(values: list[float], n: int, fn) -> list[float]:
    """pandas rolling(n) with min_periods=n: NaN until n values (none NaN) are in the window."""
    out = [NAN] * len(values)
    for i in range(n - 1, len(values)):
        w = values[i - n + 1:i + 1]
        if any(math.isnan(x) for x in w):
            continue
        out[i] = fn(w)
    return out


def _std(w: list[float]) -> float:   # sample standard deviation (ddof=1), as pandas
    m = sum(w) / len(w)
    return math.sqrt(sum((x - m) ** 2 for x in w) / (len(w) - 1)) if len(w) > 1 else NAN


def sub_strategy_positions(close: list[float], n: int, allow_shorts: bool = False,
                           short_size: float = 0.5) -> tuple[list[float], list[float]]:
    """Position and trailing stop of ONE lookback (long 1, flat 0; with shorts, -short_size)."""
    rmax, rmin = _rolling(close, n, max), _rolling(close, n, min)
    pos, stop = [0.0] * len(close), [NAN] * len(close)
    state, cur = 0, NAN
    for i, c in enumerate(close):
        if math.isnan(rmax[i]):
            continue
        mid = 0.5 * (rmax[i] + rmin[i])
        if state == 0:
            if c >= rmax[i]:       # close is the n-day high: enter long, stop at the channel mid
                state, cur = 1, mid
            elif allow_shorts and c <= rmin[i]:   # n-day low: enter short
                state, cur = -1, mid
        elif state == 1:
            cur = max(cur, mid)    # trailing: never falls
            if c <= cur:
                state, cur = 0, NAN
        else:
            cur = min(cur, mid)    # mirror image: never rises
            if c >= cur:
                state, cur = 0, NAN
        pos[i] = 1.0 if state == 1 else (-abs(short_size) if state == -1 else 0.0)
        stop[i] = cur
    return pos, stop


def vol_scalar(close: list[float], p: TrendParams, periods: int = ANNUALIZATION) -> list[float]:
    ret = [NAN] + [(close[i] / close[i - 1] - 1.0) if close[i - 1] else NAN for i in range(1, len(close))]
    sigma = _rolling(ret, p.vol_window, _std)
    out = []
    for s in sigma:
        if math.isnan(s):
            out.append(NAN)
        else:
            s = s * math.sqrt(periods)
            out.append(min(p.target_vol / s, p.leverage_cap) if s > 0 else p.leverage_cap)
    return out


def asset_weight(close: list[float], p: TrendParams, periods: int = ANNUALIZATION) -> list[float]:
    """Target weight of one asset per bar: mean over lookbacks of (vol scalar × position); 0 while undefined."""
    vs = vol_scalar(close, p, periods)
    subs = [sub_strategy_positions(close, n, p.allow_shorts, p.short_size)[0] for n in p.lookbacks]
    out = []
    for i, v in enumerate(vs):
        out.append(0.0 if math.isnan(v) else v * sum(s[i] for s in subs) / len(subs))
    return out


def select_universe(history: dict[str, list[tuple[int, float, float]]], as_of_day: int, p: TrendParams,
                    current: list[str] | None = None) -> list[str]:
    """Point-in-time universe. ``history[sym]`` = [(day_index, close, quote_volume)] in day order (day_index = days since
    epoch), only rows <= as_of_day are used. Top-N by 30-day median dollar volume, as the original's crypto-only pool."""
    current = list(current or [])
    scores: dict[str, float] = {}
    for sym, rows in history.items():
        d = [r for r in rows if r[0] <= as_of_day]
        if len(d) < 30 or as_of_day - d[0][0] < p.min_listing_days:
            continue
        vols = [r[2] for r in d[-30:] if not math.isnan(r[2])]
        if vols:
            scores[sym] = median(vols)
    ok = [s for s, v in scores.items() if v >= p.liq_enter_usd]
    ranked = sorted(ok, key=lambda s: scores[s], reverse=True)
    keep = [s for s in current if s in scores and scores[s] >= p.liq_exit_usd and s in ok]
    for s in ranked:
        if len(keep) >= p.n_assets:
            break
        if s not in keep:
            keep.append(s)
    return keep[:p.n_assets]


def target_weights(closes: dict[str, list[float]], universe: list[str], p: TrendParams) -> dict[str, float]:
    """Weight per universe member at the last close given (the series are cut at the decision bar): weight × 1/N."""
    if not universe:
        return {}
    share = 1.0 / len(universe)
    out = {}
    for sym in universe:
        c = closes.get(sym) or []
        w = 0.0 if len(c) < p.min_history_days else asset_weight(c, p)[-1]
        out[sym] = (w if p.allow_shorts else max(0.0, w)) * share
    return out


def apply_rebalance_threshold(target: dict[str, float], previous: dict[str, float], threshold: float) -> dict[str, float]:
    """Entries/exits always execute; size changes only beyond ``threshold`` of the previous weight."""
    out = {}
    for sym in set(target) | set(previous):
        t, prev = float(target.get(sym, 0.0)), float(previous.get(sym, 0.0))
        if (t == 0) != (prev == 0) or (t * prev < 0):   # entry, exit or side change: always
            out[sym] = t
        elif prev != 0 and abs(t - prev) / abs(prev) > threshold:
            out[sym] = t
        else:
            out[sym] = prev
    return out


def exit_ladder(close: list[float], p: TrendParams) -> list[tuple[int, float]]:
    """(lookback, stop) of the sub-strategies holding the position, nearest stop first (it shrinks in steps)."""
    levels = []
    for n in p.lookbacks:
        pos, stop = sub_strategy_positions(close, n)
        if pos and pos[-1] > 0 and not math.isnan(stop[-1]):
            levels.append((n, stop[-1]))
    return sorted(levels, key=lambda x: -x[1])

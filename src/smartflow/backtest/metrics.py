"""Performance statistics on closed trades. Every number is in R unless the name says otherwise."""

from __future__ import annotations

import datetime as dt
import math
import random
import statistics as st
from dataclasses import asdict, dataclass

MONTH_MS = 30.4375 * 86_400_000


@dataclass
class Stats:
    n: int
    win_rate: float
    avg_r: float
    median_r: float
    avg_win: float
    avg_loss: float
    profit_factor: float
    total_r: float
    t_stat: float
    ci95_low: float
    ci95_high: float
    max_dd_r: float
    max_dd_days: float
    trades_per_month: float
    avg_hold_bars: float
    fees_r: float
    builder_r: float
    funding_r: float
    slippage_r: float
    # fixed-fractional equity (risk_per_trade of equity per trade, compounding at exit)
    risk_per_trade: float
    cagr: float
    equity_max_dd: float
    sharpe_monthly: float
    sortino_monthly: float

    def row(self) -> str:
        return (f"n={self.n:5d}  avg {self.avg_r:+.3f}R [{self.ci95_low:+.2f},{self.ci95_high:+.2f}]  med "
                f"{self.median_r:+.2f}  win {100 * self.win_rate:4.1f}%  PF {self.profit_factor:4.2f}  tot "
                f"{self.total_r:+7.1f}R  maxDD {self.max_dd_r:5.1f}R  t={self.t_stat:4.1f}")

    def to_dict(self) -> dict:
        return {k: (None if isinstance(v, float) and math.isnan(v) else v) for k, v in asdict(self).items()}


def _r(t) -> float:
    return t.r


def _exit_time(t) -> int:
    return t.exit_time


def _entry_time(t) -> int:
    return getattr(t, "entry_time", 0) or getattr(t, "open_time", 0)


def bootstrap_ci(rs: list[float], n_boot: int = 2000, seed: int = 0) -> tuple[float, float]:
    if len(rs) < 2:
        return math.nan, math.nan
    rnd = random.Random(seed)
    n = len(rs)
    means = sorted(sum(rs[rnd.randrange(n)] for _ in range(n)) / n for _ in range(n_boot))
    return means[int(0.025 * n_boot)], means[int(0.975 * n_boot) - 1]


def compute(trades: list, start_ms: int, end_ms: int, risk_per_trade: float = 0.005, boot: bool = True) -> Stats:
    trades = sorted(trades, key=_exit_time)
    rs = [_r(t) for t in trades]
    n = len(rs)
    nan = math.nan
    if n == 0:
        return Stats(0, *([nan] * 6), 0.0, *([nan] * 3), 0.0, 0.0, 0.0, nan, 0.0, 0.0, 0.0, 0.0, risk_per_trade,
                     nan, nan, nan, nan)
    wins = [r for r in rs if r > 0]
    losses = [r for r in rs if r <= 0]
    sd = st.pstdev(rs) if n > 1 else nan
    t_stat = st.mean(rs) / (sd / math.sqrt(n)) if n > 1 and sd > 0 else nan
    lo, hi = bootstrap_ci(rs) if boot else (nan, nan)
    # drawdown on the cumulative R curve (by exit time)
    peak, cum, dd, dd_start, dd_days, peak_t = 0.0, 0.0, 0.0, None, 0.0, start_ms
    for t, r in zip(trades, rs):
        cum += r
        if cum >= peak:
            peak, peak_t = cum, t.exit_time
        else:
            dd = max(dd, peak - cum)
            dd_days = max(dd_days, (t.exit_time - peak_t) / 86_400_000)
    # fixed-fractional equity, monthly returns
    eq, eq_peak, eq_dd = 1.0, 1.0, 0.0
    monthly: dict[str, float] = {}
    for t, r in zip(trades, rs):
        before = eq
        eq *= max(0.0, 1 + risk_per_trade * r)
        key = dt.datetime.fromtimestamp(t.exit_time / 1000, dt.timezone.utc).strftime("%Y-%m")
        monthly[key] = (1 + monthly.get(key, 0.0)) * (eq / before) - 1
        eq_peak = max(eq_peak, eq)
        eq_dd = max(eq_dd, 1 - eq / eq_peak)
    years = (end_ms - start_ms) / (365.25 * 86_400_000)
    cagr = eq ** (1 / years) - 1 if years > 0 and eq > 0 else nan
    # fill months with no exits as 0 returns
    months = []
    d = dt.datetime.fromtimestamp(start_ms / 1000, dt.timezone.utc).replace(day=1)
    end = dt.datetime.fromtimestamp(end_ms / 1000, dt.timezone.utc)
    while d < end:
        months.append(monthly.get(d.strftime("%Y-%m"), 0.0))
        d = (d.replace(day=28) + dt.timedelta(days=4)).replace(day=1)
    sharpe = sortino = nan
    if len(months) > 2:
        m, s = st.mean(months), st.pstdev(months)
        sharpe = m / s * math.sqrt(12) if s > 0 else nan
        downside = math.sqrt(sum(min(0.0, x) ** 2 for x in months) / len(months))
        sortino = m / downside * math.sqrt(12) if downside > 0 else nan
    hold = [t.exit_bar - (t.entry_bar if getattr(t, "entry_bar", -1) >= 0 else t.bar) for t in trades]

    def avg_attr(name: str) -> float:
        vals = [getattr(t, name) for t in trades if hasattr(t, name)]
        return st.mean(vals) if vals else nan

    return Stats(
        n=n, win_rate=len(wins) / n, avg_r=st.mean(rs), median_r=st.median(rs),
        avg_win=st.mean(wins) if wins else nan, avg_loss=st.mean(losses) if losses else nan,
        profit_factor=sum(wins) / -sum(losses) if losses and sum(losses) < 0 else nan, total_r=sum(rs),
        t_stat=t_stat, ci95_low=lo, ci95_high=hi, max_dd_r=dd, max_dd_days=dd_days,
        trades_per_month=n / ((end_ms - start_ms) / MONTH_MS), avg_hold_bars=st.mean(hold),
        fees_r=avg_attr("r_fees"), builder_r=avg_attr("r_builder"), funding_r=avg_attr("r_funding"),
        slippage_r=avg_attr("r_slip"), risk_per_trade=risk_per_trade, cagr=cagr, equity_max_dd=eq_dd,
        sharpe_monthly=sharpe, sortino_monthly=sortino,
    )

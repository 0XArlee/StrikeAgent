"""A user's account as the live agent runs it, over the backtest's trades (``backtest.sim``).

``metrics.compute`` compounds ``risk_per_trade x R`` at each exit: the strategy's own measure. The agent differs in
three ways that change the money (never the trades' R):

- size: the stop costs ``risk / loss_buffer`` when it fills cleanly (``agent/risk.py``: a 25 % slippage margin), on the
  equity at the entry;
- the daily and weekly loss limits: an entry is skipped when the equity marked to market (closed results plus open
  trades at the latest close) fell ``max_daily_loss`` / ``max_weekly_loss`` from its first value of the UTC day / ISO
  week (``runner._loss_windows``);
- what the owner sees is the equity with the open trades in it: its drawdown is measured that way;
- optionally (``margin``) Strike's margin: each position holds notional / leverage of the available balance (cross
  margin: available = equity - initial margins), and an entry whose margin is above 90 % of it is skipped
  (agent/risk.py). ``"min"``: the lowest leverage the notional allows; ``"fit"``: the lowest that makes the margin fit,
  up to ``max_leverage``. With ``balance`` (the starting $), entries below Strike's minimum order are skipped too.

Used for the figures the page shows (``web/scripts/gen_strategy.py``) and for studying risk presets and limits.
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass, field
from pathlib import Path

from ..agent.risk import RiskConfig

DAY_MS = 86_400_000


@dataclass
class AccountRun:
    cagr: float
    max_dd: float                      # peak-to-trough of the marked-to-market equity
    final: float                       # equity at the end (1 = start)
    taken: int
    skipped: list[float] = field(default_factory=list)            # R of the entries the loss limits skipped
    no_margin: list[float] = field(default_factory=list)          # R of the entries with no room for their margin
    too_small: list[float] = field(default_factory=list)          # R of the entries below Strike's minimum order
    monthly: list[tuple[str, float]] = field(default_factory=list)  # (YYYY-MM, marked-to-market equity at its end)


def bar_closes(root: Path, symbols, tf: str) -> dict[str, dict[int, float]]:
    """{symbol: {close time (ms): close}} from the downloaded klines (the closes the agent marks open trades at)."""
    from ..core.timeframes import tf_ms
    from ..data.binance import kline_path
    from ..data.store import load_candles
    step = tf_ms(tf)
    out = {}
    for s in symbols:
        out[s] = {c.open_time + step: c.close for c in load_candles(kline_path(root, s, tf), f"binance-spot:{s}")}
    return out


def _week(ms: int) -> tuple[int, int]:
    return dt.datetime.fromtimestamp(ms / 1000, dt.timezone.utc).isocalendar()[:2]


def leverage_for(notional: float, equity: float, available: float, mode: str, cap: float) -> int | None:
    """The leverage of a new position (agent/risk.py): ``min`` the lowest the notional allows; ``fit`` the lowest that
    also keeps its initial margin within 90 % of the available balance, up to ``cap``. None: it does not fit."""
    import math
    low = max(1, math.ceil(notional / equity))
    if mode == "fit":
        for lev in range(low, int(cap) + 1):
            if notional / lev <= 0.9 * available:
                return lev
        return None
    return low if notional / low <= 0.9 * available else None


def agent_account(trades: list, closes: dict[str, dict[int, float]], risk: float, window: tuple[int, int],
                  limits: bool = True, cfg: RiskConfig | None = None, margin: str | None = None,
                  balance: float | None = None, min_notional: float = 10.0) -> AccountRun:
    """The account of an agent at ``risk`` per trade (the preset the owner picks) over these trades."""
    cfg = cfg or RiskConfig()
    clean = risk / cfg.loss_buffer
    times = sorted({T for c in closes.values() for T in c if window[0] <= T <= window[1]}
                   | {t.entry_time for t in trades} | {t.exit_time for t in trades if t.exit_time})
    entries: dict[int, list] = {}
    for t in sorted(trades, key=lambda t: t.entry_time):
        entries.setdefault(t.entry_time, []).append(t)
    eq, peak, max_dd = 1.0, 1.0, 0.0
    open_: dict[int, tuple] = {}          # id -> (trade, money per R, initial margin, notional)
    last: dict[str, float] = {}
    day0: dict[int, float] = {}
    week0: dict[tuple, float] = {}
    run = AccountRun(0.0, 0.0, 1.0, 0)
    month: dict[str, float] = {}

    def close_due(T: int, strict: bool) -> None:
        nonlocal eq
        for k in [k for k, (t, *_) in open_.items() if (t.exit_time < T if strict else t.exit_time <= T)]:
            t, per_r, *_ = open_.pop(k)
            eq += per_r * t.r

    def marked() -> float:
        return eq + sum(per_r * (last.get(t.symbol, t.entry) - t.entry) * t.dir / t.risk for t, per_r, *_ in open_.values())

    for T in times:
        for s, c in closes.items():
            if T in c:
                last[s] = c[T]
        close_due(T, strict=True)      # a stop or an exit before this moment
        mtm = marked()
        d, w = T // DAY_MS, _week(T)
        day0.setdefault(d, mtm)
        week0.setdefault(w, mtm)
        for t in entries.get(T, []):
            if limits and (mtm - day0[d] <= -cfg.max_daily_loss * day0[d] or mtm - week0[w] <= -cfg.max_weekly_loss * week0[w]):
                run.skipped.append(t.r)
                continue
            per_r = clean * eq
            notional = per_r / (t.risk / t.entry)                 # the stop distance as a share of the price
            lev_cap = cfg.max_leverage
            if notional > lev_cap * mtm:                            # size capped by leverage (agent/risk.py)
                per_r *= lev_cap * mtm / notional
                notional = lev_cap * mtm
            if balance is not None and notional * balance < min_notional:
                run.too_small.append(t.r)
                continue
            im = 0.0
            if margin:
                used = sum(x[2] for x in open_.values())
                if sum(x[3] for x in open_.values()) + notional > cfg.max_total_leverage * mtm:
                    run.no_margin.append(t.r)
                    continue
                lev = leverage_for(notional, mtm, mtm - used, margin, lev_cap)
                if lev is None:
                    run.no_margin.append(t.r)
                    continue
                im = notional / lev
            open_[id(t)] = (t, per_r, im, notional)
            run.taken += 1
        close_due(T, strict=False)     # a stop can fill in the candle the trade entered
        mtm = marked()
        peak = max(peak, mtm)
        max_dd = max(max_dd, 1 - mtm / peak)
        month[dt.datetime.fromtimestamp(T / 1000, dt.timezone.utc).strftime("%Y-%m")] = mtm
    for t, per_r, *_ in open_.values():     # still open at the end of the window: at its result
        eq += per_r * t.r
    years = (window[1] - window[0]) / (365.25 * DAY_MS)
    run.final, run.max_dd = eq, max_dd
    run.cagr = eq ** (1 / years) - 1 if eq > 0 else -1.0
    run.monthly = sorted(month.items())
    return run

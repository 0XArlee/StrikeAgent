"""Each strategy's backtest figures, for the site's catalog and for the health check (``config/figures/<id>.json``).

From the registry entry (config/strategies.json: parameters, timeframe, how positions stack, core markets): the
realistic backtest 2022-01 -> 2026-10 on Binance prices with Strike's taker fee, slippage, funding and the builder fee
on every fill. The account figures (yearly growth, drawdown, curve) are the account as the live agent runs it at the
default risk preset (backtest/account.py: its slippage margin, its loss limits, Strike's margin, drawdown with the
open trades in it).

    smartflow figures --builder-bps 20                 # every strategy of the registry
    smartflow figures --builder-bps 20 --strategy pyramid
"""

from __future__ import annotations

import datetime as dt
import json
from dataclasses import replace
from pathlib import Path

from .. import ENGINE_VERSION, strategies
from ..agent.risk import RiskConfig
from .account import agent_account, bar_closes
from .sim import CostModel, ExecModel
from .study import WINDOWS, evaluate


def strategy_figures(s: strategies.Strategy, builder_bps: int, root: Path = Path("data")) -> dict:
    from ..live.fleet import DEFAULT_RISK, RISK
    window = WINDOWS["full"]
    symbols = tuple(m.replace("-USD", "USDT") for m in s.markets_core)
    st, _, trades = evaluate(root, symbols, s.timeframe, s.params, replace(CostModel(), builder_fee_bps=builder_bps),
                             ExecModel(policy=s.policy, max_stack=max(1, s.max_stack)), window)
    risk = min(RISK[DEFAULT_RISK], RISK[s.max_risk])   # the preset new agents of this strategy start with
    acct = agent_account(trades, bar_closes(root, symbols, s.timeframe), risk, window, margin="fit")
    years = (window[1] - window[0]) / (365.25 * 86400e3)
    day = lambda ms: dt.datetime.fromtimestamp(ms / 1000, dt.timezone.utc).date().isoformat()
    return {
        "strategy": s.id, "engine": ENGINE_VERSION, "generated": dt.date.today().isoformat(),
        "timeframe": s.timeframe, "markets": list(s.markets_core), "params": s.params.fingerprint(),
        "period": [day(window[0]), day(window[1])], "builder_fee_bps": builder_bps, "taker_fee_bps": 5,
        "risk_per_trade_pct": round(100 * risk, 2), "clean_stop_pct": round(100 * risk / RiskConfig().loss_buffer, 2),
        "dd_includes_open": True,
        "trades": st.n, "trades_per_year": round(st.n / years), "avg_r": round(st.avg_r, 2),
        "ci95": [round(st.ci95_low, 2), round(st.ci95_high, 2)], "win_rate": round(st.win_rate, 3),
        "avg_win_r": round(st.avg_win, 2), "profit_factor": round(st.profit_factor, 2), "max_dd_r": round(st.max_dd_r, 1),
        "cagr_pct": round(100 * acct.cagr, 1), "equity_max_dd_pct": round(100 * acct.max_dd, 1),
        "sharpe": round(st.sharpe_monthly, 2), "equity_curve": [[m, round(v, 4)] for m, v in acct.monthly],
    }


def write(sid: str | None, builder_bps: int, root: Path = Path("data"), log=print) -> list[Path]:
    out = []
    for s in strategies.all_strategies():
        if sid and s.id != sid:
            continue
        if not s.runnable:
            log(f"{s.id}: not live or not runnable, no figures")
            continue
        f = strategy_figures(s, builder_bps, root)
        p = strategies.FIGURES / f"{s.id}.json"
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(f, indent=1) + "\n", encoding="utf-8", newline="\n")
        log(f"{s.id}: {f['trades']} trades, {f['avg_r']:+.2f} R, {f['cagr_pct']} % a year, drawdown {f['equity_max_dd_pct']} % -> {p}")
        out.append(p)
    if sid and not out:
        raise SystemExit(f"no runnable strategy {sid!r} in the registry")
    return out

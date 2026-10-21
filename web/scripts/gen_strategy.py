"""Strategy figures for the landing (web/src/data/strategy.json) from the realistic backtest: 4h, BTC+ETH+SOL,
the official configuration (core.config.OFFICIAL: script + wide-range filter + 4 ATR chandelier), Strike taker fee, slippage, funding and the Smart Flow builder fee on every fill.
The account figures (yearly growth, drawdown, curve) are the account as the live agent runs it at the default risk
(backtest/account.py: its slippage margin, its loss limits, drawdown with the open trades in it).

    .venv/Scripts/python web/scripts/gen_strategy.py --builder-bps 20                     # Smart Flow -> strategy.json
    .venv/Scripts/python web/scripts/gen_strategy.py --builder-bps 20 --policy pyramid    # -> strategy-pyramid.json
"""

import argparse
import datetime as dt
import json
import sys
from dataclasses import replace
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))
from smartflow import ENGINE_VERSION  # noqa: E402
from smartflow.backtest.sim import CostModel, ExecModel  # noqa: E402
from smartflow.backtest.study import CORE, WINDOWS, evaluate  # noqa: E402
from smartflow.agent.risk import RiskConfig  # noqa: E402
from smartflow.backtest.account import agent_account, bar_closes  # noqa: E402
from smartflow.core.config import OFFICIAL  # noqa: E402
from smartflow.live.fleet import DEFAULT_RISK, RISK  # noqa: E402

ap = argparse.ArgumentParser()
ap.add_argument("--builder-bps", type=int, required=True)
ap.add_argument("--policy", default="single", choices=["single", "pyramid"])
a = ap.parse_args()

W = WINDOWS["full"]
s, per, trades = evaluate(ROOT / "data", CORE, "240", OFFICIAL, replace(CostModel(), builder_fee_bps=a.builder_bps),
                         ExecModel(policy=a.policy, max_stack=3), W)
risk = RISK[DEFAULT_RISK]   # the preset new agents start with
acct = agent_account(trades, bar_closes(ROOT / "data", CORE, "240"), risk, W, margin="fit")   # Strike margin, as risk.py
curve = [[m, round(v, 4)] for m, v in acct.monthly]
years = (W[1] - W[0]) / (365.25 * 86400e3)
out = {
    "engine": ENGINE_VERSION, "generated": dt.date.today().isoformat(), "strategy": "pyramid" if a.policy == "pyramid" else "smartflow",
    "timeframe": "4h", "markets": ["BTC-USD", "ETH-USD", "SOL-USD"], "params": "official",
    "period": ["2022-01-01", "2026-10-18"], "builder_fee_bps": a.builder_bps, "taker_fee_bps": 5, "risk_per_trade_pct": round(100 * risk, 2),
    "clean_stop_pct": round(100 * risk / RiskConfig().loss_buffer, 2), "dd_includes_open": True,
    "trades": s.n, "trades_per_year": round(s.n / years), "avg_r": round(s.avg_r, 2), "ci95": [round(s.ci95_low, 2), round(s.ci95_high, 2)],
    "win_rate": round(s.win_rate, 3), "avg_win_r": round(s.avg_win, 2), "profit_factor": round(s.profit_factor, 2),
    "max_dd_r": round(s.max_dd_r, 1), "cagr_pct": round(100 * acct.cagr, 1), "equity_max_dd_pct": round(100 * acct.max_dd, 1),
    "sharpe": round(s.sharpe_monthly, 2), "equity_curve": curve,
}
(ROOT / "web" / "src" / "data" / ("strategy-pyramid.json" if a.policy == "pyramid" else "strategy.json")).write_text(json.dumps(out, indent=1), encoding="utf-8")
print({k: v for k, v in out.items() if k != "equity_curve"}, len(curve), "months")

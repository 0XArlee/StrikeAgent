"""Volume study (2026-10-20): more trades with a real edge. Position policies x market sets x windows, with the costs
a user pays (taker 5 + builder 20 bps per fill, slippage, funding), at 0.5 % risk per trade. For each: the user's
edge (R/trade, 95 % CI), CAGR and drawdown, and the builder's income as % of the user's capital per year
(= trades per year x builder cost in R x risk per trade).

    python -m smartflow.backtest.volume_study [--root data]
"""

from __future__ import annotations

import argparse
from pathlib import Path

from ..core.config import Params
from .sim import CostModel, ExecModel
from .study import CORE, OOS_ASSETS, WINDOWS, evaluate

POLICIES = [("single", 1), ("pyramid", 2), ("pyramid", 3), ("pyramid_rev", 3)]
SETS = {"core BTC/ETH/SOL": list(CORE), "all 8": list(CORE) + list(OOS_ASSETS)}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="smartflow.backtest.volume_study")
    ap.add_argument("--root", default="data")
    ap.add_argument("--tf", default="240")
    ap.add_argument("--risk", type=float, default=0.005)
    a = ap.parse_args(argv)
    cost = CostModel(builder_fee_bps=20.0)
    for set_name, syms in SETS.items():
        print(f"\n### {set_name} · tf {a.tf} · risk {100 * a.risk:.2f} % per trade")
        for pol, k in POLICIES:
            label = pol if pol == "single" else f"{pol} x{k}"
            cells = []
            for w in ("dev", "val", "test", "full"):
                s, _, _ = evaluate(Path(a.root), syms, a.tf, Params(), cost, ExecModel(policy=pol, max_stack=k), WINDOWS[w], risk_per_trade=a.risk)
                years = (WINDOWS[w][1] - WINDOWS[w][0]) / (365.25 * 86_400_000)
                builder_yr = s.n / years * s.builder_r * a.risk if s.n else 0.0
                ci = f"[{s.ci95_low:+.2f},{s.ci95_high:+.2f}]"
                cells.append(f"{w}: n {s.n:4d} {s.avg_r:+.2f}R{ci} CAGR {100 * s.cagr:+5.1f}% DD {100 * s.equity_max_dd:4.1f}% builder {100 * builder_yr:4.1f}%/yr")
            print(f"  {label:15s} " + " | ".join(cells))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

"""Parity of the port with BotStrike's original Trend daily model, on the same daily data (run on the agents' host):

    PYTHONDONTWRITEBYTECODE=1 /opt/botstrike/app/.venv/bin/python -m smartflow.trend.parity /opt/botstrike/app/strategies/trend_daily_model.py

The original file is loaded on its own (no BotStrike package import, nothing written there). Needs pandas: BotStrike's venv.
"""

from __future__ import annotations

import importlib.util
import math
import sys
from pathlib import Path

from ..data.binance import kline_path
from ..data.store import read_rows
from . import model as port

SYMBOLS = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "XRPUSDT", "BNBUSDT", "ADAUSDT", "NEARUSDT", "ZECUSDT"]


def main(argv: list[str]) -> int:
    import pandas as pd
    spec = importlib.util.spec_from_file_location("bs_trend_model", argv[1])
    bs = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = bs   # dataclasses look the module up while the file runs
    spec.loader.exec_module(bs)
    root = Path(argv[2]) if len(argv) > 2 else Path("data")
    frames, hist, closes = {}, {}, {}
    for sym in SYMBOLS:
        rows = read_rows(kline_path(root, sym, "D"))
        t = [int(r[0]) for r in rows]
        c = [float(r[4]) for r in rows]
        qv = [float(r[6]) if r[6] != "" else math.nan for r in rows]
        frames[sym] = pd.DataFrame({"close": c, "quote_volume": qv}, index=pd.to_datetime(t, unit="ms"))
        hist[sym] = [(x // 86_400_000, cc, q) for x, cc, q in zip(t, c, qv)]
        closes[sym] = c
    worst, checked = 0.0, 0
    from dataclasses import replace
    pairs = {k: (v, bs.TrendParams(target_vol=v.target_vol, leverage_cap=v.leverage_cap)) for k, v in port.PRESETS.items()}
    pairs["with shorts"] = (replace(port.PRESETS["standard"], allow_shorts=True), bs.TrendParams(allow_shorts=True))
    for name, (pp, bp) in pairs.items():
        for sym in SYMBOLS:
            mine = port.asset_weight(closes[sym], pp)
            theirs = bs.asset_weight(frames[sym]["close"], bp).tolist()
            d = max(abs(a - b) for a, b in zip(mine, theirs))
            worst, checked = max(worst, d), checked + len(mine)
        print(f"asset weights, {name:12s}: {len(SYMBOLS)} markets, largest difference {worst:.2e}")
    # universe and final weights on a weekly grid over the last two years
    days = sorted({d for rows in hist.values() for d, _, _ in rows})[-730::7]
    same_u = same_w = 0
    cur_mine, cur_bs = [], []
    p, bp = port.PRESETS["standard"], bs.TrendParams()
    for day in days:
        u1 = port.select_universe(hist, day, p, cur_mine)
        u2 = bs.select_universe(frames, pd.Timestamp(day * 86_400_000, unit="ms"), bp, cur_bs)
        same_u += u1 == u2
        cur_mine, cur_bs = u1, u2
        cut = {s: [c for (d, c, _) in hist[s] if d <= day] for s in u1}
        w1 = port.target_weights(cut, u1, p)
        w2 = bs.target_weights(frames, u2, pd.Timestamp(day * 86_400_000, unit="ms"), bp)
        same_w += all(abs(w1.get(s, 0) - w2.get(s, 0)) < 1e-9 for s in set(w1) | set(w2))
    print(f"universe: {same_u}/{len(days)} weeks identical · final weights: {same_w}/{len(days)} identical")
    ok = worst < 1e-9 and same_u == len(days) and same_w == len(days)
    print("PARITY OK" if ok else "PARITY FAILED")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))

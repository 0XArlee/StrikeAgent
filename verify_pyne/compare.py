"""Compare smartflow/core against PyneCore running the independent Pyne re-translation of the indicator.

    python verify_pyne/compare.py <pyne_output.csv> <chart_1h.csv> <htf_4h.csv> [--htf-mode closed|previous]

``closed``   = PyneCore ``lookahead_off`` + ``structure()`` (most recently closed HTF bar, incl. the one closing with
               the chart bar); ``previous`` = the script's ``structure()[1]`` + ``lookahead_on``.
Exit code 0 only if every compared plot matches on every bar after ``--skip`` bars.
"""

from __future__ import annotations

import bisect
import csv
import datetime as dt
import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from smartflow.core.config import Params  # noqa: E402
from smartflow.core.engine import SignalEngine  # noqa: E402
from smartflow.core.htf import HtfStructure  # noqa: E402
from smartflow.core.timeframes import bar_close_time, floor_time  # noqa: E402
from smartflow.core.types import Candle  # noqa: E402

COLS = {"Signal": ("sig_dir", 0), "HTF trend": ("htf_trend", 0), "EMA trend": ("ema_trend", 0),
        "Relative volume": ("rel_vol", 1e-9), "Money flow": ("flow", 1e-7), "Fast EMA": ("ema_f", 1e-9),
        "Slow EMA": ("ema_s", 1e-9)}


def read_candles(p: Path) -> list[Candle]:
    with p.open() as f:
        r = csv.DictReader(f)
        return [Candle(int(float(x["timestamp"])) * 1000, float(x["open"]), float(x["high"]), float(x["low"]),
                       float(x["close"]), float(x["volume"])) for x in r]


def num(s: str) -> float:
    return math.nan if s in ("", "NaN", "nan") else float(s)


def main(argv: list[str]) -> int:
    out_csv, chart_csv, htf_csv = map(Path, argv[1:4])
    mode = argv[argv.index("--htf-mode") + 1] if "--htf-mode" in argv else "closed"
    global CHART, HTF
    CHART = argv[argv.index("--tf") + 1] if "--tf" in argv else "60"
    HTF = argv[argv.index("--htf") + 1] if "--htf" in argv else "240"
    skip = int(argv[argv.index("--skip") + 1]) if "--skip" in argv else 0
    chart, htf = read_candles(chart_csv), read_candles(htf_csv)
    s = HtfStructure(5)
    h_open = [b.open_time for b in htf]
    trends = [s.update(b) for b in htf]
    eng = SignalEngine(Params())  # chart TF only matters for the HTF alignment above
    with out_csv.open() as f:
        pyne = list(csv.DictReader(f))
    assert len(pyne) == len(chart), (len(pyne), len(chart))
    bad = {k: 0 for k in COLS}
    first_bad = {}
    signals = [0, 0]
    for i, (c, row) in enumerate(zip(chart, pyne)):
        t_row = int(dt.datetime.fromisoformat(row["time"]).timestamp() * 1000)
        assert t_row == c.open_time, (i, t_row, c.open_time)
        k = bisect.bisect_right(h_open, floor_time(c.open_time, HTF)) - 1
        if mode == "closed" and k >= 0 and bar_close_time(h_open[k], HTF) == bar_close_time(c.open_time, CHART):
            idx = k
        else:
            idx = k - 1
        trend = trends[idx] if idx >= 0 else None
        st = eng.update(c, trend)
        if i < skip:
            continue
        for col, (attr, tol) in COLS.items():
            a = num(row[col])
            b = getattr(st, attr)
            b = math.nan if b is None else float(b)
            same = (math.isnan(a) and math.isnan(b)) or (not math.isnan(a) and not math.isnan(b) and
                                                         abs(a - b) <= tol * max(1.0, abs(a)))
            if not same:
                bad[col] += 1
                first_bad.setdefault(col, (i, row["time"], a, b))
        signals[0] += 1 if num(row["Signal"]) not in (0.0,) else 0
        signals[1] += 1 if st.sig_dir else 0
    n = len(chart) - skip
    print(f"bars compared: {n} (skip {skip}), HTF mode '{mode}'; signals PyneCore={signals[0]} engine={signals[1]}")
    for col in COLS:
        extra = f"  first: {first_bad[col]}" if col in first_bad else ""
        print(f"  {col:16} mismatches {bad[col]}{extra}")
    ok = not any(bad.values())
    print("RESULT:", "IDENTICAL" if ok else "DIFFERENCES")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))

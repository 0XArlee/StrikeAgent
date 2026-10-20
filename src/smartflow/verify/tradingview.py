"""Bar-by-bar comparison of the engine against a TradingView "Export chart data" CSV of the original indicator.

How to produce the CSV (TradingView, chart BINANCE:BTCUSDT 1h, indicator Smart Flow Signals with default inputs):
chart menu (top-left ⋯ / camera icon) → "Export chart data…" → "Time format: UNIX timestamp" → Export.
The CSV carries the chart's OHLCV plus every plot of the script; the comparable ones are the data-window plots
``Signal``, ``HTF trend``, ``Relative volume``, ``EMA trend`` and the pane plots ``Money flow``, ``Fast EMA``,
``Slow EMA``.

The engine is fed the CSV's own OHLCV (so the comparison is not polluted by data-source differences) and HTF bars
from our Binance store (TradingView's ``request.security`` uses the exchange's native HTF bars, which we verified to
equal the aggregation of the 1 h bars). The first ``warmup`` bars are skipped: TradingView starts the script at the
first loaded bar, so EMA/ATR seeds differ until they converge.
"""

from __future__ import annotations

import csv
import math
from dataclasses import dataclass, field
from pathlib import Path

from ..core.config import Params
from ..core.runner import run_history
from ..core.types import Candle

PLOTS = {  # our BarState attribute -> (TradingView column title, kind, tolerance)
    "sig_dir": ("Signal", "int", 0),
    "htf_trend": ("HTF trend", "int", 0),
    "ema_trend": ("EMA trend", "int", 0),
    "rel_vol": ("Relative volume", "rel", 1e-6),
    "flow": ("Money flow", "abs", 1e-6),
    "ema_f": ("Fast EMA", "rel", 1e-9),
    "ema_s": ("Slow EMA", "rel", 1e-9),
}


@dataclass
class Comparison:
    bars_compared: int = 0
    mismatches: dict[str, int] = field(default_factory=dict)
    examples: dict[str, list[str]] = field(default_factory=dict)
    signals_tv: int = 0
    signals_ours: int = 0
    missing_columns: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return self.bars_compared > 0 and not any(self.mismatches.values())

    def report(self) -> str:
        lines = [f"bars compared: {self.bars_compared}   signals TV={self.signals_tv} ours={self.signals_ours}"]
        for k, (title, _, _) in PLOTS.items():
            if title in self.missing_columns:
                lines.append(f"  {title:16} (not in export)")
                continue
            n = self.mismatches.get(k, 0)
            lines.append(f"  {title:16} mismatches: {n}" + ("" if not n else "  e.g. " + "; ".join(self.examples[k][:3])))
        lines.append("RESULT: " + ("IDENTICAL" if self.ok else "DIFFERENCES FOUND"))
        return "\n".join(lines)


def read_tv_csv(path: Path) -> tuple[list[dict], list[str]]:
    with path.open(newline="", encoding="utf-8-sig") as f:
        r = csv.DictReader(f)
        return list(r), r.fieldnames or []


def _num(x: str | None) -> float:
    if x is None or x.strip() == "" or x.strip().lower() in ("nan", "na"):
        return math.nan
    return float(x)


def _time_ms(x: str) -> int:
    v = float(x)
    return int(v * 1000) if v < 1e11 else int(v)


def compare(tv_csv: Path, htf_candles: list[Candle], params: Params, chart_tf: str, warmup: int = 1500,
            source: str = "tradingview-export") -> Comparison:
    rows, cols = read_tv_csv(tv_csv)
    lower = {c.lower(): c for c in cols}

    def col(title: str) -> str | None:
        return lower.get(title.lower())

    candles = [Candle(_time_ms(r[col("time")]), _num(r[col("open")]), _num(r[col("high")]), _num(r[col("low")]),
                      _num(r[col("close")]), _num(r.get(col("volume") or "Volume")), source) for r in rows]
    res = run_history(candles, htf_candles, params, chart_tf)
    cmp = Comparison(missing_columns=[t for t, _, _ in PLOTS.values() if col(t) is None])
    for i, (row, st) in enumerate(zip(rows, res.states)):
        if i < warmup:
            continue
        cmp.bars_compared += 1
        for attr, (title, kind, tol) in PLOTS.items():
            c = col(title)
            if c is None:
                continue
            tv = _num(row[c])
            ours = getattr(st, attr)
            ours = math.nan if ours is None else float(ours)
            if math.isnan(tv) and math.isnan(ours):
                continue
            if kind == "int":
                bad = math.isnan(tv) != math.isnan(ours) or int(tv) != int(ours)
            elif kind == "rel":
                bad = math.isnan(tv) or math.isnan(ours) or abs(tv - ours) > tol * max(1.0, abs(tv))
            else:
                bad = math.isnan(tv) or math.isnan(ours) or abs(tv - ours) > tol * max(1.0, abs(tv))
            if bad:
                cmp.mismatches[attr] = cmp.mismatches.get(attr, 0) + 1
                cmp.examples.setdefault(attr, []).append(f"t={st.open_time} tv={tv} ours={ours}")
        if col("Signal"):
            cmp.signals_tv += 1 if _num(row[col("Signal")]) not in (0.0,) and not math.isnan(_num(row[col("Signal")])) else 0
        cmp.signals_ours += 1 if st.sig_dir != 0 else 0
    return cmp

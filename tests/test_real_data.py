"""Checks on downloaded Binance data (skipped when the data is not present)."""

import csv
import math

from test_engine import same_state

from smartflow.core.config import Params
from smartflow.core.runner import run_history
from smartflow.data.binance import kline_path
from smartflow.data.store import load_candles, validate
from smartflow.verify.tradingview import compare


def _load(root, sym="BTCUSDT", n=6000):
    c = load_candles(kline_path(root, sym, "60"), sym)[-n:]
    h = [x for x in load_candles(kline_path(root, sym, "240"), sym) if x.open_time < c[-1].open_time + 1]
    return c, h


def test_data_quality(need_data):
    c = load_candles(kline_path(need_data, "BTCUSDT", "240"), "b")
    rep = validate(c, "240")
    assert rep.ok and rep.missing_bars == 0


def test_no_lookahead_on_real_data(need_data):
    c, h = _load(need_data)
    full = run_history(c, h, Params(), "60").states
    cut = 4500
    t_cut = c[cut].open_time
    part = run_history(c[:cut], [x for x in h if x.open_time < t_cut], Params(), "60").states
    assert all(same_state(a, b) for a, b in zip(full[:cut], part))
    assert sum(1 for s in full if s.sig_dir) > 10


def test_tradingview_comparator_selftest(need_data, tmp_path):
    """Build a TV-shaped CSV from our own output and check the comparator reads it back as identical."""
    c, h = _load(need_data, n=3000)
    res = run_history(c, h, Params(), "60")
    path = tmp_path / "BINANCE_BTCUSDT, 60.csv"
    with path.open("w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["time", "open", "high", "low", "close", "Volume", "Signal", "HTF trend", "Relative volume",
                    "Money flow", "EMA trend", "Fast EMA", "Slow EMA"])
        for x, s in zip(c, res.states):
            nanstr = lambda v: "NaN" if v is None or (isinstance(v, float) and math.isnan(v)) else repr(v)
            w.writerow([x.open_time // 1000, x.open, x.high, x.low, x.close, x.volume, s.sig_dir,
                        nanstr(s.htf_trend), nanstr(s.rel_vol), nanstr(s.flow), s.ema_trend, nanstr(s.ema_f),
                        nanstr(s.ema_s)])
    cmp = compare(path, h, Params(), "60", warmup=500)
    assert cmp.ok, cmp.report()
    assert cmp.signals_tv == cmp.signals_ours > 0

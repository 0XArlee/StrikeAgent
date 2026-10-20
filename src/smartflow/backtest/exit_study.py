"""Exit and stop study: can a fixed or partial take profit, a break-even stop, a stop beyond a liquidity zone, an
exchange-side trailing stop or a chandelier trail improve Smart Flow after all costs?

Same signals, same execution model and same costs as ``sim.simulate`` (next-open fills, gap-aware stops, slippage,
taker + builder fee per fill, funding); ``XRules()`` reproduces ``simulate`` trade for trade (checked by
``self_check``). Every variant is measured on the fixed dev / val / test windows and on the out-of-sample assets, and
is only worth proposing if it beats the reference in all of them.

Run: ``python -m smartflow.backtest.exit_study`` (writes reports/exit_study.md and .json).
"""

from __future__ import annotations

import bisect
import json
import math
import time
from dataclasses import asdict, dataclass, replace
from pathlib import Path

from ..core.config import Params
from ..core.exits import close_exit
from ..core.pine import ge, isna, le
from .metrics import compute
from .sim import CostModel, ExecModel, SimTrade, simulate
from .study import CORE, OOS_ASSETS, WINDOWS, signals


@dataclass(frozen=True)
class XRules:
    # initial stop: "atr" = p.stop_atr x ATR (the script); "range" = beyond the broken range's far side (lo_n / hi_n,
    # where the range's stops sit), "swing" = beyond the extreme of the last swing_n bars, "signal" = beyond the
    # signal candle; each of those plus stop_k ATR, never closer than stop_min_atr, trade skipped beyond stop_max_atr
    stop: str = "atr"
    stop_k: float = 0.0
    stop_pct: float = 0.0         # buffer beyond the level as a fraction of price ("a few pips": 0.0005 = 0.05 %)
    swing_n: int = 5              # "swing": bars looked back; "pivot": bars on each side of a confirmed swing low/high
    stop_min_atr: float = 0.5
    stop_max_atr: float = 4.0
    tp_r: float = 0.0             # full take profit at this many R (0 = none)
    part_frac: float = 0.0        # partial take profit: this fraction closed at part_r R
    part_r: float = 0.0
    be_after_part: bool = False   # after the partial, the stop goes to break-even
    be_r: float = 0.0             # stop to break-even once the price has reached +be_r R (0 = off)
    be_struct: float = -1.0       # >= 0: stop to break-even once a close is beyond the signal candle's extreme + k ATR
    be_fees: bool = True          # the break-even level also covers the round trip's fees
    exch_trail: float = -1.0      # >= 0: after each close the stop on the exchange rises to the channel level - k ATR
    chand: float = 0.0            # > 0: after each close the stop rises to the best extreme since entry - k ATR
    close_exit: bool = True       # the strategy's close-based exit (10-candle channel) stays on
    time_bars: int = 0            # > 0: after this many bars a trade still below time_r R is closed at the next open
    time_r: float = 0.0

    def label(self) -> str:
        d = {k: v for k, v in asdict(self).items() if v != getattr(XRules(), k)}
        return ", ".join(f"{k}={v}" for k, v in d.items()) or "reference"


@dataclass(slots=True)
class _Pos:
    t: SimTrade
    sl: float
    risk0: float
    left: float = 1.0
    pieces: list = None           # [(fraction, price, time_ms, reason)]
    best: float = math.nan
    be_done: bool = False
    part_done: bool = False
    pending: str = ""
    entry_fee_paid: bool = False


def simulate_x(symbol: str, candles, states, p: Params, cost: CostModel, exe: ExecModel, x: XRules, funding=None,
               start_ms: int | None = None, end_ms: int | None = None) -> list[SimTrade]:
    out: list[SimTrade] = []
    open_pos: list[_Pos] = []
    pending: list[_Pos] = []
    closes = [c.close for c in candles]
    times = [c.open_time for c in candles]
    slip, sslip = cost.slippage_bps / 1e4, cost.stop_slippage_bps / 1e4
    fee, bfee = cost.taker_fee_bps / 1e4, cost.builder_fee_bps / 1e4

    def price_at(tm: int) -> float:
        k = bisect.bisect_right(times, tm) - 1
        return closes[max(0, k)]

    def realize(ps: _Pos, frac: float, px: float, i: int, reason: str, ref_px: float) -> None:
        ps.pieces.append((frac, px, times[i], reason, ref_px))
        ps.left -= frac
        if ps.left <= 1e-9:
            finish(ps)

    def finish(ps: _Pos) -> None:
        t, risk = ps.t, ps.risk0
        g = f = b = fu = sl_ = 0.0
        for frac, px, tm, _, ref in ps.pieces:
            g += frac * (px - t.entry) * t.dir / risk
            f += frac * fee * (t.entry + px) / risk
            b += frac * bfee * (t.entry + px) / risk
            sl_ += frac * (abs(t.entry - t.ref_entry) + abs(px - ref)) / risk
            if cost.funding and funding is not None:
                fu += frac * sum(rate * price_at(ft) * t.dir for ft, rate in funding.between(t.entry_time, tm)) / risk
        last = ps.pieces[-1]
        t.exit_time, t.reason = last[2], last[3] + (" (after partial)" if len(ps.pieces) > 1 else "")
        t.exit_bar = bisect.bisect_left(times, last[2])
        t.exit = sum(fr * px for fr, px, *_ in ps.pieces)
        t.r_gross, t.r_fees, t.r_builder, t.r_funding, t.r_slip = g, f, b, fu, sl_
        out.append(t)

    def be_level(ps: _Pos) -> float:
        t = ps.t
        cushion = (2 * (fee + bfee) * t.entry) if x.be_fees else 0.0
        return t.entry + t.dir * cushion

    def raise_stop(ps: _Pos, lvl: float) -> None:
        if isna(lvl):
            return
        ps.sl = max(ps.sl, lvl) if ps.t.dir == 1 else min(ps.sl, lvl)

    def initial_stop(i: int, s, d: int) -> float | None:
        atr = s.atr
        if x.stop == "atr":
            return s.close - d * p.stop_atr * atr
        if x.stop == "range":
            lvl = s.lo_n if d == 1 else s.hi_n
        elif x.stop == "swing":
            lo = max(0, i - x.swing_n + 1)
            lvl = min(c.low for c in candles[lo:i + 1]) if d == 1 else max(c.high for c in candles[lo:i + 1])
        elif x.stop == "pivot":   # the last confirmed swing low (high) beyond the entry: where the stops sit
            k, lvl = x.swing_n, math.nan
            for j in range(i - k, k - 1, -1):
                lo, hi = candles[j - k:j], candles[j + 1:j + k + 1]
                if d == 1 and candles[j].low < s.close and all(candles[j].low < q.low for q in lo + hi):
                    lvl = candles[j].low
                    break
                if d == -1 and candles[j].high > s.close and all(candles[j].high > q.high for q in lo + hi):
                    lvl = candles[j].high
                    break
                if i - j > 60:
                    break
        else:   # "signal"
            lvl = candles[i].low if d == 1 else candles[i].high
        if isna(lvl):
            return None
        sl = lvl - d * (x.stop_k * atr + x.stop_pct * lvl)
        dist = (s.close - sl) * d
        if dist < x.stop_min_atr * atr:
            sl = s.close - d * x.stop_min_atr * atr
        elif dist > x.stop_max_atr * atr:
            return None
        return sl

    for i, (c, s) in enumerate(zip(candles, states)):
        # 1. fills at the open: pending exits, then pending entries
        for ps in list(open_pos):
            if ps.pending:
                realize(ps, ps.left, c.open * (1 - slip * ps.t.dir), i, ps.pending, c.open)
                open_pos.remove(ps)
        for ps in pending:
            held = [o for o in open_pos]
            if exe.policy == "single" and held:
                continue
            if exe.policy.startswith("pyramid") and (any(o.t.dir != ps.t.dir for o in held) or len(held) >= exe.max_stack):
                continue
            px = c.open * (1 + slip * ps.t.dir)
            t = ps.t
            if (t.dir == 1 and px <= ps.sl) or (t.dir == -1 and px >= ps.sl) or abs(px - ps.sl) < 1e-12:
                continue
            t.entry_bar, t.entry_time, t.entry = i, times[i], px
            ps.risk0 = abs(px - ps.sl)
            t.sl = ps.sl
            t.tp = px + t.dir * x.tp_r * ps.risk0 if x.tp_r > 0 else math.nan
            ps.best = px
            open_pos.append(ps)
        pending = []

        # 2. intrabar: stop first (conservative), then the partial target, then the full target
        for ps in list(open_pos):
            t = ps.t
            if t.entry_bar > i:
                continue
            d = t.dir
            hit_sl = le(c.low, ps.sl) if d == 1 else ge(c.high, ps.sl)
            if hit_sl:
                gapped = exe.stop_gap and ((d == 1 and c.open < ps.sl) or (d == -1 and c.open > ps.sl)) and t.entry_bar < i
                base = c.open if gapped else ps.sl
                why = "stop" if not ps.be_done and abs(ps.sl - t.sl) < 1e-12 else "trailed stop"
                realize(ps, ps.left, base * (1 - sslip * d), i, why + (" (gap)" if gapped else ""), ps.sl)
                open_pos.remove(ps)
                continue
            if x.part_frac > 0 and not ps.part_done:
                lvl = t.entry + d * x.part_r * ps.risk0
                if ge(c.high, lvl) if d == 1 else le(c.low, lvl):
                    gapped = ((d == 1 and c.open > lvl) or (d == -1 and c.open < lvl)) and t.entry_bar < i
                    realize(ps, x.part_frac, (c.open if gapped else lvl) * (1 - slip * d), i, "partial target", lvl)
                    ps.part_done = True
                    if x.be_after_part:
                        raise_stop(ps, be_level(ps))
                        ps.be_done = True
            if not isna(t.tp) and (ge(c.high, t.tp) if d == 1 else le(c.low, t.tp)):
                gapped = ((d == 1 and c.open > t.tp) or (d == -1 and c.open < t.tp)) and t.entry_bar < i
                realize(ps, ps.left, (c.open if gapped else t.tp) * (1 - slip * d), i, "target", t.tp)
                open_pos.remove(ps)
                continue
            if x.be_r > 0 and not ps.be_done:
                lvl = t.entry + d * x.be_r * ps.risk0
                if ge(c.high, lvl) if d == 1 else le(c.low, lvl):
                    raise_stop(ps, be_level(ps))   # takes effect from the next bar (intrabar order unknown)
                    ps.be_done = True

        # 3. at the close: the strategy's exit, the time stop, then the stops that move
        for ps in open_pos:
            t = ps.t
            if ps.pending or i <= t.signal_bar:
                continue
            d = t.dir
            ps.best = max(ps.best, c.high) if d == 1 else min(ps.best, c.low)
            if x.close_exit:
                reason = close_exit(s, d, i - t.signal_bar, p)
                if reason:
                    ps.pending = reason
                    continue
            if x.time_bars and i - t.entry_bar >= x.time_bars and (s.close - t.entry) * d / ps.risk0 < x.time_r:
                ps.pending = "time stop"
                continue
            if x.be_struct >= 0 and not ps.be_done:
                sig = candles[t.signal_bar]
                lvl = (sig.high + x.be_struct * s.atr) if d == 1 else (sig.low - x.be_struct * s.atr)
                if (s.close > lvl) if d == 1 else (s.close < lvl):
                    raise_stop(ps, be_level(ps))
                    ps.be_done = True
            if x.exch_trail >= 0:
                raise_stop(ps, (s.chan_lo_next - x.exch_trail * s.atr) if d == 1 else (s.chan_hi_next + x.exch_trail * s.atr))
            if x.chand > 0:
                raise_stop(ps, ps.best - d * x.chand * s.atr)

        # 4. new signal
        in_window = (start_ms is None or c.open_time >= start_ms) and (end_ms is None or c.open_time < end_ms)
        if s.sig_dir != 0 and in_window and not isna(s.atr):
            sl = initial_stop(i, s, s.sig_dir)
            if sl is None:
                continue
            t = SimTrade(symbol, s.sig_dir, i, c.open_time, s.close, sl, math.nan)
            held = [o for o in open_pos if not o.pending]   # one already closing at the next open does not block it
            if exe.policy == "single" and held:
                continue
            if exe.policy.startswith("pyramid") and held and (held[0].t.dir != t.dir or len(held) >= exe.max_stack):
                continue
            pending.append(_Pos(t, sl, 0.0, pieces=[]))
    return out


# ------------------------------------------------------------------------------------------------ evaluation
def run_set(root: Path, symbols, p: Params, cost: CostModel, exe: ExecModel, x: XRules, window) -> list[SimTrade]:
    trades = []
    for sym in symbols:
        m, run = signals(root, sym, "240", p)
        trades += simulate_x(sym, m.candles, run.states, p, cost, exe, x, m.funding, *window)
    return trades


def self_check(root: Path, p: Params, cost: CostModel, exe: ExecModel) -> None:
    """XRules() must give exactly the trades of the official simulator."""
    w = WINDOWS["full"]
    for sym in CORE:
        m, run = signals(root, sym, "240", p)
        ref = simulate(sym, m.candles, run.states, p, cost, exe, m.funding, *w).trades
        mine = simulate_x(sym, m.candles, run.states, p, cost, exe, XRules(), m.funding, *w)
        key = lambda t: (t.signal_time, round(t.r, 9))
        a, b = sorted(map(key, ref)), sorted(map(key, mine))
        assert a == b, f"{sym}: {len(a)} vs {len(b)} trades; first diff {next((u, v) for u, v in zip(a, b) if u != v) if len(a) == len(b) else ''}"


def metrics(trades, window) -> dict:
    s = compute(trades, *window, risk_per_trade=0.005, boot=True)
    return {"n": s.n, "r": s.avg_r, "lo": s.ci95_low, "hi": s.ci95_high, "win": s.win_rate, "pf": s.profit_factor,
            "cagr": s.cagr, "dd": s.equity_max_dd, "ddr": s.max_dd_r, "tot": s.total_r}


VARIANTS: list[tuple[str, str, XRules]] = [
    ("ref", "Referencia: stop 1,5 ATR, salida por el canal de 10 velas", XRules()),
    # fixed and partial take profits
    ("tp1.5", "TP fijo 1,5R", XRules(tp_r=1.5)), ("tp2", "TP fijo 2R", XRules(tp_r=2)), ("tp3", "TP fijo 3R", XRules(tp_r=3)),
    ("tp4", "TP fijo 4R", XRules(tp_r=4)), ("tp6", "TP fijo 6R", XRules(tp_r=6)), ("tp10", "TP fijo 10R", XRules(tp_r=10)),
    ("p50@1", "50 % a 1R, resto con el canal", XRules(part_frac=.5, part_r=1)),
    ("p50@2", "50 % a 2R, resto con el canal", XRules(part_frac=.5, part_r=2)),
    ("p33@2", "33 % a 2R, resto con el canal", XRules(part_frac=1 / 3, part_r=2)),
    ("p50@2+be", "50 % a 2R y stop a break-even", XRules(part_frac=.5, part_r=2, be_after_part=True)),
    ("p33@3+be", "33 % a 3R y stop a break-even", XRules(part_frac=1 / 3, part_r=3, be_after_part=True)),
    # break-even
    ("be1", "Break-even al llegar a +1R", XRules(be_r=1)), ("be1.5", "Break-even al llegar a +1,5R", XRules(be_r=1.5)),
    ("be2", "Break-even al llegar a +2R", XRules(be_r=2)), ("be3", "Break-even al llegar a +3R", XRules(be_r=3)),
    ("beS0.5", "Break-even cuando una vela cierra 0,5 ATR por encima de la vela de ruptura", XRules(be_struct=.5)),
    ("beS1", "Break-even cuando una vela cierra 1 ATR por encima de la vela de ruptura", XRules(be_struct=1)),
    ("beS2", "Break-even cuando una vela cierra 2 ATR por encima de la vela de ruptura", XRules(be_struct=2)),
    # initial stop beyond a liquidity zone
    ("atr1.0", "Stop a 1,0 ATR", None), ("atr2.0", "Stop a 2,0 ATR", None), ("atr2.5", "Stop a 2,5 ATR", None),
    ("rng0.25", "Stop bajo el rango roto (mín. 20 velas) - 0,25 ATR", XRules(stop="range", stop_k=.25)),
    ("rng0.5", "Stop bajo el rango roto - 0,5 ATR", XRules(stop="range", stop_k=.5)),
    ("sw5", "Stop bajo el último swing (5 velas) - 0,25 ATR", XRules(stop="swing", swing_n=5, stop_k=.25)),
    ("sw5b", "Stop bajo el último swing (5 velas) - 0,5 ATR", XRules(stop="swing", swing_n=5, stop_k=.5)),
    ("sw10", "Stop bajo el último swing (10 velas) - 0,25 ATR", XRules(stop="swing", swing_n=10, stop_k=.25)),
    ("sig0.25", "Stop bajo la vela de ruptura - 0,25 ATR", XRules(stop="signal", stop_k=.25)),
    ("sig0.5", "Stop bajo la vela de ruptura - 0,5 ATR", XRules(stop="signal", stop_k=.5)),
    # "a few pips" beyond the liquidity zone (Edgar): a small buffer in % of price
    ("rng.05%", "Stop 0,05 % bajo el mínimo del rango roto", XRules(stop="range", stop_pct=.0005)),
    ("rng.1%", "Stop 0,1 % bajo el mínimo del rango roto", XRules(stop="range", stop_pct=.001)),
    ("rng.2%", "Stop 0,2 % bajo el mínimo del rango roto", XRules(stop="range", stop_pct=.002)),
    ("sw5.1%", "Stop 0,1 % bajo el mínimo de las 5 últimas velas", XRules(stop="swing", swing_n=5, stop_pct=.001)),
    ("sw10.1%", "Stop 0,1 % bajo el mínimo de las 10 últimas velas", XRules(stop="swing", swing_n=10, stop_pct=.001)),
    ("sig.1%", "Stop 0,1 % bajo la vela de ruptura", XRules(stop="signal", stop_pct=.001)),
    ("pv2.05%", "Stop 0,05 % bajo el último mínimo pivote (2 velas a cada lado)", XRules(stop="pivot", swing_n=2, stop_pct=.0005)),
    ("pv2.1%", "Stop 0,1 % bajo el último mínimo pivote (2 velas a cada lado)", XRules(stop="pivot", swing_n=2, stop_pct=.001)),
    ("pv3.1%", "Stop 0,1 % bajo el último mínimo pivote (3 velas a cada lado)", XRules(stop="pivot", swing_n=3, stop_pct=.001)),
    ("pv5.1%", "Stop 0,1 % bajo el último mínimo pivote (5 velas a cada lado)", XRules(stop="pivot", swing_n=5, stop_pct=.001)),
    ("pv3.2%", "Stop 0,2 % bajo el último mínimo pivote (3 velas a cada lado)", XRules(stop="pivot", swing_n=3, stop_pct=.002)),
    # stops that follow the price on the exchange
    ("xt0", "Stop en Strike = nivel del canal (intravela)", XRules(exch_trail=0)),
    ("xt0.5", "Stop en Strike = canal - 0,5 ATR (respaldo)", XRules(exch_trail=.5)),
    ("xt1", "Stop en Strike = canal - 1 ATR (respaldo)", XRules(exch_trail=1)),
    ("ch3", "Chandelier 3 ATR además del canal", XRules(chand=3)), ("ch4", "Chandelier 4 ATR además del canal", XRules(chand=4)),
    ("ch3only", "Solo chandelier 3 ATR (sin canal)", XRules(chand=3, close_exit=False)),
    ("time10", "Salida por tiempo: tras 10 velas por debajo de 0R", XRules(time_bars=10, time_r=0)),
    ("time20", "Salida por tiempo: tras 20 velas por debajo de +0,5R", XRules(time_bars=20, time_r=.5)),
]


def run(root: Path, out_dir: Path, log=print) -> dict:
    t0 = time.time()
    P = Params()
    cost = CostModel(builder_fee_bps=20.0)      # the real configuration: Strike taker + Smart Flow 0.20 % per fill
    exe = ExecModel()
    self_check(root, P, cost, exe)
    log(f"self-check ok ({time.time() - t0:.0f}s)")
    res: dict = {"cost": cost.label(), "variants": []}
    for vid, desc, x in VARIANTS:
        p, xr = P, x
        if x is None:   # a different ATR stop is a strategy parameter
            p, xr = replace(P, stop_atr=float(vid[3:])), XRules()
        row = {"id": vid, "desc": desc, "rules": xr.label() if x is not None else f"stop_atr={p.stop_atr}"}
        for w in ("full", "dev", "val", "test"):
            row[w] = metrics(run_set(root, CORE, p, cost, exe, xr, WINDOWS[w]), WINDOWS[w])
        row["oos"] = metrics(run_set(root, OOS_ASSETS, p, cost, exe, xr, WINDOWS["full"]), WINDOWS["full"])
        row["pyr"] = metrics(run_set(root, CORE, p, cost, ExecModel(policy="pyramid", max_stack=3), xr, WINDOWS["full"]),
                             WINDOWS["full"])
        res["variants"].append(row)
        f = row["full"]
        log(f"{vid:9s} n={f['n']:4d} R/op={f['r']:+.3f} CAGR={100 * f['cagr']:5.1f}% DD={100 * f['dd']:5.1f}% | "
            f"dev {row['dev']['r']:+.2f} val {row['val']['r']:+.2f} test {row['test']['r']:+.2f} | "
            f"oos {row['oos']['r']:+.3f} | pyr CAGR {100 * row['pyr']['cagr']:.1f}%  ({time.time() - t0:.0f}s)")
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "exit_study.json").write_text(json.dumps(res, indent=1, default=float), encoding="utf-8")
    (out_dir / "exit_study.md").write_text(report_md(res), encoding="utf-8")
    return res


def report_md(res: dict) -> str:
    ref = res["variants"][0]
    pct = lambda v: f"{100 * v:.1f} %"
    lines = ["# Estudio de salidas y stops (Smart Flow 4h, BTC/ETH/SOL)", "",
             f"Costes: {res['cost']}. Riesgo 0,5 % por operación. Una posición por mercado salvo la columna Pyramid.", "",
             "| id | variante | ops | R/op | IC95 | acierto | PF | CAGR | caída máx. | dev | val | test | 5 activos OOS | Pyramid CAGR / caída |",
             "|---|---|---|---|---|---|---|---|---|---|---|---|---|---|"]
    for v in res["variants"]:
        f = v["full"]
        better = all(v[w]["r"] > ref[w]["r"] for w in ("dev", "val", "test")) and v["oos"]["r"] >= ref["oos"]["r"]
        mark = " **✓**" if better and v is not ref else ""
        lines.append(f"| {v['id']}{mark} | {v['desc']} | {f['n']} | {f['r']:+.3f} | [{f['lo']:+.2f}, {f['hi']:+.2f}] | "
                     f"{100 * f['win']:.0f} % | {f['pf']:.2f} | {pct(f['cagr'])} | {pct(f['dd'])} | {v['dev']['r']:+.2f} | "
                     f"{v['val']['r']:+.2f} | {v['test']['r']:+.2f} | {v['oos']['r']:+.3f} | {pct(v['pyr']['cagr'])} / {pct(v['pyr']['dd'])} |")
    lines += ["", "✓ = mejor R/op que la referencia en desarrollo, validación y test, y no peor en los 5 activos fuera de muestra.",
              "Las variantes de stop cambian el tamaño de 1R: compáralas por CAGR y caída máxima, no solo por R/op."]
    return "\n".join(lines) + "\n"


if __name__ == "__main__":
    import sys
    root = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("data")
    run(root, Path("reports"))


# ------------------------------------------------------------------------------------------------ phase 2
def phase2(root: Path, out_dir: Path, log=print) -> dict:
    """Is the chandelier gain a plateau or a lucky point, and does it add up with the entry filters?"""
    t0 = time.time()
    P = Params()
    cost, exe = CostModel(builder_fee_bps=20.0), ExecModel()
    rf = replace(P, range_filter=True)
    v2 = replace(P, vol_min=2.0)
    rows = [("ref", "Referencia", P, XRules())]
    rows += [(f"ch{k:g}", f"Chandelier {k:g} ATR", P, XRules(chand=k)) for k in (3.5, 4, 4.5, 5, 6, 8)]
    rows += [
        ("ch4+be3", "Chandelier 4 ATR + break-even a +3R", P, XRules(chand=4, be_r=3)),
        ("ch4+beS2", "Chandelier 4 ATR + break-even estructural (2 ATR)", P, XRules(chand=4, be_struct=2)),
        ("rf", "Filtro de rango amplio", rf, XRules()),
        ("vol2", "Volumen >= 2x", v2, XRules()),
        ("rf+vol2", "Filtro de rango + volumen >= 2x", replace(rf, vol_min=2.0), XRules()),
        ("rf+ch4", "Filtro de rango + chandelier 4 ATR", rf, XRules(chand=4)),
        ("rf+ch5", "Filtro de rango + chandelier 5 ATR", rf, XRules(chand=5)),
        ("vol2+ch4", "Volumen >= 2x + chandelier 4 ATR", v2, XRules(chand=4)),
        ("rf+ch4+xt1", "Filtro de rango + chandelier 4 ATR + respaldo canal-1 ATR", rf, XRules(chand=4, exch_trail=1)),
    ]
    res: dict = {"cost": cost.label(), "variants": []}
    for vid, desc, p, xr in rows:
        row = {"id": vid, "desc": desc, "rules": xr.label() + (", range_filter" if p.range_filter else "") +
               (f", vol_min={p.vol_min}" if p.vol_min != Params().vol_min else "")}
        for w in ("full", "dev", "val", "test"):
            row[w] = metrics(run_set(root, CORE, p, cost, exe, xr, WINDOWS[w]), WINDOWS[w])
        row["oos"] = metrics(run_set(root, OOS_ASSETS, p, cost, exe, xr, WINDOWS["full"]), WINDOWS["full"])
        row["oos_each"] = {a: metrics(run_set(root, [a], p, cost, exe, xr, WINDOWS["full"]), WINDOWS["full"])["r"]
                           for a in OOS_ASSETS}
        row["core_each"] = {a: metrics(run_set(root, [a], p, cost, exe, xr, WINDOWS["full"]), WINDOWS["full"])["r"]
                            for a in CORE}
        row["pyr"] = metrics(run_set(root, CORE, p, cost, ExecModel(policy="pyramid", max_stack=3), xr, WINDOWS["full"]),
                             WINDOWS["full"])
        res["variants"].append(row)
        f = row["full"]
        log(f"{vid:11s} n={f['n']:4d} R/op={f['r']:+.3f} [{f['lo']:+.2f},{f['hi']:+.2f}] CAGR={100 * f['cagr']:5.1f}% "
            f"DD={100 * f['dd']:5.1f}% | dev {row['dev']['r']:+.2f} val {row['val']['r']:+.2f} test {row['test']['r']:+.2f} | "
            f"oos {row['oos']['r']:+.3f} ({' '.join(f'{k[:3]}{v:+.2f}' for k, v in row['oos_each'].items())}) | "
            f"core {' '.join(f'{k[:3]}{v:+.2f}' for k, v in row['core_each'].items())} | pyr {100 * row['pyr']['cagr']:.1f}%/"
            f"{100 * row['pyr']['dd']:.1f}%  ({time.time() - t0:.0f}s)")
    (out_dir / "exit_study_phase2.json").write_text(json.dumps(res, indent=1, default=float), encoding="utf-8")
    (out_dir / "exit_study_phase2.md").write_text(report_md(res).replace("# Estudio de salidas y stops", "# Fase 2: chandelier y filtros de entrada"), encoding="utf-8")
    return res

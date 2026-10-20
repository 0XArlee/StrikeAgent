"""Reproducible research suite: every experiment states its hypothesis, runs, and records the result and verdict.

Run: ``smartflow research`` (writes ``reports/experiments.md`` and ``reports/experiments.json``).
Failed hypotheses are recorded exactly like successful ones.
"""

from __future__ import annotations

import bisect
import json
import math
import statistics as st
import time
from dataclasses import replace
from pathlib import Path

from ..core.config import BiasSource, ExitMode, Params
from ..core.runner import run_history
from ..core.timeframes import normalize
from ..core.types import Candle
from .metrics import Stats, compute
from .sim import CostModel, ExecModel, simulate
from .study import CORE, OOS_ASSETS, WINDOWS, evaluate, market, signals

REALISTIC = CostModel()             # taker 5 bp/fill, builder 0, slippage 2/5 bp, funding on
EXE = ExecModel()                   # next-open, gap-aware, one position per market


class Report:
    def __init__(self) -> None:
        self.md: list[str] = []
        self.data: dict = {}

    def section(self, eid: str, title: str, hypothesis: str) -> None:
        self.md += [f"\n## {eid} — {title}\n", f"**Hipótesis:** {hypothesis}\n"]
        self.data[eid] = {"title": title, "hypothesis": hypothesis, "rows": []}
        self._cur = eid

    def table(self, header: list[str], rows: list[list]) -> None:
        self.md.append("| " + " | ".join(header) + " |")
        self.md.append("|" + "---|" * len(header))
        for r in rows:
            self.md.append("| " + " | ".join(str(x) for x in r) + " |")
        self.md.append("")
        self.data[self._cur]["rows"] += [dict(zip(header, r)) for r in rows]

    def verdict(self, text: str) -> None:
        self.md.append(f"**Veredicto:** {text}\n")
        self.data[self._cur]["verdict"] = text

    def text(self, t: str) -> None:
        self.md.append(t + "\n")


def f3(x: float) -> str:
    return "n/a" if x is None or (isinstance(x, float) and math.isnan(x)) else f"{x:+.3f}"


def ci(s: Stats) -> str:
    return "n/a" if math.isnan(s.ci95_low) else f"[{s.ci95_low:+.2f}, {s.ci95_high:+.2f}]"


def srow(label: str, s: Stats) -> list:
    return [label, s.n, f3(s.avg_r), ci(s), f"{s.t_stat:.1f}" if not math.isnan(s.t_stat) else "n/a",
            f"{100 * s.win_rate:.0f}%" if s.n else "-", f"{s.profit_factor:.2f}" if not math.isnan(s.profit_factor) else "-",
            f"{s.total_r:+.0f}", f"{s.max_dd_r:.0f}"]


SHDR = ["config", "n", "R/op", "IC95", "t", "win", "PF", "R total", "maxDD R"]


def agg_2h(candles: list[Candle]) -> list[Candle]:
    out, cur = [], None
    step = 2 * 3_600_000
    for c in candles:
        k = (c.open_time // step) * step
        if cur is None or cur[0] != k:
            if cur:
                out.append(Candle(*cur[:6], c.source))
            cur = [k, c.open, c.high, c.low, c.close, c.volume]
        else:
            cur[2], cur[3], cur[4], cur[5] = max(cur[2], c.high), min(cur[3], c.low), c.close, cur[5] + c.volume
    if cur:
        out.append(Candle(*cur[:6], candles[-1].source))
    return out


def run(root: Path, out_dir: Path, quick: bool = False, log=print) -> Report:
    t0 = time.time()
    rep = Report()
    P = Params()
    full = WINDOWS["full"]
    tfs = ["60", "240"]

    # ---------------------------------------------------------------- E1
    rep.section("E1", "Del modelo de referencia a la ejecución realista en Strike",
                "Las cifras del script (entrada al cierre, stop exacto, operaciones solapadas) sobrestiman lo que "
                "una cuenta de Strike (posición neta por mercado) puede capturar.")
    steps = [
        ("A referencia (solape, fill al cierre, taker 5bp)", CostModel(5, 0, 0, 0, False), ExecModel("close", "close", False, "overlap")),
        ("B + una posición por mercado (netting)", CostModel(5, 0, 0, 0, False), ExecModel("close", "close", False, "single")),
        ("C + entrada/salidas a la apertura siguiente", CostModel(5, 0, 0, 0, False), ExecModel("next_open", "next_open", False, "single")),
        ("D + stops con gap", CostModel(5, 0, 0, 0, False), ExecModel("next_open", "next_open", True, "single")),
        ("E + slippage 2bp mercado / 5bp stop", CostModel(5, 0, 2, 5, False), ExecModel("next_open", "next_open", True, "single")),
        ("F + funding (proxy perp Binance)", REALISTIC, EXE),
    ]
    for tf in tfs:
        rows = [srow(f"{tf} {lbl}", evaluate(root, CORE, tf, P, c, e, full)[0]) for lbl, c, e in steps]
        rep.table(SHDR, rows)
    rep.verdict("Ver tablas: el modelo F es la base de todas las comparaciones siguientes.")
    log(f"E1 done {time.time() - t0:.0f}s")

    # ---------------------------------------------------------------- E2
    rep.section("E2", "Builder fee: punto de equilibrio",
                "Una builder fee por fill (entrada y salida) del 1 % (100 bps) destruye la ventaja; existe un nivel "
                "compatible con una expectativa neta positiva para el usuario.")
    fees = [0, 1, 2, 5, 10, 15, 20, 30, 50, 75, 100]
    for tf in tfs:
        rows, be = [], None
        prev = None
        for b in fees:
            s = evaluate(root, CORE, tf, P, replace(REALISTIC, builder_fee_bps=b), EXE, full, boot=True)[0]
            rows.append([f"{tf} {b} bp", s.n, f3(s.avg_r), ci(s), f"{s.builder_r:.3f}", f"{100 * s.cagr:.1f}%",
                         f"{100 * s.equity_max_dd:.1f}%"])
            if prev is not None and be is None and prev[1] > 0 >= s.avg_r:
                be = prev[0] + (b - prev[0]) * prev[1] / (prev[1] - s.avg_r)
            prev = (b, s.avg_r)
        rep.table(["config", "n", "R/op neto", "IC95", "coste builder R/op", "CAGR (0,5% riesgo/op)", "maxDD equity"], rows)
        rep.text(f"Punto de equilibrio {tf}: ≈ {be:.0f} bps por fill." if be else f"{tf}: sin punto de equilibrio en el rango.")
    rep.verdict("Ver tablas y puntos de equilibrio; interpretación en docs/05_informe_cuantitativo.md.")
    log(f"E2 done {time.time() - t0:.0f}s")

    # ---------------------------------------------------------------- E3
    rep.section("E3", "Estabilidad temporal: desarrollo / validación / test",
                "Si la ventaja es real debe ser positiva en los tres tramos fijados de antemano.")
    rows = []
    for tf in tfs:
        for w in ("dev", "val", "test", "strike"):
            s, per, _ = evaluate(root, CORE, tf, P, REALISTIC, EXE, WINDOWS[w])
            r = srow(f"{tf} {w}", s) + ["  ".join(f"{k[:3]} {v.avg_r:+.2f} ({v.n})" for k, v in per.items())]
            rows.append(r)
    rep.table(SHDR + ["por activo"], rows)
    rep.verdict("Ver tabla; interpretación en docs/05_informe_cuantitativo.md.")
    log(f"E3 done {time.time() - t0:.0f}s")

    # ---------------------------------------------------------------- E4
    rep.section("E4", "Por año y por régimen",
                "La ventaja no depende de un único año ni de un único régimen de mercado.")
    for tf in tfs:
        _, _, trades = evaluate(root, CORE, tf, P, REALISTIC, EXE, full, boot=False)
        rows = []
        for y in range(2022, 2027):
            a, b = int(time.mktime((y, 1, 1, 0, 0, 0, 0, 0, 0)) * 1000), int(time.mktime((y + 1, 1, 1, 0, 0, 0, 0, 0, 0)) * 1000)
            ty = [t for t in trades if a <= t.signal_time < b]
            rows.append(srow(f"{tf} {y}", compute(ty, max(a, full[0]), min(b, full[1]), boot=False)))
        # regimes: daily close vs 200D SMA of the same asset, at the signal
        reg = {"a favor de la tendencia diaria (SMA200D)": [], "contra la tendencia diaria": [],
               "volatilidad baja (ATR% tercio inferior)": [], "volatilidad media": [], "volatilidad alta": []}
        atrp = []
        for s in CORE:
            m, runr = signals(root, s, tf, P)
            dm = market(root, s, "D", P)
            dts = [c.open_time for c in dm.candles]
            dcl = [c.close for c in dm.candles]
            sma = [math.nan] * len(dcl)
            for i in range(199, len(dcl)):
                sma[i] = sum(dcl[i - 199:i + 1]) / 200
            idx = {c.open_time: i for i, c in enumerate(m.candles)}
            for t in [t for t in trades if t.symbol == s]:
                i = idx[t.signal_time]
                k = bisect.bisect_right(dts, t.signal_time) - 2   # last fully closed daily bar
                if k >= 199:
                    with_trend = (dcl[k] > sma[k]) == (t.dir == 1)
                    reg["a favor de la tendencia diaria (SMA200D)" if with_trend else "contra la tendencia diaria"].append(t)
                atrp.append((runr.states[i].atr / runr.states[i].close, t))
        atrp.sort(key=lambda x: x[0])
        n3 = len(atrp) // 3
        for j, name in enumerate(["volatilidad baja (ATR% tercio inferior)", "volatilidad media", "volatilidad alta"]):
            reg[name] = [t for _, t in atrp[j * n3:(j + 1) * n3 if j < 2 else len(atrp)]]
        for name, ts in reg.items():
            rows.append(srow(f"{tf} {name}", compute(ts, *full, boot=False)))
        rep.table(SHDR, rows)
    rep.verdict("Ver tablas (los terciles de volatilidad usan la muestra completa: es descriptivo, no una regla).")
    log(f"E4 done {time.time() - t0:.0f}s")

    # ---------------------------------------------------------------- E5
    rep.section("E5", "Activos fuera de muestra",
                "El autor midió BTC/ETH/SOL; si la lógica generaliza, debe funcionar en activos que no se usaron "
                "para diseñarla (XRP, BNB, ADA, NEAR, ZEC; todos listados en Strike).")
    rows = []
    avail = [s for s in OOS_ASSETS if (root / "binance" / "spot" / f"{s}_4h.csv").exists()]
    for tf in tfs:
        s, per, _ = evaluate(root, avail, tf, P, REALISTIC, EXE, full)
        rows.append(srow(f"{tf} {len(avail)} activos OOS", s) +
                     ["  ".join(f"{k[:-4]} {v.avg_r:+.2f} ({v.n})" for k, v in per.items())])
    rep.table(SHDR + ["por activo"], rows)
    rep.verdict("Ver tabla.")
    log(f"E5 done {time.time() - t0:.0f}s")

    # ---------------------------------------------------------------- E6
    rep.section("E6", "Otros timeframes",
                "El script dice que por debajo de 1h las comisiones se comen la ventaja; 2h y 1D deberían comportarse "
                "entre 1h y 4h si la lógica es robusta.")
    rows = []
    for tf in (["30", "120", "60", "240", "D"] if not quick else ["240"]):
        trades, per = [], {}
        for s in CORE:
            if tf == "120":
                m = market(root, s, "60", P)
                c2 = agg_2h(m.candles)
                runr = run_history(c2, market(root, s, "D", P).candles, P, "120")
                r = simulate(s, c2, runr.states, P, REALISTIC, EXE, m.funding, *full)
            else:
                if not (root / "binance" / "spot" / f"{s}_{ {'30': '30m', '60': '1h', '240': '4h', 'D': '1d'}[tf]}.csv").exists():
                    continue
                m, runr = signals(root, s, tf, P)
                r = simulate(s, m.candles, runr.states, P, REALISTIC, EXE, m.funding, *full)
            trades += r.trades
            per[s] = compute(r.trades, *full, boot=False)
        if trades:
            label = {"30": "30m", "60": "1h", "120": "2h", "240": "4h", "D": "1D"}[tf]
            rows.append(srow(label, compute(trades, *full)) + [f"{compute(trades, *full, boot=False).fees_r:.3f}"])
    rep.table(SHDR + ["comisiones R/op"], rows)
    rep.verdict("Ver tabla.")
    log(f"E6 done {time.time() - t0:.0f}s")

    # ---------------------------------------------------------------- E7
    rep.section("E7", "Sensibilidad de parámetros (uno a uno alrededor de los valores por defecto)",
                "Una ventaja robusta forma una meseta: valores vecinos dan resultados parecidos. Un pico aislado en "
                "el valor por defecto sería señal de sobreajuste.")
    grid = {"look_n": [10, 15, 20, 30, 40], "range_min": [0.7, 0.85, 1.0, 1.2, 1.5], "body_min": [0.5, 0.6, 0.7],
            "vol_min": [0.0, 1.0, 1.5, 2.0, 2.5], "stop_atr": [1.0, 1.25, 1.5, 2.0, 2.5],
            "chan_n": [5, 7, 10, 15, 20, 30], "htf_swing": [3, 5, 8]}
    if quick:
        grid = {"chan_n": [10, 20]}
    for tf in tfs:
        rows = []
        for name, vals in grid.items():
            for v in vals:
                pv = replace(P, **{name: v})
                s = evaluate(root, CORE, tf, pv, REALISTIC, EXE, full, boot=False)[0]
                d = evaluate(root, CORE, tf, pv, REALISTIC, EXE, WINDOWS["dev"], boot=False)[0]
                tst = evaluate(root, CORE, tf, pv, REALISTIC, EXE, WINDOWS["test"], boot=False)[0]
                rows.append([f"{tf} {name}={v}" + (" (def)" if getattr(P, name) == v else ""), s.n, f3(s.avg_r),
                             f"{s.total_r:+.0f}", f3(d.avg_r), f3(tst.avg_r)])
        rep.table(["config", "n", "R/op total", "R total", "R/op dev", "R/op test"], rows)
    rep.verdict("Ver tablas.")
    log(f"E7 done {time.time() - t0:.0f}s")

    # ---------------------------------------------------------------- E8
    rep.section("E8", "Filtros opcionales, salidas y sesgo (modo experimental vs referencia)",
                "Cada opción del script se compara con la referencia en los tres tramos; solo se recomendaría una que "
                "mejore en desarrollo Y se mantenga en validación y test.")
    variants = [
        ("referencia", P),
        ("filtro rango amplio", replace(P, range_filter=True)),
        ("filtro nube EMA", replace(P, ema_filter=True)),
        ("filtro money flow", replace(P, flow_filter=True)),
        ("salida money-flow cross", replace(P, exit_mode=ExitMode.FLOW_CROSS)),
        ("salida lo primero", replace(P, exit_mode=ExitMode.FIRST)),
        ("TP 2R", replace(P, tp_r=2.0)), ("TP 4R", replace(P, tp_r=4.0)),
        ("sesgo EMA lenta", replace(P, bias_source=BiasSource.SLOW_EMA)),
        ("sesgo cualquiera", replace(P, bias_source=BiasSource.EITHER)),
        ("sin sesgo", replace(P, bias_source=BiasSource.NONE)),
    ]
    if quick:
        variants = variants[:2]
    for tf in tfs:
        rows = []
        for lbl, pv in variants:
            res = [evaluate(root, CORE, tf, pv, REALISTIC, EXE, WINDOWS[w], boot=False)[0] for w in ("dev", "val", "test")]
            fl = evaluate(root, CORE, tf, pv, REALISTIC, EXE, full, boot=False)[0]
            rows.append([f"{tf} {lbl}", fl.n, f3(fl.avg_r), f"{fl.total_r:+.0f}"] + [f3(x.avg_r) for x in res])
        rep.table(["config", "n", "R/op total", "R total", "dev", "val", "test"], rows)
    rep.verdict("Ver tablas.")
    log(f"E8 done {time.time() - t0:.0f}s")

    # ---------------------------------------------------------------- E9
    rep.section("E9", "Walk-forward de la selección de variante",
                "Elegir cada 6 meses la mejor variante de los 18 meses anteriores ¿mejora fuera de muestra a quedarse "
                "siempre con la referencia? (si no, no se optimiza).")
    cands = [("referencia", P), ("filtro rango amplio", replace(P, range_filter=True)),
             ("salida money-flow cross", replace(P, exit_mode=ExitMode.FLOW_CROSS)),
             ("canal 20", replace(P, chan_n=20)), ("sesgo cualquiera", replace(P, bias_source=BiasSource.EITHER))]
    from .study import ms
    half_year = int(182.6 * 86_400_000)
    for tf in tfs:
        wf, ref, rows = [], [], []
        for k in range(10):
            test_start = ms(2023, 7) + k * half_year
            test_end = min(test_start + half_year, full[1])
            if test_start >= full[1]:
                break
            train = (test_start - int(547.9 * 86_400_000), test_start)
            scores = [(evaluate(root, CORE, tf, pv, REALISTIC, EXE, train, boot=False)[0].avg_r, lbl, pv) for lbl, pv in cands]
            best = max(scores, key=lambda x: x[0])
            _, _, tb = evaluate(root, CORE, tf, best[2], REALISTIC, EXE, (test_start, test_end), boot=False)
            _, _, trf = evaluate(root, CORE, tf, P, REALISTIC, EXE, (test_start, test_end), boot=False)
            wf += tb
            ref += trf
            rows.append([f"{tf} fold {k + 1}", time.strftime('%Y-%m', time.gmtime(test_start / 1000)), best[1],
                         f3(compute(tb, test_start, test_end, boot=False).avg_r),
                         f3(compute(trf, test_start, test_end, boot=False).avg_r)])
        rep.table(["fold", "test desde", "elegida (train 18m)", "R/op test elegida", "R/op test referencia"], rows)
        a, b = compute(wf, ms(2023, 7), full[1]), compute(ref, ms(2023, 7), full[1])
        rep.table(SHDR, [srow(f"{tf} walk-forward", a), srow(f"{tf} referencia fija", b)])
    rep.verdict("Ver tablas.")
    log(f"E9 done {time.time() - t0:.0f}s")

    out_dir.mkdir(parents=True, exist_ok=True)
    head = [f"# Registro de experimentos — Smart Flow Agent\n",
            f"Generado por `smartflow research` en {time.strftime('%Y-%m-%d %H:%M UTC', time.gmtime())}. "
            f"Datos: Binance spot (señal y precios) + funding de perpetuos Binance como proxy; ventana completa "
            f"2022-01-01 → 2026-10-18. Modelo base: {REALISTIC.label()}; {EXE.label()}. Riesgo por operación para "
            f"métricas de equity: 0,5 %. R/op = R neto por operación. IC95 = bootstrap del R medio.\n"]
    (out_dir / "experiments.md").write_text("\n".join(head + rep.md), encoding="utf-8")
    (out_dir / "experiments.json").write_text(json.dumps(rep.data, indent=1, ensure_ascii=False), encoding="utf-8")
    log(f"research done in {time.time() - t0:.0f}s -> {out_dir}")
    return rep

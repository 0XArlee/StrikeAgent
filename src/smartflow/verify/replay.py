"""Independent replay: the backtest engine over the freshly downloaded Binance history, bar by bar, against what each
paper agent wrote in its journal (inputs, indicators and the final decision). On the agents' host, from the app folder:

    systemctl start smartflow-data.service     # fresh history first (as root)
    python -m smartflow.verify.replay
"""
import json, math
from pathlib import Path
from smartflow.agent.config import load
from smartflow.core.runner import run_history
from smartflow.core.timeframes import normalize
from smartflow.data.binance import kline_path
from smartflow.data.store import load_candles

root = Path("data")
total = ok = 0
worst = 0.0
for name in ["reference", "recommended", "2h", "flowexit"]:
    cfg = load(Path(f"config/paper-{name}.toml"))
    tf = normalize(cfg.tf)
    seen = {}
    for ln in (Path("runs") / cfg.name / "journal.jsonl").read_text().splitlines():
        try:
            r = json.loads(ln)
        except json.JSONDecodeError:
            continue
        if r.get("kind") == "analysis":
            seen[(r["market"], int(r["bar"]))] = r
    n_agent = n_match = 0
    for mm in cfg.markets:
        from smartflow.core.runner import resolve_htf
        htf_tf, _ = resolve_htf(cfg.params, tf)
        hist = load_candles(kline_path(root, mm.signal, tf), f"binance-spot:{mm.signal}")
        htf = load_candles(kline_path(root, mm.signal, htf_tf), f"binance-spot:{mm.signal}")
        res = run_history(hist, htf, cfg.params, tf)
        by = {c.open_time: (c, st) for c, st in zip(hist, res.states)}
        for (mkt, bar), r in seen.items():
            if mkt != mm.strike or bar not in by:
                continue
            c, st = by[bar]
            n_agent += 1
            same = True
            for k_j, v_b in (("close", c.close), ("atr", st.atr), ("rel_vol", st.rel_vol), ("flow", st.flow)):
                v_j = r.get(k_j)
                if v_j is None or v_b is None or (isinstance(v_b, float) and math.isnan(v_b)):
                    same &= (v_j is None) == (v_b is None)
                    continue
                d = abs(float(v_j) - float(v_b)) / max(1e-12, abs(float(v_b)))
                worst = max(worst, d)
                same &= d < 1e-6
            same &= int(r.get("sig_dir") or 0) == int(st.sig_dir) and r.get("htf_trend") == st.htf_trend
            same &= list(r.get("why") or []) == list(st.why_no_signal(cfg.params))
            n_match += same
            if not same:
                print(f"  MISMATCH {name} {mkt} bar {bar}: journal sig {r.get('sig_dir')} rel_vol {r.get('rel_vol')} | replay sig {st.sig_dir} rel_vol {st.rel_vol}")
    signals = sum(1 for r in seen.values() if int(r.get("sig_dir") or 0) != 0)
    print(f"{name:12s} tf {tf:>3}: {n_match}/{n_agent} candles identical to the backtest engine | signals in the journal: {signals}")
    total += n_agent; ok += n_match
print(f"ALL: {ok}/{total} identical (largest relative difference {worst:.1e})")

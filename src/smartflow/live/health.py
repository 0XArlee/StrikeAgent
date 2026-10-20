"""Strategy health: how each strategy is doing for real against what its backtest promised, and a safety hold.

Measured on the official paper agent of each strategy (``config/city.toml``: ``paper-reference`` = Smart Flow,
``paper-pyramid`` = Smart Flow Pyramid): it runs the official parameters on Strike's real book, all day, and is one
series per strategy (the users' agents take the same signals, so pooling them would only repeat the same trades).
Only its trades on the backtest's markets (BTC, ETH, SOL) opened with the official parameters count.

States, checked every hour (``smartflow health``, ``deploy/smartflow-health.timer``):

- ``ok``: nothing unusual for this sample size.
- ``watch`` (alert to the operator): after 20 trades the average R is below 0, after 30 it is below the backtest's
  95 % interval, or the drawdown in R reached the backtest's worst.
- ``hold``: after 30 trades the whole 95 % interval of the average R is below 0 (the strategy is losing, not just
  unlucky), or the drawdown reached 1.5x the backtest's worst. ``runs/strategy-hold.json`` then stops every user's
  agent of that strategy from opening new trades (agent/runner.py); open trades keep their stop and exits, and the
  paper agent keeps measuring. Only the operator lifts it: ``smartflow health --release <strategy>``.
"""

from __future__ import annotations

import json
import math
import time
from pathlib import Path

from .. import notify
from ..api.city import load_city, snapshot
from ..core.config import OFFICIAL

STRATEGIES = ("smartflow", "pyramid")
AGENT_ID = {"smartflow": "sf-reference", "pyramid": "sf-pyramid"}   # config/city.toml
CORE = ("BTC-USD", "ETH-USD", "SOL-USD")
# The backtest each strategy is judged against (web/src/data/strategy*.json, generated 2026-10-20 by
# web/scripts/gen_strategy.py --builder-bps 20: 4h, BTC+ETH+SOL, official parameters, 2022-01 -> 2026-10, 0.5 % risk).
# tests/test_health.py checks these against the page's files.
EXPECT = {
    "smartflow": {"avg_r": 0.62, "ci95": (0.22, 1.07), "max_dd_r": 28.4, "trades_per_year": 62},
    "pyramid": {"avg_r": 0.65, "ci95": (0.31, 1.0), "max_dd_r": 45.8, "trades_per_year": 101},
}
WATCH_N, HOLD_N = 20, 30
HOLD_FILE, STATE_FILE = "strategy-hold.json", "health.json"
NAMES = {"smartflow": "Smart Flow", "pyramid": "Smart Flow Pyramid"}


def evaluate(strategy: str, rs: list[float]) -> dict:
    """The state of one strategy from its trades' R (oldest first)."""
    e = EXPECT[strategy]
    n = len(rs)
    avg = sum(rs) / n if n else 0.0
    sd = math.sqrt(sum((r - avg) ** 2 for r in rs) / (n - 1)) if n > 1 else 0.0
    hi = avg + 1.96 * sd / math.sqrt(n) if n > 1 else math.inf
    peak = cum = dd = 0.0
    for r in rs:
        cum += r
        peak = max(peak, cum)
        dd = max(dd, peak - cum)
    why_hold, why_watch = [], []
    if n >= HOLD_N and hi < 0:
        why_hold.append(f"after {n} trades the average is {avg:+.2f} R and its 95 % interval is entirely below 0 "
                        f"(upper end {hi:+.2f} R)")
    if dd >= 1.5 * e["max_dd_r"]:
        why_hold.append(f"drawdown {dd:.1f} R, 1.5x the backtest's worst ({e['max_dd_r']:.1f} R)")
    if n >= WATCH_N and avg < 0:
        why_watch.append(f"after {n} trades the average is {avg:+.2f} R (backtest {e['avg_r']:+.2f} R)")
    elif n >= HOLD_N and avg < e["ci95"][0]:
        why_watch.append(f"after {n} trades the average is {avg:+.2f} R, below the backtest's 95 % interval "
                         f"[{e['ci95'][0]:+.2f}, {e['ci95'][1]:+.2f}]")
    if dd >= e["max_dd_r"] and not why_hold:
        why_watch.append(f"drawdown {dd:.1f} R reached the backtest's worst ({e['max_dd_r']:.1f} R)")
    state = "hold" if why_hold else "watch" if why_watch else "ok"
    return {"state": state, "n": n, "avg_r": round(avg, 3), "ci95_high": round(hi, 3) if math.isfinite(hi) else None,
            "total_r": round(sum(rs), 2), "dd_r": round(dd, 2), "why": why_hold or why_watch,
            "expected": {"avg_r": e["avg_r"], "ci95": list(e["ci95"]), "max_dd_r": e["max_dd_r"]}}


def strategy_trades(city_toml: Path, root: Path = Path(".")) -> dict[str, list[float]]:
    """R of each strategy's official paper agent: closed, not tests, on the core markets, official parameters."""
    fp = OFFICIAL.fingerprint()
    agents = {a.id: a for a in load_city(city_toml, root)}
    out = {}
    for strat, aid in AGENT_ID.items():
        a = agents.get(aid)
        if not a:
            out[strat] = []
            continue
        snap = snapshot(a, full=True)
        trades = sorted((t for t in snap.get("trades", []) if not t.get("test") and t.get("market") in CORE
                         and t.get("params") == fp), key=lambda t: t["time"])
        out[strat] = [float(t["r"]) for t in trades]
    return out


def holds(runs_root: Path) -> dict:
    """{strategy: {"since": ms, "why": [...]}} for the strategies on hold."""
    try:
        d = json.loads((Path(runs_root) / HOLD_FILE).read_text(encoding="utf-8"))
        return {k: v for k, v in d.items() if k in STRATEGIES and isinstance(v, dict)}
    except (OSError, json.JSONDecodeError):
        return {}


def hold_reason(runs_root: Path, strategy: str) -> str | None:
    h = holds(runs_root).get(strategy)
    return "; ".join(h.get("why") or ["set by the operator"]) if h else None


def _write(path: Path, doc: dict) -> None:
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(doc, indent=1), encoding="utf-8")
    tmp.replace(path)


def check(city_toml: Path, runs_root: Path, root: Path = Path("."), now_ms: int | None = None, log=print) -> dict:
    """Evaluates both strategies, writes runs/health.json, sets a hold when one is breached and alerts the operator
    whenever a state changes (a hold stays until released by hand)."""
    now_ms = now_ms or int(time.time() * 1000)
    runs_root = Path(runs_root)
    prev = {}
    try:
        prev = json.loads((runs_root / STATE_FILE).read_text(encoding="utf-8")).get("strategies", {})
    except (OSError, json.JSONDecodeError):
        pass
    on_hold = holds(runs_root)
    res = {}
    for strat, rs in strategy_trades(city_toml, root).items():
        r = evaluate(strat, rs)
        res[strat] = r
        was = (prev.get(strat) or {}).get("state", "ok")
        if r["state"] == "hold" and strat not in on_hold:
            on_hold[strat] = {"since": now_ms, "why": r["why"]}
            _write(runs_root / HOLD_FILE, on_hold)
            notify.send("critical", f"{NAMES[strat]} ON HOLD: users' agents open no new trades. " + "; ".join(r["why"])
                        + f". Review, then: smartflow health --release {strat}", source="health", cooldown_s=0)
        elif r["state"] != was:
            level = "warning" if r["state"] == "watch" else "info" if r["state"] == "ok" else "error"
            notify.send(level, f"{NAMES[strat]}: {was} -> {r['state']} ({r['n']} trades, average {r['avg_r']:+.2f} R, "
                               f"drawdown {r['dd_r']:.1f} R). " + "; ".join(r["why"]), source="health", cooldown_s=0)
        log(f"{strat}: {r['state']} n={r['n']} avg={r['avg_r']:+.3f}R dd={r['dd_r']:.1f}R {'HOLD' if strat in on_hold else ''}")
    doc = {"time": now_ms, "strategies": res, "holds": on_hold}
    runs_root.mkdir(parents=True, exist_ok=True)
    _write(runs_root / STATE_FILE, doc)
    return doc


def release(runs_root: Path, strategy: str) -> bool:
    """Lifts a hold (the operator's decision, after reviewing the trades)."""
    h = holds(runs_root)
    if strategy not in h:
        return False
    h.pop(strategy)
    _write(Path(runs_root) / HOLD_FILE, h)
    notify.send("warning", f"{NAMES[strategy]}: hold released by the operator; users' agents trade again",
                source="health", cooldown_s=0)
    return True

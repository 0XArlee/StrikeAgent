"""Strategy health: how each strategy is doing for real against what its backtest promised, and a safety hold.

Measured on the official paper agent of each strategy of the registry (``config/strategies.json`` ``paper``: e.g.
``paper-reference`` = Smart Flow, ``paper-pyramid`` = Smart Flow Pyramid): it runs the strategy's parameters on
Strike's real book, all day, and is one series per strategy (the users' agents take the same signals, so pooling them
would only repeat the same trades). Only its trades on the strategy's core markets opened with its parameters count,
against its own backtest (``config/figures/<id>.json``). A strategy with no paper agent or no figures is not judged.

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

from .. import notify, strategies
from ..api.city import load_city, snapshot

WATCH_N, HOLD_N = 20, 30
HOLD_FILE, STATE_FILE = "strategy-hold.json", "health.json"


def expected(strategy: str) -> dict | None:
    """What the strategy's backtest promised (config/figures/<id>.json, web/scripts/gen_strategy.py)."""
    f = strategies.figures(strategy)
    if not f:
        return None
    return {"avg_r": f["avg_r"], "ci95": tuple(f["ci95"]), "max_dd_r": f["max_dd_r"], "trades_per_year": f["trades_per_year"]}


def judged() -> list[strategies.Strategy]:
    """The registry's strategies that have an official paper agent and backtest figures."""
    return [s for s in strategies.all_strategies() if s.paper_city_id and expected(s.id)]


def name(strategy: str) -> str:
    return strategies.get(strategy).name if strategy in strategies.load()[1] else strategy


def evaluate(strategy: str, rs: list[float]) -> dict:
    """The state of one strategy from its trades' R (oldest first)."""
    e = expected(strategy)
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
    """R of each judged strategy's official paper agent: closed, not tests, on its core markets, its parameters."""
    agents = {a.id: a for a in load_city(city_toml, root)}
    out = {}
    for s in judged():
        a = agents.get(s.paper_city_id)
        if not a:
            out[s.id] = []
            continue
        fp = s.params.fingerprint()
        snap = snapshot(a, full=True)
        trades = sorted((t for t in snap.get("trades", []) if not t.get("test") and t.get("market") in s.markets_core
                         and t.get("params") == fp), key=lambda t: t["time"])
        out[s.id] = [float(t["r"]) for t in trades]
    return out


def holds(runs_root: Path) -> dict:
    """{strategy: {"since": ms, "why": [...]}} for the strategies on hold."""
    try:
        d = json.loads((Path(runs_root) / HOLD_FILE).read_text(encoding="utf-8"))
        return {k: v for k, v in d.items() if k in strategies.load()[1] and isinstance(v, dict)}
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
            notify.send("critical", f"{name(strat)} ON HOLD: users' agents open no new trades. " + "; ".join(r["why"])
                        + f". Review, then: smartflow health --release {strat}", source="health", cooldown_s=0)
        elif r["state"] != was:
            level = "warning" if r["state"] == "watch" else "info" if r["state"] == "ok" else "error"
            notify.send(level, f"{name(strat)}: {was} -> {r['state']} ({r['n']} trades, average {r['avg_r']:+.2f} R, "
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
    notify.send("warning", f"{name(strategy)}: hold released by the operator; users' agents trade again",
                source="health", cooldown_s=0)
    return True

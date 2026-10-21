"""Scheduled US macro releases and the strategies: are trades opened right before a Fed decision, a CPI or a jobs
report (or whose signal candle held one) worse than the rest, and would skipping them help the account?

Decided before looking at any result (proposal of 2026-10-21, "fase 1"):

- groups, per trade: "pre" = a release inside the first candle after the entry (the entry sits right before it);
  "signal" = a release inside the signal candle (the breakout happened on it); "open" = a release later while the
  trade was open; "clean" = none of those.
- rules: R1 skip "pre" entries, R2 skip "signal" entries, R3 skip both.
- a rule is adopted only if (a) the trades it removes are clearly worse than the ones it keeps: the 95 % interval of
  the difference of their mean R is below 0, and (b) the agent's account (yearly growth / drawdown, at the default risk)
  improves on the dev window and is not worse on val or test.
- stress: the backtest charges 5 bps beyond a stop; at a release real fills can be much worse, so every stop filled
  in a candle that held a release is also charged STRESS_BPS more, to see whether the conclusion survives.
- added after the first run, and said so in the report: (a) also needs at least MIN_REMOVED removed trades. That run
  "adopted" skipping Pyramid's entries before a release on 2 trades, where a bootstrap interval means nothing.

Same signals, execution and costs as the site's figures (backtest/figures.py): registry parameters, next-open fills,
gap-aware stops, Strike's taker fee, the 20 bps builder fee, funding.

Run: ``python -m smartflow.backtest.event_study`` (writes reports/event_study.md and .json).
"""

from __future__ import annotations

import datetime as dt
import json
import random
from dataclasses import replace
from pathlib import Path

from .. import strategies
from .account import agent_account, bar_closes
from .sim import CostModel, ExecModel
from .study import WINDOWS, evaluate

EVENTS_FILE = Path(__file__).resolve().parents[3] / "config" / "macro_events.json"
STRESS_BPS = 30.0        # extra cost of a stop filled in a candle with a release (6x the backtest's 5 bps)
RULES = {"ref": set(), "R1": {"pre"}, "R2": {"signal"}, "R3": {"pre", "signal"}}
MIN_REMOVED = 10         # fewer removed trades than this and "clearly worse" cannot be told from chance
SPLITS = ("dev", "val", "test")


def _ny_utc_offset_h(day: dt.date) -> int:
    """New York's offset from UTC that day: -4 from the second Sunday of March to the first Sunday of November (the
    US rule since 2007; every release is at 08:30 or 14:00, far from the 02:00 switch), -5 otherwise. No tz database
    needed (Windows has none)."""
    def sunday(month: int, nth: int) -> dt.date:
        d = dt.date(day.year, month, 1)
        return d + dt.timedelta(days=(6 - d.weekday()) % 7 + 7 * (nth - 1))
    return -4 if sunday(3, 2) <= day < sunday(11, 1) else -5


def load_events(path: Path = EVENTS_FILE) -> list[tuple[int, str]]:
    """Every release as (UTC ms, kind), sorted."""
    doc = json.loads(path.read_text(encoding="utf-8"))
    assert doc["timezone"] == "America/New_York", doc["timezone"]
    out = []
    for kind, days in doc["events"].items():
        hh, mm = map(int, doc["kinds"][kind]["time"].split(":"))
        for d in days:
            day = dt.date.fromisoformat(d)
            local = dt.datetime(day.year, day.month, day.day, hh, mm, tzinfo=dt.timezone(dt.timedelta(hours=_ny_utc_offset_h(day))))
            out.append((int(local.timestamp() * 1000), kind))
    return sorted(out)


def _any(events: list[tuple[int, str]], lo: int, hi: int) -> list[str]:
    return [k for t, k in events if lo <= t < hi]


def classify(t, events: list[tuple[int, str]], tf_ms: int) -> dict:
    end = (t.exit_time or t.entry_time) + tf_ms      # the exit candle's end (a stop is hit inside it)
    stop = t.reason.startswith(("stop", "chandelier stop"))
    return {
        "pre": _any(events, t.entry_time, t.entry_time + tf_ms),
        "signal": _any(events, t.entry_time - tf_ms, t.entry_time),
        "open": _any(events, t.entry_time + tf_ms, end),
        "stop_on_release": stop and bool(_any(events, t.exit_time, t.exit_time + tf_ms)),
    }


def _boot_mean(xs: list[float], n: int = 4000, seed: int = 7) -> tuple[float, float, float]:
    if not xs:
        return float("nan"), float("nan"), float("nan")
    rnd = random.Random(seed)
    means = sorted(sum(rnd.choices(xs, k=len(xs))) / len(xs) for _ in range(n))
    return sum(xs) / len(xs), means[int(0.025 * n)], means[int(0.975 * n)]


def _boot_diff(a: list[float], b: list[float], n: int = 4000, seed: int = 11) -> tuple[float, float, float]:
    """Mean(a) - mean(b) and its 95 % bootstrap interval."""
    if not a or not b:
        return float("nan"), float("nan"), float("nan")
    rnd = random.Random(seed)
    d = sorted(sum(rnd.choices(a, k=len(a))) / len(a) - sum(rnd.choices(b, k=len(b))) / len(b) for _ in range(n))
    return sum(a) / len(a) - sum(b) / len(b), d[int(0.025 * n)], d[int(0.975 * n)]


def stressed(t, flags: dict):
    if not flags["stop_on_release"]:
        return t
    return replace(t, r_gross=t.r_gross - STRESS_BPS / 1e4 * t.exit / t.risk)


def run_strategy(s: strategies.Strategy, events, root: Path, builder_bps: int = 20) -> dict:
    from ..live.fleet import DEFAULT_RISK, RISK
    symbols = tuple(m.replace("-USD", "USDT") for m in s.markets_core)
    tf_ms = int(s.timeframe) * 60_000
    cost = replace(CostModel(), builder_fee_bps=builder_bps)
    exe = ExecModel(policy=s.policy, max_stack=max(1, s.max_stack))
    risk = min(RISK[DEFAULT_RISK], RISK[s.max_risk])
    closes = bar_closes(root, symbols, s.timeframe)
    out: dict = {"strategy": s.id, "risk_pct": round(100 * risk, 2), "windows": {}}
    for wname in ("full", *SPLITS):
        w = WINDOWS[wname]
        _, _, trades = evaluate(root, symbols, s.timeframe, s.params, cost, exe, w, boot=False)
        ev = [e for e in events if w[0] - tf_ms <= e[0] < w[1] + tf_ms]
        flags = [classify(t, ev, tf_ms) for t in trades]
        res: dict = {"events": len([e for e in ev if w[0] <= e[0] < w[1]]), "trades": len(trades)}
        if wname == "full":
            groups = {}
            for g in ("pre", "signal", "open"):
                xs = [t.r for t, f in zip(trades, flags) if f[g]]
                groups[g] = _stats(xs)
            xs = [t.r for t, f in zip(trades, flags) if not (f["pre"] or f["signal"] or f["open"])]
            groups["clean"] = _stats(xs)
            groups["stop_on_release"] = sum(f["stop_on_release"] for f in flags)
            res["groups"] = groups
            res["by_kind"] = {k: _stats([t.r for t, f in zip(trades, flags) if k in f["pre"]]) for k in ("fomc", "cpi", "nfp")}
        for stress in (False, True):
            tt = [stressed(t, f) if stress else t for t, f in zip(trades, flags)]
            rules = {}
            for rname, skip in RULES.items():
                keep = [t for t, f in zip(tt, flags) if not any(f[g] for g in skip)]
                gone = [t for t, f in zip(tt, flags) if any(f[g] for g in skip)]
                acct = agent_account(keep, closes, risk, w, margin="fit")
                rules[rname] = {
                    "n": len(keep), "removed": len(gone),
                    "avg_r": _mean([t.r for t in keep]),
                    "removed_avg_r": _mean([t.r for t in gone]),
                    "diff": list(_boot_diff([t.r for t in gone], [t.r for t in keep])) if gone else None,
                    "cagr_pct": round(100 * acct.cagr, 1), "max_dd_pct": round(100 * acct.max_dd, 1),
                    "ratio": round(acct.cagr / acct.max_dd, 2) if acct.max_dd > 0 else None,
                }
            res["stressed" if stress else "plain"] = rules
        out["windows"][wname] = res
    out["verdict"] = {stress: {r: _verdict(out, r, stress) for r in RULES if r != "ref"} for stress in ("plain", "stressed")}
    return out


def _mean(xs: list[float]) -> float | None:
    return round(sum(xs) / len(xs), 3) if xs else None


def _stats(xs: list[float]) -> dict:
    m, lo, hi = _boot_mean(xs)
    return {"n": len(xs), "avg_r": round(m, 3) if xs else None, "ci95": [round(lo, 3), round(hi, 3)] if xs else None,
            "win_rate": round(sum(x > 0 for x in xs) / len(xs), 3) if xs else None}


def _verdict(out: dict, rule: str, mode: str) -> dict:
    """The pre-registered test: removed trades clearly worse (full window) and the account better on dev, not worse on
    val and test."""
    full = out["windows"]["full"][mode][rule]
    enough = full["removed"] >= MIN_REMOVED
    worse = enough and bool(full["diff"]) and full["diff"][2] < 0
    def better(w: str, strict: bool) -> bool:
        a, b = out["windows"][w][mode][rule]["ratio"], out["windows"][w][mode]["ref"]["ratio"]
        if a is None or b is None:
            return False
        return a > b if strict else a >= b - 0.02
    acct = better("dev", True) and better("val", False) and better("test", False)
    return {"removed": full["removed"], "enough_trades": enough, "removed_clearly_worse": worse, "account_better": acct,
            "adopt": worse and acct}


def report(results: list[dict]) -> str:
    L = ["# Scheduled macro releases and the strategies", "",
         f"Generated {dt.date.today().isoformat()} by `python -m smartflow.backtest.event_study`. Releases: Fed decisions (14:00 "
         "New York), US CPI and jobs reports (08:30 New York), official calendars in `config/macro_events.json`. "
         f"Stress: stops filled in a candle with a release cost {STRESS_BPS:g} bps more.", "",
         "Pre-registered: a rule is adopted only if the trades it removes are clearly worse (95 % interval of the difference "
         "of mean R below 0) and the account (yearly growth / drawdown) improves on dev and is not worse on val and test. "
         f"Added after the first run: it must also remove at least {MIN_REMOVED} trades (that run \"adopted\" a rule for Pyramid "
         "on 2 trades, where the interval means nothing).", "",
         "How to read it: trades that stayed open through a release look far better than the rest only because long trades "
         "are the ones that span releases, and long trades are this trend strategy's winners; it says nothing about the "
         "releases. Smart Flow opens almost nothing right before a release: the hours before one are quiet, and its "
         "breakout needs a wide candle on 1.5x volume.", ""]
    for r in results:
        f = r["windows"]["full"]
        L += [f"## {r['strategy']} (risk {r['risk_pct']} % per trade)", "",
              f"{f['events']} releases and {f['trades']} trades in 2022-01 → 2026-10; {f['groups']['stop_on_release']} stops filled in a candle with a release.", "",
              "| group | trades | mean R | 95 % interval | win rate |", "|---|---|---|---|---|"]
        names = {"pre": "opened right before a release", "signal": "signal candle held a release", "open": "a release while open", "clean": "none"}
        for g, n in names.items():
            x = f["groups"][g]
            L.append(f"| {n} | {x['n']} | {x['avg_r']} | {x['ci95']} | {x['win_rate']} |")
        L += ["", "Opened right before, by kind: " + ", ".join(f"{k} {v['n']} trades, mean {v['avg_r']} R" for k, v in f["by_kind"].items()), ""]
        for mode in ("plain", "stressed"):
            L += [f"### Rules, {'with the stress' if mode == 'stressed' else 'backtest costs'}", "",
                  "| rule | window | trades | removed | mean R kept | mean R removed | diff (95 %) | yearly | drawdown | ratio |", "|---|---|---|---|---|---|---|---|---|---|"]
            for rule in RULES:
                for w in ("full", *SPLITS):
                    x = r["windows"][w][mode][rule]
                    d = "" if not x["diff"] else f"{x['diff'][0]:+.2f} ({x['diff'][1]:+.2f} … {x['diff'][2]:+.2f})"
                    L.append(f"| {rule} | {w} | {x['n']} | {x['removed']} | {x['avg_r']} | {x['removed_avg_r']} | {d} | {x['cagr_pct']} % | {x['max_dd_pct']} % | {x['ratio']} |")
            v = r["verdict"][mode]
            L += ["", "Verdict: " + "; ".join(f"{k}: {x['removed']} removed{'' if x['enough_trades'] else ' (too few)'}, clearly worse {x['removed_clearly_worse']}, account better {x['account_better']} → **{'adopt' if x['adopt'] else 'no'}**" for k, x in v.items()), ""]
    return "\n".join(L) + "\n"


def main(root: Path = Path("data")) -> None:
    events = load_events()
    results = [run_strategy(s, events, root) for s in strategies.all_strategies() if s.runnable]
    Path("reports").mkdir(exist_ok=True)
    Path("reports/event_study.json").write_text(json.dumps(results, indent=1) + "\n", encoding="utf-8", newline="\n")
    Path("reports/event_study.md").write_text(report(results), encoding="utf-8", newline="\n")
    for r in results:
        print(r["strategy"], json.dumps(r["verdict"]))


if __name__ == "__main__":
    main()

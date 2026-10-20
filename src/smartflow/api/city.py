"""Strike City feed: public, read-only snapshots of the agents, built from their journals and state files.

The city page (``web/src/city``) renders these snapshots. Nothing here can place or change an order: it only reads
``runs/<agent>/journal.jsonl`` and ``runs/<agent>/state.json``. Only agents listed in ``config/city.toml`` with
``public = true`` are exposed, and only what the city shows: decisions, positions and closed trades. Exchange
responses, order ids and anything else in the journal stay out.

Decisions travel as ``code`` + ``args`` so the page can render them in each language; ``text`` keeps the engine's
own English sentence as a fallback.
"""

from __future__ import annotations

import json
import math
import re
import time
import tomllib
from dataclasses import dataclass
from pathlib import Path

from .. import ENGINE_VERSION
from ..core.timeframes import normalize, tf_ms

MAX_CHECKS = 64                  # latest routine checks kept (8 markets x 8 candles = 32 h on 4h)
MAX_EVENTS = 40                  # latest signals, risk rejections, orders, exits and alerts kept
MAX_TRADES = 200
STALE_GRACE_MS = 20 * 60_000     # an agent that missed its candle by this much is shown offline
ANALYSIS_WINDOW_MS = 3 * 60_000  # right after a candle close the agent is shown analysing
UNFUNDED_USD = 1.0               # a live account below this (and nothing open) is waiting for its first deposit

# The engine's reasons for "no signal" (core/engine.py BarState.why_no_signal) -> structured reasons.
_WHY = [
    (re.compile(r"no displacement: range (?P<range>[\d.]+) ATR \(min (?P<rmin>[\d.]+)\), body (?P<body>\d+)% of range "
                r"\(min (?P<bmin>\d+)%\)"), "disp"),
    (re.compile(r"no breakout: close inside the (?P<n>\d+)-candle range"), "inside"),
    (re.compile(r"breakout candle closes against its own direction"), "against_candle"),
    (re.compile(r"volume too low: x(?P<vol>[\d.]+|nan) of its 20-candle average \(min x(?P<vmin>[\d.]+)\)"), "volume"),
    (re.compile(r"(?P<side>buy|sell) setup against the bias"), "bias"),
    (re.compile(r"signal skipped: born inside a wide range \(last 100 candles span (?P<span>[\d.]+) ATR, filter "
                r"(?P<fmax>[\d.]+)\)"), "wide_range"),
    (re.compile(r"signal skipped: (?P<skip>.+)"), "skipped"),
    (re.compile(r"warming up"), "warmup"),
    (re.compile(r"no setup"), "none"),
]


def parse_why(why: list[str]) -> tuple[list[str], dict]:
    """Engine sentences -> (reason codes, numeric args). Unknown sentences become ``unknown`` (text kept by caller)."""
    reasons: list[str] = []
    args: dict = {}
    for s in why:
        for rx, code in _WHY:
            m = rx.search(s)
            if not m:
                continue
            g = {k: v for k, v in m.groupdict().items() if v is not None}
            if code == "disp":
                rng, rmin, body, bmin = float(g["range"]), float(g["rmin"]), int(g["body"]), int(g["bmin"])
                args.update(range=rng, rmin=rmin, body=body, bmin=bmin)
                short = [c for c, bad in (("range", rng < rmin), ("body", body < bmin)) if bad]
                reasons += short or ["range", "body"]   # rounding can hide which one failed
            elif code == "volume":   # "xnan" while the 20-candle average warms up
                args.update(vol=_num(g["vol"]), vmin=float(g["vmin"]))
                reasons.append(code)
            elif code == "inside":
                args["n"] = int(g["n"])
                reasons.append(code)
            elif code == "bias":
                args["side"] = "long" if g["side"] == "buy" else "short"
                reasons.append(code)
            elif code == "wide_range":
                args.update(span=float(g["span"]), fmax=float(g["fmax"]))
                reasons.append(code)
            elif code == "skipped":
                reasons.append(code)
            else:
                reasons.append(code)
            break
        else:
            reasons.append("unknown")
    return reasons, args


def _ms(iso: str) -> int:
    from datetime import datetime
    return int(datetime.fromisoformat(iso).timestamp() * 1000)


def _num(v) -> float | None:
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    return f if math.isfinite(f) else None


def _exit_kind(reason: str) -> str:
    r = (reason or "").lower()
    if r == "test finished":
        return "test"
    if "chandelier" in r:
        return "chandelier"
    if r == "stop" or "stop" in r and "no protection" not in r:
        return "stop"
    if "target" in r:
        return "target"
    if "trailing" in r or "channel" in r:
        return "trail"
    if "candle limit" in r:
        return "time"
    if "money-flow" in r or "flow" in r:
        return "flow"
    return "other"


@dataclass(frozen=True)
class CityAgent:
    """One public agent of the city (``config/city.toml``)."""
    id: str
    name: str
    config: Path
    run_dir: Path
    owner: str = "Smart Flow"
    look: dict | None = None      # character (web/src/city/look.ts validates it in the page)


def load_city(path: Path, root: Path = Path(".")) -> list[CityAgent]:
    raw = tomllib.loads(path.read_text(encoding="utf-8"))
    out = []
    for a in raw.get("agent", []):
        if not a.get("public", False):
            continue
        cfg = root / a["config"]
        name = tomllib.loads(cfg.read_text(encoding="utf-8")).get("name", a["id"])
        runs = root / a.get("runs_root", "runs")
        out.append(CityAgent(a["id"], a["name"], cfg, runs / name, a.get("owner", "Smart Flow"), a.get("look")))
    return out


def load_live(runs_root: Path, env: str) -> list[CityAgent]:
    """Users' agents trading their own Strike account (the fleet's registry). The site shows only the ones whose owner
    made them public, under the name and character the owner chose there."""
    try:
        reg = json.loads((runs_root / f"fleet-{env}.json").read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    out = []
    for uid, v in reg.items():
        run = runs_root / str(v.get("run", ""))
        if (run / "agent.toml").exists():
            out.append(CityAgent(uid, str(v.get("name", uid)), run / "agent.toml", run, "Strike user"))
    return out


def _read_jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    out = []
    with path.open(encoding="utf-8") as f:
        for ln in f:
            try:
                out.append(json.loads(ln))
            except json.JSONDecodeError:
                continue   # a line being written right now
    return out


def _variant(params: dict) -> str:
    """The script's parameters ("reference"), the official Smart Flow configuration ("official") or an experiment."""
    if not params:
        return "reference"
    from ..core.config import OFFICIAL, Params
    ref = Params().to_dict()
    return "official" if {k: v for k, v in OFFICIAL.to_dict().items() if v != ref[k]} == params else "experimental"


def snapshot(agent: CityAgent, now_ms: int | None = None, full: bool = False) -> dict:
    """Everything the city shows about one agent. ``full``: every closed trade, with the parameter fingerprint it
    was opened with (live/health.py), instead of the latest MAX_TRADES for the page."""
    now_ms = now_ms or int(time.time() * 1000)
    cfg = tomllib.loads(agent.config.read_text(encoding="utf-8"))
    tf = normalize(str(cfg.get("tf", "240")))
    tf_len = tf_ms(tf)
    markets = [m["strike"] for m in cfg.get("markets", [])]
    params = cfg.get("params", {})
    risk = cfg.get("risk", {})
    mode = cfg.get("mode", "analysis")
    recs = _read_jsonl(agent.run_dir / "journal.jsonl")
    state = json.loads((agent.run_dir / "state.json").read_text()) if (agent.run_dir / "state.json").exists() else {}

    decisions: list[dict] = []
    last_bar: dict[str, int] = {}
    latest_check: dict[str, dict] = {}
    trail: dict[str, float] = {}
    signals: dict[str, dict] = {}
    fills: dict[str, dict] = {}
    exit_px: dict[str, dict] = {}
    trades: list[dict] = []
    alerts: list[dict] = []
    first_ts = last_check = None
    seen_bars: set[tuple[str, int]] = set()
    agent_fills: dict[str, list[int]] = {}   # times the agent itself traded, per market
    test_fills: dict[str, list[int]] = {}    # of those, its test trades' (kept apart from the strategy's results)
    closed_later: list[tuple[str, dict, str, int]] = []   # exits journaled without a price (mainnet)

    def closed(tid: str, info: dict, reason: str, t: int) -> None:
        tr = _trade(tid, signals.get(tid), fills.get(tid), info, reason, t)
        if not tr:
            return
        test = bool((signals.get(tid) or {}).get("test"))
        if test:
            tr["test"] = True      # a test trade the owner asked for: marked as such
        tr["params"] = (fills.get(tid) or {}).get("params")
        trades.append(tr)
        agent_fills.setdefault(tr["market"], []).append(t)
        if test:
            test_fills.setdefault(tr["market"], []).append(t)
        decisions.append({"time": t, "market": tr["market"], "kind": "exit", "code": "test_close" if test else "close",
                          "args": {"side": tr["side"], "r": tr["r"], "reason": tr["reason"], "price": tr["exit"]}})

    for r in recs:
        if "ts" not in r:
            continue
        t = _ms(r["ts"])
        first_ts = first_ts or t
        kind, mkt = r.get("kind"), r.get("market", "")
        if kind == "analysis":
            bar = int(r.get("bar", 0))
            ot = r.get("open_trade") or {}
            if _num(ot.get("exit_if_close_beyond")) is not None:
                trail[mkt] = float(ot["exit_if_close_beyond"])
            else:
                trail.pop(mkt, None)
            if (mkt, bar) in seen_bars:   # a restart re-journals the last bar: not a new check
                continue
            seen_bars.add((mkt, bar))
            last_check = t
            last_bar[mkt] = max(last_bar.get(mkt, 0), bar)
            if int(r.get("sig_dir") or 0) != 0:
                continue                  # the signal record that follows tells this bar's story
            why = r.get("why") or []
            reasons, args = parse_why(why)
            args.update(r=",".join(reasons), close=_num(r.get("close")))
            d = {"time": t, "market": mkt, "kind": "analysis", "code": "check", "args": args,
                 "text": "; ".join(why), "bar": bar}
            decisions.append(d)
            latest_check[mkt] = d
        elif kind == "signal" and r.get("trade_id") and r.get("test"):
            signals[r["trade_id"]] = r      # a test trade the owner asked for: not a strategy signal
        elif kind == "signal" and r.get("trade_id"):
            signals[r["trade_id"]] = r
            decisions.append({"time": t, "market": mkt, "kind": "signal", "code": "signal",
                              "args": {"side": "long" if r.get("dir") == 1 else "short", "price": _num(r.get("close")),
                                       "vol": _num(r.get("rel_vol")), "stop": _num(r.get("stop"))}})
        elif kind == "signal":
            decisions.append({"time": t, "market": mkt, "kind": "risk", "code": "not_traded",
                              "args": {"side": "long" if r.get("dir") == 1 else "short"},
                              "text": r.get("reason", "")})
        elif kind == "decision" and r.get("accepted") is False:
            reasons = r.get("reasons") or []
            sig = signals.get(r.get("trade_id", ""), {})
            code, args = "risk_other", {}
            txt = "; ".join(reasons)
            if "no equity" in txt:   # an empty account: not a loss limit (agent/risk.py stops there)
                code = "risk_balance"
            elif "strategy on hold" in txt:
                code = "risk_hold"
            elif m := re.search(r"spread ([\d.]+) ?bps", txt):
                code, args = "risk_spread", {"bps": float(m.group(1))}
            elif "daily loss" in txt:
                code = "risk_daily"
            elif "weekly loss" in txt:
                code = "risk_weekly"
            elif "position" in txt and "open" in txt:
                code = "risk_open"
            elif "not filled" in txt:
                code = "not_filled"
            elif m := re.search(r"notional \$([\d.]+) below market minimum \$([\d.]+)", txt):
                code, args = "risk_min", {"notional": float(m.group(1)), "min": float(m.group(2))}
            elif "below market minimum" in txt:
                code = "risk_min"
            decisions.append({"time": t, "market": sig.get("market", mkt), "kind": "risk", "code": code,
                              "args": args, "text": txt})
        elif kind == "fill":
            fills[r["trade_id"]] = r
            trail.pop(mkt, None)          # a new trade: the previous one's exit level no longer applies
            sig = signals.get(r["trade_id"], {})
            agent_fills.setdefault(mkt, []).append(t)
            if sig.get("test"):
                test_fills.setdefault(mkt, []).append(t)
            decisions.append({"time": t, "market": mkt, "kind": "order", "code": "test_open" if sig.get("test") else "open",
                              "args": {"side": "long" if (_num(r.get("qty")) or 0) > 0 else "short",
                                       "price": _num(r.get("entry")), "stop": _num(sig.get("stop"))}})
        elif kind in ("paper_order", "live_order") and r.get("action") == "exit":
            tid = r.get("trade_id", "")
            om = mkt or (fills.get(tid) or signals.get(tid) or {}).get("market", "")
            agent_fills.setdefault(om, []).append(t)
            if (signals.get(tid) or {}).get("test"):
                test_fills.setdefault(om, []).append(t)
            resp = r.get("response") or {}
            if isinstance(resp, dict) and _num(resp.get("price")) is not None:
                exit_px[r["trade_id"]] = resp
        elif kind == "exit":
            tid = r.get("trade_id", "")
            info = {**exit_px.get(tid, {}), **{k: r[k] for k in ("price", "pnl", "fees") if k in r}}
            if _num(info.get("price")) is None:
                closed_later.append((tid, info, r.get("reason", ""), t))   # mainnet: priced from the account's fills
                continue
            closed(tid, info, r.get("reason", ""), t)
        elif kind == "alert" and r.get("code") in ("test_funds", "test_busy"):
            # the owner's test trade could not run: why, in the owner's language (not an operational alert)
            decisions.append({"time": t, "market": mkt, "kind": "alert", "code": r["code"],
                              "args": {k: _num(r.get(k)) for k in ("needs", "available") if _num(r.get(k)) is not None},
                              "text": str(r.get("message", ""))[:200]})
        elif kind == "alert" and r.get("level") in ("warning", "error", "critical"):
            a = {"time": t, "level": r["level"], "message": str(r.get("message", ""))[:200]}
            alerts.append(a)
            decisions.append({"time": t, "market": mkt or (r.get("market") or ""), "kind": "alert", "code": "alert",
                              "args": {"level": r["level"]}, "text": a["message"]})

    positions = _positions(state, signals, trail)
    try:   # a user's live agent: its real Strike account (positions of any origin, e.g. opened by hand)
        acct = json.loads((agent.run_dir / "account.json").read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        acct = None
    # Strike mainnet does not return completed orders: an exit the journal has without a price takes it (and its
    # fees and P&L) from the account's own fills that closed it
    used: set[int] = set()
    for tid, info, reason, t in closed_later:
        sig, fill = signals.get(tid) or {}, fills.get(tid) or {}
        if acct and fill:
            got = _closing_fills(acct.get("fills", []), sig.get("market") or fill.get("market", ""), 1 if sig.get("dir") == 1 else -1,
                                 abs(_num(fill.get("qty")) or 0), _ms(fill["ts"]), t, used)
            if got:
                info = {**info, **got}
                times = got.pop("times")
                agent_fills.setdefault(sig.get("market") or fill.get("market", ""), []).extend(times)
                if sig.get("test"):
                    test_fills.setdefault(sig.get("market") or fill.get("market", ""), []).extend(times)
        closed(tid, info, reason, t)
    trades.sort(key=lambda x: x["time"])
    if acct:
        # executions on the owner's account that the agent did not make (by hand, another app): in its activity too,
        # from the moment the agent started (older ones are the account's own past, not this agent's)
        for f in acct.get("fills", [])[:30]:
            ft, fm = _num(f.get("time")), f.get("market", "")
            if ft is None or (first_ts and ft < first_ts) or _by_agent(f, agent_fills):
                continue
            decisions.append({"time": int(ft), "market": fm, "kind": "account", "code": "account_fill",
                              "args": {"side": "buy" if f.get("side") == "buy" else "sell", "price": _num(f.get("price"))}})
        own = {p["market"]: p for p in positions}
        positions = [{"stop": None, "trail": None, "openedAt": _num(x.get("openedAt")), "id": None, **own.get(x["market"], {}),
                      "market": x["market"], "side": x["side"], "entry": _num(x.get("entry")), "qty": _num(x.get("size")),
                      "upnl": _num(x.get("upnl"))} for x in acct.get("positions", [])]
    stale = last_check is None or now_ms - last_check > tf_len + STALE_GRACE_MS
    if stale:
        status = "offline"
    elif positions:
        status = "in_trade"
    elif acct and not acct.get("orders") and (_num(acct.get("equity")) or 0) < UNFUNDED_USD:
        status = "unfunded"
    elif now_ms - last_check < ANALYSIS_WINDOW_MS:
        status = "analyzing"
    else:
        status = "waiting"
    paper = state.get("_paper") or {}
    equity0 = _num(paper.get("equity0")) or _num(cfg.get("paper_equity"))
    cash = _num(paper.get("cash"))
    if acct:   # measured on the starting balance plus what was deposited since, never counting deposits as gains
        base, flows = _base(acct)
        equity0, cash = (base or None), _num(acct.get("equity"))
    # routine checks (8 markets every candle) must not push signals, orders and exits out of the activity log
    decisions.sort(key=lambda d: d["time"], reverse=True)
    routine = [d for d in decisions if d["kind"] == "analysis"][:MAX_CHECKS]
    events = [d for d in decisions if d["kind"] != "analysis"][:MAX_EVENTS]
    decisions = sorted(routine + events, key=lambda d: d["time"], reverse=True)
    for d in decisions:
        d.pop("bar", None)
    own = [r for r in recs[-50:] if "engine" in r] or [{}]   # the agent's own records (the fleet's carry no engine)
    out = {
        "id": agent.id, "name": agent.name, "owner": agent.owner, "look": agent.look,
        "kind": "paper" if mode == "simulation" else "live" if mode in ("confirmation", "autonomous") else "analysis",
        "env": cfg.get("env", "testnet"), "tf": tf, "engine": own[-1].get("engine", ENGINE_VERSION),
        "params": own[-1].get("params", ""),
        "variant": _variant(params), "changes": sorted(params) if _variant(params) == "experimental" else [],
        "strategy": "pyramid" if cfg.get("policy") == "pyramid" else "smartflow",
        "markets": markets, "riskPct": 100 * float(risk.get("risk_per_trade", 0.005)),
        "feeBps": int(cfg.get("builder_fee_bps", 0)),
        "equity0": equity0, "cash": cash,
        "since": first_ts, "lastCheck": last_check,
        "nextCheck": (now_ms // tf_len + 1) * tf_len + 15_000,
        "status": status, "alerts": alerts[-5:][::-1],
        "positions": positions,
        "trades": (trades if full else [{k: v for k, v in x.items() if k != "params"} for x in trades[-MAX_TRADES:]])[::-1],
        # the counts over every trade, also the ones older than the list above (tests never count)
        "tally": _tally([x for x in trades if not x.get("test")]),
        "checks": {m: {"time": d["time"], "args": d["args"], "text": d["text"]} for m, d in latest_check.items()},
        "decisions": decisions,
    }
    if acct:
        out["portfolio"] = _portfolio(acct, positions, int(cfg.get("builder_fee_bps", 0)), first_ts, agent_fills, test_fills)
        out["result"] = round(cash - (_num(acct.get("first_balance")) or 0) - flows, 6) if cash is not None else None
    return out


def _base(acct: dict) -> tuple[float, float]:
    """(what a live account's result is measured on: its starting balance plus the money deposited since; the net
    money moved in since the start, which the result leaves out). fleet.account_flows keeps the transfers."""
    start = _num(acct.get("first_balance")) or 0.0
    return round(start + (_num(acct.get("inflows")) or 0.0), 6), _num(acct.get("flows")) or 0.0


def _tally(trades: list[dict]) -> dict:
    """Win/loss counts in R over every closed trade (the page shows them; the trade list it gets is capped)."""
    rs = [float(t["r"]) for t in trades if _num(t.get("r")) is not None]
    won = sum(r for r in rs if r > 0)
    return {"n": len(rs), "wins": sum(1 for r in rs if r > 0), "won": round(won, 4), "lost": round(won - sum(rs), 4),
            "best": round(max(rs), 4) if rs else 0.0}


def _closing_fills(acct_fills: list[dict], market: str, d: int, qty: float, entry_ms: int, exit_ms: int,
                   used: set[int]) -> dict | None:
    """The account fills that closed a trade: on the closing side, between its entry and shortly after the agent
    closed it (a stop fills before the agent notices, a market exit just after), the latest first, up to its size.
    The entry's own fills add their fees, so the result is net of both."""
    side = "sell" if d == 1 else "buy"
    t_of = lambda f: _num(f.get("time")) or 0
    cands = sorted((f for f in acct_fills if f.get("market") == market and f.get("side") == side and id(f) not in used
                    and entry_ms - 60_000 <= t_of(f) <= exit_ms + 120_000), key=t_of, reverse=True)
    got = notional = fees = pnl = 0.0
    times = []
    for f in cands:
        if qty and got >= qty * (1 - 1e-9):
            break
        size = abs(_num(f.get("size")) or 0)
        take = min(size, qty - got) if qty else size
        if take <= 0:
            continue
        share = take / size
        got += take
        notional += take * (_num(f.get("price")) or 0)
        fees += (_num(f.get("fee")) or 0) * share
        pnl += (_num(f.get("pnl")) or 0) * share
        used.add(id(f))
        times.append(int(t_of(f)))
    if got <= 0:
        return None
    opening = "buy" if d == 1 else "sell"
    fees += sum(_num(f.get("fee")) or 0 for f in acct_fills if f.get("market") == market and f.get("side") == opening
                and abs(t_of(f) - entry_ms) <= 30_000)
    return {"price": notional / got, "pnl": pnl, "fees": fees, "times": times}


def _by_agent(f: dict, agent_fills: dict[str, list[int]]) -> bool:
    ft = _num(f.get("time"))
    return ft is not None and any(abs(ft - x) < 30_000 for x in agent_fills.get(f.get("market", ""), []))


def _portfolio(acct: dict, positions: list[dict], fee_bps: int, since: int | None = None,
               agent_fills: dict[str, list[int]] | None = None, test_fills: dict[str, list[int]] | None = None) -> dict:
    """The live account in full. The site shows the amounts only to its owner (everyone else sees percentages).
    Executions and fees count from the moment the agent started; the builder fee only on the agent's own fills."""
    stops = {p["market"]: p.get("stop") for p in positions}
    mine = [f for f in acct.get("fills", []) if since is None or (_num(f.get("time")) or 0) >= since]
    fills = mine[:30]
    ours = [f for f in mine if _by_agent(f, agent_fills or {})]
    tests = [f for f in ours if _by_agent(f, test_fills or {})]
    net = lambda fs: round(sum((_num(f.get("pnl")) or 0) - (_num(f.get("fee")) or 0) for f in fs), 6)
    hist = acct.get("history", [])
    step = max(1, len(hist) // 120)   # at most ~120 points on the chart
    base, flows = _base(acct)
    return {
        "time": _num(acct.get("time")), "start": _num(acct.get("first_balance")), "equity": _num(acct.get("equity")),
        # deposits, withdrawals and transfers since it started: net (left out of the result) and gross in (its base)
        "flows": flows, "inflows": _num(acct.get("inflows")) or 0.0, "base": base,
        "balance": _num(acct.get("balance")), "available": _num(acct.get("available")), "upnl": _num(acct.get("upnl")),
        "margin": _num(acct.get("margin")),
        "positions": [{**{k: x.get(k) for k in ("market", "side", "size", "entry", "mark", "upnl", "lev", "liq", "funding", "margin", "openedAt")},
                       "stop": stops.get(x.get("market"))} for x in acct.get("positions", [])],
        "orders": [{k: o.get(k) for k in ("market", "side", "type", "size", "price", "stop", "reduceOnly", "status")} for o in acct.get("orders", [])],
        "fills": [{**{k: f.get(k) for k in ("time", "market", "side", "price", "size", "fee", "pnl", "role")},
                   "agent": _by_agent(f, agent_fills or {}), "test": _by_agent(f, test_fills or {})} for f in fills],
        # where the result since connecting comes from (the rest: builder rewards, funding, deposits, withdrawals)
        "realized": round(sum(_num(f.get("pnl")) or 0 for f in mine), 6),
        # the same, net of fees, split: the strategy's trades, the owner's test trades, trades made outside the agent
        "split": {"strategy": net([f for f in ours if f not in tests]), "test": net(tests), "outside": net([f for f in mine if f not in ours])},
        "fees": {"trading": round(sum(_num(f.get("fee")) or 0 for f in mine), 6),
                 "builder": round(sum((_num(f.get("price")) or 0) * (_num(f.get("size")) or 0) for f in ours) * fee_bps / 1e4, 6),
                 "builderBps": fee_bps},
        "history": (hist[::step] + ([hist[-1]] if hist and (len(hist) - 1) % step else []))[-121:],
    }


def _trade(tid: str, sig: dict | None, fill: dict | None, info: dict, reason: str, t: int) -> dict | None:
    """A closed trade in R: (exit - entry) * dir / |entry - stop|, net of the fees the account paid."""
    if not sig or not fill:
        return None
    entry, stop, px = _num(fill.get("entry")), _num(sig.get("stop")), _num(info.get("price"))
    qty = abs(_num(fill.get("qty")) or 0)
    if entry is None or stop is None or px is None or entry == stop:
        return None
    d = 1 if sig.get("dir") == 1 else -1
    dist = abs(entry - stop)
    r_gross = (px - entry) * d / dist
    pnl, fees = _num(info.get("pnl")), _num(info.get("fees"))
    r_net = (pnl - fees) / (qty * dist) if pnl is not None and fees is not None and qty else r_gross
    return {"id": tid, "market": sig.get("market", ""), "side": "long" if d == 1 else "short", "entry": entry,
            "exit": px, "stop": stop, "r": round(r_net, 3), "rGross": round(r_gross, 3), "qty": qty,
            "pnl": round(pnl - fees, 6) if pnl is not None and fees is not None else None,   # net, in the account's money
            # the same over the position's size (shows no amount, so the public city gets it too)
            "pnlPct": round((pnl - fees) / (entry * qty), 6) if pnl is not None and fees is not None and qty else None,
            "reason": _exit_kind(info.get("reason") or reason), "openedAt": _ms(fill["ts"]), "time": t}


def _positions(state: dict, signals: dict, trail: dict) -> list[dict]:
    out = []
    for mkt, v in state.items():
        if mkt.startswith("_") or not isinstance(v, dict):
            continue
        # every open trade of the market (pyramid: several in one direction), or the single one of older states
        for tr in v.get("trades") if v.get("trades") is not None else ([v["trade"]] if v.get("trade") else []):
            p = _position(mkt, tr, trail)
            if p:
                out.append(p)
    return out


def _position(mkt: str, tr: dict, trail: dict) -> dict | None:
    """One open trade as the city shows it (None while it is not a position yet)."""
    if not tr or tr.get("state") not in ("position_open", "protected", "exit_requested", "partially_filled"):
        return None
    data = tr.get("data", {})
    entry, stop = _num(data.get("entry")), _num(data.get("stop"))
    if entry is None or stop is None:
        return None
    return {"market": mkt, "side": "long" if tr.get("dir") == 1 else "short", "entry": entry, "stop": stop,
            "trail": trail.get(mkt, stop), "qty": _num(data.get("qty")),
            "openedAt": int(1000 * (_num(data.get("filled_at")) or 0)) or None, "id": tr.get("trade_id")}


def _clean(v):
    """JSON for browsers: NaN / inf (an indicator still warming up) become null."""
    if isinstance(v, float):
        return v if math.isfinite(v) else None
    if isinstance(v, dict):
        return {k: _clean(x) for k, x in v.items()}
    if isinstance(v, list):
        return [_clean(x) for x in v]
    return v


def build(agents: list[CityAgent], now_ms: int | None = None) -> dict:
    now_ms = now_ms or int(time.time() * 1000)
    snaps = []
    for a in agents:
        try:
            snaps.append(snapshot(a, now_ms))
        except Exception as e:   # one broken run dir must not take the city down
            snaps.append({"id": a.id, "name": a.name, "status": "offline", "error": type(e).__name__})
    return _clean({"generated": now_ms, "engine": ENGINE_VERSION, "agents": snaps})

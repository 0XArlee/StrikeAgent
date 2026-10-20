"""Users' agents trading on their own Strike accounts (builder connect), run on the agents' host.

Every minute the fleet pulls the links from the site (``GET /api/internal/live``, HMAC signed), keeps the key pool
topped up and offers its fresh public keys (``POST /api/internal/keys``), and starts or stops one agent thread per
link. Each agent is the standard Smart Flow agent with the official parameters, on the user's markets and risk,
signing with the user's API wallet from the key pool and sending ``X-Builder-Fee-Bps`` on every order. Mainnet stays
off unless ``allow_mainnet`` is passed explicitly; autonomous orders also need SMARTFLOW_LIVE_ACK (agent/config.py).
"""

from __future__ import annotations

import hashlib
import hmac
import json
import threading
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

from ..agent.config import AgentConfig, MarketMap
from ..agent.journal import redact
from ..audit import AuditLog
from ..core.config import OFFICIAL, Params
from ..agent.risk import RiskConfig
from .keypool import KeyPool

UA = "smartflow-fleet/1.0"
HISTORY_EVERY_MS, HISTORY_POINTS = 5 * 60_000, 7 * 24 * 12
ACCOUNT_EVERY_S = 60        # an account with positions or orders is read every minute
ACCOUNT_IDLE_EVERY_S = 180  # one with nothing open every 3 minutes; any account right after its agent acts
FILLS_KEPT = 5000   # Strike returns the latest 50: the file keeps every one seen, so totals since connecting stay whole
TRANSFERS_KEPT = 500
FLOWS_V = 2   # how account.json keeps its transfers: an older file has its "base" marks worked out again
WEB_AUDIT_EVERY_S = 60      # the site's record of what owners signed, copied here every minute
RISK = {"conservative": 0.0025, "standard": 0.005, "assertive": 0.01}


def _sig(secret: str, ts: str, payload: str) -> str:
    return hmac.new(secret.encode(), f"{ts}.{payload}".encode(), hashlib.sha256).hexdigest()


class Site:
    """The two host endpoints of the Strike City site."""

    def __init__(self, base: str, secret: str, timeout: float = 20):
        self.base, self.secret, self.timeout = base.rstrip("/"), secret, timeout

    def _req(self, method: str, path: str, body: bytes | None, payload: str) -> dict:
        ts = str(int(time.time() * 1000))
        req = urllib.request.Request(self.base + path, data=body, method=method, headers={
            "Content-Type": "application/json", "User-Agent": UA, "X-SF-Time": ts, "X-SF-Signature": _sig(self.secret, ts, payload)})
        with urllib.request.urlopen(req, timeout=self.timeout) as r:
            return json.loads(r.read() or b"{}")

    def links(self) -> dict:
        return self._req("GET", "/api/internal/live", None, "GET /api/internal/live")

    def offer(self, env: str, free: list[str]) -> dict:
        raw = json.dumps({"env": env, "free": free}, separators=(",", ":"))
        return self._req("POST", "/api/internal/keys", raw.encode(), raw)

    def audit(self, after: int) -> dict:
        path = f"/api/internal/audit?after={int(after)}"
        return self._req("GET", path, None, f"GET {path}")

    def anchors(self, files: list[str]) -> dict:
        """The heads of these audit files the site kept: {"anchors": {file: [[seq, hash], ...]}}."""
        raw = json.dumps({"files": files}, separators=(",", ":"))
        return self._req("POST", "/api/internal/heads", raw.encode(), raw)


def _f(v) -> float | None:
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def read_account(env: str, signer) -> dict:
    """The user's Strike account as the city shows it: balances, every open position (whoever opened it), the orders
    waiting on the book (stops) and the latest fills."""
    from ..strike.client import MAINNET, TESTNET, StrikeClient
    c = StrikeClient(TESTNET if env == "testnet" else MAINNET, signer)
    c.sync_clock()
    a = c.account()
    positions = []
    for p in c.positions():
        if not p.size:
            continue
        size = abs(p.size)
        positions.append({"market": p.symbol, "side": "long" if p.size > 0 else "short", "size": size, "entry": p.entry_price,
                          "upnl": p.upnl, "mark": p.entry_price + p.upnl / (size if p.size > 0 else -size),
                          "lev": p.leverage, "liq": p.liquidation_price or None, "funding": p.funding_fees,
                          "margin": _f(p.raw.get("maintenance_margin")), "openedAt": p.raw.get("create_timestamp")})
    orders = [{"market": o.symbol, "side": o.side, "type": o.type, "size": o.size, "price": o.price or None,
               "stop": o.stop_price or None, "reduceOnly": o.reduce_only, "status": o.status} for o in c.open_orders()]
    fills = [{"time": f.timestamp, "market": f.symbol, "side": f.side, "price": f.price, "size": f.size, "fee": f.fee,
              "pnl": f.realized_pnl, "role": f.role, "id": f.trade_id, "order": f.order_id} for f in c.fills(limit=50)]
    try:   # deposits, withdrawals and transfers: never counted as the agent's result (None: unknown this time)
        transfers = [{"id": t.id, "type": t.type, "amount": t.amount, "status": t.status, "time": t.timestamp}
                     for t in c.transfers()]
    except Exception:
        transfers = None
    return {"balance": a.wallet_balance, "equity": a.margin_balance, "available": a.available_balance,
            "upnl": a.unrealized_pnl, "margin": a.maintenance_margin, "positions": positions, "orders": orders, "fills": fills,
            "transfers": transfers}


def account_flows(kept: list[dict] | None, transfers: list[dict] | None, first_time: int, first_reading: bool) -> list[dict]:
    """The account's deposits, withdrawals and transfers, each marked ``base`` when the starting balance
    (``first_balance``, read at ``first_time``) already held it: only the others move the money the result is
    measured on. A transfer still pending at the first reading counts once it settles.

    ``kept``: the transfers this file already tracks (None: not tracked yet: the account's first reading, or an
    account read before transfers were kept, whose marks come from the time of its first reading)."""
    from ..strike.models import TX_DONE
    known = {str(t.get("id")): t for t in kept or []}
    if transfers is None:
        return list(known.values())
    for t in transfers:
        k = str(t.get("id"))
        if kept is not None and k in known:
            known[k] = {**t, "base": known[k].get("base", False)}
            continue
        done = str(t.get("status")) in TX_DONE
        base = done and (first_reading or (kept is None and int(t.get("time") or 0) < first_time))
        known[k] = {**t, "base": base}
    return sorted(known.values(), key=lambda t: -(int(t.get("time") or 0)))[:TRANSFERS_KEPT]


def net_flows(transfers: list[dict]) -> tuple[float, float]:
    """(net money moved in since the start, gross money moved in): what the result leaves out, and what it is
    measured on beside the starting balance."""
    from ..strike.models import TX_DONE
    live = [float(t.get("amount") or 0) for t in transfers if not t.get("base") and str(t.get("status")) in TX_DONE]
    return round(sum(live), 6), round(sum(a for a in live if a > 0), 6)


def agent_config(link: dict, env: str, code: str, fee_bps: int, venue_markets: set[str], runs_root: str, data_root: str,
                 allow_mainnet: bool = False) -> AgentConfig:
    """The official Smart Flow agent for one user, with the strategy they picked (only the markets this venue lists):
    the same official parameters for everyone, in both strategies (core.config.OFFICIAL)."""
    markets = [MarketMap(m, m.replace("-USD", "USDT")) for m in link["markets"] if m in venue_markets]
    pyramid = link.get("strategy") == "pyramid"
    return AgentConfig(
        name=f"live-{link['userId']}", mode="autonomous", env=env, tf="240", markets=markets, params=OFFICIAL,
        policy="pyramid" if pyramid else "single", max_stack=3,
        risk=RiskConfig(risk_per_trade=RISK.get(link.get("risk", "standard"), 0.005),
                        max_open_positions=24 if pyramid else 8),
        builder_code=code, builder_fee_bps=fee_bps, builder_fee_approved_bps=link.get("feeBps", fee_bps),
        allow_autonomous=True, allow_mainnet=allow_mainnet and env == "mainnet", runs_root=runs_root, data_root=data_root)


def params_toml(p: Params) -> str:
    """The parameters that differ from the script's, as TOML lines (what the city and the agent read back)."""
    ref, out = Params().to_dict(), ""
    for k, v in p.to_dict().items():
        if v != ref[k]:
            out += f"{k} = {str(v).lower() if isinstance(v, bool) else repr(v) if isinstance(v, str) else v}\n"
    return out


def write_toml(cfg: AgentConfig, path: Path) -> None:
    """What the city needs to describe the agent (api/city.py reads this, like config/paper-*.toml)."""
    mk = ", ".join(f'{{ strike = "{m.strike}", signal = "{m.signal}" }}' for m in cfg.markets)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(f'# generated by the fleet\nname = "{cfg.name}"\nmode = "{cfg.mode}"\nenv = "{cfg.env}"\ntf = "{cfg.tf}"\n'
                    f'markets = [{mk}]\nbuilder_fee_bps = {cfg.builder_fee_bps}\npolicy = "{cfg.policy}"\nmax_stack = {cfg.max_stack}\n'
                    f'[params]\n{params_toml(cfg.params)}[risk]\n'
                    f'risk_per_trade = {cfg.risk.risk_per_trade}\nmax_open_positions = {cfg.risk.max_open_positions}\n', encoding="utf-8")


@dataclass
class Running:
    pub: str
    stop: threading.Event
    thread: threading.Thread
    strategy: str = "smartflow"
    key: tuple = ()           # what the agent was started with: a change restarts it
    test_seen: int = 0        # the owner's latest test-trade request already handed to the agent
    started: float = field(default_factory=time.time)


def _key(link: dict) -> tuple:
    return (link.get("strategy", "smartflow"), tuple(link.get("markets", [])), link.get("risk", "standard"))


class Fleet:
    def __init__(self, site: Site, pool: KeyPool, venue_markets: Callable[[], set[str]], runs_root: str, data_root: str,
                 start_agent: Callable[[AgentConfig, object, threading.Event, Callable[[str], None]], None] | None = None,
                 allow_mainnet: bool = False, log: Callable[[str], None] = print, min_free_keys: int = 3,
                 account_reader: Callable[[str, object], dict] | None = None):
        self.site, self.pool, self.venue_markets = site, pool, venue_markets
        self.runs_root, self.data_root, self.allow_mainnet, self.log = runs_root, data_root, allow_mainnet, log
        self.start_agent = start_agent or _run_agent
        self.min_free = min_free_keys
        self.account_reader = account_reader   # read_account in production; None: the city gets the journal only
        self._acct_at: dict[str, float] = {}     # when each account was last read
        self._acct_busy: dict[str, bool] = {}    # whether it had positions or orders then
        self._offered: tuple = ((), 0.0)         # keys last offered to the site, and when
        self._venue: tuple = (set(), 0.0)        # markets listed on the venue, and when they were read
        self._web_at, self._web_after = 0.0, None   # the site's audit rows: when last copied, and the last id copied
        self._skipped: set[str] = set()           # users whose markets the venue does not list (said once)
        self.running: dict[str, Running] = {}
        self.registry = Path(runs_root) / f"fleet-{pool.env}.json"   # one fleet per network (testnet, mainnet)

    def tick(self) -> dict:
        doc = self.site.links()
        env = doc["env"]
        if env != self.pool.env:
            raise RuntimeError(f"the site trades on {env} but this key pool is {self.pool.env}")
        if env == "mainnet" and not self.allow_mainnet:
            raise PermissionError("mainnet links but the fleet was not started with allow_mainnet")
        free = self.pool.ensure(set(doc.get("used", [])), self.min_free)
        if tuple(sorted(free)) != self._offered[0] or time.time() - self._offered[1] >= 60:   # no POST every turn
            self.site.offer(env, free)
            self._offered = (tuple(sorted(free)), time.time())
        want = {l["userId"]: l for l in doc.get("links", []) if l.get("status") == "active" and doc.get("builderCode")}
        # a new key, strategy, markets or risk restarts the user's agent with them
        for uid in [u for u in self.running if u not in want or want[u]["pub"] != self.running[u].pub
                    or _key(want[u]) != self.running[u].key]:
            self.log(f"stop {uid}")
            r = self.running.pop(uid)
            why = ("the owner stopped, paused or deleted it on the site" if uid not in want
                   else "a new API wallet was linked" if want[uid]["pub"] != r.pub else "the owner changed its settings")
            r.stop.set()
            r.thread.join(90)   # never two agents on one account, even for a moment
            self._host(uid, "stop", reason=why, stopped=not r.thread.is_alive())
        for uid, l in want.items():
            if uid in self.running and self.running[uid].thread.is_alive():
                continue
            if time.time() - self._venue[1] >= 600:   # the venue's markets, read when an agent starts (10 min cache)
                self._venue = (self.venue_markets(), time.time())
            venue = self._venue[0]
            cfg = agent_config(l, env, doc["builderCode"], int(doc["feeBps"]), venue, self.runs_root, self.data_root, self.allow_mainnet)
            if not cfg.markets:
                self.log(f"skip {uid}: none of its markets is listed on Strike {env}")
                if uid not in self._skipped:
                    self._skipped.add(uid)
                    self._host(uid, "skip", reason=f"none of its markets is listed on Strike {env}", markets=l.get("markets"))
                continue
            self._skipped.discard(uid)
            write_toml(cfg, Path(self.runs_root) / cfg.name / "agent.toml")
            stop = threading.Event()
            signer = self.pool.signer(l["pub"])
            t = threading.Thread(target=self.start_agent, args=(cfg, signer, stop, self.log), name=cfg.name, daemon=True)
            self.running[uid] = Running(l["pub"], stop, t, l.get("strategy", "smartflow"), _key(l))
            self._host(uid, "start", env=env, link={k: l.get(k) for k in ("name", "strategy", "markets", "risk", "accountId", "pub",
                                                                         "feeBps", "status", "testAt")},
                       builder_code=doc["builderCode"], fee_bps=int(doc["feeBps"]), markets_run=[m.strike for m in cfg.markets],
                       risk_per_trade=cfg.risk.risk_per_trade)
            t.start()
            self.log(f"start {uid} on {env}: {', '.join(m.strike for m in cfg.markets)}, risk {cfg.risk.risk_per_trade:.2%}")
        for uid in [u for u in self.running if u in want]:
            self._test_request(uid, want[uid])
            if self._account_due(uid):
                self._account(uid, env, self.running[uid].pub)
        self._copy_web_audit(env)
        # who runs, for the city push (names come from the site, never the wallet address)
        self.registry.parent.mkdir(parents=True, exist_ok=True)
        self.registry.write_text(json.dumps({uid: {"name": want[uid]["name"], "run": f"live-{uid}"} for uid in self.running if uid in want}),
                                 encoding="utf-8")
        return {"env": env, "running": sorted(self.running), "free_keys": len(free)}

    def _test_request(self, uid: str, link: dict) -> None:
        """The owner asked for a test trade (signed on the site): hand it to their running agent, once."""
        at = int(link.get("testAt") or 0)
        r = self.running[uid]
        if at <= r.test_seen:
            return
        r.test_seen = at
        p = Path(self.runs_root) / f"live-{uid}" / "test_request.json"
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps({"at": at}), encoding="utf-8")
        self._host(uid, "test_handed", at=at)
        self.log(f"[live-{uid}] test trade requested")

    def _host(self, uid: str, action: str, **fields) -> None:
        """What the fleet did with this user's agent, in the agent's own journal (the same chain)."""
        try:
            AuditLog(Path(self.runs_root) / f"live-{uid}" / "journal.jsonl").write("host", action=action, **redact(fields))
        except OSError as e:
            self.log(f"[live-{uid}] audit write failed: {e!r}")

    def _copy_web_audit(self, env: str) -> None:
        """runs/web-audit-<env>.jsonl: the site's record of every owner action (with the signed message and the
        wallet signature), copied here every minute so it also exists outside Cloudflare."""
        if time.time() - self._web_at < WEB_AUDIT_EVERY_S:
            return
        self._web_at = time.time()
        log = AuditLog(Path(self.runs_root) / f"web-audit-{env}.jsonl")
        if self._web_after is None:
            self._web_after = max([int(r.get("id") or 0) for r in log.read() if r.get("kind") == "web"] or [0])
        try:
            got = self.site.audit(self._web_after).get("rows", [])
        except Exception as e:   # the site keeps the rows: the next minute copies them
            self.log(f"web audit copy failed: {e!r}")
            return
        for row in sorted(got, key=lambda r: int(r.get("id") or 0)):
            rid = int(row.get("id") or 0)
            if rid > self._web_after:
                log.write("web", **row)
                self._web_after = rid

    def _account_due(self, uid: str) -> bool:
        """Every minute, and within seconds after the agent did something (its journal changed): an order or a fill
        shows in the city without waiting for the minute."""
        last, now = self._acct_at.get(uid, 0.0), time.time()
        if now - last >= (ACCOUNT_EVERY_S if self._acct_busy.get(uid, True) else ACCOUNT_IDLE_EVERY_S):
            return True
        try:
            changed = (Path(self.runs_root) / f"live-{uid}" / "journal.jsonl").stat().st_mtime > last
        except OSError:
            changed = False
        return changed and now - last >= 5

    def _account(self, uid: str, env: str, pub: str) -> None:
        """runs/live-<uid>/account.json: what the city shows as this agent's account (api/city.py)."""
        if not self.account_reader:
            return
        p = Path(self.runs_root) / f"live-{uid}" / "account.json"
        self._acct_at[uid] = time.time()
        try:
            acct = self.account_reader(env, self.pool.signer(pub))
        except Exception as e:   # Strike unreachable: keep the last one, try again next minute
            self.log(f"[live-{uid}] account unavailable: {e!r}")
            return
        try:
            prev = json.loads(p.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            prev = {}
        now = int(time.time() * 1000)
        tracked = prev.get("flows_v") == FLOWS_V
        first_time = int(prev["first_time"]) if tracked and prev.get("first_time") else (self._first_seen(uid, prev) if prev else now)
        got = acct.pop("transfers", None)
        transfers = account_flows(prev.get("transfers", []) if tracked else None, got, first_time, first_reading=not prev)
        flows, inflows = net_flows(transfers)
        self._audit_transfers(uid, prev.get("transfers", []), transfers)
        # equity every 5 minutes for the chart, a week of it, with the money moved in by then (so the public chart
        # shows the result, never a deposit)
        hist = [h for h in prev.get("history", []) if isinstance(h, list) and len(h) in (2, 4)][-HISTORY_POINTS:]
        if acct.get("equity") is not None and (not hist or now - hist[-1][0] >= HISTORY_EVERY_MS):
            hist = (hist + [[now, acct["equity"], flows, inflows]])[-HISTORY_POINTS:]
        def key(f: dict) -> tuple:
            return f.get("time"), f.get("market"), f.get("side"), f.get("price"), f.get("size")
        new = acct.get("fills", [])
        seen = {key(f) for f in new}
        known = {key(f) for f in prev.get("fills", [])}
        self._audit_account(uid, prev, acct, [f for f in new if key(f) not in known])
        fills = sorted(new + [f for f in prev.get("fills", []) if key(f) not in seen], key=lambda f: -(f.get("time") or 0))
        self._acct_busy[uid] = bool(acct.get("positions") or acct.get("orders"))
        acct = {**acct, "time": now, "first_balance": prev.get("first_balance", acct.get("balance")), "first_time": first_time,
                "transfers": transfers, "flows": flows, "inflows": inflows, "history": hist, "fills": fills[:FILLS_KEPT],
                # tracked once its transfers were read at least once (a failed read must not make old ones look new)
                "flows_v": FLOWS_V if tracked or got is not None else prev.get("flows_v")}
        p.parent.mkdir(parents=True, exist_ok=True)
        tmp = p.with_suffix(".tmp")
        tmp.write_text(json.dumps(acct), encoding="utf-8")
        tmp.replace(p)

    def _audit_transfers(self, uid: str, before: list[dict], now: list[dict]) -> None:
        """Each deposit, withdrawal or transfer of the account, when first seen and when its status (or whether the
        starting balance already held it) changes, in account.jsonl."""
        was = {str(t.get("id")): (t.get("status"), bool(t.get("base"))) for t in before}
        try:
            log = AuditLog(Path(self.runs_root) / f"live-{uid}" / "account.jsonl")
            for t in sorted(now, key=lambda t: int(t.get("time") or 0)):
                if was.get(str(t.get("id"))) != (t.get("status"), bool(t.get("base"))):
                    log.write("transfer", **t)
        except OSError as e:
            self.log(f"[live-{uid}] audit write failed: {e!r}")

    def _first_seen(self, uid: str, prev: dict) -> int | None:
        """When this account was first read, for accounts read before ``first_time`` was kept: the first point of its
        chart (written with ``first_balance``, while the chart still holds it), else its agent's first journal line
        (the fleet reads the account right after starting the agent), else the first line of its account log."""
        hist = [h for h in prev.get("history", []) if isinstance(h, list) and h]
        if hist and len(hist) < HISTORY_POINTS:
            return int(hist[0][0])
        from datetime import datetime
        for name in ("journal.jsonl", "account.jsonl"):
            try:
                with (Path(self.runs_root) / f"live-{uid}" / name).open(encoding="utf-8") as f:
                    return int(datetime.fromisoformat(json.loads(f.readline() or "{}")["ts"]).timestamp() * 1000)
            except (OSError, json.JSONDecodeError, KeyError, ValueError):
                continue
        return None

    def _audit_account(self, uid: str, prev: dict, acct: dict, new_fills: list[dict]) -> None:
        """Every fill of the account (the agent's and anyone else's) and every change of its balance, positions or
        orders: fills.jsonl and account.jsonl next to the journal. A balance that moves without fills is a deposit,
        a withdrawal or funding."""
        run = Path(self.runs_root) / f"live-{uid}"

        def shape(a: dict) -> tuple:
            return (round(float(a.get("balance") or 0), 4),
                    sorted((p.get("market"), p.get("side"), p.get("size"), p.get("entry")) for p in a.get("positions", [])),
                    sorted((o.get("market"), o.get("side"), o.get("type"), o.get("size"), o.get("price"), o.get("stop"),
                            o.get("status")) for o in a.get("orders", [])))
        try:
            fl = AuditLog(run / "fills.jsonl")
            # the first time, the fills account.json already kept (from before this log existed) go first
            earlier = [] if fl.path.exists() else prev.get("fills", [])
            for f in sorted(earlier, key=lambda f: f.get("time") or 0) + sorted(new_fills, key=lambda f: f.get("time") or 0):
                fl.write("fill", **f)
            log = AuditLog(run / "account.jsonl")
            if prev and shape(prev) == shape(acct) and log.path.exists():   # the first reading is always kept
                return
            before, now = prev.get("balance"), acct.get("balance")
            log.write(
                "account", balance=now, equity=acct.get("equity"), available=acct.get("available"), upnl=acct.get("upnl"),
                margin=acct.get("margin"), positions=acct.get("positions", []), orders=acct.get("orders", []),
                balance_change=None if before is None or now is None else round(float(now) - float(before), 6),
                new_fills=len(new_fills),
                new_fills_net=round(sum(float(f.get("pnl") or 0) - float(f.get("fee") or 0) for f in new_fills), 6))
        except OSError as e:
            self.log(f"[live-{uid}] audit write failed: {e!r}")

    def run(self, every: float = 10) -> None:
        while True:
            try:
                self.tick()
            except (urllib.error.URLError, TimeoutError) as e:
                self.log(f"site unreachable: {e!r}")
            except Exception as e:   # never die: the next turn may work (agents keep running meanwhile)
                self.log(f"fleet error: {e!r}")
            time.sleep(every)


def _run_agent(cfg: AgentConfig, signer, stop: threading.Event, log: Callable[[str], None]) -> None:
    from ..agent.runner import Agent
    while not stop.is_set():
        try:
            cfg.validate()
            Agent.build(cfg, signer).run(log=lambda m: log(f"[{cfg.name}] {m}"), stop=stop)
        except PermissionError as e:   # missing explicit authorisation: do not retry in a loop
            log(f"[{cfg.name}] refused: {e}")
            _host_note(cfg, "refused", error=str(e)[:1000])
            return
        except Exception as e:
            log(f"[{cfg.name}] crashed: {e!r}; restarting in 60 s")
            _host_note(cfg, "crashed", error=repr(e)[:1000], restart_in_s=60)
            stop.wait(60)


def _host_note(cfg: AgentConfig, action: str, **fields) -> None:
    try:
        AuditLog(cfg.run_dir / "journal.jsonl").write("host", action=action, **redact(fields))
    except OSError:
        pass

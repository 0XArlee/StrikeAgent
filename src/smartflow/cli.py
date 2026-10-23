"""Command line: ``smartflow <command> --help``."""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import sys
import time
from dataclasses import replace
from pathlib import Path

from . import ENGINE_VERSION


def _load_secrets(env: str) -> None:
    from . import secretstore
    f = Path("secrets") / f"strike_{env}.env"
    if secretstore.exists(f):   # plain, or encrypted at rest (smartflow secrets lock)
        for ln in secretstore.read_text(f).splitlines():
            if "=" in ln and not ln.lstrip().startswith("#"):
                k, v = ln.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip())


def _ms(s: str) -> int:
    return int(dt.datetime.fromisoformat(s).replace(tzinfo=dt.timezone.utc).timestamp() * 1000)


def cmd_data(a) -> int:
    from .data.binance import sync_funding, sync_klines
    root = Path(a.root)
    for sym in a.symbols.split(","):
        for tf in a.tfs.split(","):
            sync_klines(root, sym, tf, _ms(a.start))
        sync_funding(root, sym, _ms(a.start))
    return 0


def cmd_backtest(a) -> int:
    from .backtest.sim import CostModel, ExecModel
    from .backtest.study import WINDOWS, evaluate
    from .core.config import Params
    p = Params()
    for kv in a.set or []:
        k, v = kv.split("=", 1)
        cur = getattr(p, k)
        p = replace(p, **{k: type(cur)(v) if not isinstance(cur, bool) else v.lower() in ("1", "true", "yes")})
    cost = CostModel(builder_fee_bps=a.builder_bps, slippage_bps=a.slip_bps)
    exe = ExecModel(policy=a.policy, max_stack=a.max_stack)
    window = WINDOWS[a.window] if a.window in WINDOWS else tuple(_ms(x) for x in a.window.split(":"))
    s, per, trades = evaluate(Path(a.root), a.symbols.split(","), a.tf, p, cost, exe, window)
    print(f"Smart Flow {ENGINE_VERSION} | tf {a.tf} | {a.window} | params {'reference' if p.is_reference else p.fingerprint()}")
    print(f"costs: {cost.label()} | {exe.label()}")
    print("ALL   ", s.row())
    for k, v in per.items():
        print(f"{k:6}", v.row())
    print(f"CAGR {100 * s.cagr:.1f}% / maxDD {100 * s.equity_max_dd:.1f}% at {100 * s.risk_per_trade:.1f}% risk per "
          f"trade; Sharpe(m) {s.sharpe_monthly:.2f}; costs/trade: fees {s.fees_r:.3f}R builder {s.builder_r:.3f}R "
          f"funding {s.funding_r:+.3f}R slippage {s.slippage_r:.3f}R")
    if a.trades:
        with open(a.trades, "w", encoding="utf-8") as f:
            f.write("symbol,dir,signal_time,entry_time,entry,stop,exit_time,exit,reason,r,r_gross,fees,builder,funding\n")
            for t in sorted(trades, key=lambda t: t.signal_time):
                f.write(f"{t.symbol},{t.dir},{t.signal_time},{t.entry_time},{t.entry},{t.sl},{t.exit_time},{t.exit},"
                        f"{t.reason},{t.r:.4f},{t.r_gross:.4f},{t.r_fees:.4f},{t.r_builder:.4f},{t.r_funding:.4f}\n")
        print("trades ->", a.trades)
    return 0


def cmd_research(a) -> int:
    from .backtest.research import run
    run(Path(a.root), Path(a.out), quick=a.quick)
    return 0


def cmd_verify_tv(a) -> int:
    from .core.config import Params
    from .core.timeframes import auto_htf
    from .data.binance import kline_path
    from .data.store import load_candles
    from .verify.tradingview import compare
    htf = load_candles(kline_path(Path(a.root), a.symbol, auto_htf(a.tf)), f"binance-spot:{a.symbol}")
    c = compare(Path(a.csv), htf, Params(), a.tf, warmup=a.warmup)
    print(c.report())
    return 0 if c.ok else 1


def _markets(s: str):
    from .agent.config import MarketMap
    return [MarketMap(*x.split(":")) for x in s.split(",")]


def cmd_analyze(a) -> int:
    """Current state of each market, explained, with what the agent would do (no orders)."""
    from .agent.config import AgentConfig
    from .agent.runner import Agent
    cfg = AgentConfig(name="analyze", mode="analysis", env=a.env, tf=a.tf, markets=_markets(a.markets))
    ag = Agent.build(cfg)
    ag.warmup(log=lambda *_: None)
    p = cfg.params
    for m in ag.markets.values():
        st = m.last_state
        t = time.strftime("%Y-%m-%d %H:%M", time.gmtime(st.open_time / 1000))
        q = ag._public_quote(m.strike)
        from .net import get_json
        spot = float(get_json("https://api.binance.com/api/v3/ticker/price", {"symbol": m.signal})["price"])
        basis = (q.mark / spot - 1) * 1e4
        trend = {1: "bullish", -1: "bearish", 0: "no trend", None: "unknown"}[st.htf_trend]
        print(f"\n== {m.strike} (signal: Binance {m.signal} {a.tf}) · last closed candle {t} UTC · close {st.close:g}")
        print(f"   Strike mark {q.mark:g} (vs Binance spot now {spot:g}: {basis:+.1f} bps) · bid/ask {q.bid:g}/{q.ask:g} · funding/h {q.funding_rate:+.6f}")
        print(f"   ATR {st.atr:.4g} ({100 * st.atr / st.close:.2f}%) · vol x{st.rel_vol:.2f} · money flow {st.flow:+.0f} · "
              f"HTF {m.runner.htf} {trend} · EMAs {'rising' if st.ema_trend == 1 else 'falling' if st.ema_trend == -1 else 'flat'}")
        if st.sig_dir:
            stop = st.close - st.sig_dir * p.stop_atr * st.atr
            print(f"   >>> SIGNAL {'BUY' if st.sig_dir == 1 else 'SELL'}: entry ~{st.close:g}, stop {stop:g} "
                  f"(1R = {100 * p.stop_atr * st.atr / st.close:.2f}% of the price), exit: a close back through the {p.chan_n}-candle channel")
        else:
            print("   No signal: " + "; ".join(st.why_no_signal(p)))
        print(f"   To buy, the next candle would need to close > {m.runner.engine._prev['hi_n']:g} "
              f"(the {p.look_n}-candle high) with a range ≥ {p.range_min:g} ATR, a body ≥ {100 * p.body_min:.0f}% and "
              f"volume ≥ x{p.vol_min:g}; to sell: close < {m.runner.engine._prev['lo_n']:g}.")
    print("\n(For information only: not a recommendation nor a promise of results; see docs/STRATEGY.md.)")
    return 0


def cmd_strike_check(a) -> int:
    from .strike.check import run_public_checks
    return run_public_checks(a.env)


def cmd_auth_check(a) -> int:
    _load_secrets(a.env)
    from .strike.check import run_auth_checks
    return run_auth_checks(a.env)


def cmd_keys(a) -> int:
    from .strike.keys import main
    return main(["keys", a.env])


def cmd_agent(a) -> int:
    from .agent.config import load
    from .agent.runner import Agent
    cfg = load(Path(a.config))
    _load_secrets(cfg.env)
    ag = Agent.build(cfg)
    if a.action == "run":
        ag.run(once=a.once)
        if a.once:
            ag.step()
            print(f"one step done; journal: {cfg.run_dir / 'journal.jsonl'}")
    elif a.action == "approve":
        ag.warmup(log=lambda *_: None)
        print(ag.approve(a.trade_id))
    elif a.action == "status":
        st = json.loads((cfg.run_dir / "state.json").read_text()) if (cfg.run_dir / "state.json").exists() else {}
        print(json.dumps(st, indent=1))
        for r in ag.journal.read()[-a.last:]:
            print(json.dumps(r, ensure_ascii=False)[:400])
    return 0


def cmd_api(a) -> int:
    from .api.server import serve
    srv = serve(Path(a.city), a.host, a.port, allow_origin=a.origin, news=Path(a.news) if a.news else None)
    print(f"smartflow api on http://{a.host}:{srv.server_address[1]} (read-only: /api/health /api/info /api/city)")
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass
    return 0


def cmd_push(a) -> int:
    from .api.push import run
    secret = os.environ.get("SMARTFLOW_PUSH_SECRET", "")
    url = a.url or os.environ.get("SMARTFLOW_PUSH_URL", "")
    if len(secret) < 32 or not url.startswith("https://"):
        print("set SMARTFLOW_PUSH_URL (https://...) and SMARTFLOW_PUSH_SECRET (>= 32 chars)")
        return 2
    run(Path(a.city), url, secret, a.every, live_env=a.live_env, news=Path(a.news) if a.news else None,
        copy=Path(a.copy) if a.copy else None)
    return 0


def cmd_news(a) -> int:
    from .news.classify import from_env
    from .news.service import NewsService
    from .news.store import Store
    d = Path(a.dir)
    svc = NewsService(Store(d / "news.db"), d / "news.json", classifier=from_env(os.environ))
    if not svc.classifier:
        print("ANTHROPIC_API_KEY not set: headlines are collected and measured, not scored")
    if a.once:
        print(json.dumps(svc.cycle()))
        return 0
    svc.run()
    return 0


def cmd_copy(a) -> int:
    from .copytrade.service import CopyService
    from .copytrade.store import Store
    d = Path(a.dir)
    svc = CopyService(Store(d / "copy.db"), d / "copy.json")
    if a.once:
        print(json.dumps(svc.cycle()))
        return 0
    svc.run()
    return 0


def cmd_copypilot(a) -> int:
    """Copy with your agent: the copy plans the owners signed on the site, carried out on Strike (keys stay here)."""
    from .copytrade.pilot import CopyPilot, Plans
    from .live.fleet import Site
    from .live.keypool import KeyPool
    from .strike.client import MAINNET, TESTNET, StrikeClient
    secret = os.environ.get("SMARTFLOW_FLEET_SECRET", "")
    url = a.url or os.environ.get("SMARTFLOW_FLEET_URL", "")
    if len(secret) < 32 or not url.startswith("https://"):
        print("set SMARTFLOW_FLEET_URL (the site, https://...) and SMARTFLOW_FLEET_SECRET (its PUSH_SECRET, >= 32 chars)")
        return 2
    if a.env == "mainnet" and not a.allow_mainnet:
        print("mainnet needs --allow-mainnet (real money)")
        return 2
    pool = KeyPool.from_files(Path(a.keys), Path(a.master), a.env)
    base = TESTNET if a.env == "testnet" else MAINNET
    clients: dict[str, StrikeClient] = {}

    def client_for(pub: str) -> StrikeClient:
        if pub not in clients:
            clients[pub] = StrikeClient(base, signer=pool.signer(pub))
            clients[pub].sync_clock()
        return clients[pub]

    def read(path: str):
        try:
            return json.loads(Path(path).read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return None
    log = lambda m: print(f"{dt.datetime.now(dt.timezone.utc):%Y-%m-%d %H:%M:%S} {m}", flush=True)
    pilot = CopyPilot(Plans(Site(url, secret)), client_for, a.env, Path(a.dir) / f"pilot-{a.env}.json",
                      lambda: read(str(Path(a.dir) / "copy.json")), lambda: read(a.news), log=log)
    if a.once:
        print(json.dumps(pilot.tick()))
        return 0
    pilot.run(a.every)
    return 0


def cmd_telegram(a) -> int:
    """The alerts bot on Telegram: Strike Finance for everyone, and each owner's agent, accounts and copies."""
    from .alerts.bot import AlertsBot, Site, env_file
    from .alerts.telegram import Telegram
    token = os.environ.get("TELEGRAM_BOT_TOKEN", "")
    sites = {}
    for spec in a.site:
        env, _, path = spec.partition("=")
        if path.startswith("env:"):   # from this process's environment: <PREFIX>_URL and <PREFIX>_SECRET
            url, secret = os.environ.get(f"{path[4:]}_URL", ""), os.environ.get(f"{path[4:]}_SECRET", "")
        else:
            kv = env_file(path)
            url, secret = kv.get("SMARTFLOW_FLEET_URL", ""), kv.get("SMARTFLOW_FLEET_SECRET", "")
        if env not in ("testnet", "mainnet") or len(secret) < 32 or not url.startswith("https://"):
            print(f"--site {env}=...: needs SMARTFLOW_FLEET_URL and SMARTFLOW_FLEET_SECRET in {path}")
            return 2
        sites[env] = Site(env, url, secret)
    log = lambda m: print(f"{dt.datetime.now(dt.timezone.utc):%Y-%m-%d %H:%M:%S} {m}", flush=True)
    bot = AlertsBot(Telegram(token or ("0:dry-run" if a.once else "")), sites, Path(a.dir), Path(a.runs), Path(a.copy_dir), Path(a.news), log=log)
    if a.once:   # one minute of Strike's alerts, printed, nothing sent
        new = bot.watch.tick()
        print(json.dumps({"alerts": new, "snapshot": {k: v for k, v in bot.watch.snapshot().items() if k != "near"}}, default=str)[:4000])
        return 0
    me = bot.tg.me()
    log(f"telegram: @{me.get('username')} ready, {len(bot.state['chats'])} chats, sites: {', '.join(sites)}")
    bot.run(a.every)
    return 0


def cmd_fleet(a) -> int:
    from .live.fleet import Fleet, Site, read_account
    from .live.keypool import KeyPool
    from .strike.client import MAINNET, TESTNET, StrikeClient
    secret = os.environ.get("SMARTFLOW_FLEET_SECRET", "")
    url = a.url or os.environ.get("SMARTFLOW_FLEET_URL", "")
    if len(secret) < 32 or not url.startswith("https://"):
        print("set SMARTFLOW_FLEET_URL (the site, https://...) and SMARTFLOW_FLEET_SECRET (its PUSH_SECRET, >= 32 chars)")
        return 2
    if a.env == "mainnet" and not a.allow_mainnet:
        print("mainnet needs --allow-mainnet (real money)")
        return 2
    key_file = Path(a.master)
    if a.init:
        KeyPool.new_master_key(key_file)
        print(f"master key ready: {key_file}")
        return 0
    pool = KeyPool.from_files(Path(a.keys), key_file, a.env)
    public = StrikeClient(TESTNET if a.env == "testnet" else MAINNET)
    fleet = Fleet(Site(url, secret), pool, lambda: set(public.markets()), a.runs, str(Path(a.root)),
                  allow_mainnet=a.allow_mainnet, log=lambda m: print(f"{dt.datetime.now(dt.timezone.utc):%Y-%m-%d %H:%M:%S} {m}", flush=True),
                  account_reader=read_account)
    if a.once:
        print(json.dumps(fleet.tick()))
        return 0
    fleet.run(a.every)
    return 0


def cmd_audit(a) -> int:
    from . import audit
    from .live import audit_report as ar
    runs = Path(a.runs)
    if a.what == "verify":
        bad = 0
        for p in audit.files(runs):
            v = audit.verify(p)
            bad += not v["ok"]
            print(f"{'OK  ' if v['ok'] else 'FAIL'} {p.relative_to(runs).as_posix()}: {v['lines']} lines, {v['chained']} chained"
                  + (f", {v['legacy']} before the chain (sealed)" if v["legacy"] else "")
                  + (f", unchained lines {v['loose']}" if v["loose"] else "")
                  + "".join(f"\n     {x}" for x in v["problems"]))
        print("every log is intact" if not bad else f"{bad} log(s) FAILED the check")
        return 1 if bad else 0
    if not a.user:
        print("audit report needs the user (u-…, the agent's name or the wallet address)")
        return 2
    uid = ar.uid_for(a.user, runs, a.env)
    day = lambda s, end: None if not s else int(dt.datetime.fromisoformat(s + ("T23:59:59.999" if end and len(s) == 10 else ""))
                                                 .replace(tzinfo=dt.timezone.utc).timestamp() * 1000)
    anchors = None
    if a.site:
        from .live.fleet import Site
        run = f"live-{uid}"
        names = [f"web-audit-{a.env}.jsonl"] + [f"{run}/{n}" for n in ("journal.jsonl", "fills.jsonl", "account.jsonl")]
        anchors = Site(os.environ.get("SMARTFLOW_FLEET_URL", ""), os.environ.get("SMARTFLOW_FLEET_SECRET", "")).anchors(names)["anchors"]
    doc = ar.build(runs, uid, a.env, day(a.since, False), day(a.until, True), checks=not a.no_checks, anchors=anchors)
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    stem = out / f"{uid}-{dt.datetime.now(dt.timezone.utc):%Y%m%dT%H%M%SZ}"
    stem.with_suffix(".md").write_text(ar.markdown(doc), encoding="utf-8")
    stem.with_suffix(".json").write_text(json.dumps(doc, ensure_ascii=False, indent=1, default=str), encoding="utf-8")
    ok = all(v["ok"] for v in doc["integrity"].values()) and all(x["ok"] for v in doc["anchors"].values() for x in v)
    print(f"{stem}.md ({len(doc['timeline'])} events, {len(doc['trades'])} trades, {len(doc['consents'])} signatures) — "
          + ("records intact" if ok else "INTEGRITY PROBLEMS: see the report"))
    return 0 if ok else 1


def cmd_health(a) -> int:
    from .live import health
    if a.release:
        ok = health.release(Path(a.runs), a.release)
        print(f"{a.release}: hold released" if ok else f"{a.release} was not on hold")
        return 0 if ok else 1
    doc = health.check(Path(a.city), Path(a.runs))
    print(json.dumps({k: {x: v[x] for x in ("state", "n", "avg_r", "dd_r", "why")} for k, v in doc["strategies"].items()},
                     ensure_ascii=False, indent=1))
    print("holds:", json.dumps(doc["holds"]) if doc["holds"] else "none")
    return 0


def cmd_watchdog(a) -> int:
    from .live import watchdog
    doc = watchdog.run_once(Path(a.runs), Path(a.city))
    return 1 if doc["open"] else 0


def cmd_figures(a) -> int:
    from .backtest.figures import write
    write(a.strategy, a.builder_bps, Path(a.root))
    return 0


def cmd_site_check(a) -> int:
    from . import notify
    from .live.watchdog import site_check
    why = site_check(a.url)
    if why:
        print(f"PROBLEM: {why}")
        notify.send("critical", why, source="external watchdog", cooldown_s=0)
        return 1
    print(f"{a.url}: agents' data is fresh")
    return 0


def cmd_alert_test(a) -> int:
    from . import notify
    if not notify.configured():
        print("SMARTFLOW_ALERT_WEBHOOK is not set (on the host: /etc/smartflow/alert.env)")
        return 2
    ok = notify.send("warning", a.text, source="test", cooldown_s=0)
    print("sent" if ok else "NOT sent (see the line above)")
    return 0 if ok else 1


def cmd_secrets(a) -> int:
    from . import secretstore
    folder = Path(a.dir)
    if a.action == "lock":
        n = secretstore.lock(folder)
        print(f"{n} file(s) encrypted")
    for name, enc in secretstore.status(folder):
        print(f"{'encrypted' if enc else 'PLAIN    '}  {name}")
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="smartflow", description=f"Smart Flow Agent {ENGINE_VERSION}")
    ap.add_argument("--root", default="data", help="market data directory")
    sub = ap.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("data", help="download / update Binance klines and funding")
    s.add_argument("--symbols", default="BTCUSDT,ETHUSDT,SOLUSDT")
    s.add_argument("--tfs", default="60,240,D,W")
    s.add_argument("--start", default="2020-09-01")
    s.set_defaults(fn=cmd_data)

    s = sub.add_parser("backtest", help="execution-realistic backtest")
    s.add_argument("--tf", default="240")
    s.add_argument("--symbols", default="BTCUSDT,ETHUSDT,SOLUSDT")
    s.add_argument("--window", default="full", help="full|dev|val|test|strike or YYYY-MM-DD:YYYY-MM-DD")
    s.add_argument("--builder-bps", type=float, default=0.0)
    s.add_argument("--slip-bps", type=float, default=2.0)
    s.add_argument("--policy", default="single", choices=["single", "reverse", "overlap", "pyramid", "pyramid_rev"])
    s.add_argument("--max-stack", type=int, default=3, help="pyramid: trades per market at most")
    s.add_argument("--set", action="append", help="experimental parameter override, e.g. --set chan_n=20")
    s.add_argument("--trades", help="write the trade list to this CSV")
    s.set_defaults(fn=cmd_backtest)

    s = sub.add_parser("research", help="run the full experiment suite -> reports/")
    s.add_argument("--out", default="reports")
    s.add_argument("--quick", action="store_true")
    s.set_defaults(fn=cmd_research)

    s = sub.add_parser("verify-tv", help="compare against a TradingView chart-data export of the indicator")
    s.add_argument("csv")
    s.add_argument("--symbol", default="BTCUSDT")
    s.add_argument("--tf", default="60")
    s.add_argument("--warmup", type=int, default=1500)
    s.set_defaults(fn=cmd_verify_tv)

    s = sub.add_parser("analyze", help="explain the current state of each market (no orders)")
    s.add_argument("--tf", default="240")
    s.add_argument("--env", default="mainnet")
    s.add_argument("--markets", default="BTC-USD:BTCUSDT,ETH-USD:ETHUSDT,SOL-USD:SOLUSDT")
    s.set_defaults(fn=cmd_analyze)

    s = sub.add_parser("strike-check", help="check public Strike endpoints against the documentation")
    s.add_argument("--env", default="testnet", choices=["testnet", "mainnet"])
    s.set_defaults(fn=cmd_strike_check)

    s = sub.add_parser("auth-check", help="read-only signed calls with your API wallet (secrets/strike_<env>.env)")
    s.add_argument("--env", default="testnet", choices=["testnet", "mainnet"])
    s.set_defaults(fn=cmd_auth_check)

    s = sub.add_parser("keys", help="generate an API-wallet key pair locally")
    s.add_argument("env", nargs="?", default="testnet", choices=["testnet", "mainnet"])
    s.set_defaults(fn=cmd_keys)

    s = sub.add_parser("agent", help="run / approve / status")
    s.add_argument("action", choices=["run", "approve", "status"])
    s.add_argument("trade_id", nargs="?")
    s.add_argument("--config", default="config/agent.toml")
    s.add_argument("--once", action="store_true", help="warm up, do one step and exit")
    s.add_argument("--last", type=int, default=20)
    s.set_defaults(fn=cmd_agent)

    s = sub.add_parser("api", help="read-only public API for Strike City (/api/city from the agents' journals)")
    s.add_argument("--city", default="config/city.toml")
    s.add_argument("--host", default="127.0.0.1")
    s.add_argument("--port", type=int, default=8787)
    s.add_argument("--origin", default="*", help="Access-Control-Allow-Origin")
    s.add_argument("--news", help="serve this news.json (smartflow news) at /api/news")
    s.set_defaults(fn=cmd_api)

    s = sub.add_parser("push", help="push the city snapshot to the Strike City site (outbound, HMAC signed)")
    s.add_argument("--city", default="config/city.toml")
    s.add_argument("--url", help="default: $SMARTFLOW_PUSH_URL")
    s.add_argument("--every", type=float, default=10.0)
    s.add_argument("--live-env", choices=["testnet", "mainnet"], help="also push the users' agents of this network's fleet")
    s.add_argument("--news", help="also send this news.json (smartflow news) when it changes")
    s.add_argument("--copy", help="also send this copy.json (smartflow copy) when it changes")
    s.set_defaults(fn=cmd_push)

    s = sub.add_parser("news", help="the News Tower's data: headlines, model scores, reactions on Strike -> news.json")
    s.add_argument("--dir", default="/var/lib/smartflow/news", help="its database and news.json")
    s.add_argument("--once", action="store_true", help="one cycle and exit")
    s.set_defaults(fn=cmd_news)

    s = sub.add_parser("copy", help="Strike's copy trading for Strike City: leads, copiers, Strike's totals, kept -> copy.json")
    s.add_argument("--dir", default="/var/lib/smartflow/copy", help="its database and copy.json")
    s.add_argument("--once", action="store_true", help="one cycle and exit")
    s.set_defaults(fn=cmd_copy)

    s = sub.add_parser("copypilot", help="copy with your agent: the owners' signed copy plans, carried out on Strike")
    s.add_argument("--env", choices=["testnet", "mainnet"], default="testnet")
    s.add_argument("--url", help="the Strike City site; default: $SMARTFLOW_FLEET_URL")
    s.add_argument("--keys", default="/var/lib/smartflow/keys", help="encrypted API-wallet key pool")
    s.add_argument("--master", default="/etc/smartflow/keys.key", help="master key of the pool (AES-256)")
    s.add_argument("--dir", default="/var/lib/smartflow/copy", help="copy.json (the traders) and the pilot's state")
    s.add_argument("--news", default="/var/lib/smartflow/news/news.json", help="the News Tower's document (security alarm)")
    s.add_argument("--every", type=float, default=60.0)
    s.add_argument("--once", action="store_true", help="one pass, print it and exit")
    s.add_argument("--allow-mainnet", action="store_true")
    s.set_defaults(fn=cmd_copypilot)

    s = sub.add_parser("telegram", help="the alerts bot on Telegram (token in $TELEGRAM_BOT_TOKEN)")
    s.add_argument("--site", action="append", default=[], metavar="ENV=FILE",
                   help="a site: ENV=<env file with SMARTFLOW_FLEET_URL/SECRET> or ENV=env:<PREFIX> for $<PREFIX>_URL/_SECRET (repeat)")
    s.add_argument("--dir", default="/var/lib/smartflow/alerts", help="the bot's state")
    s.add_argument("--runs", default="runs", help="the agents' journals")
    s.add_argument("--copy-dir", default="/var/lib/smartflow/copy", help="the copy collector's database and the pilots' state")
    s.add_argument("--news", default="/var/lib/smartflow/news/news.json", help="the News Tower's document")
    s.add_argument("--every", type=float, default=60.0)
    s.add_argument("--once", action="store_true", help="one minute of Strike's alerts, printed (nothing sent)")
    s.set_defaults(fn=cmd_telegram)

    s = sub.add_parser("fleet", help="run the users' agents connected with the builder code (keys stay on this host)")
    s.add_argument("--env", choices=["testnet", "mainnet"], default="testnet")
    s.add_argument("--url", help="the Strike City site; default: $SMARTFLOW_FLEET_URL")
    s.add_argument("--keys", default="/var/lib/smartflow/keys", help="encrypted API-wallet key pool")
    s.add_argument("--master", default="/etc/smartflow/keys.key", help="master key of the pool (AES-256)")
    s.add_argument("--runs", default="runs")
    s.add_argument("--every", type=float, default=10.0)
    s.add_argument("--once", action="store_true", help="one turn, print it and exit")
    s.add_argument("--init", action="store_true", help="create the master key if missing and exit")
    s.add_argument("--allow-mainnet", action="store_true")
    s.set_defaults(fn=cmd_fleet)

    s = sub.add_parser("audit", help="check the tamper-evident logs, or write one user's audit report (claims)")
    s.add_argument("what", choices=["verify", "report"])
    s.add_argument("user", nargs="?", help="report: u-xxxxxxxxxxxx, the agent's name or the wallet address")
    s.add_argument("--env", choices=["testnet", "mainnet"], default="mainnet")
    s.add_argument("--runs", default="runs")
    s.add_argument("--since", help="report: from this UTC date or time (ISO, e.g. 2026-10-20)")
    s.add_argument("--until", help="report: up to this UTC date or time (ISO)")
    s.add_argument("--no-checks", action="store_true", help="report: leave out the routine candle checks")
    s.add_argument("--site", action="store_true",
                   help="report: also check the heads the site kept ($SMARTFLOW_FLEET_URL, $SMARTFLOW_FLEET_SECRET)")
    s.add_argument("--out", default="reports/audit")
    s.set_defaults(fn=cmd_audit)

    s = sub.add_parser("health", help="each strategy's real results against its backtest; sets / releases its safety hold")
    s.add_argument("--city", default="config/city.toml")
    s.add_argument("--runs", default="runs")
    s.add_argument("--release", metavar="STRATEGY", help="lift the hold of this strategy (its id in config/strategies.json)")
    s.set_defaults(fn=cmd_health)

    s = sub.add_parser("watchdog", help="check the host once (services, pushes, agents, disk) and alert the operator")
    s.add_argument("--city", default="config/city.toml")
    s.add_argument("--runs", default="runs")
    s.set_defaults(fn=cmd_watchdog)

    s = sub.add_parser("figures", help="each strategy's backtest figures for the catalog and the health check (config/figures)")
    s.add_argument("--builder-bps", type=int, default=20)
    s.add_argument("--strategy", help="only this strategy (its id in config/strategies.json)")
    s.set_defaults(fn=cmd_figures)

    s = sub.add_parser("site-check", help="from outside the host: does the site still get the agents' data? (exit 1 if not)")
    s.add_argument("--url", default="https://edgecraft-strikecity.pages.dev")
    s.set_defaults(fn=cmd_site_check)

    s = sub.add_parser("alert-test", help="send a test alert to $SMARTFLOW_ALERT_WEBHOOK")
    s.add_argument("--text", default="Smart Flow: test alert, nothing is wrong")
    s.set_defaults(fn=cmd_alert_test)

    s = sub.add_parser("secrets", help="encrypt the PC's secrets/ at rest (Windows DPAPI) or show their state")
    s.add_argument("action", choices=["lock", "status"])
    s.add_argument("--dir", default="secrets")
    s.set_defaults(fn=cmd_secrets)

    a = ap.parse_args(argv)
    return a.fn(a)


if __name__ == "__main__":
    sys.exit(main())

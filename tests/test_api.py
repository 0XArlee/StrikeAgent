"""Strike City feed (/api/city): journal -> snapshot, reason parsing against the real engine, and the HTTP server."""

import json
import threading
import urllib.error
import urllib.request
from dataclasses import replace

from conftest import HOUR, aggregate, synthetic
from test_agent import FakeVenue

from smartflow.agent import runner as runner_mod
from smartflow.agent.config import AgentConfig, MarketMap
from smartflow.agent.execution import PaperExecution
from smartflow.agent.journal import Journal
from smartflow.agent.risk import RiskEngine
from smartflow.agent.runner import Agent
from smartflow.api.city import CityAgent, build, parse_why, snapshot
from smartflow.api.server import serve
from smartflow.core.config import BiasSource, Params
from smartflow.core.runner import run_history


def test_every_engine_reason_is_understood():
    """The city renders reasons from codes; a new engine sentence must not silently become 'unknown'."""
    bars = synthetic(3000, seed=5)
    htf = aggregate(bars, 4 * HOUR)
    seen = set()
    for p in (Params(), replace(Params(), range_filter=True, range_max=4), replace(Params(), ema_filter=True),
              replace(Params(), flow_filter=True), replace(Params(), bias_source=BiasSource.NONE)):
        for st in run_history(bars, htf, p, "60").states:
            why = st.why_no_signal(p)
            reasons, _ = parse_why(why)
            assert "unknown" not in reasons, why
            seen.update(reasons)
    assert {"range", "body", "inside", "volume", "bias", "warmup"} <= seen
    assert {"wide_range", "skipped"} & seen


def test_parse_why_args():
    r, a = parse_why(["no displacement: range 0.89 ATR (min 1.0), body 57% of range (min 60%)",
                      "volume too low: x0.90 of its 20-candle average (min x1.5)"])
    assert r == ["range", "body", "volume"]
    assert a == {"range": 0.89, "rmin": 1.0, "body": 57, "bmin": 60, "vol": 0.9, "vmin": 1.5}
    assert parse_why(["no displacement: range 1.02 ATR (min 1.0), body 47% of range (min 60%)"])[0] == ["body"]
    assert parse_why(["sell setup against the bias (HTF structure bullish)"]) == (["bias"], {"side": "short"})
    assert parse_why(["something new"])[0] == ["unknown"]


def _cfg_toml(path, name, tf="60", markets=("SYN-USD",), params=""):
    mk = ", ".join(f'{{ strike = "{m}", signal = "{m[:3]}USDT" }}' for m in markets)
    path.write_text(f'name = "{name}"\nmode = "simulation"\nenv = "mainnet"\ntf = "{tf}"\nmarkets = [{mk}]\n'
                    f'builder_fee_bps = 10\npaper_equity = 10000.0\n[params]\n{params}\n[risk]\nrisk_per_trade = 0.005\n')
    return path


def _run_paper(tmp_path, monkeypatch, n=2600):
    """The end-to-end paper run of test_agent, kept as a run dir for the city to read."""
    bars = synthetic(n, seed=21, start=0, step=HOUR)
    htf = aggregate(bars, 4 * HOUR)
    venue = FakeVenue()
    clock = {"now": bars[1999].open_time + HOUR + 15_000}

    def fake_fetch(symbol, tf, limit=1000, now_ms=None, start_ms=None):
        now = now_ms or clock["now"]
        step = HOUR if tf == "60" else 4 * HOUR
        src = bars if tf == "60" else htf
        closed = [c for c in src if c.open_time + step <= now and (start_ms is None or c.open_time >= start_ms)]
        return closed[-limit:] if start_ms is None else closed[:limit]

    monkeypatch.setattr(runner_mod, "fetch_closed", fake_fetch)
    monkeypatch.setattr(runner_mod.time, "sleep", lambda s: None)
    monkeypatch.setattr(runner_mod, "RiskEngine", lambda c, root: RiskEngine(c, tmp_path))
    cfg = AgentConfig(name="city-e2e", mode="simulation", env="testnet", tf="60", markets=[MarketMap("SYN-USD", "SYNUSDT")],
                      params=replace(Params(), bias_source=BiasSource.NONE), data_root=str(tmp_path / "nodata"),
                      runs_root=str(tmp_path / "runs"))
    adapter = PaperExecution(venue, 10_000, builder_fee_bps=10)
    ag = Agent(cfg, adapter, Journal(cfg.run_dir / "journal.jsonl", "simulation", "fp"), public=venue)
    ag._saved = {}
    ag.warmup(log=lambda *_: None)
    for i in range(2000, n):
        venue.px = bars[i].close
        clock["now"] = bars[i].open_time + HOUR + 15_000
        ag.step(clock["now"])
        venue.px = bars[i].low if i % 2 else bars[i].high
        ag.reconcile()
    return cfg, adapter


def test_snapshot_matches_the_paper_account(tmp_path, monkeypatch):
    cfg, adapter = _run_paper(tmp_path, monkeypatch)
    agent = CityAgent("e2e", "E2E", _cfg_toml(tmp_path / "e2e.toml", cfg.name, params='bias_source = "None"'),
                      cfg.run_dir)
    s = snapshot(agent)
    exits = [e for e in adapter.events if e["event"] == "exit"]
    assert exits and len(s["trades"]) == len(exits)
    # each trade's R is the account's own P&L (after taker + builder fees) divided by the risk taken at the stop
    for t, e in zip(reversed(s["trades"]), exits):
        dist = abs(t["entry"] - t["stop"])
        assert abs(t["r"] - (e["pnl"] - e["fees"]) / (e["qty"] * dist)) < 1e-3
        assert t["r"] < t["rGross"]                      # fees always cost something
        assert t["reason"] in ("stop", "trail", "target", "time", "flow")
    assert [p["market"] for p in s["positions"]] == list(adapter.pos)
    assert s["status"] == ("in_trade" if adapter.pos else "analyzing")
    assert s["kind"] == "paper" and s["variant"] == "experimental" and s["changes"] == ["bias_source"]
    kinds = {d["kind"] for d in s["decisions"]}
    assert {"analysis", "signal", "order", "exit"} <= kinds
    assert all(d["args"]["r"] and "unknown" not in d["args"]["r"] for d in s["decisions"] if d["kind"] == "analysis")
    # nothing from the exchange plumbing leaks into the public document
    blob = json.dumps(build([agent]))
    for k in ("client_order_id", "response", "\"plan\"", "signature", "NaN"):
        assert k not in blob


def test_offline_and_dedup(tmp_path):
    run = tmp_path / "runs" / "x"
    run.mkdir(parents=True)
    rec = {"ts": "2026-10-19T08:00:20+00:00", "kind": "analysis", "market": "BTC-USD", "bar": 1, "sig_dir": 0,
           "why": ["no setup"], "close": 1.0}
    (run / "journal.jsonl").write_text("\n".join(json.dumps(r) for r in (rec, {**rec, "ts": "2026-10-19T09:30:00+00:00"},
                                                                       {"partial": True})) + "\n{broken")
    a = CityAgent("x", "X", _cfg_toml(tmp_path / "x.toml", "x", tf="240", markets=("BTC-USD",)), run)
    from smartflow.api.city import _ms
    t0, restart = _ms("2026-10-19T08:00:20+00:00"), _ms("2026-10-19T09:30:00+00:00")
    s = snapshot(a, restart + 60_000)
    assert len(s["decisions"]) == 1 and s["lastCheck"] == t0       # a restart re-journals the bar: not a new check
    assert s["status"] == "waiting"
    assert snapshot(a, t0 + 60_000)["status"] == "analyzing"
    assert snapshot(a, t0 + 4 * 3600_000 + 25 * 60_000)["status"] == "offline"   # missed its candle


def test_server_routes(tmp_path):
    run = tmp_path / "runs" / "x"
    run.mkdir(parents=True)
    (run / "journal.jsonl").write_text("")
    (tmp_path / "config").mkdir()
    _cfg_toml(tmp_path / "config" / "x.toml", "x")
    city = tmp_path / "city.toml"
    city.write_text('[info]\nfee_bps = 10\nmarkets = ["SYN-USD"]\n[[agent]]\nid = "x"\nname = "X"\n'
                    'config = "config/x.toml"\npublic = true\n[[agent]]\nid = "hidden"\nname = "H"\n'
                    'config = "config/x.toml"\npublic = false\n')
    srv = serve(city, "127.0.0.1", 0, root=tmp_path)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    base = f"http://127.0.0.1:{srv.server_address[1]}"
    try:
        def get(path, data=None):
            req = urllib.request.Request(base + path, data=data, method="POST" if data is not None else "GET")
            try:
                with urllib.request.urlopen(req, timeout=5) as r:
                    return r.status, dict(r.headers), json.loads(r.read())
            except urllib.error.HTTPError as e:
                return e.code, dict(e.headers), json.loads(e.read())
        code, h, doc = get("/api/city")
        assert code == 200 and h["Access-Control-Allow-Origin"] == "*" and h["X-Content-Type-Options"] == "nosniff"
        assert [a["id"] for a in doc["agents"]] == ["x"]                # private agents are never listed
        assert doc["agents"][0]["status"] == "offline"                   # an empty journal is not "running"
        code, _, info = get("/api/info")
        assert code == 200 and info["feeBps"] == 10 and info["connect"] is False and info["agentHealthy"] is False
        assert get("/api/health")[0] == 200
        assert get("/api/connect/challenge", b"{}")[0] == 501            # onboarding: honest "not enabled yet"
        assert get("/api/nope")[0] == 404
        assert get("/api/city", b"{}")[0] == 405
    finally:
        srv.shutdown()
        srv.server_close()


def test_push_signature_and_fingerprint():
    """The host signs "{ms}.{body}" with HMAC-SHA256 (web/server/handlers.ts push checks exactly this); a snapshot
    that only differs in its build time is not re-sent."""
    import hashlib
    import hmac
    from smartflow.api.push import encode, fingerprint, sign
    body = encode({"generated": 1, "agents": []})
    assert sign("s" * 32, "1792400000000", body) == hmac.new(b"s" * 32, b"1792400000000." + body, hashlib.sha256).hexdigest()
    assert fingerprint({"generated": 1, "agents": [1]}) == fingerprint({"generated": 2, "agents": [1]})
    assert fingerprint({"generated": 1, "agents": [1]}) != fingerprint({"generated": 1, "agents": [2]})


def test_city_agent_look_passthrough(tmp_path):
    """The character of an official agent (config/city.toml `look`) reaches the city as is; the page validates it."""
    (tmp_path / "config").mkdir()
    _cfg_toml(tmp_path / "config" / "x.toml", "x")
    (tmp_path / "runs" / "x").mkdir(parents=True)
    city = tmp_path / "city.toml"
    city.write_text('[[agent]]\nid = "x"\nname = "X"\nconfig = "config/x.toml"\npublic = true\n'
                    'look = { hair = "afro", top = "hoodie", topColor = "#0f766e" }\n')
    from smartflow.api.city import load_city
    [a] = load_city(city, tmp_path)
    s = snapshot(a)
    assert s["look"] == {"hair": "afro", "top": "hoodie", "topColor": "#0f766e"}


def test_checks_only_of_the_markets_it_trades_now(tmp_path):
    """An agent whose owner dropped some markets keeps their old checks in its journal: the city shows only the
    markets it trades now (it looked as if it still checked eight)."""
    run = tmp_path / "runs" / "y"
    run.mkdir(parents=True)
    recs = [{"ts": "2026-10-19T08:00:20+00:00", "kind": "analysis", "market": m, "bar": 1, "sig_dir": 0, "why": ["no setup"], "close": 1.0}
            for m in ("BTC-USD", "ETH-USD", "NEAR-USD", "ZEC-USD")]
    (run / "journal.jsonl").write_text("\n".join(json.dumps(r) for r in recs) + "\n")
    a = CityAgent("y", "Y", _cfg_toml(tmp_path / "y.toml", "y", tf="240", markets=("BTC-USD", "ETH-USD")), run)
    from smartflow.api.city import _ms
    s = snapshot(a, _ms("2026-10-19T08:01:00+00:00"))
    assert sorted(s["checks"]) == ["BTC-USD", "ETH-USD"] and s["markets"] == ["BTC-USD", "ETH-USD"]


def test_feedback_goes_to_the_operator_and_is_acknowledged_only_once_sent():
    from smartflow.api.push import Feedback
    calls, out = [], []
    fb = Feedback("https://site.example/api/internal/push", "s3cret", log=lambda m: None,
                  send=lambda level, text, source="", key=None, cooldown_s=None: out.append((level, text, key)) or key != "b")

    def req(method, path, body, payload):
        calls.append((method, path, payload))
        if method == "GET":
            return {"items": [{"id": "a", "subject": "Idea", "message": "More regions", "user": "Agent X", "page": "#/city",
                               "image": "https://site.example/api/feedback/image?id=a&sig=x"},
                              {"id": "b", "subject": "Bug", "message": "...", "user": None, "page": None, "image": None}]}
        return {"ok": True}
    fb._req = req
    fb.maybe_send()
    assert out[0][0] == "feedback" and "Idea" in out[0][1] and "Image: https://site.example" in out[0][1] and "site.example" in out[0][1]
    assert calls[0] == ("GET", "/api/internal/feedback", "GET /api/internal/feedback")
    assert calls[1][0] == "POST" and '"ids":["a"]' in calls[1][2]          # "b" did not go out: it stays on the site
    fb.maybe_send()
    assert len(calls) == 2                                                 # once a minute


def test_feedback_waits_on_the_site_without_a_webhook(monkeypatch):
    from smartflow.api.push import Feedback
    monkeypatch.delenv("SMARTFLOW_ALERT_WEBHOOK", raising=False)
    fb = Feedback("https://site.example/api/internal/push", "s3cret", log=lambda m: None)
    fb._req = lambda *a: (_ for _ in ()).throw(AssertionError("must not ask the site"))
    fb.maybe_send()

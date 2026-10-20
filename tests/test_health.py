"""Strategy health and its safety hold, alerts to the operator, the host watchdog and the PC's encrypted secrets."""

import json
import sys
from pathlib import Path

import pytest

from smartflow import notify
from smartflow.live import health, watchdog

ROOT = Path(__file__).resolve().parents[1]


def test_expectations_match_the_backtest_the_page_shows():
    for strat, f in (("smartflow", "strategy.json"), ("pyramid", "strategy-pyramid.json")):
        p = ROOT / "web" / "src" / "data" / f
        if not p.exists():   # the agents' host has no web/
            pytest.skip("web/ not here")
        d = json.loads(p.read_text(encoding="utf-8"))
        e = health.EXPECT[strat]
        assert (d["avg_r"], tuple(d["ci95"]), d["max_dd_r"], d["trades_per_year"]) == (e["avg_r"], e["ci95"], e["max_dd_r"], e["trades_per_year"])


def test_health_states():
    ok = health.evaluate("smartflow", [3.0, -1.0, -1.0] * 12)
    assert ok["state"] == "ok" and ok["n"] == 36
    # few trades: too early to say anything, whatever they are
    assert health.evaluate("smartflow", [-1.0] * 10)["state"] == "ok"
    # 20 trades averaging below 0: the operator is told
    w = health.evaluate("smartflow", [2.0, -1.0, -1.0, -1.0] * 5)
    assert w["state"] == "watch" and "average" in w["why"][0]
    # 30+ trades whose whole 95 % interval is below 0: hold
    h = health.evaluate("smartflow", [1.0, -1.0, -1.0, -1.0, -1.0] * 8)
    assert h["state"] == "hold" and h["ci95_high"] < 0
    # a drawdown 1.5x the backtest's worst (28.4 R): hold, even before 30 trades
    dd = health.evaluate("smartflow", [-1.5] * 29)
    assert dd["state"] == "hold" and dd["dd_r"] == 43.5 and "drawdown" in dd["why"][0]
    assert health.evaluate("pyramid", [-1.5] * 29)["state"] == "watch"      # pyramid's worst is 45.8 R


def test_hold_is_set_once_alerted_and_only_released_by_hand(tmp_path, monkeypatch):
    sent = []
    monkeypatch.setattr(health.notify, "send", lambda level, text, **kw: sent.append((level, text)) or True)
    monkeypatch.setattr(health, "strategy_trades", lambda city, root=Path("."): {"smartflow": [1.0, -1.0, -1.0, -1.0, -1.0] * 8,
                                                                                   "pyramid": [3.0, -1.0, -1.0] * 12})
    doc = health.check(Path("x"), tmp_path, log=lambda m: None)
    assert doc["strategies"]["smartflow"]["state"] == "hold" and set(doc["holds"]) == {"smartflow"}
    assert [lvl for lvl, _ in sent] == ["critical"] and "ON HOLD" in sent[0][1]
    assert health.hold_reason(tmp_path, "smartflow") and health.hold_reason(tmp_path, "pyramid") is None
    # the numbers recover: the hold stays until the operator lifts it
    monkeypatch.setattr(health, "strategy_trades", lambda city, root=Path("."): {"smartflow": [3.0, -1.0, -1.0] * 12,
                                                                                   "pyramid": [3.0, -1.0, -1.0] * 12})
    health.check(Path("x"), tmp_path, log=lambda m: None)
    assert health.hold_reason(tmp_path, "smartflow")
    assert health.release(tmp_path, "smartflow") and health.hold_reason(tmp_path, "smartflow") is None
    assert not health.release(tmp_path, "smartflow")


def test_live_agent_opens_nothing_while_its_strategy_is_on_hold(tmp_path):
    """The hold stops real orders; a paper agent keeps trading (it is what measures the strategy)."""
    from smartflow.agent.lifecycle import S
    from smartflow.agent.runner import Agent

    class Live:
        live = True

    runs = tmp_path / "runs"
    runs.mkdir()
    (runs / "strategy-hold.json").write_text(json.dumps({"smartflow": {"since": 1, "why": ["losing for real"]}}))
    rejected = []

    class J:
        def write(self, kind, **f):
            rejected.append((kind, f))

    class Cfg:
        params = type("P", (), {"stop_atr": 1.5, "tp_r": 0.0, "chan_n": 20, "exit_mode": type("E", (), {"value": "x"})()})()
        runs_root, policy = str(runs), "single"

    class M:
        strike, blocked, trades = "BTC-USD", "", []
        runner = type("R", (), {"engine": type("E", (), {"bars": 10})()})()

    ag = Agent.__new__(Agent)
    ag.cfg, ag.adapter, ag.journal = Cfg(), Live(), J()
    st = type("St", (), {"sig_dir": 1, "close": 100.0, "atr": 2.0, "rel_vol": 2.0, "flow": 0.1, "htf_trend": 1, "rng": 4.0, "body": 3.0})()
    c = type("C", (), {"open_time": 1, "source": "binance"})()
    ag._on_signal(M(), c, st, 0)
    [(kind, f)] = [x for x in rejected if x[0] == "decision"]
    assert f["accepted"] is False and f["reasons"][0].startswith("strategy on hold: losing for real")
    assert S.REJECTED_BY_RISK


def test_alert_formats_per_service():
    url, body = notify.payload("https://api.telegram.org/bot123:abc/sendMessage?chat_id=42", "error", "push stopped", "watchdog")
    assert url == "https://api.telegram.org/bot123:abc/sendMessage" and body["chat_id"] == "42" and "push stopped" in body["text"]
    assert "content" in notify.payload("https://discord.com/api/webhooks/1/x", "warning", "t", "s")[1]
    assert set(notify.payload("https://hooks.slack.com/services/a", "warning", "t", "s")[1]) == {"text"}
    assert notify.payload("https://example.org/hook", "warning", "t", "s")[1]["level"] == "warning"


def test_alerts_cool_down_and_respect_the_level(monkeypatch):
    posted = []

    class R:
        def read(self):
            return b"{}"
    monkeypatch.setattr(notify.urllib.request, "urlopen", lambda req, timeout=8: posted.append(req) or R())
    monkeypatch.setattr(notify, "_sent", {})
    monkeypatch.delenv("SMARTFLOW_ALERT_WEBHOOK", raising=False)
    assert not notify.send("error", "x")                    # not configured: nothing, no error
    monkeypatch.setenv("SMARTFLOW_ALERT_WEBHOOK", "https://example.org/h")
    assert not notify.send("info", "only info")             # below the default level (warning)
    assert notify.send("warning", "Strike down", source="a")
    assert not notify.send("warning", "Strike down", source="a")    # the same, within the cooldown
    assert notify.send("warning", "Strike down", source="b")        # another agent's
    assert notify.send("warning", "Strike down", source="a", cooldown_s=0)
    assert len(posted) == 3


def test_watchdog_finds_what_stopped_and_says_when_it_is_solved(tmp_path, monkeypatch):
    sent = []
    monkeypatch.setattr(watchdog.notify, "send", lambda level, text, **kw: sent.append((level, text)) or True)
    env = tmp_path / "push.env"
    env.write_text("SMARTFLOW_PUSH_URL=https://site.example/api/internal/push\nSMARTFLOW_PUSH_SECRET=x\n")   # as on the host
    monkeypatch.setattr(watchdog, "SITES", {"production": str(env)})
    city = tmp_path / "city.toml"
    city.write_text("")
    now = 1_800_000_000_000
    down = {"smartflow-push"}
    asked = []
    kw = dict(active=lambda u: u not in down, info=lambda url: asked.append(url) or {"pushedAt": now - 40 * 60_000},
              exists=lambda p: p == str(env) or p == "/etc/smartflow/push.env", disk=lambda p: type("U", (), {"used": 50, "total": 100})(),
              now_ms=now)
    doc = watchdog.run_once(tmp_path, city, log=lambda m: None, **kw)
    assert set(doc["open"]) == {"unit:smartflow-push", "push:production"}
    assert asked == ["https://site.example"]                # the site's origin, not the push endpoint
    assert len(sent) == 2 and all(lvl == "error" for lvl, _ in sent)
    watchdog.run_once(tmp_path, city, log=lambda m: None, **kw)
    assert len(sent) == 2                                   # still down: no repeat before 6 h
    down.clear()
    kw["info"] = lambda url: {"pushedAt": now - 60_000}
    doc = watchdog.run_once(tmp_path, city, log=lambda m: None, **kw)
    assert doc["open"] == {} and [t for _, t in sent[2:]] == ["solved: service smartflow-push is not running",
                                                              "solved: the production site got no data from the agents for 40 min"]


@pytest.mark.skipif(sys.platform != "win32", reason="DPAPI is Windows-only")
def test_secrets_encrypted_at_rest_read_back(tmp_path):
    from smartflow import secretstore
    (tmp_path / "strike_testnet.env").write_bytes(b"STRIKE_API_PRIVATE_KEY=abc\n")
    assert secretstore.lock(tmp_path, log=lambda m: None) == 1
    assert not (tmp_path / "strike_testnet.env").exists()
    raw = (tmp_path / "strike_testnet.env.dpapi").read_bytes()
    assert b"abc" not in raw                                  # not readable as it is on disk
    assert secretstore.read_text(tmp_path / "strike_testnet.env") == "STRIKE_API_PRIVATE_KEY=abc\n"
    assert secretstore.status(tmp_path) == [("strike_testnet.env.dpapi", True)]


def test_external_check_of_the_site():
    now = 1_800_000_000_000
    assert watchdog.site_check("https://s", now, info=lambda u: {"pushedAt": now - 60_000, "agentHealthy": True}) is None
    assert "for 40 min" in watchdog.site_check("https://s", now, info=lambda u: {"pushedAt": now - 40 * 60_000, "agentHealthy": True})
    assert "never" in watchdog.site_check("https://s", now, info=lambda u: {"agentHealthy": True})
    assert "offline" in watchdog.site_check("https://s", now, info=lambda u: {"pushedAt": now, "agentHealthy": False})

    def down(u):
        raise TimeoutError()
    assert "does not answer" in watchdog.site_check("https://s", now, info=down)

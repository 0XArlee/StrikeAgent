"""Users' API-wallet key pool: encrypted at rest, never reused, signatures verifiable with the public key."""

from datetime import datetime, timezone
import json

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

from smartflow.live.keypool import KeyPool


def test_keypool_encrypts_tops_up_and_never_reuses(tmp_path):
    pool = KeyPool(tmp_path / "keys", bytes(range(32)), "testnet")
    free = pool.ensure(set(), minimum=3)
    assert len(free) == 3 and all(len(p) == 64 for p in free)
    # stored encrypted: the private key is nowhere in the files
    for p in free:
        d = json.loads((tmp_path / "keys" / f"testnet-{p}.json").read_text())
        assert set(d) == {"pub", "env", "created", "nonce", "ct"}
        s = pool.signer(p)
        assert s.public_key == p
        priv_hex = s._key.private_bytes_raw().hex()
        assert priv_hex not in (tmp_path / "keys" / f"testnet-{p}.json").read_text()
    # a handed-out key is never offered again; the pool refills
    used = {free[0]}
    again = pool.ensure(used, minimum=3)
    assert free[0] not in again and len(again) == 3
    # the signature checks out with the public key Strike authorised
    s = pool.signer(again[0])
    h = s.headers("GET", "/v2/account", "", timestamp=1792400000, nonce="n1")
    sig = next(v for k, v in h.items() if "signature" in k.lower())
    Ed25519PublicKey.from_public_bytes(bytes.fromhex(again[0])).verify(
        bytes.fromhex(sig), s.message("GET", "/v2/account", 1792400000, "n1", "").encode())


def test_keypool_wrong_master_key_or_env_cannot_decrypt(tmp_path):
    pub = KeyPool(tmp_path, bytes(32), "testnet").generate()
    with pytest.raises(Exception):
        KeyPool(tmp_path, bytes([1]) * 32, "testnet").signer(pub)
    # the environment is bound into the ciphertext: a testnet key cannot be passed off as mainnet
    (tmp_path / f"testnet-{pub}.json").rename(tmp_path / f"mainnet-{pub}.json")
    with pytest.raises(Exception):
        KeyPool(tmp_path, bytes(32), "mainnet").signer(pub)


class FakeSite:
    def __init__(self, links, code="sf-test"):
        self.doc = {"env": "testnet", "builderCode": code, "feeBps": 20, "used": [], "links": links}
        self.offered = []

    def links(self):
        return self.doc

    def offer(self, env, free):
        self.offered.append((env, list(free)))
        return {"ok": True}


def test_fleet_starts_stops_and_never_trades_unlisted_markets(tmp_path):
    from smartflow.live.fleet import Fleet
    pool = KeyPool(tmp_path / "keys", bytes(32), "testnet")
    pub = pool.generate()
    started = []

    def fake_agent(cfg, signer, stop, log):
        started.append((cfg.name, cfg.env, cfg.mode, [m.strike for m in cfg.markets], cfg.builder_fee_bps, signer.public_key))
        stop.wait(5)

    link = {"userId": "u-1", "name": "Ana", "pub": pub, "accountId": "acc", "feeBps": 20, "risk": "standard",
            "markets": ["BTC-USD", "XRP-USD"], "status": "active"}
    site = FakeSite([link])
    fleet = Fleet(site, pool, lambda: {"BTC-USD", "ETH-USD"}, str(tmp_path / "runs"), str(tmp_path / "data"), start_agent=fake_agent,
                  log=lambda m: None)
    out = fleet.tick()
    fleet.running["u-1"].thread.join(0.5)
    assert out["running"] == ["u-1"] and out["free_keys"] >= 3 and site.offered
    # testnet, autonomous, 20 bps, the user's own key, and XRP dropped because this venue does not list it
    assert started == [("live-u-1", "testnet", "autonomous", ["BTC-USD"], 20, pub)]
    assert (tmp_path / "runs" / "live-u-1" / "agent.toml").exists()
    # the owner turns it off -> the agent is stopped
    site.doc["links"] = [dict(link, status="paused")]
    fleet.tick()
    assert "u-1" not in fleet.running
    # mainnet links are refused unless the fleet was started for mainnet
    site.doc["env"] = "mainnet"
    with pytest.raises(RuntimeError):
        fleet.tick()


def test_fleet_command_refuses_without_site_or_mainnet_ack(monkeypatch, capsys):
    from smartflow.cli import main
    monkeypatch.delenv("SMARTFLOW_FLEET_SECRET", raising=False)
    monkeypatch.delenv("SMARTFLOW_FLEET_URL", raising=False)
    assert main(["fleet", "--once"]) == 2
    monkeypatch.setenv("SMARTFLOW_FLEET_SECRET", "s" * 40)
    monkeypatch.setenv("SMARTFLOW_FLEET_URL", "http://insecure.example")
    assert main(["fleet", "--once"]) == 2            # https only
    monkeypatch.setenv("SMARTFLOW_FLEET_URL", "https://qa.example")
    assert main(["fleet", "--once", "--env", "mainnet"]) == 2   # real money needs --allow-mainnet


def test_fleet_writes_the_real_account_for_the_city(tmp_path):
    import json
    from smartflow.api.city import load_live, snapshot
    from smartflow.live.fleet import Fleet
    pool = KeyPool(tmp_path / "keys", bytes(32), "testnet")
    pub = pool.generate()
    seen = []
    accounts = iter([{"balance": 1440.0, "equity": 1440.0, "upnl": 0.0, "positions": [], "orders": [], "fills": []},
                     {"balance": 1440.4, "equity": 1443.4, "available": 1428.8, "upnl": 3.0, "margin": 0.36,
                      "positions": [{"market": "SOL-USD", "side": "long", "size": 0.14, "entry": 82.67, "upnl": 3.0, "mark": 104.1,
                                     "lev": 1, "liq": None, "funding": 0.0, "margin": 0.36, "openedAt": 1792458135323}],
                      "orders": [{"market": "SOL-USD", "side": "sell", "type": "stop", "size": 0.14, "price": None, "stop": 78.4,
                                  "reduceOnly": True, "status": "untriggered"}],
                      "fills": [{"time": 1792458135323, "market": "SOL-USD", "side": "buy", "price": 82.67, "size": 0.14,
                                 "fee": 0.0058, "pnl": 0.0, "role": "taker"},
                                # the account's own past, 15 days before the agent existed: never the agent's
                                {"time": 1791162135323, "market": "ADA-USD", "side": "sell", "price": 0.2594, "size": 100,
                                 "fee": 0.01, "pnl": 12.0, "role": "taker"}]}])

    def reader(env, signer):
        seen.append((env, signer.public_key))
        return next(accounts)

    link = {"userId": "u-2", "name": "Edgar", "pub": pub, "accountId": "acc", "feeBps": 20, "risk": "assertive",
            "markets": ["SOL-USD"], "status": "active"}
    runs = tmp_path / "runs"
    fleet = Fleet(FakeSite([link]), pool, lambda: {"SOL-USD"}, str(runs), str(tmp_path / "data"),
                  start_agent=lambda cfg, signer, stop, log: stop.wait(5), log=lambda m: None, account_reader=reader)
    fleet.tick()
    started = datetime.fromtimestamp(1792458000, timezone.utc).isoformat()   # the agent's first journal line
    (runs / "live-u-2" / "journal.jsonl").write_text(json.dumps({"ts": started, "kind": "note"}) + "\n")
    fleet._acct_at["u-2"] = 0.0   # as if a minute had passed
    fleet.tick()
    assert seen == [("testnet", pub), ("testnet", pub)]     # the user's own key, every minute
    acct = json.loads((runs / "live-u-2" / "account.json").read_text())
    assert acct["first_balance"] == 1440.0 and acct["equity"] == 1443.4   # the start balance is kept
    # the city push picks it up from the registry, with the real position (opened by hand: no stop known)
    agents = load_live(runs, "testnet")
    assert [(a.id, a.name, a.owner) for a in agents] == [("u-2", "Edgar", "Strike user")]
    s = snapshot(agents[0])
    assert s["kind"] == "live" and s["env"] == "testnet" and s["equity0"] == 1440.0 and s["cash"] == 1443.4
    assert [(p["market"], p["side"], p["qty"], p["entry"], p["stop"]) for p in s["positions"]] == [("SOL-USD", "long", 0.14, 82.67, None)]
    assert load_live(runs, "mainnet") == []
    # the SOL buy was not the agent's: it shows in the agent's activity as an execution on the owner's account
    assert [(d["code"], d["market"], d["args"]["side"]) for d in s["decisions"] if d["kind"] == "account"] == [("account_fill", "SOL-USD", "buy")]
    pf = s["portfolio"]   # the whole account for the owner's view
    assert pf["start"] == 1440.0 and pf["equity"] == 1443.4 and pf["available"] == 1428.8
    assert pf["positions"][0]["mark"] == 104.1 and pf["positions"][0]["openedAt"] == 1792458135323
    assert pf["orders"][0]["type"] == "stop" and [f["price"] for f in pf["fills"]] == [82.67]   # nothing from before it started
    assert pf["fees"]["trading"] == 0.0058 and pf["fees"]["builder"] == 0.0   # a hand fill pays no builder fee
    assert pf["realized"] == 0.0 and [f["agent"] for f in pf["fills"]] == [False]
    # Strike only returns the latest fills: the file keeps every one seen, so the totals since connecting stay whole
    fleet.account_reader = lambda env, signer: {
        "balance": 1439.9, "equity": 1439.9, "available": 1439.9, "upnl": 0.0, "margin": 0.0, "positions": [], "orders": [],
        "fills": [{"time": 1792459000000, "market": "SOL-USD", "side": "sell", "price": 79.1, "size": 0.14, "fee": 0.0055,
                   "pnl": -0.4998, "role": "taker"}]}
    fleet._acct_at["u-2"] = 0.0
    fleet.tick()
    acct = json.loads((runs / "live-u-2" / "account.json").read_text())
    assert [f["time"] for f in acct["fills"]] == [1792459000000, 1792458135323, 1791162135323]
    pf = snapshot(load_live(runs, "testnet")[0])["portfolio"]
    assert pf["realized"] == -0.4998 and pf["fees"]["trading"] == round(0.0058 + 0.0055, 6)
    assert len(pf["history"]) == 1 and pf["history"][0][1] == 1440.0   # one point per 5 minutes
    for r in fleet.running.values():
        r.stop.set()



def test_agent_config_runs_the_strategy_the_user_picked(tmp_path):
    from smartflow.live.fleet import agent_config, write_toml
    import tomllib
    link = {"userId": "u-3", "markets": ["BTC-USD", "ETH-USD"], "risk": "standard", "feeBps": 20, "strategy": "pyramid"}
    cfg = agent_config(link, "mainnet", "SmartFlowAgent-EdgeCraft", 20, {"BTC-USD", "ETH-USD"}, str(tmp_path), str(tmp_path), allow_mainnet=True)
    assert cfg.policy == "pyramid" and cfg.max_stack == 3 and cfg.risk.max_open_positions == 24 and cfg.allow_mainnet
    write_toml(cfg, tmp_path / "a.toml")
    back = tomllib.loads((tmp_path / "a.toml").read_text(encoding="utf-8"))
    assert back["policy"] == "pyramid" and back["max_stack"] == 3   # the city snapshot reads it from there
    # every user's agent runs the official configuration, and its file says so (the city labels it "official")
    from smartflow.core.config import OFFICIAL
    assert cfg.params == OFFICIAL and back["params"] == {"range_filter": True, "chand_atr": 4.0}
    plain = agent_config({**link, "strategy": None}, "testnet", "c", 20, {"BTC-USD"}, str(tmp_path), str(tmp_path))
    assert plain.policy == "single" and plain.risk.max_open_positions == 8 and not plain.allow_mainnet


def test_mainnet_exit_without_price_takes_it_from_the_account_fills(tmp_path):
    """Strike mainnet does not return completed orders: the journal knows a trade closed but not at what price. The
    city prices it from the account's own fills (net of both fills' fees), counts it, and marks those fills as the
    agent's (not 'outside the agent')."""
    from smartflow.api.city import load_live, snapshot
    from smartflow.live.fleet import Fleet
    pool = KeyPool(tmp_path / "keys", bytes(32), "mainnet")
    pub = pool.generate()
    link = {"userId": "u-4", "name": "Odin", "pub": pub, "accountId": "acc", "feeBps": 20, "risk": "assertive",
            "markets": ["BTC-USD"], "status": "active"}
    fills = [{"time": 1792471579296, "market": "BTC-USD", "side": "sell", "price": 81970.0, "size": 0.00014, "fee": 0.005451, "pnl": 0.0056, "role": "taker"},
             {"time": 1792471445993, "market": "BTC-USD", "side": "buy", "price": 81930.0, "size": 0.00014, "fee": 0.00544834, "pnl": 0.0, "role": "taker"}]
    acct = {"balance": 103.0, "equity": 103.0, "available": 103.0, "upnl": 0.0, "margin": 0.0, "positions": [], "orders": [], "fills": fills}
    runs = tmp_path / "runs"
    site = FakeSite([link])
    site.doc["env"] = "mainnet"
    fleet = Fleet(site, pool, lambda: {"BTC-USD"}, str(runs), str(tmp_path / "data"), allow_mainnet=True,
                  start_agent=lambda cfg, signer, stop, log: stop.wait(5), log=lambda m: None, account_reader=lambda env, s: acct)
    fleet.tick()
    tid = "BTC-USD-test-1792471445278"
    iso = lambda ms: datetime.fromtimestamp(ms / 1000, timezone.utc).isoformat()
    base = {"mode": "autonomous", "engine": "1.0.0", "params": "x"}
    recs = [{"ts": iso(1792471440000), "kind": "analysis", "market": "BTC-USD", "bar": 1, "sig_dir": 0, "why": []},
            {"ts": iso(1792471445278), "kind": "signal", "market": "BTC-USD", "trade_id": tid, "dir": 1, "close": 81929.0, "stop": 80778.4, "test": True},
            {"ts": iso(1792471455000), "kind": "fill", "market": "BTC-USD", "trade_id": tid, "entry": 81930.0, "qty": 0.00014},
            {"ts": iso(1792471579000), "kind": "live_order", "trade_id": tid, "action": "exit", "reason": "test finished", "ok": True,
             "response": {"status": "pending"}},
            {"ts": iso(1792471579100), "kind": "exit", "market": "BTC-USD", "trade_id": tid, "reason": "test finished"}]
    (runs / "live-u-4" / "journal.jsonl").write_text("".join(json.dumps({**base, **r}) + "\n" for r in recs))
    s = snapshot(load_live(runs, "mainnet")[0])
    [t] = s["trades"]
    assert t["test"] and t["exit"] == 81970.0 and t["reason"] == "test"
    assert t["pnl"] == round(0.0056 - 0.005451 - 0.00544834, 6)              # net of both fills' fees
    assert [f["agent"] for f in s["portfolio"]["fills"]] == [True, True]      # the agent's own, not "outside the agent"
    assert [f["test"] for f in s["portfolio"]["fills"]] == [True, True]
    # the account's result split: the test trade apart from the strategy's results
    assert s["portfolio"]["split"] == {"strategy": 0.0, "test": round(0.0056 - 0.005451 - 0.00544834, 6), "outside": 0.0}
    assert not [d for d in s["decisions"] if d["code"] == "account_fill"]
    assert [d["code"] for d in s["decisions"] if d["kind"] in ("order", "exit")] == ["test_close", "test_open"]
    for r in fleet.running.values():
        r.stop.set()


def test_fleet_reads_the_account_every_minute_and_right_after_the_agent_acts(tmp_path):
    """The fleet turns every 10 s; the Strike account is read every minute, and within seconds after the agent's
    journal changed (an order, a fill), so the city shows it without waiting for the minute."""
    import time as _t
    from smartflow.live.fleet import Fleet
    pool = KeyPool(tmp_path / "keys", bytes(32), "testnet")
    pub = pool.generate()
    reads = []
    acct = {"balance": 100.0, "equity": 100.0, "upnl": 0.0, "positions": [], "orders": [], "fills": []}
    link = {"userId": "u-5", "name": "N", "pub": pub, "accountId": "a", "feeBps": 20, "risk": "standard",
            "markets": ["SOL-USD"], "status": "active"}
    runs = tmp_path / "runs"
    fleet = Fleet(FakeSite([link]), pool, lambda: {"SOL-USD"}, str(runs), str(tmp_path / "data"),
                  start_agent=lambda cfg, signer, stop, log: stop.wait(5), log=lambda m: None,
                  account_reader=lambda env, s: reads.append(1) or acct)
    fleet.tick()
    fleet.tick()
    assert len(reads) == 1                                   # a second turn right away: no new read
    (runs / "live-u-5" / "journal.jsonl").write_text('{"kind": "fill"}')
    fleet._acct_at["u-5"] = _t.time() - 6                    # the agent acted 6 s after the last read
    fleet.tick()
    assert len(reads) == 2                                   # read again within seconds, not a minute
    fleet.tick()
    assert len(reads) == 2                                   # nothing new: waits for the minute
    for r in fleet.running.values():
        r.stop.set()


def test_risk_presets_and_the_pyramid_cap():
    """0.5 / 1 / 2 % per trade (standard by default); Smart Flow Pyramid never above the standard preset, whatever the
    site sent (docs/08 "Niveles de riesgo")."""
    from smartflow.live.fleet import DEFAULT_RISK, RISK, agent_config, risk_for
    assert RISK == {"conservative": 0.005, "standard": 0.01, "assertive": 0.02} and DEFAULT_RISK == "standard"
    assert risk_for({"risk": "assertive"}) == 0.02 and risk_for({}) == 0.01
    assert risk_for({"risk": "assertive", "strategy": "pyramid"}) == 0.01
    assert risk_for({"risk": "conservative", "strategy": "pyramid"}) == 0.005
    cfg = agent_config({"userId": "u-7", "markets": ["BTC-USD"], "risk": "assertive", "strategy": "pyramid", "feeBps": 20},
                       "testnet", "c", 20, {"BTC-USD"}, "runs", "data")
    assert cfg.risk.risk_per_trade == 0.01

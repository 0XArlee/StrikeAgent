"""An agent connected to an empty Strike account, and deposits/withdrawals afterwards: the risk engine's reason, what
the city says, the account's result (never counting a deposit as a gain) and the trade counts beyond the list."""

import json
import tempfile
from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path

from test_agent import ctx
from test_live import FakeSite

from smartflow.agent.risk import RiskConfig, RiskEngine
from smartflow.live.keypool import KeyPool

iso = lambda ms: datetime.fromtimestamp(ms / 1000, timezone.utc).isoformat()
BASE = {"mode": "autonomous", "engine": "1.0.0", "params": "x"}


def test_empty_account_is_said_as_such_not_as_a_loss_limit():
    eng = RiskEngine(RiskConfig(), Path(tempfile.mkdtemp()))
    p, m, a = ctx()
    d = eng.evaluate(p, m, replace(a, equity=0.0, available=0.0))
    # before: "no equity" + "daily loss limit hit (0.00)" + "weekly loss limit hit (0.00)" (0 <= -2 % of 0)
    assert not d.accepted and d.reasons == ["no equity: the account has no balance"]
    d = eng.evaluate(p, m, replace(a, equity=-5.0, available=0.0))
    assert d.reasons == ["no equity: the account has no balance"]


def _live(tmp_path, accounts, env="mainnet"):
    """A user's live agent on the fleet, with these account readings in turn."""
    from smartflow.live.fleet import Fleet
    pool = KeyPool(tmp_path / "keys", bytes(32), env)
    pub = pool.generate()
    link = {"userId": "u-9", "name": "Zero", "pub": pub, "accountId": "acc", "feeBps": 20, "risk": "standard",
            "markets": ["BTC-USD"], "status": "active"}
    site = FakeSite([link])
    site.doc["env"] = env
    it = iter(accounts)
    fleet = Fleet(site, pool, lambda: {"BTC-USD"}, str(tmp_path / "runs"), str(tmp_path / "data"), allow_mainnet=True,
                  start_agent=lambda cfg, signer, stop, log: stop.wait(5), log=lambda m: None,
                  account_reader=lambda e, s: next(it))
    return fleet


def _acct(balance, transfers=None, **kw):
    return {"balance": balance, "equity": balance, "available": balance, "upnl": 0.0, "margin": 0.0, "positions": [],
            "orders": [], "fills": [], "transfers": transfers, **kw}


def test_unfunded_agent_then_a_deposit_is_not_a_gain(tmp_path):
    from smartflow.api.city import load_live, snapshot
    runs = tmp_path / "runs"
    dep = {"id": 7, "type": "deposit", "amount": 500.0, "status": "pending", "time": 1792500000000}
    fleet = _live(tmp_path, [_acct(0.0, []), _acct(0.0, [dep]), _acct(500.0, [{**dep, "status": "settled"}]),
                             _acct(512.5, [{**dep, "status": "settled"}])])
    fleet.tick()
    now = 1792500300000
    recs = [{"ts": iso(now - 60_000), "kind": "analysis", "market": "BTC-USD", "bar": 1, "sig_dir": 0, "why": []},
            {"ts": iso(now - 50_000), "kind": "signal", "market": "BTC-USD", "trade_id": "BTC-USD-1-L", "dir": 1, "close": 1.0, "stop": 0.9},
            {"ts": iso(now - 49_000), "kind": "decision", "trade_id": "BTC-USD-1-L", "accepted": False,
             "reasons": ["no equity: the account has no balance"]}]
    (runs / "live-u-9" / "journal.jsonl").write_text("".join(json.dumps({**BASE, **r}) + "\n" for r in recs))
    s = snapshot(load_live(runs, "mainnet")[0], now)
    assert s["status"] == "unfunded"                       # waiting for its first deposit, not "analysing"
    [risk] = [d for d in s["decisions"] if d["kind"] == "risk"]
    assert risk["code"] == "risk_balance"                  # "the account has no balance", not "daily loss limit"
    assert s["equity0"] is None and s["result"] == 0.0     # nothing to measure a return on yet
    for _ in range(3):                                     # the deposit arrives (pending, then settled), then a gain
        fleet._acct_at["u-9"] = 0.0
        fleet.tick()
    acct = json.loads((runs / "live-u-9" / "account.json").read_text())
    assert acct["first_balance"] == 0.0 and acct["flows"] == 500.0 and acct["inflows"] == 500.0
    s = snapshot(load_live(runs, "mainnet")[0], now)
    pf = s["portfolio"]
    assert s["status"] != "unfunded" and pf["start"] == 0.0 and pf["flows"] == 500.0 and pf["base"] == 500.0
    assert s["equity0"] == 500.0 and s["cash"] == 512.5 and s["result"] == 12.5   # the deposit is not the result
    # the deposit is in the account's audit log, pending and then settled
    log = [json.loads(x) for x in (runs / "live-u-9" / "account.jsonl").read_text().splitlines()]
    assert [(r["kind"], r["status"]) for r in log if r["kind"] == "transfer"] == [("transfer", "pending"), ("transfer", "settled")]
    for r in fleet.running.values():
        r.stop.set()


def test_transfers_already_in_the_starting_balance_never_count():
    from smartflow.live.fleet import account_flows, net_flows
    old = {"id": 1, "type": "deposit", "amount": 1000.0, "status": "settled", "time": 100}
    # first reading: the 1000 deposited before are the starting balance itself
    t = account_flows(None, [old], first_time=200, first_reading=True)
    assert net_flows(t) == (0.0, 0.0)
    # later: a withdrawal and a new deposit move the base; the old one still does not
    later = account_flows(t, [old, {"id": 2, "type": "withdraw", "amount": -300.0, "status": "completed", "time": 300},
                              {"id": 3, "type": "deposit", "amount": 50.0, "status": "pending", "time": 310}], 200, False)
    assert net_flows(later) == (-300.0, 0.0)                # the pending deposit is not in the balance yet
    # Strike unreachable for transfers this time: the known ones stay
    assert account_flows(later, None, 200, False) == later
    # an account read before transfers were kept: what is older than its first reading is the starting balance
    mig = account_flows(None, [old, {"id": 4, "type": "deposit", "amount": 20.0, "status": "settled", "time": 250}], 200, False)
    assert net_flows(mig) == (20.0, 20.0)


def test_existing_account_takes_its_first_reading_from_its_chart(tmp_path):
    """An account read before transfers were kept (the case of 2026-10-21): its start is the chart's first point, not
    the first line of the account log (written hours later), so the transfers in between count as money moved."""
    from smartflow.api.city import load_live, snapshot
    runs = tmp_path / "runs"
    t0 = 1792463827000                      # first reading: 103.05 $ (the deposit before it is in there)
    tx = [{"id": 1, "type": "deposit", "amount": 103.04, "status": "settled", "time": t0 - 3_000_000},
          {"id": 2, "type": "transfer", "amount": -11.0, "status": "completed", "time": t0 + 3_600_000},
          {"id": 3, "type": "transfer", "amount": 11.0, "status": "completed", "time": t0 + 3_660_000},
          {"id": 4, "type": "transfer", "amount": -11.0, "status": "completed", "time": t0 + 3_720_000},
          {"id": 5, "type": "transfer", "amount": 13.9, "status": "completed", "time": t0 + 66_000_000}]
    fleet = _live(tmp_path, [_acct(106.08, tx)])
    run = runs / "live-u-9"
    run.mkdir(parents=True, exist_ok=True)
    # what the older code left: first balance and the chart from the first reading, an account log started later,
    # and transfers already marked with the account log's (wrong) time
    (run / "account.json").write_text(json.dumps({"first_balance": 103.05, "history": [[t0, 103.05], [t0 + 300_000, 103.05]],
                                                  "first_time": t0 + 47_000_000, "transfers": [{**x, "base": True} for x in tx[:4]],
                                                  "flows": 13.9, "inflows": 13.9}))
    (run / "account.jsonl").write_text(json.dumps({"ts": iso(t0 + 47_000_000), "kind": "account"}) + "\n")
    fleet.tick()
    acct = json.loads((run / "account.json").read_text())
    assert acct["first_time"] == t0 and acct["flows_v"] == 2
    assert acct["flows"] == 2.9 and acct["inflows"] == 24.9      # -11 + 11 - 11 + 13.9 moved since the first reading
    (run / "journal.jsonl").write_text(json.dumps({**BASE, "ts": iso(t0), "kind": "analysis", "market": "BTC-USD", "bar": 1,
                                                   "sig_dir": 0, "why": []}) + "\n")
    s = snapshot(load_live(runs, "mainnet")[0], t0 + 66_100_000)
    assert s["result"] == round(106.08 - 103.05 - 2.9, 6)          # +0.13 $, not the -10.87 $ of the wrong marks
    for r in fleet.running.values():
        r.stop.set()


def test_parse_transfers_signs_and_types():
    from smartflow.strike.models import parse_transfers
    rows = parse_transfers({"transactions": [
        {"id": 1, "type": "deposit", "amount": "1440.378049", "status": "settled", "timestamp": 1792376000000},
        {"id": 2, "type": "withdraw", "amount": "25", "status": "completed", "timestamp": 1792377000000},
        {"id": 3, "type": 10, "amount": "-5", "status": "COMPLETED", "timestamp": 1792378000000}], "count": 3})
    assert [(t.type, t.amount, t.status) for t in rows] == [("deposit", 1440.378049, "settled"), ("withdraw", -25.0, "completed"),
                                                            ("transfer", -5.0, "completed")]
    assert parse_transfers({"transactions": None, "count": 0}) == []


def test_test_trade_without_balance_says_how_much_it_needs(tmp_path):
    from smartflow.api.city import CityAgent, snapshot
    run = tmp_path / "runs" / "live-u-8"
    run.mkdir(parents=True)
    (run / "agent.toml").write_text('name = "live-u-8"\nmode = "autonomous"\nenv = "mainnet"\ntf = "240"\n'
                                    'markets = [{ strike = "BTC-USD", signal = "BTCUSDT" }]\n')
    now = 1792500300000
    recs = [{"ts": iso(now - 60_000), "kind": "analysis", "market": "BTC-USD", "bar": 1, "sig_dir": 0, "why": []},
            {"ts": iso(now - 30_000), "kind": "alert", "level": "warning", "code": "test_funds", "needs": 11.76, "available": 0.0,
             "message": "test trade: no market ready (BTC-USD: needs 11.20 $ (available 0.00 $))"},
            {"ts": iso(now - 20_000), "kind": "alert", "level": "warning", "code": "test_busy",
             "message": "test trade: no market ready (BTC-USD: busy or no data)"}]
    (run / "journal.jsonl").write_text("".join(json.dumps({**BASE, **r}) + "\n" for r in recs))
    s = snapshot(CityAgent("u-8", "N", run / "agent.toml", run), now)
    got = [(d["code"], d.get("args")) for d in s["decisions"] if d["kind"] == "alert"]
    assert got == [("test_busy", {}), ("test_funds", {"needs": 11.76, "available": 0.0})]
    assert s["alerts"] == []   # the owner's test is not an operational alert of the agent


def test_trade_counts_cover_every_trade_beyond_the_list(tmp_path, monkeypatch):
    import smartflow.api.city as city
    from smartflow.api.city import CityAgent, snapshot
    monkeypatch.setattr(city, "MAX_TRADES", 3)
    run = tmp_path / "runs" / "p"
    run.mkdir(parents=True)
    (run / "agent.toml").write_text('name = "p"\nmode = "simulation"\nenv = "mainnet"\ntf = "240"\n'
                                    'markets = [{ strike = "BTC-USD", signal = "BTCUSDT" }]\n')
    recs, t0 = [], 1792000000000
    for i, r in enumerate([2.0, -1.0, -1.0, 3.0, -1.0]):
        tid, t = f"BTC-USD-{i}-L", t0 + i * 3_600_000
        recs += [{"ts": iso(t), "kind": "signal", "market": "BTC-USD", "trade_id": tid, "dir": 1, "close": 100.0, "stop": 90.0},
                 {"ts": iso(t + 1000), "kind": "fill", "market": "BTC-USD", "trade_id": tid, "entry": 100.0, "qty": 1.0},
                 {"ts": iso(t + 2000), "kind": "exit", "market": "BTC-USD", "trade_id": tid, "price": 100.0 + 10 * r, "reason": "stop"}]
    (run / "journal.jsonl").write_text("".join(json.dumps({**BASE, **r}) + "\n" for r in recs))
    s = snapshot(CityAgent("p", "P", run / "agent.toml", run))
    assert len(s["trades"]) == 3 and "params" not in s["trades"][0]
    assert s["tally"] == {"n": 5, "wins": 2, "won": 5.0, "lost": 3.0, "best": 3.0}
    full = snapshot(CityAgent("p", "P", run / "agent.toml", run), full=True)
    assert len(full["trades"]) == 5 and full["trades"][0]["params"] == "x"

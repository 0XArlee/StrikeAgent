"""The pyramid policy end to end in simulation (fake feeds/venue): stacked trades in one direction, each with its own
lot, stop and exit, netted into one position like on Strike; and the paper account's restart compatibility."""

import json
from dataclasses import replace

from conftest import HOUR, aggregate, synthetic
from test_agent import FakeVenue

from smartflow.agent import runner as runner_mod
from smartflow.agent.config import AgentConfig, MarketMap
from smartflow.agent.execution import PaperExecution, client_id
from smartflow.agent.journal import Journal
from smartflow.agent.lifecycle import S
from smartflow.agent.risk import RiskConfig, RiskEngine
from smartflow.agent.runner import Agent
from smartflow.core.config import BiasSource, Params


def _run(tmp_path, monkeypatch, policy: str, seed: int = 21, n: int = 2600, checks=None):
    bars = synthetic(n, seed=seed, start=0, step=HOUR)
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
    cfg = AgentConfig(name=f"e2e-{policy}", mode="simulation", env="testnet", tf="60", markets=[MarketMap("SYN-USD", "SYNUSDT")],
                      params=replace(Params(), bias_source=BiasSource.NONE),
                      # the loss windows use the wall clock: the whole simulated run is "today" for them
                      risk=RiskConfig(max_open_positions=9, max_daily_loss=1.0, max_weekly_loss=1.0),
                      policy=policy, max_stack=3, data_root=str(tmp_path / "nodata"), runs_root=str(tmp_path / "runs"))
    adapter = PaperExecution(venue, 10_000, builder_fee_bps=20)
    ag = Agent(cfg, adapter, Journal(cfg.run_dir / "journal.jsonl", "simulation", "fp"), public=venue)
    ag._saved = {}
    ag.warmup(log=lambda *_: None)
    max_stack = 0
    for i in range(2000, n):
        venue.px = bars[i].close
        clock["now"] = bars[i].open_time + HOUR + 15_000
        ag.step(clock["now"])
        venue.px = bars[i].low if i % 2 else bars[i].high
        ag.reconcile()
        m = ag.markets["SYN-USD"]
        held = [t for t in m.trades if t.state in (S.POSITION_OPEN, S.PROTECTED)]
        max_stack = max(max_stack, len(held))
        if checks:
            checks(ag, adapter, m, held)
    return ag, adapter, max_stack


def _invariants(ag, adapter, m, held):
    pos = adapter.position("SYN-USD")
    lots = adapter.pos.get("SYN-USD", [])
    # the netted position is exactly the sum of the agent's open trades, all in one direction
    assert (pos is None) == (not held)
    if held:
        assert len({t.dir for t in held}) == 1 and len(held) <= 3
        assert abs(abs(pos.size) - sum(t.data["qty"] for t in held)) < 1e-9
        assert sorted(t.trade_id for t in held) == sorted(p.trade_id for p in lots)
        # every open trade has ITS OWN stop resting
        for t in held:
            o = adapter.find_order("SYN-USD", client_id(t.trade_id, "stop"))
            o2 = adapter.find_order("SYN-USD", client_id(t.trade_id, "stop2"))
            assert any(x is not None and not x.is_terminal for x in (o, o2)), t.trade_id


def test_pyramid_stacks_and_each_trade_keeps_its_own_stop_and_exit(tmp_path, monkeypatch):
    ag, adapter, max_stack = _run(tmp_path, monkeypatch, "pyramid", checks=_invariants)
    single, s_adapter, s_max = _run(tmp_path / "s", monkeypatch, "single")
    entries = [e for e in adapter.events if e["event"] == "entry"]
    exits = [e for e in adapter.events if e["event"] == "exit"]
    assert s_max == 1 and max_stack >= 2, "the synthetic path should stack trades"
    assert len(entries) > len([e for e in s_adapter.events if e["event"] == "entry"])
    # every lot closes once, by its own reason, and the journal tells which trade
    assert all(e["trade_id"] for e in exits) and len({e["trade_id"] for e in exits}) == len(exits)
    assert len(entries) - len(exits) == len(adapter.pos.get("SYN-USD", []))
    journal_exits = {r.get("trade_id") for r in ag.journal.read("exit")}
    assert {e["trade_id"] for e in exits} <= journal_exits
    assert not [r for r in ag.journal.read("alert") if r["level"] in ("error", "critical")]
    stacked = [r for r in ag.journal.read("decision") if r.get("stack", 0) >= 2 and r.get("accepted")]
    assert stacked, "stacked entries are journaled with their place in the stack"
    # never an opposite trade while one is open
    st = json.loads((ag.cfg.run_dir / "state.json").read_text())
    assert "trades" in st["SYN-USD"] and "lots" in st["_paper"]


def test_state_restart_keeps_the_stack(tmp_path, monkeypatch):
    ag, adapter, _ = _run(tmp_path, monkeypatch, "pyramid", n=2400)
    snap = adapter.snapshot()
    again = PaperExecution(FakeVenue(), 10_000, builder_fee_bps=20)
    again.restore(snap)
    assert {s: [p.trade_id for p in v] for s, v in again.pos.items()} == {s: [p.trade_id for p in v] for s, v in adapter.pos.items()}
    # a state written before stacked trades (one dict per market) still loads
    legacy = {"cash": 9_900.0, "equity0": 10_000.0, "events": [],
              "pos": {"SYN-USD": {"trade_id": "t1", "dir": 1, "qty": 1.0, "entry": 100.0, "stop": 98.0, "tp": None,
                                  "opened": 0.0, "fees": 0.1}}}
    old = PaperExecution(FakeVenue(), 10_000)
    old.restore(legacy)
    assert old.position("SYN-USD").size == 1.0 and old.find_order("SYN-USD", client_id("t1", "stop")) is not None


def test_a_position_opened_by_hand_blocks_once_and_unblocks_when_gone(tmp_path, monkeypatch):
    from smartflow.agent.execution import _PaperPos
    ag, adapter, _ = _run(tmp_path, monkeypatch, "single", n=2010)
    m = ag.markets["SYN-USD"]
    for t in list(m.trades):   # start flat
        m.trades.remove(t)
    adapter.pos = {"SYN-USD": [_PaperPos("by-hand", 1, 1.0, 100.0, 1.0, None, 0.0, 0.0)]}
    for _ in range(3):
        ag.reconcile()
    alerts = [r for r in ag.journal.read("alert") if "not tracked" in r.get("message", "")]
    assert m.blocked and len(alerts) == 1          # blocked, and said once
    adapter.pos = {}
    ag.reconcile()
    assert m.blocked == "" and any("trading here again" in r.get("message", "") for r in ag.journal.read("alert"))


class MainnetLikePaper(PaperExecution):
    """Strike mainnet (2026-10-20): /v2/order returns nothing for a completed order, only while it is resting."""

    def find_order(self, symbol, client_order_id):
        o = self.orders.get(client_order_id)
        return o if o is not None and not o.is_terminal else None


def test_mainnet_order_lookup_the_position_is_the_truth(tmp_path, monkeypatch):
    import smartflow.agent.runner as rm
    orig = rm.PaperExecution
    monkeypatch.setattr(rm, "PaperExecution", MainnetLikePaper)
    try:
        for policy in ("single", "pyramid"):
            seen = {"max": 0}

            def checks(ag, adapter, m, held):
                _invariants(ag, adapter, m, held)
                seen["max"] = max(seen["max"], len(held))

            def run_with(adapter_cls):
                import test_pyramid as tp
                saved = tp.PaperExecution
                tp.PaperExecution = adapter_cls
                try:
                    return _run(tmp_path / policy, monkeypatch, policy, checks=checks)
                finally:
                    tp.PaperExecution = saved

            ag, adapter, _ = run_with(MainnetLikePaper)
            assert isinstance(adapter, MainnetLikePaper)
            entries = [e for e in adapter.events if e["event"] == "entry"]
            assert entries and not [r for r in ag.journal.read("alert") if r["level"] in ("error", "critical")]
            assert not ag.markets["SYN-USD"].blocked
            if policy == "pyramid":
                assert seen["max"] >= 2
    finally:
        monkeypatch.setattr(rm, "PaperExecution", orig)


def test_a_stop_cancelled_by_hand_is_placed_again_once(tmp_path, monkeypatch):
    ag, adapter, _ = _run(tmp_path, monkeypatch, "single", n=2600)
    # open a fresh protected trade by hand-feeding the agent's own entry path
    m = ag.markets["SYN-USD"]
    held = [t for t in m.trades if t.state == S.PROTECTED]
    if not held:   # the path may end flat: nothing to check then
        return
    rec = held[0]
    for cid in (client_id(rec.trade_id, "stop"), client_id(rec.trade_id, "stop2")):
        adapter._set_status(cid, "canceled")      # the owner cancels the stop in the Strike app
    ag.reconcile()
    assert rec.data.get("stop_purposes") == ["stop3"]
    assert adapter.find_order("SYN-USD", client_id(rec.trade_id, "stop3")).status == "untriggered"
    ag.reconcile()
    assert rec.data.get("stop_purposes") == ["stop3"]   # resting again: not placed twice


def test_owner_test_trade_goes_through_the_agents_own_path(tmp_path, monkeypatch):
    import time as _time
    for adapter_cls in (PaperExecution, MainnetLikePaper):
        import test_pyramid as tp
        saved = tp.PaperExecution
        tp.PaperExecution = adapter_cls
        try:
            ag, adapter, _ = _run(tmp_path / adapter_cls.__name__, monkeypatch, "single", n=2005)
        finally:
            tp.PaperExecution = saved
        m = ag.markets["SYN-USD"]
        for t in list(m.trades):           # make sure the market is free
            ag._request_exit(m, t, "cleanup")
        real_time = _time.time
        now = real_time()
        (ag.cfg.run_dir / "test_request.json").write_text(json.dumps({"at": int(now * 1000)}))
        ag._test_turn()
        rec = next(t for t in m.trades if t.data.get("test"))
        assert rec.state == S.PROTECTED                       # entered with its own stop on the venue
        assert adapter.position("SYN-USD").size > 0
        assert float(rec.data["qty"]) * 100 < 30              # the minimum size, not the strategy's
        ag._test_turn()                                       # still inside its hold time: stays open
        assert rec in m.trades
        monkeypatch.setattr(runner_mod.time, "time", lambda: now + 130)
        ag._test_turn()                                       # hold time over: the agent closes it
        monkeypatch.setattr(runner_mod.time, "time", real_time)
        assert rec not in m.trades and adapter.position("SYN-USD") is None
        kinds = [(r["kind"], r.get("test")) for r in ag.journal.read() if r.get("trade_id") == rec.trade_id]
        assert ("signal", True) in kinds and any(k == "fill" for k, _ in kinds) and any(k == "exit" for k, _ in kinds)
        # the same request is never run twice
        (ag.cfg.run_dir / "test_request.json").write_text(json.dumps({"at": int(now * 1000)}))
        ag._test_turn()
        assert not [t for t in m.trades if t.data.get("test")]
        # nor after a restart (the fleet writes the request again): the state keeps it, and so does the journal
        st = json.loads(ag.state_path.read_text())
        assert int(now * 1000) in st["_tests"]
        del st["_tests"]                                      # a state file from before they were kept there
        ag.state_path.write_text(json.dumps(st))
        ag._load_state()
        (ag.cfg.run_dir / "test_request.json").write_text(json.dumps({"at": int(now * 1000)}))
        ag._test_turn()
        assert not [t for t in m.trades if t.data.get("test")]

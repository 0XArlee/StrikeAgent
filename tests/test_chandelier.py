"""The official configuration (core.config.OFFICIAL): the wide-range filter and a chandelier stop that rises on the
exchange. The simulator, the study's independent implementation and the live agent must all do the same thing."""

from dataclasses import replace

from conftest import HOUR, aggregate, synthetic
from test_pyramid import MainnetLikePaper, _run

from smartflow.agent.lifecycle import S
from smartflow.backtest.exit_study import XRules, simulate_x
from smartflow.backtest.sim import CostModel, ExecModel, simulate
from smartflow.core.config import OFFICIAL, BiasSource, Params
from smartflow.core.runner import run_history


def test_official_configuration_is_the_script_plus_two_changes():
    assert OFFICIAL.range_filter and OFFICIAL.chand_atr == 4.0
    assert replace(OFFICIAL, range_filter=False, chand_atr=0.0) == Params()   # nothing else differs from the script
    OFFICIAL.validate()


def test_simulator_chandelier_matches_the_study_implementation():
    bars = synthetic(6000, seed=5, step=HOUR)
    htf = aggregate(bars, 24 * HOUR)
    cost, exe = CostModel(builder_fee_bps=20.0), ExecModel()
    for k in (2.0, 4.0):
        p = replace(Params(), bias_source=BiasSource.NONE, chand_atr=k)
        run = run_history(bars, htf, p, "60")
        ref = simulate("SYN", bars, run.states, p, cost, exe).trades
        mine = simulate_x("SYN", bars, run.states, replace(p, chand_atr=0.0), cost, exe, XRules(chand=k))
        assert len(ref) > 20
        assert sorted((t.signal_time, round(t.r, 9)) for t in ref) == sorted((t.signal_time, round(t.r, 9)) for t in mine)
        assert any(t.reason.startswith("chandelier stop") for t in ref), "the trail should close some trades"


def _chandelier_checks(seen):
    def check(ag, adapter, m, held):
        for t in held:
            stop = float(t.data["plan_stop"])
            prev = seen.get(t.trade_id)
            if prev is not None:   # the stop only ever tightens
                assert (stop - prev) * t.dir >= -1e-9, (t.trade_id, prev, stop)
            seen[t.trade_id] = stop
            if t.state == S.PROTECTED:   # exactly one of the trade's own stops is resting
                mine = ag._stop_cids(t)
                resting = [o for o in adapter.open_orders("SYN-USD") if o.client_order_id in mine and not o.is_terminal]
                assert len(resting) == 1, (t.trade_id, [o.client_order_id for o in resting])
    return check


def test_agent_raises_the_stop_on_the_exchange_and_never_loosens_it(tmp_path, monkeypatch):
    import test_pyramid as tp
    orig = tp.AgentConfig

    def with_chandelier(**kw):   # the harness's config, with the trail on (2 ATR: it moves often on 1h bars)
        kw["params"] = replace(kw["params"], chand_atr=2.0)
        return orig(**kw)

    for adapter_cls in (tp.PaperExecution, MainnetLikePaper):
        monkeypatch.setattr(tp, "AgentConfig", with_chandelier)
        saved = tp.PaperExecution
        tp.PaperExecution = adapter_cls
        try:
            seen: dict[str, float] = {}
            ag, adapter, _ = _run(tmp_path / adapter_cls.__name__, monkeypatch, "single", checks=_chandelier_checks(seen))
        finally:
            tp.PaperExecution = saved
            monkeypatch.setattr(tp, "AgentConfig", orig)
        moved = [r for r in ag.journal.read("paper_order") if r.get("action") == "stop moved"]
        assert moved and all(r["ok"] for r in moved)
        assert all((r["new"] - r["old"]) * (1 if r["new"] > r["old"] else -1) > 0 for r in moved)
        exits = [e for e in adapter.events if e["event"] == "exit"]
        assert exits and not [r for r in ag.journal.read("alert") if r["level"] in ("error", "critical")]


def test_agent_wakes_up_at_once_for_what_its_owner_is_waiting_for(tmp_path, monkeypatch):
    """A test request (or a test trade whose hold time is over) must not wait for the agent's 30 s turn."""
    import json as _json
    import time as _time
    ag, adapter, _ = _run(tmp_path, monkeypatch, "single", n=2100)
    assert not ag._owner_waiting()
    (ag.cfg.run_dir / "test_request.json").write_text(_json.dumps({"at": int(_time.time() * 1000)}))
    assert ag._owner_waiting()

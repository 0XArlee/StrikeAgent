"""The strategy registry (config/strategies.json): every strategy users can pick in one place, and a new entry turns
into working agents with no other change (fleet, risk cap, city, safety hold)."""

import copy
import json
import tomllib
from pathlib import Path

import pytest

from test_live import FakeSite

from smartflow import strategies
from smartflow.core.config import OFFICIAL
from smartflow.live.keypool import KeyPool

ROOT = Path(__file__).resolve().parents[1]


def test_registry_is_valid_and_its_paper_agents_match():
    default, all_ = strategies.load()
    assert default == "smartflow" and list(all_) == ["smartflow", "pyramid"]
    assert all(s.params == OFFICIAL for s in all_.values())          # both run the official configuration today
    city = tomllib.loads((ROOT / "config" / "city.toml").read_text(encoding="utf-8"))
    shown = {a["id"]: a["config"] for a in city["agent"]}
    for s in all_.values():
        assert s.paper_city_id in shown and shown[s.paper_city_id] == s.paper_config
        paper = tomllib.loads((ROOT / s.paper_config).read_text(encoding="utf-8"))
        assert paper["strategy"] == s.id and paper.get("policy", "single") == s.policy and paper["tf"] == s.timeframe
        assert {k: v for k, v in OFFICIAL.to_dict().items() if v != type(OFFICIAL)().to_dict()[k]} == paper["params"]
        assert {m["strike"] for m in paper["markets"]} >= set(s.markets_core)
    assert all_["pyramid"].policy == "pyramid" and all_["pyramid"].max_stack == 3 and all_["pyramid"].max_risk == "standard"


def _registry_with(tmp_path, monkeypatch, **extra):
    raw = json.loads((ROOT / "config" / "strategies.json").read_text(encoding="utf-8"))
    new = copy.deepcopy(raw["strategies"][1])
    new.update({"id": "trendrider", "name": "Trend Rider", "tag": "Rider", "policy": "pyramid", "max_stack": 2,
                "max_open_positions": 6, "max_risk": "conservative", "params": {"range_filter": True, "chand_atr": 3.0},
                "markets": {"core": ["BTC-USD"], "allowed": ["BTC-USD", "ETH-USD"]}, "paper": {}}, **extra)
    raw["strategies"].append(new)
    p = tmp_path / "strategies.json"
    p.write_text(json.dumps(raw), encoding="utf-8")
    monkeypatch.setattr(strategies, "REGISTRY", p)
    return new


def test_a_new_strategy_gives_working_agents_with_no_other_change(tmp_path, monkeypatch):
    from smartflow.api.city import load_live, snapshot
    from smartflow.live.fleet import Fleet, agent_config, risk_for
    _registry_with(tmp_path, monkeypatch)
    s = strategies.get("trendrider")
    assert s.runnable and s.params.chand_atr == 3.0
    link = {"userId": "u-new", "name": "Rider", "pub": "", "accountId": "a", "feeBps": 20, "risk": "assertive",
            "strategy": "trendrider", "markets": ["BTC-USD", "ETH-USD", "SOL-USD"], "status": "active"}
    cfg = agent_config(link, "mainnet", "code", 20, {"BTC-USD", "ETH-USD", "SOL-USD"}, str(tmp_path), str(tmp_path))
    # its own parameters, stacking and risk cap; only the markets it allows
    assert cfg.strategy == "trendrider" and cfg.policy == "pyramid" and cfg.max_stack == 2 and cfg.params.chand_atr == 3.0
    assert [m.strike for m in cfg.markets] == ["BTC-USD", "ETH-USD"] and cfg.risk.max_open_positions == 6
    assert risk_for(link) == 0.005                                   # assertive asked, conservative is its cap
    # the fleet starts it, and the city shows it under its strategy
    pool = KeyPool(tmp_path / "keys", bytes(32), "mainnet")
    link["pub"] = pool.generate()
    site = FakeSite([link])
    site.doc["env"] = "mainnet"
    runs = tmp_path / "runs"
    fleet = Fleet(site, pool, lambda: {"BTC-USD", "ETH-USD"}, str(runs), str(tmp_path / "data"), allow_mainnet=True,
                  start_agent=lambda cfg, signer, stop, log: stop.wait(5), log=lambda m: None)
    assert fleet.tick()["running"] == ["u-new"]
    toml = tomllib.loads((runs / "live-u-new" / "agent.toml").read_text(encoding="utf-8"))
    assert toml["strategy"] == "trendrider" and toml["policy"] == "pyramid" and toml["params"]["chand_atr"] == 3.0
    assert snapshot(load_live(runs, "mainnet")[0])["strategy"] == "trendrider"
    for r in fleet.running.values():
        r.stop.set()


def test_unknown_or_not_runnable_strategy_is_never_run_as_another(tmp_path, monkeypatch):
    from smartflow.live.fleet import Fleet, strategy_for
    _registry_with(tmp_path, monkeypatch, engine="momentum")          # an engine the agent cannot run (yet)
    with pytest.raises(ValueError):
        strategies.load(tmp_path / "strategies.json")
    _registry_with(tmp_path, monkeypatch, engine="momentum", status="soon")   # shown as coming, never started
    assert strategy_for({"strategy": "trendrider"}) is None
    assert strategy_for({"strategy": "nope"}) is None
    assert strategy_for({}).id == "smartflow"                           # older links with no strategy: the default
    pool = KeyPool(tmp_path / "keys", bytes(32), "testnet")
    link = {"userId": "u-x", "name": "X", "pub": pool.generate(), "accountId": "a", "feeBps": 20, "risk": "standard",
            "strategy": "trendrider", "markets": ["BTC-USD"], "status": "active"}
    fleet = Fleet(FakeSite([link]), pool, lambda: {"BTC-USD"}, str(tmp_path / "runs"), str(tmp_path / "data"),
                  start_agent=lambda cfg, signer, stop, log: stop.wait(5), log=lambda m: None)
    assert fleet.tick()["running"] == []

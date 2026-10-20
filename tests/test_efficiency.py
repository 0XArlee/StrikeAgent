"""The host must stay quiet as users join: shared candle downloads, one positions call per turn, and no city rebuild
when nothing changed."""

import threading
import time

from test_pyramid import _run

from smartflow.agent import feeds
from smartflow.api.city import CityAgent
from smartflow.api.push import files_signature


def test_every_agent_shares_one_candle_download(monkeypatch):
    calls = []

    def fake_get(url, params):
        calls.append(params["symbol"])
        time.sleep(0.05)   # a slow answer: the others must wait for it, not download again
        return [[0, "1", "2", "0.5", "1.5", "10"]]

    monkeypatch.setattr(feeds, "get_json", fake_get)
    monkeypatch.setattr(feeds, "_CACHE", {})
    threads = [threading.Thread(target=feeds.fetch_closed, args=("BTCUSDT", "240", 20, 10 ** 13)) for _ in range(25)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    feeds.fetch_closed("ETHUSDT", "240", 20, 10 ** 13)
    assert calls == ["BTCUSDT", "ETHUSDT"]   # 25 agents at the same candle close: one download per market


def test_reconcile_reads_every_position_in_one_call(tmp_path, monkeypatch):
    ag, adapter, _ = _run(tmp_path, monkeypatch, "single", n=2050)
    counts = {"all": 0, "one": 0}
    real_all, real_one = adapter.all_positions, adapter.position
    monkeypatch.setattr(adapter, "all_positions", lambda: counts.__setitem__("all", counts["all"] + 1) or real_all())
    monkeypatch.setattr(adapter, "position", lambda s: counts.__setitem__("one", counts["one"] + 1) or real_one(s))
    ag.reconcile()
    assert counts["all"] == 1 and counts["one"] == 0


def test_the_city_is_rebuilt_only_when_an_agents_files_change(tmp_path):
    run = tmp_path / "run"
    run.mkdir()
    cfg = tmp_path / "a.toml"
    cfg.write_text("name = 'a'")
    (run / "journal.jsonl").write_text('{"kind": "analysis"}\n')
    agents = [CityAgent("a", "A", cfg, run)]
    first = files_signature(agents)
    assert files_signature(agents) == first                     # nothing changed: no rebuild
    (run / "journal.jsonl").write_text('{"kind": "analysis"}\n{"kind": "fill"}\n')
    assert files_signature(agents) != first                     # the agent wrote something: rebuild

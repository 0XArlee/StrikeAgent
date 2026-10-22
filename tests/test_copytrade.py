"""Strike's copy trading for Strike City: the history kept beyond Strike's 30 days, what changed in a lead's positions,
who copies whom and how it went, and the document the city reads."""

from smartflow.copytrade.service import CopyService, app_url, recommended
from smartflow.copytrade.store import DAY, Store

NOW = 1_792_600_000_000


def trader(addr, platform="strike", score="90", direction="copy", curve=None, roi30="0.2"):
    return {"address": addr, "platform": platform, "blockchain_address": "addr1" + addr if platform == "strike" else None,
            "account_value": "1000", "pnl": {"30d": "200", "all": "500"}, "roi": {"30d": roi30}, "volume": {"30d": "10000"},
            "copy_score": score, "copy_scores": {"30d": score}, "recommended_direction": direction, "top_assets": [{"asset": "BTC"}],
            "copy_amount_coverage": [{"copy_amount": "500", "coverage": "0.5"}, {"copy_amount": "1000", "coverage": "0.85"}],
            "equity_curve_30d": curve or [[NOW - 2 * DAY, "900"], [NOW - DAY, "950"]], "last_traded_at_ms": NOW - 3600_000}


def test_equity_history_keeps_growing_past_strikes_30_days(tmp_path):
    s = Store(tmp_path / "c.db")
    s.add_traders([trader("a", curve=[[NOW - 40 * DAY, "800"], [NOW - 39 * DAY, "820"]])], NOW - 10 * DAY, {})
    s.add_traders([trader("a", curve=[[NOW - 2 * DAY, "900"], [NOW - DAY, "950"]])], NOW, {"a": 3})
    eq = s.equity("a")
    assert [v for _, v in eq] == [800, 820, 900, 950]          # the old days stay when Strike's window moves on
    assert s.history_days() == 40
    row = s.db.execute("SELECT followers FROM daily WHERE address = 'a' ORDER BY day DESC").fetchone()
    assert row["followers"] == 3


def test_position_changes_become_events():
    s = Store(":memory:")
    assert s.set_positions("a", [{"market": "BTC-USD", "side": "long", "size": 1.0, "entry": 100}], NOW) == []   # first look
    ev = s.set_positions("a", [{"market": "BTC-USD", "side": "short", "size": 1.0, "entry": 99},
                               {"market": "ETH-USD", "side": "long", "size": 2.0, "entry": 10}], NOW + 60_000)
    assert sorted((e["market"], e["kind"]) for e in ev) == [("BTC-USD", "flip"), ("ETH-USD", "open")]
    ev = s.set_positions("a", [{"market": "BTC-USD", "side": "short", "size": 2.0, "entry": 99}], NOW + 120_000)
    assert sorted((e["market"], e["kind"]) for e in ev) == [("BTC-USD", "add"), ("ETH-USD", "close")]
    assert len(s.events("a")) == 4


def test_copiers_results_per_lead():
    s = Store(":memory:")
    s.add_subs([{"follower": {"account_id": "f1"}, "lead_account_id": "a", "status": "active", "created_at": 1, "realized_pnl": "120",
                 "total_volume": "1000", "copy_mode": "fixed_ratio"},
                {"follower": {"account_id": "f2"}, "lead_account_id": "a", "status": "stopped", "created_at": 2, "realized_pnl": "-300",
                 "total_volume": "500"}], NOW)
    s.add_subs([{"follower": {"account_id": "f1"}, "lead_account_id": "a", "status": "stopped", "created_at": 1, "realized_pnl": "150",
                 "total_volume": "1200"}], NOW + 60_000)   # the same subscription later: updated, not added
    f = s.followers()["a"]
    assert f == {"active": 0, "ever": 2, "pnl": -150.0, "volume": 1700.0}


def test_document_for_the_city(tmp_path):
    calls = []

    def get(path, params=None):
        calls.append(path)
        if path == "/v2/copy/discover":
            if params["platform"] == "strike":
                return {"items": [trader("s1", score="95"), trader("s2", score="60", direction="none"), trader("s3", score="99")]}
            return {"items": [trader("0xhl", platform="hyperliquid", score="80")]}
        if path == "/v2/copy/leaderboard":
            return {"entries": [{"follower": {"account_id": "f1"}, "lead_account_id": "s1", "status": params["status"], "created_at": 5,
                                 "realized_pnl": "50", "total_volume": "900", "copy_mode": "fixed_amount", "platform": "strike"}]
                    if params["status"] == "active" else []}
        if path == "/v2/positions":
            return {"positions": [{"symbol": "BTC-USD", "size": "-0.5", "entry_price": "80000", "upnl": "12", "leverage": 5}]}
        if path == "/v2/account":
            return {"name": {"s1": "Beatrice", "s3": "Copy 1"}.get(params["account_id"]), "parent_account_id": "m1" if params["account_id"] == "s1" else None}
        if path == "/v2/copy/subscriptions":   # s3 copies someone: it is left out
            return {"subscriptions": [{"lead_account_id": "0xwhale"}] if params["account_id"] == "s3" else []}
        if path.endswith("copy-trading-summary"):
            return {"open_interest_usd": "1000", "total_allocated_usd": "2000"}
        if path.endswith("copy-trading-volumes"):
            return {"total_volume_daily": [[NOW - DAY, "BTC-USD", 100], [NOW - DAY, "ETH-USD", 50]]}
        return {}

    hl = lambda user: {"assetPositions": [{"position": {"coin": "ETH", "szi": "2", "entryPx": "3000", "unrealizedPnl": "5", "leverage": {"value": 3}}}]}
    svc = CopyService(Store(":memory:"), tmp_path / "copy.json", get=get, hl=hl, log=lambda m: None)
    s = svc.cycle(NOW)
    assert not s["errors"] and s["written"] and (tmp_path / "copy.json").exists()
    doc = svc.document(NOW)
    ids = [x["id"] for x in doc["traders"]]
    assert sorted(ids) == ["0xhl", "s1"]                             # "none" direction is not offered
    s1 = next(x for x in doc["traders"] if x["id"] == "s1")
    hl1 = next(x for x in doc["traders"] if x["id"] == "0xhl")
    assert s1["name"] == "Beatrice" and s1["subOf"] == "?" and s1["url"].endswith("/public-portfolio/s1")   # by account id
    assert doc["copyingOthers"] == [{"id": "s3", "name": "Copy 1", "copies": ["0xwhale"]}]
    assert s1["walks"] and s1["city"] is not None and s1["metrics"]["days"] == 0 and set(s1["parts"]) == {"strike", "copiers", "fall", "record", "size"}
    assert s1["copiers"]["active"] == 1 and s1["positions"][0] == {"market": "BTC-USD", "side": "short", "size": 0.5, "entry": 80000,
                                                                   "upnl": 12, "leverage": 5}
    assert s1["recommended"] == 1000 and s1["url"].endswith("/public-portfolio/s1")
    assert hl1["positions"][0]["market"] == "ETH-USD" and hl1["url"].endswith("?platform=hyperliquid")
    assert doc["strike"]["allocated"] == 2000 and doc["strike"]["volume30d"] == 150
    assert doc["copiers"][0]["follower"] == "f1"
    assert not svc.cycle(NOW + 30_000)["written"]                    # nothing new: the file stays


def test_helpers():
    assert app_url("hyperliquid", "0xabc", None).endswith("/public-portfolio/0xabc?platform=hyperliquid")
    assert app_url("strike", "019d-sub", "addr1parent").endswith("/public-portfolio/019d-sub")   # never the main account's wallet
    assert recommended([{"copy_amount": "1", "coverage": "0.1"}]) is None


def test_drawdown_and_up_days_come_from_every_day_kept():
    s = Store(":memory:")
    curve = [[NOW + i * DAY, str(v)] for i, v in enumerate([0, 100, 50, 150, 120])]
    eq = [[NOW + i * DAY, "1000"] for i in range(5)]
    it = {**trader("a"), "pnl_curve_30d": curve, "equity_curve_30d": eq}
    s.add_traders([it], NOW + 5 * DAY, {})
    m = s.metrics("a")
    assert m == {"days": 5, "dd": 0.05, "upDays": 0.5}                # 100 -> 50 on 1000 of equity; 2 of 4 days up


def test_city_score_weighs_what_copiers_made():
    score = lambda copiers, metrics, value=None: CopyService.city_score(CopyService.score_parts(90, copiers, metrics, value))
    good = score({"n": 10, "won": 9}, {"dd": 0.05, "days": 30})
    bad = score({"n": 10, "won": 1}, {"dd": 0.05, "days": 30})
    unknown = score({"n": 1, "won": 0}, {"dd": 0.05, "days": 30})
    assert good > unknown > bad and CopyService.city_score(CopyService.score_parts(None, {}, {}, None)) is None


def test_city_score_trusts_long_records_and_real_accounts_more():
    parts = CopyService.score_parts(80, {"n": 0, "won": 0}, {"dd": 0.0, "days": 7}, 762.0)
    assert parts["copiers"] is None and parts["size"] == 0 and parts["record"] == round(100 * 7 / 60, 1)
    tiny_new = CopyService.city_score(parts)
    big_old = CopyService.city_score(CopyService.score_parts(80, {"n": 0, "won": 0}, {"dd": 0.0, "days": 60}, 250_000.0))
    assert big_old > tiny_new
    # a part not known yet is left out: the others share its weight
    assert CopyService.city_score({"strike": 80, "copiers": None, "fall": None, "record": None, "size": None}) == 80


def test_evidence_scores_each_copy_with_what_came_before_it(tmp_path):
    s = Store(":memory:")
    s.add_traders([trader("good", score="60"), trader("bad", score="95")], NOW, {})
    entries = []
    for i in range(20):   # the good lead's copies mostly win, the bad one's lose: Strike's score says the opposite
        entries.append({"follower": {"account_id": f"g{i}"}, "lead_account_id": "good", "created_at": NOW - (40 - i) * DAY,
                        "status": "stopped", "realized_pnl": "10" if i % 5 else "-5", "copy_mode": "fixed_ratio"})
        entries.append({"follower": {"account_id": f"b{i}"}, "lead_account_id": "bad", "created_at": NOW - (40 - i) * DAY,
                        "status": "stopped", "realized_pnl": "-10" if i % 5 else "5", "copy_mode": "fixed_ratio"})
    s.add_subs(entries, NOW)
    svc = CopyService(s, tmp_path / "copy.json", get=lambda *a, **k: {}, hl=lambda u: {}, log=lambda *a: None)
    ev = svc.evidence(NOW)
    assert ev["copies"] == 40 and ev["leads"] == 2 and ev["base"] == 0.5
    assert ev["auc"]["strike"] < 0.5 < ev["auc"]["city"]          # what earlier copiers made beats the copy score here
    assert ev["top"]["city"] > ev["top"]["strike"]
    assert svc.evidence(NOW + 60_000) is ev                       # once an hour

"""The audit trail: tamper-evident logs of everything the agents, the fleet and the site did, and the report that
answers a claim from them."""

import json

from test_live import FakeSite

from smartflow import audit
from smartflow.agent.journal import Journal
from smartflow.live.keypool import KeyPool


def _lines(p):
    return p.read_text(encoding="utf-8").splitlines()


def _put(p, lines):   # the exact bytes, as an edit on the host would leave them
    p.write_bytes(("\n".join(lines) + "\n").encode("utf-8"))


def test_chain_detects_a_changed_removed_or_moved_line(tmp_path):
    p = tmp_path / "j.jsonl"
    log = audit.AuditLog(p)
    for i in range(5):
        log.write("note", i=i, text="ünïcode ok")
    v = audit.verify(p)
    assert v["ok"] and v["chained"] == 5 and v["head"][0] == 4 and not v["sealed"]
    good = _lines(p)
    for bad in (good[:2] + [good[2].replace('"i": 2', '"i": 7')] + good[3:],   # changed
                good[:2] + good[3:],                                          # removed
                good[:1] + [good[2], good[1]] + good[3:]):                    # moved
        _put(p, bad)
        assert not audit.verify(p)["ok"]
    # the last line removed still verifies on its own: the head the site kept is what catches it (report test)
    _put(p, good[:-1])
    assert audit.verify(p)["ok"] and audit.verify(p)["head"][0] == 3


def test_older_lines_are_sealed_by_the_first_chained_one(tmp_path):
    p = tmp_path / "journal.jsonl"
    _put(p, ['{"ts": "2026-10-19T00:00:00+00:00", "kind": "analysis"}', '{"ts": "2026-10-19T04:00:00+00:00", "kind": "analysis"}'])
    audit.AuditLog(p).write("note")
    audit.AuditLog(p).write("note")   # another writer in the same process continues the same chain
    v = audit.verify(p)
    assert v["ok"] and v["legacy"] == 2 and v["sealed"] == [3] and v["chained"] == 2
    lines = _lines(p)
    _put(p, [lines[0].replace("00:00:00", "01:00:00")] + lines[1:])
    assert not audit.verify(p)["ok"]   # the older lines cannot be changed either


def test_a_line_cut_by_a_crash_does_not_break_the_next_writes(tmp_path):
    p = tmp_path / "j.jsonl"
    audit.AuditLog(p).write("note", i=1)
    with p.open("a", encoding="utf-8", newline="") as f:
        f.write('{"ts": "2026-10-20T00:00:00+00:00", "kind": "no')   # the process died mid-line
    audit.forget(p)                                                  # a new process
    audit.AuditLog(p).write("note", i=2)
    v = audit.verify(p)
    assert v["ok"] and v["loose"] == [2] and v["sealed"] == [3] and v["chained"] == 2


def test_the_journal_is_chained_and_still_redacts(tmp_path):
    p = tmp_path / "journal.jsonl"
    j = Journal(p, "autonomous", "abc")
    j.write("live_order", action="entry", response={"order_id": 1}, signature="deadbeef")
    j.alert("warning", "something")
    recs = j.read()
    assert [r["kind"] for r in recs] == ["live_order", "alert"] and recs[0]["signature"] == "<redacted>"
    assert recs[1]["prev"] == recs[0]["hash"] and audit.verify(p)["ok"]


def test_every_call_that_changes_something_on_strike_is_traced(monkeypatch):
    from smartflow.net import HttpError
    from smartflow.strike import client as sc
    from smartflow.strike.auth import ApiWalletSigner
    from smartflow.strike.client import BuilderFee, StrikeClient
    answers = iter([(200, {"order_id": 7}, {}), (200, {"positions": []}, {}), HttpError(400, '{"error":"bad size"}', "u"),
                    TimeoutError("read timed out"), HttpError(503, "down", "u")])

    def fake(method, url, **kw):
        a = next(answers)
        if isinstance(a, Exception):
            raise a
        return a

    monkeypatch.setattr(sc, "request_json", fake)
    c = StrikeClient(sc.MAINNET, ApiWalletSigner("11" * 32), BuilderFee("SmartFlowAgent-EdgeCraft", 20))
    seen = []
    c.trace = seen.append
    c.create_order({"symbol": "BTC-USD", "side": "buy", "size": "0.0001"})
    c.positions()                                  # a read that works: not traced
    for call in (lambda: c.create_order({"symbol": "BTC-USD"}), lambda: c.cancel_order("BTC-USD", 9), lambda: c.positions()):
        try:
            call()
        except Exception:
            pass
    assert [(r["method"], r["status"]) for r in seen] == [("POST", 200), ("POST", 400), ("DELETE", None), ("GET", 503)]
    first = seen[0]
    assert first["body"]["symbol"] == "BTC-USD" and first["response"] == {"order_id": 7} and first["builder_fee_bps"] == 20
    assert "bad size" in seen[1]["error"] and "timed out" in seen[2]["error"]
    assert not any("signature" in json.dumps(r).lower() for r in seen)   # the signing headers are never kept


def test_the_fleet_records_what_it_did_and_every_fill_and_balance_change(tmp_path):
    from smartflow.live.fleet import Fleet
    pool = KeyPool(tmp_path / "keys", bytes(32), "testnet")
    pub = pool.generate()
    link = {"userId": "u-3", "name": "Ana", "pub": pub, "accountId": "acc-3", "feeBps": 20, "risk": "standard",
            "markets": ["BTC-USD"], "status": "active", "strategy": "smartflow"}

    class Site(FakeSite):
        rows = [{"id": 1, "time": 1792458000000, "user_id": "u-3", "action": "create", "ok": 1, "message": "Strike says…",
                 "signature": "84a4…", "detail": {"name": "Ana"}}]

        def audit(self, after):
            return {"rows": [r for r in self.rows if r["id"] > after]}

    fill = {"time": 1792458100000, "market": "BTC-USD", "side": "buy", "price": 81900.0, "size": 0.0001, "fee": 0.004,
            "pnl": 0.0, "role": "taker", "id": 11, "order": 5}
    accounts = iter([{"balance": 100.0, "equity": 100.0, "positions": [], "orders": [], "fills": []},
                     {"balance": 100.0, "equity": 100.0, "positions": [], "orders": [], "fills": []},   # nothing changed
                     {"balance": 99.976, "equity": 99.99, "positions": [{"market": "BTC-USD", "side": "long", "size": 0.0001,
                                                                          "entry": 81900.0}], "orders": [], "fills": [fill]},
                     {"balance": 89.976, "equity": 89.99, "positions": [{"market": "BTC-USD", "side": "long", "size": 0.0001,
                                                                          "entry": 81900.0}], "orders": [], "fills": [fill]}])
    site = Site([link])
    runs = tmp_path / "runs"
    fleet = Fleet(site, pool, lambda: {"BTC-USD"}, str(runs), str(tmp_path / "data"),
                  start_agent=lambda cfg, signer, stop, log: stop.wait(5), log=lambda m: None,
                  account_reader=lambda env, signer: next(accounts))
    for _ in range(4):
        fleet.tick()
        fleet._acct_at["u-3"] = 0.0
    site.doc["links"] = [dict(link, status="paused")]
    fleet.tick()
    run = runs / "live-u-3"
    host = [r for r in audit.read(run / "journal.jsonl") if r["kind"] == "host"]
    assert [r["action"] for r in host] == ["start", "stop"]
    assert host[0]["link"]["accountId"] == "acc-3" and host[0]["builder_code"] == "sf-test" and host[0]["fee_bps"] == 20
    assert host[1]["reason"] == "the owner stopped, paused or deleted it on the site"
    assert [f["id"] for f in audit.read(run / "fills.jsonl")] == [11]                      # once, however often it is read
    acct = audit.read(run / "account.jsonl")
    assert [a["balance"] for a in acct] == [100.0, 99.976, 89.976]                          # only when something changed
    assert acct[2]["balance_change"] == -10.0 and acct[2]["new_fills"] == 0                 # money left with no fill
    web = audit.read(runs / "web-audit-testnet.jsonl")
    assert [(r["kind"], r["id"], r["action"]) for r in web] == [("web", 1, "create")]      # copied once
    for p in (run / "journal.jsonl", run / "fills.jsonl", run / "account.jsonl", runs / "web-audit-testnet.jsonl"):
        assert audit.verify(p)["ok"], p


def test_the_report_tells_the_whole_story_and_checks_the_sites_copy(tmp_path):
    from smartflow.live import audit_report as ar
    runs = tmp_path / "runs"
    run = runs / "live-u-4"
    web = audit.AuditLog(runs / "web-audit-mainnet.jsonl")
    signed = {"message": "Strike: authorise SmartFlowAgent-EdgeCraft at 0.2%…", "signature": "84a4…", "ip": "1.2.3.0/24", "country": "ES"}
    web.write("web", id=1, time=1792458000000, user_id="u-4", address="addr1qx…", action="create", ok=1,
              detail={"name": "Ana", "strategy": "smartflow", "markets": ["BTC-USD"], "risk": "standard", "live": True}, **signed)
    web.write("web", id=2, time=1792458000000, user_id="u-4", address="addr1qx…", action="live_connect", ok=1,
              detail={"env": "mainnet", "accountId": "acc", "builderCode": "SmartFlowAgent-EdgeCraft", "feeBps": 20, "pub": "ab12…"},
              **signed)
    j = Journal(run / "journal.jsonl", "autonomous", "abc")
    j.write("signal", market="BTC-USD", trade_id="t1", dir=1, close=81900, atr=700, stop=80850, rel_vol=2.1)
    j.write("decision", trade_id="t1", accepted=True, reasons=[], summary="0.0002 BTC-USD, risk 0.50 $")
    j.write("strike_call", method="POST", url="https://api.strikefinance.org/v2/order/strategy",
            body={"symbol": "BTC-USD", "side": "buy"}, builder_fee_bps=20, status=200, response={}, ms=120)
    j.write("live_order", trade_id="t1", market="BTC-USD", action="entry", ok=True, client_order_id="sf-1-en")
    j.write("fill", trade_id="t1", market="BTC-USD", entry=81900, qty=0.0002)
    now = audit.read(run / "journal.jsonl")[-1]["ts"]
    t = ar._ms(now)
    for f in ({"time": t, "market": "BTC-USD", "side": "buy", "price": 81900, "size": 0.0002, "fee": 0.008, "pnl": 0},
              {"time": t + 3_600_000, "market": "ETH-USD", "side": "sell", "price": 3000, "size": 0.01, "fee": 0.01, "pnl": 0}):
        audit.AuditLog(run / "fills.jsonl").write("fill", **f)
    doc = ar.build(runs, ar.uid_for("u-4", runs, "mainnet"), "mainnet")
    srcs = {x["src"] for x in doc["timeline"]}
    assert {"web", "agente", "strike", "cuenta"} <= srcs
    texts = [x["text"] for x in doc["timeline"]]
    assert any("aprobó la comisión de builder SmartFlowAgent-EdgeCraft de 20 bps" in x for x in texts)
    assert any(x.startswith("Ejecución en la cuenta: BUY") and "del agente" in x for x in texts)
    assert any(x.startswith("Ejecución en la cuenta: SELL") and "FUERA del agente" in x for x in texts)
    assert doc["trades"][0]["trade"] == "t1" and doc["trades"][0]["decision"] == "aprobada"
    assert len(doc["consents"]) == 1 and doc["consents"][0]["message"].startswith("Strike: authorise")   # one signature
    assert all(v["ok"] for v in doc["integrity"].values())
    md = ar.markdown(doc)
    assert "Todo intacto" in md and "Strike: authorise SmartFlowAgent-EdgeCraft" in md
    # the site kept the head of the journal: a rewritten history no longer matches it
    head = audit.head(run / "journal.jsonl")
    anchors = {"live-u-4/journal.jsonl": [[head[0], head[1]]]}
    assert ar.build(runs, "u-4", "mainnet", anchors=anchors)["anchors"]["journal"] == [{"seq": head[0], "ok": True}]
    lines = _lines(run / "journal.jsonl")
    _put(run / "journal.jsonl", lines[:-1])   # the last line removed
    doc = ar.build(runs, "u-4", "mainnet", anchors=anchors)
    assert doc["anchors"]["journal"] == [{"seq": head[0], "ok": False}] and "ATENCIÓN" in ar.markdown(doc)
    assert ar.uid_for("addr1qxyz", runs, "mainnet").startswith("u-")


def test_the_agent_records_what_it_starts_with_but_never_a_key(tmp_path, monkeypatch):
    from test_pyramid import _run
    ag, adapter, _ = _run(tmp_path, monkeypatch, "single", n=2050)
    w = ag.started_with()
    assert w["markets"] and w["params"]["chand_atr"] is not None and w["risk"]["risk_per_trade"] > 0
    json.dumps(w, default=str)
    assert not any(k in json.dumps(w, default=str).lower() for k in ("private", "secret", "seed"))

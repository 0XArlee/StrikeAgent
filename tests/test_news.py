"""The News Tower's data (smartflow/news): feeds, dedupe, reactions measured on Strike, the reading (NET), the
scoreboard and the model's answers checked. No network: feeds, Strike and the model are fakes."""

import json

from smartflow.news import score
from smartflow.news.classify import Haiku
from smartflow.news.feeds import Headline, headline_id, parse, title_markets
from smartflow.news.reaction import MIN, Prices, measure
from smartflow.news.service import NewsService, as_of
from smartflow.news.store import Store

H = 3_600_000
NOW = 1_792_600_000_000 // MIN * MIN

RSS = b"""<?xml version="1.0"?><rss version="2.0"><channel><title>x</title>
<item><title>Fed holds rates steady - Reuters</title><link>https://news.google.com/a</link>
<pubDate>Wed, 21 Oct 2026 14:00:00 GMT</pubDate><source url="https://reuters.com">Reuters</source></item>
<item><title><![CDATA[Solana &amp; <b>ETF</b> inflows jump]]></title><link>https://example.com/sol</link>
<pubDate>Wed, 21 Oct 2026 15:30:00 +0000</pubDate></item>
<item><title>No link</title></item>
<item><title>Plain http link</title><link>http://example.com/x</link></item>
</channel></rss>"""

ATOM = b"""<?xml version="1.0"?><feed xmlns="http://www.w3.org/2005/Atom"><title>x</title>
<entry><title>Ethereum upgrade goes live</title><link href="https://example.com/eth"/><published>2026-10-21T12:00:00Z</published></entry>
</feed>"""

FEED = {"id": "gn-btc", "name": "Google News", "url": "https://news.google.com/rss/x", "markets": ["BTC-USD"]}


def test_rss_and_atom():
    a = parse(RSS, FEED)
    assert [h.title for h in a] == ["Fed holds rates steady", "Solana & ETF inflows jump"]
    assert a[0].source == "Reuters" and a[1].source == "Google News"
    assert a[0].published == 1792591200000
    assert a[1].markets == ["BTC-USD", "SOL-USD"]   # the feed's market first, then the title's
    e = parse(ATOM, {"id": "x", "name": "X", "markets": []})
    assert e[0].url == "https://example.com/eth" and e[0].markets == ["ETH-USD"] and e[0].published == 1792584000000


def test_title_markets():
    assert title_markets("Bitcoin and ETH slide") == ["BTC-USD", "ETH-USD"]
    assert title_markets("Prices near a record") == []           # "near" is not NEAR
    assert title_markets("NEAR Protocol and Cardano") == ["ADA-USD", "NEAR-USD"]
    assert title_markets("consolidation") == []                  # not SOL


def h(title, t, markets=(), feed="f"):
    return Headline(headline_id(title), title, "https://x/" + title, "Src", feed, t, list(markets))


def test_store_dedupe_and_times():
    s = Store(":memory:")
    n = s.add([h("Fed holds rates steady as inflation cools", NOW - H),
               h("Fed holds rates steady as inflation cools", NOW - H),             # same id
               h("Fed holds rates steady as inflation cools down", NOW - 2 * H),    # same story
               h("Old story", NOW - 80 * H),                                        # out of the window
               h("From the future", NOW + 3 * H)], NOW, 72 * H)
    assert n == 2
    rows = {r["title"]: r for r in s.window(NOW - 72 * H)}
    assert rows["From the future"]["t"] == NOW            # a time in the future: when it was seen


def fake_klines(prices):
    """prices: {market: f(minute open time) -> close}"""
    calls = []

    def k(market, end, limit):
        calls.append((market, end, limit))
        return [[o, "0", "0", "0", str(prices[market](o))] for o in range(end - (limit - 1) * MIN, end + MIN, MIN)]
    return k, calls


def test_reaction():
    t0 = NOW - 2 * H
    k, calls = fake_klines({"BTC-USD": lambda o: 100.0 + (o - t0) / MIN * 0.01})   # +0.01 a minute
    p = Prices(k)
    p.cover("BTC-USD", t0 - 15 * MIN, NOW)
    assert len(calls) == 1
    r = measure(p, "BTC-USD", t0, NOW)
    assert r["p0"] == 100.0 - 0.01 and r["done"]           # the close of the minute before
    assert abs(r["r60"] - ((100 + 0.59) / 99.99 - 1) * 100) < 1e-3
    young = measure(p, "BTC-USD", NOW - 20 * MIN, NOW)
    assert young["r15"] is not None and young["r60"] is None and not young["done"]
    p.cover("BTC-USD", NOW - 60 * H, NOW)                  # older: fetched backwards, 25 h a request
    assert len(calls) == 3


def item(id_, age_h, s, impact="high", cat="macro", markets=("BTC-USD",), broad=False, r60=None):
    return {"id": id_, "t": NOW - int(age_h * H), "title": id_, "hint": [], "react": {"r60": r60} if r60 is not None else None,
            "cls": {"markets": list(markets), "broad": broad, "cat": cat, "score": s, "impact": impact, "conf": 0.8, "relevant": True, "es": id_}}


def test_weights():
    a = item("a", 6, 50)
    assert abs(score.weight(a, "BTC-USD", NOW) - 0.5) < 1e-9               # one half-life
    assert abs(score.weight(item("b", 0, 50, "low"), "BTC-USD", NOW) - 0.3) < 1e-9
    assert abs(score.weight(item("c", 0, 50, r60=-0.4), "BTC-USD", NOW) - 0.3) < 1e-9   # the market went against it
    assert score.weight(item("d", 0, 50, r60=0.02), "BTC-USD", NOW) == 0.3             # flat is no confirmation
    assert score.weight(item("e", 0, 50, r60=0.3), "BTC-USD", NOW) == 1.0
    assert score.weight(item("f", 0, 50, markets=(), broad=True), "ETH-USD", NOW) == 0.5   # the whole market, for an alt


def test_reading_blend_and_labels():
    xs = [item("a", 1, 80), item("b", 30, -40, "medium")]
    rd = score.reading(xs, "BTC-USD", NOW)
    wa, wb = 0.5 ** (1 / 6), 0.6 * 0.5 ** 5
    n72 = (wa * 80 - wb * 40) / (wa + wb)
    assert abs(rd["net72"] - round(n72, 1)) < 0.05 and rd["netHigh"] == 80.0
    assert abs(rd["net"] - round(0.6 * n72 + 0.4 * 80, 1)) < 0.05 and rd["label"] == "very_bullish"
    assert score.label(10) == "neutral" and score.label(-20) == "bearish"
    assert rd["drivers"]["up"][0]["cat"] == "macro" and rd["drivers"]["up"][0]["top"] == "a"


def test_whipsaw_and_alts():
    xs = [item("a", 1, 70), item("b", 2, -60), item("c", 1, 30, markets=("ETH-USD",))]
    assert score.reading(xs, "BTC-USD", NOW)["whipsaw"]
    assert not score.reading([item("a", 1, 70), item("b", 2, -10)], "BTC-USD", NOW)["whipsaw"]
    eth = score.reading(xs, "ETH-USD", NOW)
    assert eth["net"] is None and eth["own"] == 1                     # an alt needs a couple of its own headlines
    eth = score.reading(xs + [item("d", 1, 40, markets=("ETH-USD",))], "ETH-USD", NOW)
    assert eth["net"] is not None and eth["own"] == 2
    skip = item("z", 1, 90)
    skip["cls"]["relevant"] = False
    assert score.reading([skip], "BTC-USD", NOW)["net"] is None


def test_following_and_scoreboard():
    xs = [item(f"m{i}", 1, 50, cat="macro", r60=0.4) for i in range(3)] + [item(f"r{i}", 1, -50, cat="regulation", r60=0.2) for i in range(3)]
    f = score.following(xs, NOW)
    assert f[0] == {"cat": "macro", "follow": 0.4, "n": 3} and f[1]["follow"] == -0.2
    rows = [{"market": "BTC-USD", "net": 30, "ret4": 0.5}, {"market": "BTC-USD", "net": -40, "ret4": 0.2},
            {"market": "BTC-USD", "net": 5, "ret4": -0.1}]
    assert score.scoreboard(rows)["BTC-USD"] == {"readings": 3, "called": 2, "hits": 1, "up": 2}


def test_as_of_hides_later_reactions():
    xs = [item("a", 0.5, 50, r60=0.3), item("b", 3, 50, r60=0.3)]
    xs[0]["t"] = NOW - 30 * MIN
    known = as_of(xs, NOW)
    assert known[0]["react"]["r60"] is None and known[1]["react"]["r60"] == 0.3
    assert xs[0]["react"]["r60"] == 0.3                      # the original is untouched
    assert as_of(xs, NOW - H) == [xs[1]] or as_of(xs, NOW - H)[0]["id"] == "b"


def tool_answer(items):
    return {"content": [{"type": "tool_use", "name": "classify_headlines", "input": {"items": items}}], "stop_reason": "tool_use"}


def test_haiku_answers_are_checked():
    sent = []

    def post(payload):
        sent.append(payload)
        return tool_answer([
            {"id": "a", "markets": ["BTC", "DOGE"], "broad": False, "category": "etf", "score": 140, "impact": "high",
             "confidence": 1.4, "relevant": True, "es": "Entradas récord en los ETF"},
            {"id": "b", "markets": [], "broad": True, "category": "weather", "score": 10, "impact": "low", "confidence": 0.5, "relevant": True, "es": "x"},
            {"id": "zzz", "markets": [], "broad": True, "category": "macro", "score": 10, "impact": "low", "confidence": 0.5, "relevant": True, "es": "x"},
        ])
    got = Haiku("k", post=post).classify([{"id": "a", "title": "ETF inflows", "source": "S"}, {"id": "b", "title": "?", "source": "S"}])
    assert set(got) == {"a"}                                   # a bad category and an id it was not asked about: out
    assert got["a"]["markets"] == ["BTC-USD"] and got["a"]["score"] == 100 and got["a"]["conf"] == 1.0
    assert sent[0]["tool_choice"] == {"type": "tool", "name": "classify_headlines"} and "ETF inflows" in sent[0]["messages"][0]["content"]

    def post_usage(payload):
        return {**tool_answer([]), "usage": {"input_tokens": 1200, "output_tokens": 300}}
    hk = Haiku("k", post=post_usage)
    hk.classify([{"id": "a", "title": "x", "source": "S"}])
    assert hk.tokens == [1200, 300]                           # what it costs, for the service's log


class FakeModel:
    model = "fake"

    def classify(self, items):
        return {i["id"]: {"markets": ["BTC-USD"], "broad": False, "cat": "etf", "score": 60, "impact": "high", "conf": 0.9,
                          "relevant": True, "es": "es: " + i["title"], "model": "fake"} for i in items}

    def flip(self, market, reading, headlines, events):
        return {"en": ["ETF outflows"], "es": ["Salidas de los ETF"]}


def test_service_cycle(tmp_path):
    feed_xml = RSS.replace(b"Wed, 21 Oct 2026 14:00:00 GMT", b"Wed, 21 Oct 2026 17:30:00 GMT")
    sources = {"every_s": 300, "keep_h": 72, "feeds": [FEED]}
    k, _ = fake_klines({m: (lambda o: 100.0 + (o % (7 * MIN)) / MIN) for m in ["BTC-USD", "ETH-USD", "SOL-USD"]})
    svc = NewsService(Store(tmp_path / "n.db"), tmp_path / "news.json", classifier=FakeModel(), klines=k, sources=sources,
                      fetcher=lambda url: feed_xml, log=lambda *a: None)
    now = 1792591200000 + 5 * H   # 2026-10-21 19:00 UTC: the headlines are 1.5 and 3.5 h old
    s = svc.cycle(now)
    assert s["added"] == 2 and s["classified"] == 2 and s["measured"] == 2 and s["written"]
    doc = json.loads((tmp_path / "news.json").read_text(encoding="utf-8"))
    assert doc["v"] == 1 and doc["classifier"]["on"] and doc["markets"]["BTC-USD"]["label"] in ("bullish", "very_bullish")
    assert doc["markets"]["BTC-USD"]["flip"] == {"en": ["ETF outflows"], "es": ["Salidas de los ETF"]}
    assert all(x["es"].startswith("es: ") and x["r60"] is not None for x in doc["headlines"])
    assert doc["feeds"][0]["ok"] and doc["events"]["next"]
    assert svc.store.last_reading_t() == now // H * H        # the hourly reading for the scoreboard
    assert svc.cycle(now + 60_000)["added"] == 0             # seen already


def test_service_without_model(tmp_path):
    sources = {"every_s": 300, "keep_h": 72, "feeds": [FEED]}
    k, _ = fake_klines({"BTC-USD": lambda o: 100.0, "SOL-USD": lambda o: 100.0})
    svc = NewsService(Store(tmp_path / "n.db"), tmp_path / "news.json", klines=k, sources=sources,
                      fetcher=lambda url: RSS, log=lambda *a: None)
    svc.cycle(1792602000000)
    doc = json.loads((tmp_path / "news.json").read_text(encoding="utf-8"))
    assert not doc["classifier"]["on"] and doc["markets"]["BTC-USD"]["net"] is None
    assert doc["headlines"] and all("score" not in x for x in doc["headlines"])


def test_push_sends_news_when_it_changes(tmp_path, monkeypatch):
    import os

    from smartflow.api import push
    sent = []
    monkeypatch.setattr(push, "post", lambda url, secret, body: (sent.append((url, body)), (200, "ok"))[1])
    f = tmp_path / "news.json"
    n = push.News("https://site/api/internal/push", "s" * 32, f, heartbeat=600, log=lambda *a: None)
    n.maybe_send()                                   # no file yet: nothing, quietly
    f.write_text('{"v":1}', encoding="utf-8")
    n.maybe_send()
    n.maybe_send()                                   # unchanged: not again
    assert sent == [("https://site/api/internal/news", b'{"v":1}')]
    f.write_text('{"v":1,"x":2}', encoding="utf-8")
    os.utime(f, ns=(f.stat().st_mtime_ns + 10**9, f.stat().st_mtime_ns + 10**9))
    n.maybe_send()
    assert len(sent) == 2


def test_push_news_refused_waits_a_minute(tmp_path, monkeypatch):
    from smartflow.api import push
    calls = []
    clock = [1000.0]
    monkeypatch.setattr(push, "post", lambda url, secret, body: (calls.append(1), (404, "not found"))[1])
    monkeypatch.setattr(push.time, "time", lambda: clock[0])
    f = tmp_path / "news.json"
    f.write_text("{}", encoding="utf-8")
    n = push.News("https://site/api/internal/push", "s" * 32, f, log=lambda *a: None)
    n.maybe_send(); clock[0] += 10; n.maybe_send(); clock[0] += 10; n.maybe_send()
    assert len(calls) == 1                           # not every turn of the loop
    clock[0] += 60
    n.maybe_send()
    assert len(calls) == 2


def test_old_reactions_are_measured_again(tmp_path):
    import sqlite3
    db = tmp_path / "n.db"
    s = Store(db)
    s.add([h("A headline about bitcoin", NOW - 2 * H)], NOW, 72 * H)
    s.set_react(headline_id("A headline about bitcoin"), {"m": "BTC-USD", "p0": 1, "r15": 0.0, "r60": 0.0, "done": True})
    s.add_reading(NOW - H, "BTC-USD", 20, 100)
    s.commit()
    s.db.execute("PRAGMA user_version = 0")   # as the first version left it (last-trade price)
    s.db.commit(); s.close()
    s = Store(db)
    assert s.window(NOW - 72 * H)[0]["react"] is None and s.last_reading_t() is None
    assert s.db.execute("PRAGMA user_version").fetchone()[0] == 1
    s.set_react(headline_id("A headline about bitcoin"), {"done": True}); s.commit(); s.close()
    assert Store(db).window(NOW - 72 * H)[0]["react"] == {"done": True}   # only once
    sqlite3.connect(db).close()

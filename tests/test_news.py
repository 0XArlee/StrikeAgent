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
<description><![CDATA[<p>Funds took in <b>$120M</b> on Tuesday.</p>]]></description>
<pubDate>Wed, 21 Oct 2026 15:30:00 +0000</pubDate></item>
<item><title>No link</title></item>
<item><title>Plain http link</title><link>http://example.com/x</link></item>
</channel></rss>"""

ATOM = b"""<?xml version="1.0"?><feed xmlns="http://www.w3.org/2005/Atom"><title>x</title>
<entry><title>Ethereum upgrade goes live</title><link href="https://example.com/eth"/><published>2026-10-21T12:00:00Z</published></entry>
</feed>"""

FEED = {"id": "gn-btc", "name": "Google News", "url": "https://news.google.com/rss/x", "markets": ["BTC-USD"], "tier": 1}


def test_rss_and_atom():
    a = parse(RSS, FEED)
    assert [h.title for h in a] == ["Fed holds rates steady", "Solana & ETF inflows jump"]
    assert a[0].source == "Reuters" and a[1].source == "Google News"
    assert a[0].published == 1792591200000
    assert a[1].markets == ["BTC-USD", "SOL-USD"]   # the feed's market first, then the title's
    assert a[1].summary == "Funds took in $120M on Tuesday." and a[0].summary == "" and a[0].tier == 1
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


def test_reaction_against_the_normal_move():
    import math
    t0 = NOW - 2 * H
    wave = lambda o: 100.0 * (1 + 0.002 * math.sin(o / MIN / 37.0))      # the market's usual swings
    k, _ = fake_klines({"BTC-USD": lambda o: wave(o) * (1.01 if o >= t0 else 1.0)})   # +1 % right after the headline
    p = Prices(k)
    p.cover("BTC-USD", t0 - 25 * H, NOW)
    r = measure(p, "BTC-USD", t0, NOW)
    assert r["z60"] is not None and r["z60"] > 2               # far bigger than its normal hourly move
    calm, _ = fake_klines({"BTC-USD": wave})
    q = Prices(calm)
    q.cover("BTC-USD", t0 - 25 * H, NOW)
    assert abs(measure(q, "BTC-USD", t0, NOW)["z60"]) < 2       # an ordinary hour


def item(id_, age_h, s, impact="high", cat="macro", markets=("BTC-USD",), broad=False, z60=None, tier=1, source=None, story=None, conf=0.8):
    return {"id": id_, "t": NOW - int(age_h * H), "title": id_, "hint": [], "tier": tier, "source": source or f"src-{id_}",
            "react": {"r60": z60, "z60": z60} if z60 is not None else None,
            "cls": {"markets": list(markets), "broad": broad, "cat": cat, "score": s, "impact": impact, "conf": conf, "relevant": True,
                    "story": story, "es": id_}}


def one(x):
    return score.stories([x])[0]


def test_weights():
    assert abs(score.weight(one(item("a", 6, 50)), "BTC-USD", NOW) - 0.5) < 1e-9          # one half-life
    assert abs(score.weight(one(item("b", 0, 50, "low")), "BTC-USD", NOW) - 0.3) < 1e-9
    assert abs(score.weight(one(item("c", 0, 50, z60=-1.0)), "BTC-USD", NOW) - 0.3) < 1e-9   # the market went clearly against it
    assert score.weight(one(item("d", 0, 50, z60=-0.3)), "BTC-USD", NOW) == 1.0           # a move within the noise is no verdict
    assert score.weight(one(item("e", 0, 50, z60=1.2)), "BTC-USD", NOW) == 1.0
    assert score.weight(one(item("f", 0, 50, markets=(), broad=True)), "ETH-USD", NOW) == 0.5   # the whole market, for an alt
    assert score.weight(one(item("g", 0, 50, tier=2)), "BTC-USD", NOW) == 0.8               # crypto press
    assert score.weight(one(item("h", 0, 50, tier=3)), "BTC-USD", NOW) == 0.5               # the rest


def test_only_catalysts_count():
    noise = [item("recap", 1, 60, cat="price"), item("misc", 1, 60, cat="other"), item("unsure", 1, 60, conf=0.4),
             item("flat", 1, 5)]
    irrelevant = item("ad", 1, 90)
    irrelevant["cls"]["relevant"] = False
    assert score.stories(noise + [irrelevant]) == []
    assert score.reading(noise + [irrelevant], "BTC-USD", NOW)["net"] is None   # a recap of a rise never "predicts" it


def test_one_event_counts_once():
    xs = [item("cd", 2, 40, tier=2, source="CoinDesk", story="etf-approval"), item("rt", 1, 60, tier=1, source="Reuters", story="etf-approval"),
          item("tb", 1.5, 50, tier=2, source="The Block", story="etf-approval")]
    [st] = score.stories(xs)
    assert st["id"] == "rt" and st["score"] == 60 and st["sources"] == 3   # the best source speaks for the story
    assert st["t"] == NOW - 2 * H                                            # from when it first came out
    w = score.weight(st, "BTC-USD", NOW)
    assert abs(w - 1.5 * 0.5 ** (2 / 6)) < 1e-9                               # three outlets: x1.5
    assert score.reading(xs, "BTC-USD", NOW)["n"] == 1
    many = [item(f"s{i}", 0, 40, source=f"S{i}", story="x") for i in range(6)]
    assert score.weight(one(many[0]), "BTC-USD", NOW) == 1.0 and score.weight(score.stories(many)[0], "BTC-USD", NOW) == 1.75   # capped


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
    assert eth["net"] is None and eth["own"] == 1                     # an alt needs a couple of its own stories
    eth = score.reading(xs + [item("d", 1, 40, markets=("ETH-USD",))], "ETH-USD", NOW)
    assert eth["net"] is not None and eth["own"] == 2


def test_following_and_scoreboard():
    xs = [item(f"m{i}", 1, 50, cat="macro", z60=0.4) for i in range(3)] + [item(f"r{i}", 1, -50, cat="regulation", z60=0.2) for i in range(3)]
    f = score.following(xs, NOW)
    assert f[0] == {"cat": "macro", "follow": 0.4, "n": 3} and f[1]["follow"] == -0.2   # in multiples of the normal move
    rows = [{"market": "BTC-USD", "net": 30, "ret4": 0.5}, {"market": "BTC-USD", "net": -40, "ret4": 0.2},
            {"market": "BTC-USD", "net": 5, "ret4": -0.1}]
    assert score.scoreboard(rows)["BTC-USD"] == {"readings": 3, "called": 2, "hits": 1, "up": 2}


def test_as_of_hides_later_reactions():
    xs = [item("a", 0.5, 50, z60=0.3), item("b", 3, 50, z60=0.3)]
    xs[0]["t"] = NOW - 30 * MIN
    known = as_of(xs, NOW)
    assert known[0]["react"]["r60"] is None and known[0]["react"]["z60"] is None and known[1]["react"]["z60"] == 0.3
    assert xs[0]["react"]["z60"] == 0.3                      # the original is untouched
    assert [x["id"] for x in as_of(xs, NOW - H)] == ["b"]


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

    def post_story(payload):
        sent.append(payload)
        return tool_answer([{"id": "a", "markets": ["BTC"], "broad": False, "category": "etf", "score": 40, "impact": "medium",
                             "confidence": 0.8, "relevant": True, "story": "Spot ETF: Record Inflows!", "es": "x"}])
    got = Haiku("k", post=post_story).classify([{"id": "a", "title": "ETF inflows", "source": "S", "summary": "Funds took in $1B."}],
                                               [("spot-etf-record-inflows", "ETF inflows hit a record")])
    text = sent[-1]["messages"][0]["content"]
    assert "spot-etf-record-inflows: ETF inflows hit a record" in text and "Funds took in $1B." in text
    assert got["a"]["story"] == "spot-etf-record-inflows"

    def post_usage(payload):
        return {**tool_answer([]), "usage": {"input_tokens": 1200, "output_tokens": 300}}
    hk = Haiku("k", post=post_usage)
    hk.classify([{"id": "a", "title": "x", "source": "S"}])
    assert hk.tokens == [2400, 600]                           # what it costs (an empty answer is asked again once)


class FakeModel:
    model = "fake"

    def classify(self, items, stories=()):
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
    s.db.execute("UPDATE items SET cls = '{}'")
    s.db.execute("PRAGMA user_version = 0")   # as the first version left it (last-trade price)
    s.db.commit(); s.close()
    s = Store(db)
    row = s.window(NOW - 72 * H)[0]
    assert row["react"] is None and row["cls"] is None and s.last_reading_t() is None   # measured and classified again
    assert row["tier"] == 2 and row["summary"] == "" and s.db.execute("PRAGMA user_version").fetchone()[0] == 2
    s.set_react(headline_id("A headline about bitcoin"), {"done": True}); s.commit(); s.close()
    assert Store(db).window(NOW - 72 * H)[0]["react"] == {"done": True}   # only once
    sqlite3.connect(db).close()


def test_feeds_no_longer_configured_go():
    s = Store(":memory:")
    s.add([h("From an old search", NOW - H, feed="gn-old"), h("From CoinDesk", NOW - H, feed="coindesk")], NOW, 72 * H)
    assert s.sync_feeds({"coindesk": 2, "reuters": 1}) == 1
    [row] = s.window(NOW - 72 * H)
    assert row["feed"] == "coindesk" and row["tier"] == 2


def test_a_failed_batch_loses_only_its_own():
    import smartflow.news.classify as cl
    calls = []

    def post(payload):
        calls.append(payload)
        if len(calls) == 1:
            return {"content": [], "stop_reason": "max_tokens"}      # the first batch is cut with nothing usable
        ids = [json.loads(line)["id"] for line in payload["messages"][0]["content"].splitlines()[1:]]
        return tool_answer([{"id": i, "markets": [], "broad": True, "category": "macro", "score": 20, "impact": "medium",
                             "confidence": 0.7, "relevant": True, "story": i, "es": i} for i in ids])
    hk = Haiku("k", post=post)
    items = [{"id": f"h{i}", "title": f"t{i}", "source": "S"} for i in range(cl.BATCH + 3)]
    got = hk.classify(items)
    assert len(calls) == 2 and set(got) == {f"h{i}" for i in range(cl.BATCH, cl.BATCH + 3)}
    assert hk.errors and "max_tokens" in hk.errors[0]


def test_items_left_out_are_asked_again():
    calls = []

    def post(payload):
        calls.append(payload)
        ids = [json.loads(line)["id"] for line in payload["messages"][0]["content"].splitlines()[1:]]
        answer = ids[:1] if len(calls) == 1 else ids                 # first it answers one and shortens the rest
        return tool_answer([{"id": i, "markets": [], "broad": True, "category": "macro", "score": 20, "impact": "medium",
                             "confidence": 0.7, "relevant": True, "story": i, "es": i} for i in answer])
    hk = Haiku("k", post=post)
    got = hk.classify([{"id": f"h{i}", "title": f"t{i}", "source": "S"} for i in range(5)])
    assert set(got) == {f"h{i}" for i in range(5)} and len(calls) == 2
    assert "return exactly 4 items" in calls[1]["messages"][0]["content"] and not hk.errors


def test_outlets_outside_the_list_are_left_out():
    feed = {"id": "wires", "name": "Google News", "markets": [], "tier": 1, "allow": ["Reuters"]}
    assert [x.source for x in parse(RSS, feed)] == ["Reuters"]
    s = Store(":memory:")
    s.add([Headline("a", "From a local outlet", "https://x/a", "Local Paper", "wires", NOW - H),
           Headline("b", "From Reuters", "https://x/b", "Reuters", "wires", NOW - H)], NOW, 72 * H)
    assert s.keep_outlets("wires", ["Reuters"]) == 1 and [r["source"] for r in s.window(NOW - 72 * H)] == ["Reuters"]

"""The alerts: Strike Finance's moments, one person's accounts, copies and agent, and the Telegram bot (all faked here)."""

import json

import pytest

from smartflow.alerts.bot import AlertsBot
from smartflow.alerts.strike import HOUR, StrikeWatch
from smartflow.alerts.telegram import Telegram, TelegramError
from smartflow.alerts.watch import AccountWatch, AgentWatch, liq_level
from smartflow.net import HttpError

NOW = 1_792_700_000_000
MIN = 60_000


class FakeStrike:
    def __init__(self):
        self.prices = {"BTC-USD": 80_000.0, "ETH-USD": 2_400.0, "TSLA-USD": 400.0}
        self.rates = {"BTC-USD": 0.00001}
        self.live = []
        self.listed = {"BTC-USD": {"status": "trading", "name": "Bitcoin", "leverage": 50}}
        self.pos = {}       # account -> positions
        self.acct = {}      # account -> account doc

    def tickers(self):
        return {s: {"price": p, "change": 0.0, "volume": 1e6} for s, p in self.prices.items()}

    def markets(self):
        return dict(self.listed)

    def funding(self):
        return dict(self.rates)

    def live_positions(self):
        return list(self.live)

    def positions(self, account):
        return list(self.pos.get(account, []))

    def account(self, account=None, address=None):
        if address:
            return next((d for d in self.acct.values() if d.get("blockchain_address") == address), {})
        return self.acct.get(account, {})


def pos(pid, account, symbol, size, entry, mark, liq):
    return {"id": pid, "account_id": account, "symbol": symbol, "size": str(size), "entry_price": str(entry), "mark_price": str(mark),
            "liquidation_price": str(liq), "leverage": 10}


def watch(tmp_path, strike=None, news=None, copy=None):
    return StrikeWatch(tmp_path / "s.json", strike or FakeStrike(), news=lambda: news, copy=lambda: copy, log=lambda m: None)


# ---------------------------------------------------------------- Strike for everyone
def test_a_big_move_is_said_once_per_move(tmp_path):
    st = FakeStrike()
    w = watch(tmp_path, st)
    for i in range(61):
        assert not [a for a in w.tick(NOW + i * MIN) if a["kind"] == "move"]
    st.prices["BTC-USD"] = 78_000.0               # -2.5 % in the hour: news for BTC (2 %)
    a = [x for x in w.tick(NOW + 61 * MIN) if x["kind"] == "move"]
    assert len(a) == 1 and a[0]["market"] == "BTC-USD" and a[0]["place"] == "btc" and "−2.5%" in a[0]["title"]["en"] and a[0]["title"]["es"]
    st.prices["BTC-USD"] = 77_900.0               # the same move going on: quiet
    assert not [x for x in w.tick(NOW + 62 * MIN) if x["kind"] == "move"]
    st.prices["BTC-USD"] = 75_500.0               # another threshold further: news again
    assert [x for x in w.tick(NOW + 63 * MIN) if x["kind"] == "move"]
    st.prices["TSLA-USD"] = 410.0                 # +2.5 % for a stock is ordinary (4 %)
    assert not [x for x in w.tick(NOW + 64 * MIN) if x["market"] == "TSLA-USD"]


def test_funding_liquidation_radar_whales_and_crowds(tmp_path):
    st = FakeStrike()
    w = watch(tmp_path, st)
    st.live = [pos(1, "a", "BTC-USD", 1, 80_000, 80_000, 70_000)]
    w.tick(NOW)                                   # the first reading: everything was already there
    st.rates["BTC-USD"] = 0.0005                  # longs pay 0.05 % an hour
    st.live += [pos(2, "b", "BTC-USD", -3, 80_000, 80_000, 82_000),                       # 300k $ short, 2.5 % from liquidation
                pos(3, "c", "ETH-USD", 80, 2_400, 2_400, 1_000)]                         # 192k $ new long: a whale
    kinds = {a["kind"]: a for a in w.tick(NOW + MIN)}
    assert "funding" in kinds and "longs pay shorts" in kinds["funding"]["body"]["en"]
    assert kinds["liquidation"]["place"] == "alley" and kinds["funding"]["place"] == "cafe" and kinds["liquidation"]["data"]["notional"] == 240_000 and "2.5%" in kinds["liquidation"]["title"]["en"]
    assert kinds["whale"]["market"] == "ETH-USD" and kinds["whale"]["level"] == "info"
    assert not [a for a in w.tick(NOW + 2 * MIN) if a["kind"] in ("funding", "liquidation", "whale")]   # said once
    st.live[1] = pos(2, "b", "BTC-USD", -3, 80_000, 81_200, 82_000)                      # halved the distance: again, louder
    again = [a for a in w.tick(NOW + 3 * MIN) if a["kind"] == "liquidation"]
    assert again and again[0]["level"] == "alert"
    st.live = [pos(100 + i, f"x{i}", "ZEC-USD", 10 if i < 13 else -10, 1_200, 1_200, 0) for i in range(15)]
    crowd = [a for a in w.tick(NOW + 4 * MIN) if a["kind"] == "crowd"]
    assert crowd and "87% of positions are long" in crowd[0]["title"]["en"]


def test_listings_news_macro_and_the_arena(tmp_path):
    st = FakeStrike()
    news = {"headlines": [], "events": {"next": [{"t": NOW + 20 * MIN, "kind": "cpi", "name": "US CPI"}]}, "markets": {"BTC-USD": {"label": "neutral"}}}
    copy = {"traders": [{"id": "lead1", "name": "Ace", "city": 90, "positions": []}]}
    w = watch(tmp_path, st, news, copy)
    first = w.tick(NOW)
    assert [a["kind"] for a in first] == ["macro"] and "20 min" in first[0]["title"]["en"]
    st.listed["NEW-USD"] = {"status": "trading", "name": "Newcoin", "leverage": 5}
    st.listed["BTC-USD"] = {"status": "reduce_only", "name": "Bitcoin", "leverage": 50}
    news["headlines"] = [{"cat": "exchange", "catalyst": True, "score": -45, "t": NOW, "title": "Big exchange halts withdrawals",
                          "es": "Un gran exchange congela retiradas", "source": "Reuters"}]
    news["markets"]["BTC-USD"]["label"] = "very bearish"
    copy["traders"][0]["positions"] = [{"market": "BTC-USD", "side": "long", "size": 1, "entry": 80_000}]
    kinds = {a["kind"]: a for a in w.tick(NOW + MIN)}
    assert set(kinds) >= {"listing", "status", "security", "reading", "arena"}
    assert kinds["security"]["place"] == "news" and kinds["security"]["title"]["es"].endswith("congela retiradas")
    assert kinds["arena"]["place"] == "arena" and "#1" in kinds["arena"]["title"]["en"]
    assert not [a for a in w.tick(NOW + 2 * MIN) if a["kind"] in ("security", "macro", "arena")]
    doc = w.doc(NOW)
    assert doc["v"] == 1 and doc["alerts"][0]["t"] >= doc["alerts"][-1]["t"]


def test_one_source_down_never_stops_the_others(tmp_path):
    st = FakeStrike()
    st.live_positions = lambda: (_ for _ in ()).throw(HttpError(503, "down", "x"))
    w = watch(tmp_path, st)
    w.tick(NOW)
    st.rates["BTC-USD"] = -0.001
    assert [a["kind"] for a in w.tick(NOW + MIN)] == ["funding"]


# ---------------------------------------------------------------- one person's accounts and copies
def test_liquidation_distance_escalates_and_resets():
    st = FakeStrike()
    st.acct["main"] = {"account_id": "main", "sub_accounts": [{"account_id": "sub", "name": "Copy · Ace"}], "margin_balance": "100", "maintenance_margin": "10"}
    st.acct["sub"] = {"account_id": "sub", "margin_balance": "100", "maintenance_margin": "10"}
    aw, mem = AccountWatch(st, {"TSLA-USD"}), {}
    st.pos["sub"] = [pos(1, "sub", "TSLA-USD", 3, 400, 400, 352)]            # 12 %: a word
    first = aw.check("main", mem, [])
    assert [m["level"] for m in first] == ["info"] and "Copy · Ace" in first[0]["en"][1]
    assert not aw.check("main", mem, [])                                       # not again
    st.pos["sub"] = [pos(1, "sub", "TSLA-USD", 3, 400, 400, 392)]            # 2 %: the alarm
    urgent = aw.check("main", mem, [])
    assert urgent[0]["level"] == "alert" and "2.0% from liquidation" in urgent[0]["en"][0] and urgent[0]["url"]
    st.pos["sub"] = [pos(1, "sub", "TSLA-USD", 3, 400, 400, 300)]            # margin added: 25 % away, the watch resets
    assert not aw.check("main", mem, [])
    st.pos["sub"] = [pos(1, "sub", "TSLA-USD", 3, 400, 400, 380)]
    assert aw.check("main", mem, [])
    assert liq_level(None) == 0 and liq_level(0.5) == 0


def test_a_copy_that_missed_a_trade_or_stayed_in_one_and_a_trader_in_trouble():
    st = FakeStrike()
    st.acct["main"] = {"account_id": "main", "sub_accounts": ["sub"], "margin_balance": "100", "maintenance_margin": "1"}
    st.acct["sub"] = {"account_id": "sub", "margin_balance": "100", "maintenance_margin": "1"}
    hl = {"assetPositions": [{"position": {"coin": "BTC", "szi": "1", "positionValue": "80000", "liquidationPx": "50000"}}],
          "marginSummary": {"accountValue": "100000"}, "crossMaintenanceMarginUsed": "1000"}
    aw, mem = AccountWatch(st, {"BTC-USD", "ETH-USD", "SOL-USD"}, hl=lambda a: hl), {}
    copy = [{"lead": "0xabc", "follower": "sub", "platform": "hyperliquid", "status": "active"}]
    st.pos["sub"] = [pos(1, "sub", "BTC-USD", 0.01, 80_000, 80_000, 0)]
    assert not aw.check("main", mem, copy)       # BTC was open before the watch began: never "missed"
    hl["assetPositions"].append({"position": {"coin": "ETH", "szi": "-10", "positionValue": "24000", "liquidationPx": "3000"}})
    hl["assetPositions"].append({"position": {"coin": "PURR", "szi": "100", "positionValue": "20", "liquidationPx": "0"}})
    assert not aw.check("main", mem, copy)       # one check: a copy takes seconds to follow
    missed = aw.check("main", mem, copy)
    assert [m["key"].split(":")[0] for m in missed] == ["miss"] and "ETH" in missed[0]["en"][0]   # PURR is not on Strike
    hl["assetPositions"] = [p for p in hl["assetPositions"] if p["position"]["coin"] != "BTC"]
    aw.check("main", mem, copy)
    left = aw.check("main", mem, copy)
    assert any(m["key"].startswith("left:") and "BTC" in m["en"][0] for m in left)
    hl["crossMaintenanceMarginUsed"] = "85000"   # the trader uses 85 % of its margin
    risk = [m for m in aw.check("main", mem, copy) if m["key"].startswith("leadrisk")]
    assert risk and risk[0]["level"] == "alert" and "Hyperliquid" in risk[0]["en"][0]
    copy[0]["status"] = "liquidated"
    end = aw.check("main", mem, copy)
    assert end[0]["key"].startswith("copyend") and "liquidated" in end[0]["en"][0]


# ---------------------------------------------------------------- the agent's journal and its pilot
def write(path, rows):
    with path.open("a", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r) + "\n")


def test_the_agent_journal_from_now_on(tmp_path):
    run = tmp_path / "runs" / "live-u1"
    run.mkdir(parents=True)
    j = run / "journal.jsonl"
    write(j, [{"kind": "alert", "level": "error", "message": "old problem", "ts": "2026-10-20T00:00:00"}])
    aw, mem = AgentWatch(tmp_path / "runs", tmp_path), {}
    assert aw.check("u1", "mainnet", "Nova", mem) == []            # the backlog is never sent
    write(j, [{"kind": "signal", "trade_id": "BTC-USD-1-L", "market": "BTC-USD", "dir": 1, "stop": 79_000},
              {"kind": "fill", "trade_id": "BTC-USD-1-L", "market": "BTC-USD", "entry": 80_000, "qty": 0.01},
              {"kind": "signal", "trade_id": "BTC-USD-test-9", "market": "BTC-USD", "dir": 1, "stop": 1, "test": True},
              {"kind": "fill", "trade_id": "BTC-USD-test-9", "market": "BTC-USD", "entry": 1, "qty": 1, "test": True},
              {"kind": "alert", "level": "error", "message": "Strike did not answer 3 times", "ts": "2026-10-23T10:00:01"},
              {"kind": "alert", "level": "error", "message": "Strike did not answer 4 times", "ts": "2026-10-23T10:05:00"},
              {"kind": "decision", "trade_id": "ETH-USD-2-S", "accepted": False, "reasons": ["not enough available balance"]},
              {"kind": "decision", "trade_id": "ETH-USD-3-S", "accepted": False, "reasons": ["stack full (3 trades)"]},
              {"kind": "exit", "trade_id": "BTC-USD-1-L", "market": "BTC-USD", "reason": "exit", "price": 82_000},
              {"kind": "host", "action": "pause", "ts": "x"}])
    out = aw.check("u1", "mainnet", "Nova", mem)
    keys = [m["key"].split(":")[0] for m in out]
    assert keys == ["open", "problem", "skip", "close", "host"]
    assert "Nova opened LONG BTC" == out[0]["en"][0] and "−1.2%" in out[0]["en"][1]
    assert "+2.00R" in out[3]["en"][1] and "+20.00 $" in out[3]["en"][1] and out[3]["es"][0] == "Nova cerró BTC"
    assert aw.check("u1", "mainnet", "Nova", mem) == []


def test_the_copy_pilot_log_and_its_pauses(tmp_path):
    (tmp_path / "pilot-mainnet.json").write_text(json.dumps({"u1": {"log": [{"t": 1, "kind": "start", "lead": "0xabc"}], "why": None}}))
    aw, mem = AgentWatch(tmp_path, tmp_path), {}
    assert aw._pilot("u1", "mainnet", mem) == []
    (tmp_path / "pilot-mainnet.json").write_text(json.dumps({"u1": {"log": [{"t": 1, "kind": "start", "lead": "0xabc"},
                                                                            {"t": 2, "kind": "no_funds", "available": 3.5},
                                                                            {"t": 3, "kind": "refused", "text": "below minimum"}], "why": "macro"}}))
    out = aw._pilot("u1", "mainnet", mem)
    assert [m["key"].split(":")[1] for m in out] == ["no_funds", "refused", "why"] and out[1]["level"] == "alert"


# ---------------------------------------------------------------- the bot
class FakeTelegram:
    def __init__(self):
        self.sent, self.edits, self.fail = [], [], None

    def send(self, chat, text, buttons=None, silent=False):
        if self.fail:
            raise self.fail
        self.sent.append((chat, text, buttons, silent))

    def edit(self, chat, mid, text, buttons=None):
        self.edits.append((chat, mid, text, buttons))

    def answer(self, cid, text=None):
        pass


class FakeSite:
    def __init__(self, env):
        self.env, self.claims, self.unlinks, self.docs = env, [], [], []
        self.codes = {"m" + "a" * 20: {"userId": "u1", "name": "Nova", "accountId": "main", "lang": "es"}}
        self.users = [{"userId": "u1", "chats": ["7"], "name": "Nova", "accountId": "main"}]

    def lookup(self, code):
        return self.codes.get(code, {})

    def claim(self, code, chat, who):
        self.claims.append((code, chat, who))
        return {"ok": True}

    def linked(self):
        return self.users

    def unlink(self, user, chat):
        self.unlinks.append((user, chat))

    def alerts(self, doc):
        self.docs.append(doc)


def bot(tmp_path, strike=None):
    st = strike or FakeStrike()
    tg, site = FakeTelegram(), FakeSite("mainnet")
    b = AlertsBot(tg, {"mainnet": site}, tmp_path / "alerts", tmp_path / "runs", tmp_path, tmp_path / "news.json",
                  strikes={"mainnet": st, "testnet": st}, hl=lambda a: {}, log=lambda m: None)
    return b, tg, site, st


def say(b, text, chat=7, lang="en"):
    b.handle({"update_id": 1, "message": {"text": text, "chat": {"id": chat, "type": "private"}, "from": {"first_name": "Ed", "language_code": lang}}})


def test_start_link_and_settings(tmp_path):
    b, tg, site, _ = bot(tmp_path)
    say(b, "/start", lang="es")
    assert "Alertas de EdgeCraft-StrikeCity" in tg.sent[-1][1] and b.state["chats"]["7"]["lang"] == "es"
    say(b, "/start m" + "a" * 20)
    assert site.claims == [("m" + "a" * 20, "7", "Ed")] and b.state["chats"]["7"]["user"]["accountId"] == "main"
    assert "Vinculado a Nova" in tg.sent[-2][1]
    say(b, "/start m" + "b" * 20)
    assert "caducado" in tg.sent[-2][1]
    b.handle({"update_id": 2, "callback_query": {"id": "q", "data": "t:whale", "message": {"chat": {"id": 7}, "message_id": 5}, "from": {}}})
    assert b.state["chats"]["7"]["prefs"]["whale"] is False and tg.edits[-1][1] == 5
    site.users = []                                           # unlinked on the site
    b.sync_links()
    assert b.state["chats"]["7"]["user"] is None and "ya no está vinculado" in tg.sent[-1][1]


def test_public_alerts_follow_each_chats_choices(tmp_path):
    b, tg, site, _ = bot(tmp_path)
    for chat in (1, 2, 3):
        say(b, "/start", chat=chat)
    b.state["chats"]["2"]["scope"] = "majors"
    b.state["chats"]["3"]["mute"] = NOW * 2
    tg.sent.clear()
    a = {"kind": "move", "level": "warn", "market": "TSLA-USD", "title": {"en": "Tesla +5%", "es": "Tesla +5%"}, "body": {"en": "<b>x</b>", "es": "x"}}
    b.deliver_public([a])
    assert [s[0] for s in tg.sent] == ["1"] and "&lt;b&gt;x&lt;/b&gt;" in tg.sent[0][1]   # escaped, majors-only and muted chats skipped
    tg.sent.clear()
    b.deliver_public([dict(a, level="alert", market="BTC-USD")])
    assert sorted(s[0] for s in tg.sent) == ["1", "2", "3"]                               # an alarm breaks the mute


def test_personal_messages_once_and_urgent_ones_through_the_mute(tmp_path):
    b, tg, *_ = bot(tmp_path)
    say(b, "/start")
    c = b.state["chats"]["7"]
    c["mute"] = NOW * 2
    tg.sent.clear()
    m1 = {"key": "liq:a:2", "level": "warn", "kind": "risk", "en": ("t", "b"), "es": ("t", "b")}
    m2 = {"key": "liq:a:3", "level": "alert", "kind": "risk", "en": ("urgent", "b"), "es": ("urgente", "b"), "url": "https://app.strikefinance.org"}
    assert b.deliver_mine("7", c, [m1, m2]) == 1 and "urgent" in tg.sent[-1][1] and tg.sent[-1][2]
    assert b.deliver_mine("7", c, [m2]) == 0


def test_watch_an_account_by_wallet_address(tmp_path):
    st = FakeStrike()
    st.acct["acc-1"] = {"account_id": "01a15f02-2791-73f7-bbe4-2f465681b836", "blockchain_address": "addr1" + "q" * 98, "sub_accounts": ["s1", "s2"]}
    b, tg, *_ = bot(tmp_path, st)
    say(b, "/watch addr1" + "q" * 98)
    assert "y sus 2 subcuentas" not in tg.sent[-1][1] and "and its 2 sub-accounts" in tg.sent[-1][1]
    assert b.state["chats"]["7"]["watch"][0]["account"] == "01a15f02-2791-73f7-bbe4-2f465681b836"
    say(b, "/watch nobody")
    assert "couldn't find" in tg.sent[-1][1]


def test_a_chat_that_blocked_the_bot_is_forgotten(tmp_path):
    b, tg, *_ = bot(tmp_path)
    say(b, "/start")
    tg.fail = TelegramError("sendMessage", 403, "Forbidden: bot was blocked by the user")
    b.send("7", "hello")
    assert "7" not in b.state["chats"]


def test_the_token_never_reaches_an_error():
    def http(method, url, **kw):
        raise HttpError(401, '{"ok":false,"description":"Unauthorized"}', url)
    tg = Telegram("123456:SECRET-TOKEN", http=http)
    with pytest.raises(TelegramError) as e:
        tg.me()
    assert "SECRET-TOKEN" not in str(e.value) and "getMe" in str(e.value)

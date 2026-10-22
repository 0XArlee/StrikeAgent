"""Copy with your agent: the plan its owner signed, carried out on Strike's copy trading (a fake Strike here)."""

from smartflow.copytrade.pilot import HOUR, CopyPilot, candidates, security_alarm
from smartflow.net import HttpError

NOW = 1_792_700_000_000
ACCOUNT = "01a156ba-0000-0000-0000-000000000000"


class FakeStrike:
    def __init__(self):
        self.subs: dict[str, dict] = {}
        self.calls: list[tuple] = []
        self.setup_steps = ["creating_account"]   # a managed copy answers 202 this many times before it is active
        self.balances = {None: 100.0}             # available $ per account (None: the main account)
        self.refuse = None

    def copy_subscribe(self, body):
        self.calls.append(("subscribe", dict(body)))
        if self.refuse:
            raise HttpError(400, self.refuse, "x")
        sub = f"sub-{len(self.subs) + 1}"   # every managed copy gets a sub-account of its own
        if body.get("auto_create_sub_account") and self.setup_steps:
            return {"subscription_id": "", "status": self.setup_steps.pop(0), "sub_account_id": sub}
        sid = f"s{len(self.subs) + 1}"
        self.subs[sid] = {"subscription_id": sid, "lead_account_id": body["lead_account_id"], "status": "active", "pnl": "1.5",
                          "copy_amount": body.get("copy_amount"), "account_id": sub}
        return {"subscription_id": sid, "status": "active", "sub_account_id": sub}

    def copy_stop(self, sid, sub_account_id=None):
        self.calls.append(("stop", sid, sub_account_id))
        self.subs[sid]["status"] = "stopped"

    def copy_update(self, sid, body):
        self.calls.append(("update", sid, dict(body)))

    def copy_subscriptions(self, status=None):
        return list(self.subs.values())

    def account_of(self, sub):
        return {"available_balance": str(self.balances.get(sub, 0.0))}


class FakeSite:
    def __init__(self, plan, version=1):
        self.plan, self.version, self.reports = plan, version, []

    def plans(self):
        return {"env": "testnet", "plans": [{"userId": "u1", "pub": "ab" * 32, "accountId": ACCOUNT, "plan": self.plan, "version": self.version}]}

    def report(self, env, status):
        self.reports.append(status)


def plan(**kw):
    base = {"mode": "manual", "lead": "lead-a", "platform": "strike", "sizing": {"kind": "ratio", "amount": 50}, "stopLoss": 10,
            "leverage": 3, "excluded": ["DOGE-USD"], "until": None, "alarmPause": True, "pilot": None}
    return base | kw


def trader(i, city, platform="strike", rec=10, copiers=None):
    return {"id": i, "platform": platform, "city": city, "direction": "copy", "recommended": rec, "copiers": copiers or {"n": 0, "pnl": 0}}


def make(tmp_path, p, copy=None, news=None):
    strike, site = FakeStrike(), FakeSite(p)
    pilot = CopyPilot(site, lambda pub: strike, "testnet", tmp_path / "pilot.json", lambda: copy, lambda: news, log=lambda m: None)
    return pilot, strike, site


def test_a_manual_copy_runs_in_its_own_sub_account(tmp_path):
    pilot, strike, site = make(tmp_path, plan())
    pilot.tick(NOW)
    first = strike.calls[0][1]
    assert first["auto_create_sub_account"] and first["source_account_id"] == ACCOUNT and first["request_id"]
    assert first["copy_mode"] == "fixed_ratio" and first["copy_amount"] == "50.00" and first["stop_loss_amount"] == "10.00"
    assert first["excluded_symbols"] == ["DOGE-USD"] and first["margin_settings"] == {"default_margin_mode": "isolated", "default_leverage": 3}
    assert site.reports[-1][0]["state"] == "starting"
    pilot.tick(NOW + 60_000)                     # the same request again (same request_id) until Strike says active
    assert strike.calls[1][1] == first
    s = site.reports[-1][0]
    assert s["state"] == "copying" and s["lead"] == "lead-a" and s["subAccount"] == "sub-1"
    pilot.tick(NOW + 120_000)                    # nothing to do: it copies
    assert [c[0] for c in strike.calls] == ["subscribe", "subscribe"]


def test_turning_it_off_stops_the_copy(tmp_path):
    pilot, strike, site = make(tmp_path, plan())
    strike.setup_steps = []
    pilot.tick(NOW)
    site.plan, site.version = plan(mode="off"), 2
    pilot.tick(NOW + 60_000)
    assert strike.calls[-1] == ("stop", "s1", "sub-1") and site.reports[-1][0]["state"] == "off"


def test_a_stop_loss_halts_the_plan_until_its_owner_signs_again(tmp_path):
    pilot, strike, site = make(tmp_path, plan())
    strike.setup_steps = []
    pilot.tick(NOW)
    strike.subs["s1"].update(status="stopped", stop_reason="stop_loss")
    pilot.tick(NOW + 60_000)
    assert site.reports[-1][0]["state"] == "halted" and site.reports[-1][0]["why"] == "stop_loss"
    n = len(strike.calls)
    pilot.tick(NOW + 120_000)
    assert len(strike.calls) == n                # never back on its own after a stop-loss
    strike.balances = {None: 5.0, "sub-1": 38.0}
    site.version = 2                             # signed again: a new copy, funded with what the last one left
    pilot.tick(NOW + 180_000)
    body = strike.calls[-1][1]
    assert body["auto_create_sub_account"] and body["source_account_id"] == "sub-1" and body["copy_amount"] == "38.00"
    assert site.reports[-1][0]["state"] == "copying" and site.reports[-1][0]["subAccount"] == "sub-2"


def test_without_money_it_says_so_and_starts_once_there_is(tmp_path):
    pilot, strike, site = make(tmp_path, plan())
    strike.setup_steps, strike.balances = [], {None: 12.0}
    pilot.tick(NOW)
    pilot.tick(NOW + 60_000)
    s = site.reports[-1][0]
    assert not strike.calls and s["state"] == "waiting" and s["why"] == "funds"
    assert [x["kind"] for x in s["log"]].count("no_funds") == 1 and s["log"][-1]["available"] == 12.0
    strike.balances = {None: 300.0}              # a deposit: no new signature needed
    pilot.tick(NOW + 120_000)
    assert strike.calls[-1][1]["copy_amount"] == "50.00" and site.reports[-1][0]["state"] == "copying"


def test_new_limits_patch_the_copy_and_a_new_amount_restarts_it(tmp_path):
    pilot, strike, site = make(tmp_path, plan())
    strike.setup_steps = []
    pilot.tick(NOW)
    site.plan, site.version = plan(stopLoss=20), 2
    pilot.tick(NOW + 60_000)
    assert strike.calls[-1][0] == "update" and strike.calls[-1][2]["stop_loss_amount"] == "20.00"
    site.plan, site.version = plan(stopLoss=20, sizing={"kind": "ratio", "amount": 80}), 3
    pilot.tick(NOW + 120_000)
    assert [c[0] for c in strike.calls[-2:]] == ["stop", "subscribe"] and strike.calls[-1][1]["copy_amount"] == "80.00"


def test_the_pilot_chooses_keeps_and_changes_within_its_rules(tmp_path):
    p = plan(mode="pilot", lead=None, platform=None, pilot={"minScore": 60, "platforms": ["strike", "hyperliquid"], "review": 6, "maxSwitches": 1})
    doc = {"traders": [trader("t1", 80), trader("t2", 75), trader("big", 90, rec=500), trader("lost", 95, copiers={"n": 5, "pnl": -10}),
                       trader("low", 50)]}
    pilot, strike, site = make(tmp_path, p, copy=doc)
    strike.setup_steps = []
    pilot.tick(NOW)
    assert strike.calls[-1][1]["lead_account_id"] == "t1"          # the best it can afford whose copiers did not lose
    doc["traders"] = [trader("t2", 85)] + [trader(f"x{i}", 84 - i) for i in range(6)] + [trader("t1", 70)]
    pilot.tick(NOW + HOUR)                                          # before its review: it keeps t1
    assert strike.calls[-1][0] == "subscribe" and site.reports[-1][0]["why"] == "keeps"
    pilot.tick(NOW + 7 * HOUR)                                      # reviewed, t1 is 8th now: it changes to the best
    assert [c[0] for c in strike.calls[-2:]] == ["stop", "subscribe"] and strike.calls[-1][1]["lead_account_id"] == "t2"
    doc["traders"] = [trader("t3", 90)]                             # t2 no longer qualifies, but it changed once this week
    pilot.tick(NOW + 14 * HOUR)
    assert strike.calls[-1][0] == "stop" and site.reports[-1][0]["why"] == "switch_limit"


def test_the_alarm_pauses_and_the_date_ends_it(tmp_path):
    news = {"headlines": [{"cat": "security", "catalyst": True, "score": -60, "t": NOW - HOUR}]}
    pilot, strike, site = make(tmp_path, plan(), news=news)
    strike.setup_steps = []
    pilot.tick(NOW)
    assert not strike.calls and site.reports[-1][0]["why"] == "alarm"
    pilot.news_doc = lambda: None
    pilot.tick(NOW + 60_000)
    assert strike.calls[-1][0] == "subscribe"
    site.plan, site.version = plan(until=NOW + 100_000), 2
    pilot.tick(NOW + 120_000)
    assert strike.calls[-1][0] == "stop" and site.reports[-1][0]["why"] == "until"


def test_a_copy_strike_refuses_halts_with_its_reason(tmp_path):
    pilot, strike, site = make(tmp_path, plan())
    strike.refuse = '{"error":"below the copy minimum"}'
    pilot.tick(NOW)
    s = site.reports[-1][0]
    assert s["state"] == "halted" and s["why"] == "refused" and "minimum" in s["log"][-1]["text"]
    pilot.tick(NOW + 60_000)
    assert len(strike.calls) == 1


def test_candidates_and_alarm_rules():
    p = plan(mode="pilot", pilot={"minScore": 70, "platforms": ["hyperliquid"]})
    doc = {"traders": [trader("a", 80, "strike"), trader("b", 75, "hyperliquid"), trader("c", 65, "hyperliquid")]}
    assert [t["id"] for t in candidates(doc, p)] == ["b"]
    assert security_alarm({"headlines": [{"cat": "security", "catalyst": True, "score": -20, "t": NOW}]}, NOW) is None
    assert security_alarm({"headlines": [{"cat": "security", "catalyst": True, "score": -40, "t": NOW - 30 * HOUR}]}, NOW) is None

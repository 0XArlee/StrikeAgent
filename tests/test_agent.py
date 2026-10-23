"""Risk engine, lifecycle, journal redaction and an end-to-end agent run in simulation mode (fake feeds/venue)."""

import json
import math
from dataclasses import replace

import pytest

from conftest import HOUR, aggregate, synthetic

from smartflow.agent import runner as runner_mod
from smartflow.agent.config import AgentConfig, MarketMap
from smartflow.agent.execution import PaperExecution, walk_book
from smartflow.agent.journal import Journal, redact
from smartflow.agent.lifecycle import IllegalTransition, S, TradeRecord
from smartflow.agent.risk import AccountContext, MarketContext, Proposal, RiskConfig, RiskEngine
from smartflow.agent.runner import Agent
from smartflow.core.config import BiasSource, Params
from smartflow.strike.models import FeeTier, parse_market

SPEC = parse_market({"symbol": "SYN-USD", "status": "trading", "order_tick_price": "0.0001",
                     "order_market_step_size": "0.001", "order_market_min_size": "0.001",
                     "order_market_max_size": "1000000", "order_min_notional": "5",
                     "margin_tiers": [{"max_notional": "1e12", "max_leverage": 50, "maintenance_margin_rate": "0.005"}]})


def ctx(**kw):
    p = Proposal("SYN-USD", 1, 100.05, 98.5, None, 100.0, 20)
    m = MarketContext(SPEC, 100.0, 100.05, 100.02, 1.0, 0.0005, 0)
    a = AccountContext(10_000, 10_000, 0, 0.0, 0.0, 0.0, False, 0)
    return replace(p, **{k: v for k, v in kw.items() if hasattr(p, k)}), \
        replace(m, **{k: v for k, v in kw.items() if hasattr(m, k)}), \
        replace(a, **{k: v for k, v in kw.items() if hasattr(a, k)})


def test_risk_accepts_and_sizes_from_stop(tmp_path):
    eng = RiskEngine(RiskConfig(), tmp_path)
    d = eng.evaluate(*ctx())
    assert d.accepted, d.reasons
    # 0.5 % of 10k = 50 USD over 1.55 * 1.25 per unit
    assert float(d.qty) == pytest.approx(50 / (1.55 * 1.25), abs=0.001)
    assert d.risk_usd <= 50 and d.leverage >= 1 and d.est_liq_price < 98.5


@pytest.mark.parametrize("kw,needle", [
    (dict(signal_age_s=999), "stale"), (dict(has_position_in_symbol=True), "already open"),
    (dict(bid=99.0, ask=101.0), "spread"), (dict(impact_bps=50.0), "impact"), (dict(stop=100.2), "through the stop"),
    (dict(day_pnl=-300.0), "daily loss"), (dict(open_positions=3), "max open"), (dict(mark=103.0), "differs"),
    (dict(stop=99.99), "below minimum"), (dict(builder_fee_bps=100), "expected costs"),
])
def test_risk_rejections(tmp_path, kw, needle):
    d = RiskEngine(RiskConfig(), tmp_path).evaluate(*ctx(**kw))
    assert not d.accepted and any(needle in r for r in d.reasons), d.reasons


def test_loss_limits_on_the_day_and_week_start(tmp_path):
    # as the backtest (backtest/account.py): 2 % of the equity at 00:00 UTC, 5 % of Monday's; 10,000 at both starts
    eng = RiskEngine(RiskConfig(), tmp_path)
    hit = lambda d: [r for r in d.reasons if "loss limit" in r]   # noqa: E731
    assert not hit(eng.evaluate(*ctx(equity=9_803.0, available=9_803.0, day_pnl=-197.0, week_pnl=-197.0)))   # 1.97 %
    assert hit(eng.evaluate(*ctx(equity=9_799.0, available=9_799.0, day_pnl=-201.0, week_pnl=-201.0)))
    assert not hit(eng.evaluate(*ctx(equity=9_520.0, available=9_520.0, week_pnl=-480.0)))                  # 4.8 %
    assert hit(eng.evaluate(*ctx(equity=9_499.0, available=9_499.0, week_pnl=-501.0)))


def test_kill_switch(tmp_path):
    (tmp_path / "KILL_SWITCH").write_text("stop")
    d = RiskEngine(RiskConfig(), tmp_path).evaluate(*ctx())
    assert not d.accepted and "kill switch engaged" in d.reasons


def test_builder_fee_never_increases_size(tmp_path):
    eng = RiskEngine(RiskConfig(), tmp_path)
    q0 = eng.evaluate(*ctx()).qty
    q1 = eng.evaluate(*ctx(builder_fee_bps=10)).qty
    assert q1 == q0


def test_lifecycle_rules():
    t = TradeRecord("t1", "SYN-USD", 1, 0)
    for st in (S.SIGNAL_VALIDATED, S.ORDER_PREPARED, S.ORDER_SENT, S.POSITION_OPEN, S.PROTECTED, S.EXIT_REQUESTED,
               S.POSITION_CLOSED):
        t.to(st)
    assert not t.active and len(t.history) == 7
    t2 = TradeRecord("t2", "SYN-USD", 1, 0)
    with pytest.raises(IllegalTransition):
        t2.to(S.POSITION_OPEN)           # a signal is not a position
    t3 = TradeRecord("t3", "SYN-USD", 1, 0, S.ORDER_SENT)
    with pytest.raises(IllegalTransition):
        t3.to(S.EXIT_REQUESTED)          # an accepted order is not a position
    assert TradeRecord.from_dict(t.to_dict()).state == S.POSITION_CLOSED


def test_journal_redacts_secrets(tmp_path):
    j = Journal(tmp_path / "j.jsonl", "simulation", "fp")
    j.write("live_order", private_key="ab" * 32, headers={"X-API-Wallet-Signature": "cd" * 64}, note="ok",
            blob="sig " + "ef" * 40)
    line = (tmp_path / "j.jsonl").read_text()
    assert "abab" not in line and "cdcd" not in line and "efefefefefefefefef" not in line and '"note": "ok"' in line
    assert redact({"seed_phrase": "x"}) == {"seed_phrase": "<redacted>"}


def test_walk_book():
    assert walk_book([["100", "1"], ["101", "1"]], 1.5) == pytest.approx((100 + 50.5) / 1.5)
    assert math.isnan(walk_book([["100", "1"]], 2))


# ---------------------------------------------------------------- end-to-end simulation
class FakeVenue:
    """Public Strike endpoints answered from the synthetic price path."""

    def __init__(self):
        self.px = 100.0

    def markets(self):
        return {"SYN-USD": SPEC}

    def fee_tiers(self):
        return [FeeTier(0, 0, 0.0005, -0.00005)]

    def book_ticker(self, symbol):
        return {"bidPrice": str(self.px * 0.9999), "askPrice": str(self.px * 1.0001)}

    def premium(self, symbol):
        return {"mark": self.px, "index": self.px, "funding_rate": 0.0, "next_funding_time": 0, "time": 0}

    def depth(self, symbol, limit=100):
        return {"bids": [[str(self.px * 0.9999), "1e9"]], "asks": [[str(self.px * 1.0001), "1e9"]]}


def test_agent_simulation_end_to_end(tmp_path, monkeypatch):
    bars = synthetic(2600, seed=21, start=0, step=HOUR)
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
    cfg = AgentConfig(name="e2e", mode="simulation", env="testnet", tf="60",
                      markets=[MarketMap("SYN-USD", "SYNUSDT")],
                      params=replace(Params(), bias_source=BiasSource.NONE),
                      data_root=str(tmp_path / "nodata"), runs_root=str(tmp_path / "runs"))
    adapter = PaperExecution(venue, 10_000, builder_fee_bps=5)
    ag = Agent(cfg, adapter, Journal(cfg.run_dir / "journal.jsonl", "simulation", "fp"), public=venue)
    ag._saved = {}
    monkeypatch.setattr(runner_mod, "RiskEngine", lambda c, root: RiskEngine(c, tmp_path))
    ag.warmup(log=lambda *_: None)
    for i in range(2000, 2600):
        venue.px = bars[i].close         # price available right after the close
        clock["now"] = bars[i].open_time + HOUR + 15_000
        ag.step(clock["now"])
        venue.px = bars[i].low if i % 2 else bars[i].high
        ag.reconcile()                   # paper stops checked against an intrabar extreme
    kinds = [r["kind"] for r in ag.journal.read()]
    entries = [e for e in adapter.events if e["event"] == "entry"]
    exits = [e for e in adapter.events if e["event"] == "exit"]
    assert kinds.count("analysis") == 601      # 600 closed bars + 1 startup snapshot
    assert entries and exits, "the synthetic path should trade"
    assert len(entries) - len(exits) in (0, 1)
    assert {e["reason"] for e in exits} <= {"stop", "target", "trailing exit", "candle limit", "money-flow exit"}
    # every decision is journaled with its reasons; never two positions in the same market
    assert all("accepted" in r for r in ag.journal.read("decision") if "action" not in r)
    st = json.loads((cfg.run_dir / "state.json").read_text())
    assert "SYN-USD" in st
    assert not [r for r in ag.journal.read("alert") if r["level"] in ("error", "critical")]


def test_uncertain_entry_is_reconciled_not_resent():
    from smartflow.agent.execution import _fail
    from smartflow.net import HttpError
    assert _fail("c", HttpError(0, "timeout", "u")).uncertain
    assert _fail("c", HttpError(503, "busy", "u")).uncertain
    assert not _fail("c", HttpError(400, "invalid size", "u")).uncertain


def test_leverage_rises_only_as_much_as_the_margin_needs(tmp_path):
    """Strike cross margin: the leverage only sets the initial margin. With other positions using the balance, the
    lowest leverage whose margin fits in 90 % of the available is used (up to the cap); the size never changes."""
    eng = RiskEngine(RiskConfig(), tmp_path)
    d1 = eng.evaluate(*ctx())                                   # 10k free: 1x
    assert d1.accepted and d1.leverage == 1 and d1.margin == pytest.approx(d1.notional)
    d2 = eng.evaluate(*ctx(available=2000.0))                   # notional ~2.58k: 2x makes its margin fit
    assert d2.accepted and d2.leverage == 2 and d2.qty == d1.qty and d2.margin <= 0.9 * 2000
    d3 = eng.evaluate(*ctx(available=400.0))                    # not even at 5x
    assert not d3.accepted and "exceeds 90% of available" in d3.reasons[0]


def test_paper_stops_survive_strike_outages():
    """Strike answering 503 or timing out while the paper stops are checked: that market waits for the next turn,
    the others are checked, and the agent never stops (2026-10-21: it did three times)."""
    from smartflow.agent.execution import _PaperPos
    from smartflow.net import HttpError

    class Flaky(FakeVenue):
        down = {"BAD-USD"}

        def book_ticker(self, symbol):
            if symbol in self.down:
                raise HttpError(503, "Service Temporarily Unavailable", "bookTicker")
            return super().book_ticker(symbol)

    venue = Flaky()
    ex = PaperExecution(venue, 10_000)
    ex.pos = {"BAD-USD": [_PaperPos("t1", 1, 1.0, 100.0, 99.0, None, 0.0, 0.0)],
              "SYN-USD": [_PaperPos("t2", 1, 1.0, 100.0, 99.0, None, 0.0, 0.0)]}
    venue.px = 98.0                                   # both stops are hit
    events = ex.tick()
    assert [e["symbol"] for e in events] == ["SYN-USD"] and ex.skipped == 1
    assert "BAD-USD" in ex.pos and ex.pos["BAD-USD"]  # still open: checked on the next turn
    venue.down = set()
    assert [e["symbol"] for e in ex.tick()] == ["BAD-USD"]

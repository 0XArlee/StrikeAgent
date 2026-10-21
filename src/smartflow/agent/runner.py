"""The Smart Flow agent loop.

Per market, at every closed candle of the configured timeframe:
1. pull the newly closed Binance bars (signal feed) and HTF bars, push them through the same ``StreamingRunner`` the
   backtest uses, and journal an ``analysis`` record that explains the bar (signal or the reasons for none);
2. manage the open trade: the hard stop lives on the exchange; the close-based exit (``core.exits.close_exit``, the
   same function the backtester uses) is decided here and sent as a reduce-only market order;
3. on a new signal: build the proposal, run the risk engine, then act according to the mode:
   ``analysis`` journal only · ``simulation`` paper fills on Strike's live book · ``confirmation`` write a pending
   proposal and wait for ``smartflow agent approve`` · ``autonomous`` send it (explicitly enabled only).

Between candles it reconciles local trade records with the exchange, checks that every position has its stop
resting, polls paper stops, honours the kill switch and expires stale confirmations. Unknown state never produces
orders: the market is blocked and an alert is raised.

Position policy (``AgentConfig.policy``): ``single`` holds at most one trade per market (the published strategy);
``pyramid`` stacks up to ``max_stack`` trades in the same direction. Strike nets them into one position; each trade
keeps its own lot, its own reduce-only stop and its own close-based exit, and opposite signals wait until the stack
is flat (backtest: smartflow.backtest.volume_study).
"""

from __future__ import annotations

import dataclasses
import json
import math
import time
from dataclasses import dataclass, field
from decimal import ROUND_UP, Decimal
from pathlib import Path

from ..core.exits import close_exit, trailing_level
from ..core.runner import StreamingRunner
from ..core.timeframes import bar_close_time, normalize, tf_ms
from ..core.types import Candle
from ..data.binance import kline_path
from ..data.store import load_candles
from ..strike.auth import ApiWalletSigner
from ..strike.client import MAINNET, TESTNET, BuilderFee, StrikeClient
from .config import AgentConfig
from .execution import EntryPlan, ExecutionAdapter, PaperExecution, StrikeExecution, client_id
from .feeds import fetch_closed, status
from .journal import Journal
from .lifecycle import S, TradeRecord
from .risk import AccountContext, MarketContext, Proposal, RiskEngine


UNTRACKED = "unknown position on the exchange"   # a position the agent did not open (e.g. by hand)


def _tol(qty: float) -> float:
    """Size tolerance when matching the netted position against the open trades (rounding of lot sizes)."""
    return max(1e-12, 1e-6 * abs(qty))


@dataclass
class MarketState:
    strike: str
    signal: str
    runner: StreamingRunner
    last_open: int = -1
    last_htf_open: int = -1
    healthy: bool = True
    blocked: str = ""                     # reason the market cannot open trades (unreconciled state, data...)
    trades: list[TradeRecord] = field(default_factory=list)   # oldest first; "single" policy: at most one
    last_state: object = None

    @property
    def trade(self) -> TradeRecord | None:
        """The oldest open trade (the only one under the single policy)."""
        return self.trades[0] if self.trades else None


@dataclass
class Agent:
    cfg: AgentConfig
    adapter: ExecutionAdapter | None = None
    journal: Journal = None
    markets: dict[str, MarketState] = field(default_factory=dict)
    public: StrikeClient = None

    # ------------------------------------------------------------------ construction
    @classmethod
    def build(cls, cfg: AgentConfig, signer: ApiWalletSigner | None = None) -> "Agent":
        """``signer``: the API wallet to trade with (a user's key from the fleet); default: STRIKE_API_* env."""
        base = TESTNET if cfg.env == "testnet" else MAINNET
        public = StrikeClient(base)
        journal = Journal(cfg.run_dir / "journal.jsonl", cfg.mode, cfg.params.fingerprint())
        adapter: ExecutionAdapter | None = None
        if cfg.mode == "simulation":
            adapter = PaperExecution(public, cfg.paper_equity, builder_fee_bps=cfg.builder_fee_bps)
        elif cfg.mode in ("confirmation", "autonomous"):
            builder = (BuilderFee(cfg.builder_code, cfg.builder_fee_bps, cfg.builder_fee_approved_bps)
                       if cfg.builder_code and cfg.builder_fee_bps > 0 else None)
            client = StrikeClient(base, signer or ApiWalletSigner.from_env(), builder, sub_account_id=cfg.sub_account_id)
            client.trace = lambda r: journal.write("strike_call", **r)   # every order, cancel and change, as answered
            client.sync_clock()
            adapter = StrikeExecution(client)
        a = cls(cfg, adapter, journal, public=public)
        a._load_state()
        if isinstance(adapter, PaperExecution):
            adapter.restore(a._saved.get("_paper", {}))
        return a

    # ------------------------------------------------------------------ persistence
    @property
    def state_path(self) -> Path:
        return self.cfg.run_dir / "state.json"

    def _load_state(self) -> None:
        self._saved = json.loads(self.state_path.read_text()) if self.state_path.exists() else {}
        # the journal also knows which test requests ran (a state file written before they were kept there)
        done = self._saved.setdefault("_tests", [])
        jp = self.cfg.run_dir / "journal.jsonl"
        if jp.exists():
            for line in jp.read_text(encoding="utf-8").splitlines():
                if '"kind": "test"' not in line:
                    continue
                try:
                    at = int(json.loads(line).get("at") or 0)
                except (json.JSONDecodeError, TypeError, ValueError):
                    continue
                if at and at not in done:
                    done.append(at)
            del done[:-20]

    def _save_state(self) -> None:
        d = {s: {"trades": [t.to_dict() for t in m.trades], "trade": m.trade.to_dict() if m.trade else None,
                 "blocked": m.blocked} for s, m in self.markets.items()}
        d["_equity_marks"] = self._saved.get("_equity_marks", {})
        d["_tests"] = self._saved.get("_tests", [])   # test requests already run: never twice, also across restarts
        if isinstance(self.adapter, PaperExecution):
            d["_paper"] = self.adapter.snapshot()
        self.state_path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.state_path.with_suffix(".tmp")
        tmp.write_text(json.dumps(d, indent=1, default=str))
        tmp.replace(self.state_path)

    # ------------------------------------------------------------------ warm-up
    def warmup(self, log=print) -> None:
        root = Path(self.cfg.data_root)
        tf = normalize(self.cfg.tf)
        for mm in self.cfg.markets:
            r = StreamingRunner(self.cfg.params, tf)
            hist = load_candles(kline_path(root, mm.signal, tf), f"binance-spot:{mm.signal}")
            htf = load_candles(kline_path(root, mm.signal, r.htf), f"binance-spot:{mm.signal}")
            # top up from the exchange (closed bars only)
            since = hist[-1].open_time + 1 if hist else None
            hist += [c for c in fetch_closed(mm.signal, tf, 1000, start_ms=since)
                     if not hist or c.open_time > hist[-1].open_time]
            since_h = htf[-1].open_time + 1 if htf else None
            htf += [c for c in fetch_closed(mm.signal, r.htf, 1000, start_ms=since_h)
                    if not htf or c.open_time > htf[-1].open_time]
            ms_ = MarketState(mm.strike, mm.signal, r)
            j = 0
            last_c = None
            for c in hist:
                last_c = c
                close_t = bar_close_time(c.open_time, tf)
                while j < len(htf) and bar_close_time(htf[j].open_time, r.htf) <= close_t:
                    r.push_htf(htf[j])
                    ms_.last_htf_open = htf[j].open_time
                    j += 1
                ms_.last_state = r.push(c)
                ms_.last_open = c.open_time
            saved = self._saved.get(mm.strike, {})
            rows = saved.get("trades") if saved.get("trades") is not None else ([saved["trade"]] if saved.get("trade") else [])
            ms_.trades = [t for t in (TradeRecord.from_dict(r) for r in rows) if t.active]
            ms_.blocked = saved.get("blocked", "")
            self.markets[mm.strike] = ms_
            if last_c is not None:
                self._journal_bar(ms_, last_c, ms_.last_state, True)
            log(f"warm-up {mm.strike} <- {mm.signal} {tf}: {r.engine.bars} bars, HTF {r.htf} {len(htf)} bars, "
                f"last bar {time.strftime('%Y-%m-%d %H:%M', time.gmtime(ms_.last_open / 1000))} UTC")
        self._save_state()

    # ------------------------------------------------------------------ per-candle step
    def step(self, now_ms: int | None = None) -> None:
        now_ms = now_ms or int(time.time() * 1000)
        tf = normalize(self.cfg.tf)
        for m in self.markets.values():
            try:
                self._step_market(m, tf, now_ms)
            except Exception as e:
                m.healthy = False
                self.journal.alert("error", f"{m.strike}: step failed: {e!r}", market=m.strike)
        self._save_state()

    def _step_market(self, m: MarketState, tf: str, now_ms: int) -> None:
        r = m.runner
        new = [c for c in fetch_closed(m.signal, tf, 20, now_ms) if c.open_time > m.last_open]
        htf_new = [c for c in fetch_closed(m.signal, r.htf, 10, now_ms) if c.open_time > m.last_htf_open]
        if len(new) >= 20:
            self.journal.alert("warning", f"{m.strike}: {len(new)}+ bars missed (agent was down); signals in the "
                                          f"gap are not traded", market=m.strike)
        states = []
        for c in new:
            close_t = bar_close_time(c.open_time, tf)
            for h in [h for h in htf_new if bar_close_time(h.open_time, r.htf) <= close_t
                      and h.open_time > m.last_htf_open]:
                r.push_htf(h)
                m.last_htf_open = h.open_time
            st = r.push(c)
            m.last_open = c.open_time
            m.last_state = st
            states.append((c, st))
        feed = status([c for c, _ in states] or [Candle(m.last_open, 0, 0, 0, 0, 0)], tf, now_ms)
        m.healthy = feed.ok
        if not feed.ok:
            self.journal.alert("warning", f"{m.strike}: signal feed unhealthy: {feed.message}", market=m.strike,
                               expected=feed.expected_open, last=feed.last_closed_open)
        if not r.bias.ready_for(m.last_open):
            m.healthy = False
            self.journal.alert("warning", f"{m.strike}: HTF bar missing, bias would be stale", market=m.strike)

        for k, (c, st) in enumerate(states):
            latest = k == len(states) - 1
            self._journal_bar(m, c, st, latest)
            for rec in [t for t in m.trades if t.state in (S.POSITION_OPEN, S.PROTECTED)]:
                self._manage_exit(m, rec, st)
                if rec.state == S.PROTECTED:
                    self._chandelier(m, rec, c, st)
            if st.sig_dir != 0:
                if latest and m.healthy:
                    self._on_signal(m, c, st, now_ms)
                else:
                    self.journal.write("signal", market=m.strike, bar=c.open_time, dir=st.sig_dir,
                                       action="not traded", reason="stale bar or unhealthy data")

    def _journal_bar(self, m: MarketState, c: Candle, st, latest: bool) -> None:
        p = self.cfg.params
        rec = dict(market=m.strike, feed=c.source, bar=c.open_time, close=c.close, atr=st.atr, rel_vol=st.rel_vol,
                   flow=st.flow, htf_trend=st.htf_trend, ema_trend=st.ema_trend, sig_raw=st.sig_raw,
                   sig_dir=st.sig_dir, skip=st.skip_reason, why=st.why_no_signal(p), notes=st.notes)
        live = [t for t in m.trades if t.active and "stop" in t.data]
        if live:
            levels = [{"trade_id": t.trade_id, "dir": t.dir, "state": t.state.value,
                       "exit_if_close_beyond": trailing_level(st, t.dir, t.data["stop"], p)} for t in live]
            rec["open_trade"] = {k: levels[0][k] for k in ("dir", "state", "exit_if_close_beyond")}
            if len(levels) > 1:
                rec["open_trades"] = levels
        self.journal.write("analysis", **rec)

    # ------------------------------------------------------------------ signals
    def _on_signal(self, m: MarketState, c: Candle, st, now_ms: int) -> None:
        p = self.cfg.params
        trade_id = f"{m.strike}-{c.open_time}-{'L' if st.sig_dir == 1 else 'S'}"
        if any(t.trade_id == trade_id for t in m.trades):
            return
        stop = st.close - st.sig_dir * p.stop_atr * st.atr
        tp = st.close + st.sig_dir * p.tp_r * p.stop_atr * st.atr if p.tp_r > 0 else None
        rec = TradeRecord(trade_id, m.strike, st.sig_dir, c.open_time)
        rec.data.update(signal_bar_index=m.runner.engine.bars - 1, signal_close=st.close, atr=st.atr, stop=stop,
                        tp=tp, feed=c.source)
        self.journal.write("signal", market=m.strike, trade_id=trade_id, dir=st.sig_dir, close=st.close,
                           atr=st.atr, stop=stop, tp=tp, rel_vol=st.rel_vol, flow=st.flow, htf_trend=st.htf_trend,
                           disp_atr=st.rng / st.atr, body_pct=100 * st.body / st.rng if st.rng else None,
                           exit_rule=f"close beyond the {p.chan_n}-candle channel" if p.exit_mode.value ==
                           "Trailing channel" else p.exit_mode.value)
        rec.to(S.SIGNAL_VALIDATED, "engine signal on a closed bar")
        if m.blocked:
            rec.to(S.REJECTED_BY_RISK, f"market blocked: {m.blocked}")
            self.journal.write("decision", trade_id=trade_id, accepted=False, reasons=[m.blocked])
            return
        if self.adapter is not None and self.adapter.live:
            # the strategy's safety hold (live/health.py): real money opens nothing new until the operator lifts it;
            # the paper agents keep trading so the strategy is still measured
            from ..live.health import hold_reason
            why = hold_reason(Path(self.cfg.runs_root), self.cfg.strategy)
            if why:
                rec.to(S.REJECTED_BY_RISK, f"strategy on hold: {why}")
                self.journal.write("decision", trade_id=trade_id, accepted=False, reasons=[f"strategy on hold: {why}"])
                return
        # pyramid: another trade in the same direction while the stack has room and every open one is settled
        held = [t for t in m.trades if t.active]
        stacking = self.cfg.policy == "pyramid" and bool(held)
        if stacking:
            why = ("an opposite position is open" if any(t.dir != rec.dir for t in held)
                   else f"stack full ({len(held)} trades)" if len(held) >= self.cfg.max_stack
                   else "a previous entry is not settled yet" if any(t.state not in (S.POSITION_OPEN, S.PROTECTED)
                                                                     for t in held) else "")
            if why:
                rec.to(S.REJECTED_BY_RISK, why)
                self.journal.write("decision", trade_id=trade_id, accepted=False, reasons=[why])
                return
        if self.adapter is None:   # analysis mode: size it on a nominal account for information
            q = self._public_quote(m.strike)
            decision = self._risk(m, rec, q, AccountContext(self.cfg.paper_equity, self.cfg.paper_equity, 0, 0.0,
                                                            0.0, 0.0, False, 0), now_ms)
            self.journal.write("decision", trade_id=trade_id, accepted=decision.accepted, reasons=decision.reasons,
                               summary=decision.summary(), note="analysis mode: nothing sent")
            rec.to(S.REJECTED_BY_RISK if not decision.accepted else S.CANCELLED,
                   "analysis mode" if decision.accepted else "; ".join(decision.reasons))
            return
        q = self.adapter.quote(m.strike)
        acct = self.adapter.account()
        pos = self.adapter.position(m.strike)
        n_open = sum(1 for x in self.markets.values() for t in x.trades if t.state in (S.POSITION_OPEN, S.PROTECTED))
        open_notional = sum(abs(t.data.get("qty", 0)) * t.data.get("entry", 0)
                            for x in self.markets.values() for t in x.trades if t.active)
        pending = [o for o in self.adapter.open_orders(m.strike) if not o.reduce_only]
        day_pnl, week_pnl = self._loss_windows(acct.margin_balance)
        actx = AccountContext(acct.margin_balance, acct.available_balance, n_open, open_notional, day_pnl, week_pnl,
                              pos is not None and not stacking, len(pending))
        decision = self._risk(m, rec, q, actx, now_ms)
        self.journal.write("decision", trade_id=trade_id, accepted=decision.accepted, reasons=decision.reasons,
                           summary=decision.summary(), **({"stack": len(held) + 1} if stacking else {}))
        if not decision.accepted:
            rec.to(S.REJECTED_BY_RISK, "; ".join(decision.reasons))
            return
        # Strike's leverage is per market: a stacked entry never lowers the one the open position already has
        plan = self._plan(m, rec, q, decision, keep=int(pos.leverage or 0) if pos is not None else 0)
        rec.to(S.ORDER_PREPARED, "risk accepted")
        rec.data.update(qty=float(plan.qty), limit=str(plan.limit_price), plan_stop=str(plan.stop),
                        lev=plan.leverage, decision=decision.summary())
        m.trades.append(rec)
        if self.cfg.mode == "confirmation":
            rec.to(S.PENDING_AUTHORIZATION, "waiting for operator approval")
            pend = self.cfg.run_dir / "pending" / f"{trade_id}.json"
            pend.parent.mkdir(parents=True, exist_ok=True)
            pend.write_text(json.dumps({"trade_id": trade_id, "market": m.strike, "dir": rec.dir,
                                        "qty": str(plan.qty), "limit": str(plan.limit_price),
                                        "stop": str(plan.stop), "tp": str(plan.take_profit),
                                        "decision": decision.summary(), "expires": time.time() + self.cfg.confirm_ttl_s,
                                        "approved": False}, indent=1))
            self.journal.alert("info", f"{m.strike}: {'BUY' if rec.dir == 1 else 'SELL'} proposal waiting for "
                                       f"approval: smartflow agent approve {trade_id}", trade_id=trade_id)
            return
        self._execute(m, rec, plan)

    def _public_quote(self, symbol: str):
        from .execution import _StrikeMarketData
        return _StrikeMarketData(self.public).quote(symbol)

    def _risk(self, m: MarketState, rec: TradeRecord, q, actx: AccountContext, now_ms: int):
        md = self.adapter if self.adapter is not None else None
        if md is None:
            from .execution import _StrikeMarketData
            md = _StrikeMarketData(self.public)
        spec = md.market_spec(m.strike)
        ref = q.ask if rec.dir == 1 else q.bid
        est_qty = self.cfg.risk.risk_per_trade * actx.equity / max(1e-12, abs(ref - rec.data["stop"]))
        impact = md.impact_bps(m.strike, rec.dir, est_qty)
        fees = self.public.fee_tiers()
        taker = fees[0].taker if fees else 0.0005
        age = (now_ms - bar_close_time(rec.signal_time, normalize(self.cfg.tf))) / 1000
        prop = Proposal(m.strike, rec.dir, ref, rec.data["stop"], rec.data["tp"], rec.data["signal_close"], age)
        mctx = MarketContext(spec, q.bid, q.ask, q.mark, impact, taker, self.cfg.builder_fee_bps)
        rec.data["market_ctx"] = {"bid": q.bid, "ask": q.ask, "mark": q.mark, "index": q.index,
                                  "funding_rate": q.funding_rate, "impact_bps": impact, "taker": taker}
        return RiskEngine(self.cfg.risk, Path(".")).evaluate(prop, mctx, actx)

    def _plan(self, m: MarketState, rec: TradeRecord, q, decision, keep: int = 0) -> EntryPlan:
        spec = self.adapter.market_spec(m.strike)
        slip = self.cfg.max_entry_slippage_bps / 1e4
        limit = spec.round_price(q.ask * (1 + slip), side_up=True) if rec.dir == 1 else \
            spec.round_price(q.bid * (1 - slip), side_up=False)
        stop = spec.round_price(rec.data["stop"], side_up=None)
        tp = spec.round_price(rec.data["tp"], side_up=rec.dir == -1) if rec.data["tp"] else None
        return EntryPlan(rec.trade_id, m.strike, rec.dir, decision.qty, limit, stop, tp,
                         int(max(1, math.ceil(decision.leverage), keep)))

    def _drop(self, m: MarketState, rec: TradeRecord) -> None:
        if rec in m.trades:
            m.trades.remove(rec)

    def _execute(self, m: MarketState, rec: TradeRecord, plan: EntryPlan) -> None:
        kind = "live_order" if self.adapter.live else "paper_order"
        ack = self.adapter.submit_entry(plan)
        self.journal.write(kind, trade_id=rec.trade_id, market=m.strike, action="entry", ok=ack.ok,
                           client_order_id=ack.client_order_id, response=ack.response, error=ack.error,
                           plan={"qty": str(plan.qty), "limit": str(plan.limit_price), "stop": str(plan.stop),
                                 "tp": str(plan.take_profit), "lev": plan.leverage})
        rec.data["entry_cid"] = ack.client_order_id
        if not ack.ok and ack.uncertain:
            rec.to(S.ORDER_SENT, "outcome unknown")
            rec.to(S.RECONCILIATION_PENDING, f"entry request failed with unknown outcome: {ack.error}")
            rec.data["sent_at"] = time.time()
            m.blocked = "entry outcome unknown"
            self.journal.alert("error", f"{m.strike}: entry outcome unknown ({ack.error[:120]}); NOT resending, "
                                        "reconciling by client_order_id", trade_id=rec.trade_id)
            return
        if not ack.ok:
            rec.to(S.CANCELLED, f"entry rejected: {ack.error}")
            self._drop(m, rec)
            return
        rec.to(S.ORDER_SENT, ack.client_order_id)
        rec.data["sent_at"] = time.time()
        self._confirm_entry(m, rec)

    # ------------------------------------------------------------------ reconciliation & protection
    def _others_qty(self, m: MarketState, rec: TradeRecord) -> float:
        """Size held by the market's other open trades (the position is their net sum)."""
        return sum(abs(t.data.get("qty", 0.0)) for t in m.trades
                   if t is not rec and t.state in (S.POSITION_OPEN, S.PROTECTED, S.EXIT_REQUESTED) and "entry" in t.data)

    def _confirm_entry(self, m: MarketState, rec: TradeRecord, wait_s: float = 8.0) -> None:
        deadline = time.time() + wait_s
        order = None
        while time.time() < deadline:
            order = self.adapter.find_order(m.strike, rec.data["entry_cid"])
            if order and order.is_terminal:
                break
            time.sleep(1.0 if self.adapter.live else 0)
        pos = self.adapter.position(m.strike)
        others = self._others_qty(m, rec)
        mine = abs(pos.size) - others if pos is not None and pos.side == rec.dir else 0.0
        if order is None and mine > _tol(others):
            # Strike mainnet (2026-10-20): a completed order is no longer returned by /v2/order (nor its history),
            # and fills carry no client id. The netted position is the truth: it grew by this trade's lot.
            status, builder = "filled", (None, None)
        elif order is None:
            rec.to(S.RECONCILIATION_PENDING, "entry not seen (IOC not filled, or not visible yet)")
            m.blocked = "entry order state unknown"
            self.journal.alert("warning", f"{m.strike}: entry not seen after {wait_s}s (IOC not filled?); no new "
                                          "trades here until reconciled", trade_id=rec.trade_id)
            return
        else:
            status, builder = order.status, (order.builder_code, order.builder_fee_bps)
        if pos is None or pos.side != rec.dir or mine <= _tol(others):
            if order.status in ("canceled", "rejected", "expired") and order.filled == 0:
                rec.to(S.CANCELLED, f"entry {order.status} (IOC not filled within the protective price)")
                self.journal.write("decision", trade_id=rec.trade_id, accepted=False,
                                   reasons=[f"entry {order.status}: not filled"])
                self._drop(m, rec)
                return
            rec.to(S.RECONCILIATION_PENDING, f"order {order.status} but no position seen")
            m.blocked = "order/position mismatch"
            self.journal.alert("error", f"{m.strike}: order {order.status} filled={order.filled} but no "
                                        "position; market blocked", trade_id=rec.trade_id)
            return
        # this trade's own lot out of the netted position (the size-weighted entry of the others is known)
        held = [t for t in m.trades if t is not rec and t.state in (S.POSITION_OPEN, S.PROTECTED, S.EXIT_REQUESTED)
                and "entry" in t.data]
        entry = (abs(pos.size) * pos.entry_price - sum(abs(t.data["qty"]) * t.data["entry"] for t in held)) / mine \
            if held else pos.entry_price
        rec.data.update(entry=entry, qty=mine, filled_at=time.time(), builder=builder)
        if self.adapter.live and self.cfg.builder_fee_bps > 0 and builder[1] is not None and builder[1] != self.cfg.builder_fee_bps:
            self.journal.alert("error", f"{m.strike}: builder attribution mismatch: order shows "
                                        f"{builder[0]}/{builder[1]} bps, expected "
                                        f"{self.cfg.builder_code}/{self.cfg.builder_fee_bps}", trade_id=rec.trade_id)
        rec.to(S.POSITION_OPEN if status == "filled" else S.PARTIALLY_FILLED, f"filled {mine} @ {entry}")
        if rec.state == S.PARTIALLY_FILLED:
            rec.to(S.POSITION_OPEN, "IOC remainder cancelled; trading the filled size")
        self.journal.write("fill", trade_id=rec.trade_id, market=m.strike, entry=entry, qty=mine * rec.dir,
                           order_status=status, builder=builder[0], builder_fee_bps=builder[1],
                           **({"stack": len(held) + 1} if held else {}))
        self._ensure_stop(m, rec)

    def _stop_cids(self, rec: TradeRecord) -> set[str]:
        """Every stop this trade ever had: the bracket's leg, the fallback and any placed again."""
        return {client_id(rec.trade_id, k) for k in ("stop", "stop2", *rec.data.get("stop_purposes", []),
                                                      *rec.data.get("trail_purposes", []))}

    def _ensure_stop(self, m: MarketState, rec: TradeRecord) -> None:
        """This trade's own stop must be resting (the bracket's leg or the fallback one)."""
        mine = self._stop_cids(rec)
        stops = [o for o in self.adapter.open_orders(m.strike)
                 if o.reduce_only and o.type in ("stop", "stop_limit") and o.status in ("untriggered", "open", "pending")
                 and o.client_order_id in mine]
        if stops:
            leg = stops[0]
            rec.data["stop_seen"] = True
            # the stop leg carries the builder attribution too (Strike: legs inherit the entry's code and bps)
            if (self.adapter.live and self.cfg.builder_fee_bps > 0 and leg.builder_fee_bps is not None
                    and leg.builder_fee_bps != self.cfg.builder_fee_bps and not rec.data.get("builder_alerted")):
                rec.data["builder_alerted"] = True
                self.journal.alert("error", f"{m.strike}: builder attribution mismatch on the stop leg: "
                                            f"{leg.builder_code}/{leg.builder_fee_bps} bps, expected "
                                            f"{self.cfg.builder_code}/{self.cfg.builder_fee_bps}", trade_id=rec.trade_id)
            rec.to(S.PROTECTED, f"stop resting @ {leg.stop_price}")
            return
        qty = Decimal(str(rec.data["qty"]))
        ack = self.adapter.submit_stop(rec.trade_id, m.strike, rec.dir, qty, Decimal(rec.data["plan_stop"]))
        self.journal.write("live_order" if self.adapter.live else "paper_order", trade_id=rec.trade_id,
                           action="fallback stop", ok=ack.ok, error=ack.error, response=ack.response)
        if ack.ok:
            rec.to(S.PROTECTED, "fallback reduce-only stop placed")
        else:
            self.journal.alert("critical", f"{m.strike}: position WITHOUT stop and fallback failed: closing",
                               trade_id=rec.trade_id)
            self._request_exit(m, rec, "no protection")

    def _manage_exit(self, m: MarketState, rec: TradeRecord, st) -> None:
        if rec.data.get("test"):   # a test trade ends on its timer (or its stop), never on a strategy exit
            return
        bars_since = m.runner.engine.bars - 1 - rec.data["signal_bar_index"]
        reason = close_exit(st, rec.dir, bars_since, self.cfg.params)
        if reason:
            self._request_exit(m, rec, reason)

    def _chandelier(self, m: MarketState, rec: TradeRecord, c: Candle, st) -> None:
        """Official rule (``Params.chand_atr``): after each close the trade's stop on the exchange rises to the best
        extreme since the entry minus chand_atr ATR, and never loosens. The new stop is on the book before the old one
        is cancelled, so the trade is never unprotected. Moves under 0.1 ATR are skipped (no order churn)."""
        p = self.cfg.params
        if p.chand_atr <= 0 or rec.data.get("test") or "entry" not in rec.data or not st.atr or math.isnan(st.atr):
            return
        if m.runner.engine.bars - 1 - rec.data["signal_bar_index"] < 1:
            return
        d = rec.dir
        best = float(rec.data.get("best", rec.data["entry"]))
        best = max(best, c.high) if d == 1 else min(best, c.low)
        rec.data["best"] = best
        spec = self.adapter.market_spec(m.strike)
        new = spec.round_price(best - d * p.chand_atr * st.atr, side_up=d == -1)   # rounded away from the price
        cur = float(rec.data["plan_stop"])
        if (float(new) - cur) * d < max(float(spec.tick), 0.1 * st.atr):
            return
        if (st.close - float(new)) * d <= 0:   # the trail is already through the close: leave now, at market
            self._request_exit(m, rec, "chandelier stop")
            return
        purposes = rec.data.setdefault("trail_purposes", [])
        purpose = f"tr{len(purposes) + 1}"
        old = self._stop_cids(rec)
        ack = self.adapter.submit_stop(rec.trade_id, m.strike, d, Decimal(str(rec.data["qty"])), new, purpose=purpose)
        self.journal.write("live_order" if self.adapter.live else "paper_order", trade_id=rec.trade_id, market=m.strike,
                           action="stop moved", old=cur, new=float(new), ok=ack.ok, error=ack.error)
        if not ack.ok:
            self.journal.alert("warning", f"{m.strike}: could not raise the stop to {new} ({ack.error}); the previous "
                                          f"stop stays", trade_id=rec.trade_id)
            return
        purposes.append(purpose)
        rec.data["plan_stop"], rec.data["stop"] = str(new), float(new)
        for o in self.adapter.open_orders(m.strike):
            if o.reduce_only and o.client_order_id in old:
                try:
                    self.adapter.cancel(m.strike, o.order_id)
                except Exception as e:
                    self.journal.alert("warning", f"{m.strike}: could not cancel the previous stop {o.client_order_id}: {e}")

    def _request_exit(self, m: MarketState, rec: TradeRecord, reason: str) -> None:
        pos = self.adapter.position(m.strike) if self.adapter else None
        if pos is None:
            rec.to(S.RECONCILIATION_PENDING, "exit wanted but no position (closed on exchange?)")
            self.reconcile()
            return
        rec.to(S.EXIT_REQUESTED, reason)
        # alone in the market it closes the whole position; stacked, only its own lot
        alone = not any(t is not rec and t.state in (S.POSITION_OPEN, S.PROTECTED, S.EXIT_REQUESTED) for t in m.trades)
        qty = abs(pos.size) if alone else min(abs(pos.size), abs(rec.data.get("qty", 0.0)))
        ack = self.adapter.submit_exit(rec.trade_id, m.strike, rec.dir, Decimal(str(qty)), reason)
        self.journal.write("live_order" if self.adapter.live else "paper_order", trade_id=rec.trade_id,
                           action="exit", reason=reason, ok=ack.ok, response=ack.response, error=ack.error)
        if not ack.ok:
            rec.to(S.ERROR, f"exit failed: {ack.error}")
            self.journal.alert("critical", f"{m.strike}: exit order failed ({ack.error}); position still open",
                               trade_id=rec.trade_id)
            return
        if alone:
            self._finish_if_flat(m, rec, reason)
        else:
            self._finish_lot(m, rec, reason)

    def _cancel_legs(self, m: MarketState, rec: TradeRecord | None) -> None:
        """Cancel the resting reduce-only legs of one trade (or every leg when ``rec`` is None)."""
        mine = (self._stop_cids(rec) | {client_id(rec.trade_id, "target")}) if rec else None
        for o in self.adapter.open_orders(m.strike):
            if o.reduce_only and (mine is None or o.client_order_id in mine):
                try:
                    self.adapter.cancel(m.strike, o.order_id)
                except Exception as e:
                    self.journal.alert("warning", f"{m.strike}: could not cancel leftover {o.client_order_id}: {e}")

    def _close_trade(self, m: MarketState, rec: TradeRecord, reason: str, **extra) -> None:
        rec.to(S.POSITION_CLOSED, reason)
        self.journal.write("exit", trade_id=rec.trade_id, market=m.strike, reason=reason, **extra)
        self._drop(m, rec)

    def _finish_if_flat(self, m: MarketState, rec: TradeRecord, reason: str) -> None:
        if self.adapter.position(m.strike) is None:
            self._cancel_legs(m, None)   # leftover strategy legs
            self._close_trade(m, rec, reason)

    def _finish_lot(self, m: MarketState, rec: TradeRecord, reason: str) -> None:
        """A stacked trade's exit: once its lot left the position, its own legs go and the others stay. Mainnet does
        not return completed orders, so the netted position decides (the order, where the venue still has it)."""
        o = self.adapter.find_order(m.strike, client_id(rec.trade_id, "exit"))
        pos = self.adapter.position(m.strike)
        others = self._others_qty(m, rec)
        left = (o is not None and o.status == "filled") or (pos is None and others <= 0) or \
            (pos is not None and abs(abs(pos.size) - others) <= _tol(others))
        if left:
            self._cancel_legs(m, rec)
            self._close_trade(m, rec, reason)

    def reconcile(self) -> None:
        """Compare local records with the exchange. Never sends entries; may only close/cancel or block."""
        if self.adapter is None:
            return
        for ev in self.adapter.tick():   # paper stops/targets, one lot at a time
            m = self.markets.get(ev["symbol"])
            if not m:
                continue
            rec = next((t for t in m.trades if t.trade_id == ev.get("trade_id")), None)
            if rec is None and len(m.trades) == 1:
                rec = m.trades[0]
            if rec and rec.state in (S.PROTECTED, S.POSITION_OPEN, S.EXIT_REQUESTED):
                if ev.get("reason") == "stop" and rec.data.get("trail_purposes"):
                    ev = {**ev, "reason": "chandelier stop"}   # the stop had followed the price
                rec.to(S.POSITION_CLOSED, ev["reason"])
                self.journal.write("exit", market=m.strike, **ev)
                self._drop(m, rec)
        try:   # one call for every market (a call per market adds up across many users' agents)
            positions = self.adapter.all_positions()
        except Exception as e:
            self.journal.alert("warning", f"reconcile read failed: {e!r}")
            return
        for m in self.markets.values():
            pos = positions.get(m.strike)
            held = [t for t in m.trades if t.state in (S.POSITION_OPEN, S.PROTECTED, S.EXIT_REQUESTED)]
            settling = [t for t in m.trades if t.state in (S.RECONCILIATION_PENDING, S.ORDER_SENT)]
            if pos is not None and not held and not settling:
                if m.blocked != UNTRACKED:   # say it once, not at every reconcile
                    m.blocked = UNTRACKED
                    self.journal.alert("error", f"{m.strike}: position {pos.size} not tracked by the agent (opened "
                                                "outside it?); no new trades here while it is open", market=m.strike)
            elif pos is None and not held and not settling and m.blocked == UNTRACKED:
                m.blocked = ""               # the owner closed it: the market is the agent's again
                self.journal.alert("info", f"{m.strike}: the untracked position is gone; trading here again",
                                   market=m.strike)
            elif held and pos is None:
                for rec in held:
                    self._close_trade(m, rec, "closed on the exchange (chandelier stop)" if rec.data.get("trail_purposes")
                                      else "closed on the exchange (stop/target/liquidation)")
                self._cancel_legs(m, None)
            elif held and pos is not None:
                self._settle_lots(m, held, pos)
            for rec in [t for t in m.trades if t.state == S.RECONCILIATION_PENDING]:
                if pos is not None and pos.side == rec.dir and abs(pos.size) > self._others_qty(m, rec) + 1e-12:
                    others = self._others_qty(m, rec)
                    mine = abs(pos.size) - others
                    rec.data.update(entry=rec.data.get("entry", pos.entry_price) if others else pos.entry_price, qty=mine)
                    rec.to(S.POSITION_OPEN, "reconciled: position found")
                    m.blocked = ""
                    self._ensure_stop(m, rec)
                elif pos is None or abs(pos.size) <= self._others_qty(m, rec) + 1e-12:
                    o = self.adapter.find_order(m.strike, rec.data["entry_cid"]) if rec.data.get("entry_cid") else None
                    if o is not None and not o.is_terminal:
                        continue                     # still working on the engine: wait
                    if o is None and time.time() - rec.data.get("sent_at", 0) < 60:
                        continue                     # may not be visible yet
                    rec.to(S.POSITION_CLOSED if "entry" in rec.data else S.CANCELLED,
                           f"reconciled: no position (order {o.status if o else 'not found'})")
                    m.blocked = ""
                    self._drop(m, rec)
            for rec in [t for t in m.trades if t.state == S.POSITION_OPEN]:
                self._ensure_stop(m, rec)
        self._save_state()

    def _settle_lots(self, m: MarketState, held: list[TradeRecord], pos) -> None:
        """The position is still open: match it against the open trades. Lots that are gone (their stop, target or
        exit filled) are closed; a stop that vanished while the position is whole is placed again."""
        resting = {o.client_order_id for o in self.adapter.open_orders(m.strike)
                   if o.reduce_only and o.status in ("untriggered", "open", "pending")}
        total = sum(abs(t.data.get("qty", 0.0)) for t in held)
        missing = total - abs(pos.size)
        if missing > _tol(total) and len(held) > 1:
            gone = []
            for rec in held:
                own = self._stop_cids(rec) | {client_id(rec.trade_id, "target")}
                filled = any((o := self.adapter.find_order(m.strike, cid)) is not None and o.status == "filled"
                             for cid in own | {client_id(rec.trade_id, "exit")})
                stop_gone = rec.state == S.PROTECTED and rec.data.get("stop_seen") and not (own & resting)
                if filled or stop_gone or rec.state == S.EXIT_REQUESTED:
                    gone.append(rec)
            if gone and abs(sum(abs(t.data.get("qty", 0.0)) for t in gone) - missing) <= _tol(total):
                for rec in gone:
                    self._cancel_legs(m, rec)
                    self._close_trade(m, rec, ("closed on the exchange (chandelier stop)" if rec.data.get("trail_purposes")
                                               else "closed on the exchange (stop)") if rec.state != S.EXIT_REQUESTED
                                      else rec.history[-1][2] if rec.history else "exit")
            elif m.blocked != "stacked position does not match":
                m.blocked = "stacked position does not match"
                self.journal.alert("error", f"{m.strike}: position {pos.size} does not match the open trades "
                                            f"({total} held); no new trades here until it does", market=m.strike)
            return
        if abs(missing) <= _tol(total):
            if m.blocked == "stacked position does not match":
                m.blocked = ""
            for rec in held:   # whole position: every PROTECTED trade must still have its own stop resting
                purposes = rec.data.setdefault("stop_purposes", [])
                if rec.state == S.PROTECTED and rec.data.get("stop_seen") and not (self._stop_cids(rec) & resting):
                    if len(purposes) >= 3:   # placed again three times and gone again: close instead of looping
                        self._request_exit(m, rec, "stop keeps disappearing")
                        continue
                    self.journal.alert("warning", f"{m.strike}: the stop of {rec.trade_id} is no longer on the book; "
                                                  "placing it again", trade_id=rec.trade_id)
                    purposes.append(f"stop{3 + len(purposes)}")
                    ack = self.adapter.submit_stop(rec.trade_id, m.strike, rec.dir, Decimal(str(rec.data["qty"])),
                                                   Decimal(rec.data["plan_stop"]), purpose=purposes[-1])
                    self.journal.write("live_order" if self.adapter.live else "paper_order", trade_id=rec.trade_id,
                                       action="stop placed again", ok=ack.ok, error=ack.error)
                    if not ack.ok:
                        self._request_exit(m, rec, "no protection")

    def _loss_windows(self, equity: float) -> tuple[float, float]:
        """Equity change since 00:00 UTC and since Monday 00:00 UTC (realised + unrealised), from equity marks
        persisted in the state file."""
        day = time.strftime("%Y-%m-%d", time.gmtime())
        week = time.strftime("%G-W%V", time.gmtime())
        marks = self._saved.setdefault("_equity_marks", {})
        if marks.get("day", [None])[0] != day:
            marks["day"] = [day, equity]
        if marks.get("week", [None])[0] != week:
            marks["week"] = [week, equity]
        return equity - marks["day"][1], equity - marks["week"][1]

    # ------------------------------------------------------------------ confirmation
    def approve(self, trade_id: str) -> str:
        pend = self.cfg.run_dir / "pending" / f"{trade_id}.json"
        if not pend.exists():
            return "no such pending proposal"
        p = json.loads(pend.read_text())
        m = self.markets.get(p["market"])
        if time.time() > p["expires"]:
            pend.unlink()
            return "expired"
        rec = next((t for t in m.trades if t.trade_id == trade_id), None) if m else None
        if rec is None or rec.state != S.PENDING_AUTHORIZATION:
            return "proposal no longer valid (state changed)"
        q = self.adapter.quote(m.strike)
        risk_dist = abs(rec.data["signal_close"] - rec.data["stop"])
        drift = (((q.ask if rec.dir == 1 else q.bid) - rec.data["signal_close"]) * rec.dir) / risk_dist
        if drift > self.cfg.max_entry_drift_r:
            rec.to(S.CANCELLED, f"price moved {drift:.2f}R since the signal")
            pend.unlink()
            self._drop(m, rec)
            self._save_state()
            return f"refused: price moved {drift:.2f}R in the trade direction since the signal"
        plan = EntryPlan(trade_id, m.strike, rec.dir, Decimal(p["qty"]), Decimal(p["limit"]), Decimal(p["stop"]),
                         Decimal(p["tp"]) if p["tp"] not in ("None", None) else None,
                         int(float(rec.data.get("lev", 1)) or 1))
        self.journal.write("decision", trade_id=trade_id, action="approved by operator")
        self._execute(m, rec, plan)
        pend.unlink()
        self._save_state()
        return f"sent: {rec.state.value}"

    # ------------------------------------------------------------------ main loop
    def run(self, log=print, once: bool = False, stop=None) -> None:
        """``stop``: a threading.Event; when set the loop returns at its next turn (the fleet stops a user's agent)."""
        tf_len = tf_ms(normalize(self.cfg.tf))
        self.warmup(log)
        if once:
            self.reconcile()
            return
        log(f"agent '{self.cfg.name}' running in {self.cfg.mode.upper()} mode on {self.cfg.env}"
            + (f", pyramid up to {self.cfg.max_stack} trades per market" if self.cfg.policy == "pyramid" else ""))
        self.journal.write("agent_start", **self.started_with())
        next_close = (int(time.time() * 1000) // tf_len + 1) * tf_len
        try:
            self._loop(tf_len, next_close, stop)
        except BaseException as e:
            self.journal.write("agent_stop", reason="crashed", error=repr(e)[:1000],
                               open_trades={s: [t.trade_id for t in m.trades if t.active] for s, m in self.markets.items()})
            raise
        self.journal.write("agent_stop", reason="stopped by the host",
                           open_trades={s: [t.trade_id for t in m.trades if t.active] for s, m in self.markets.items()})

    def started_with(self) -> dict:
        """Everything the agent runs with, for the audit (never a key: the API wallet's public key is enough)."""
        c = self.cfg
        signer = getattr(getattr(self.adapter, "c", None), "signer", None)
        return {"name": c.name, "env": c.env, "mode": c.mode, "tf": c.tf, "policy": c.policy, "max_stack": c.max_stack,
                "markets": [m.strike for m in c.markets], "params": dataclasses.asdict(c.params),
                "risk": dataclasses.asdict(c.risk), "builder_code": c.builder_code, "builder_fee_bps": c.builder_fee_bps,
                "builder_fee_approved_bps": c.builder_fee_approved_bps, "sub_account_id": c.sub_account_id,
                "api_wallet": getattr(signer, "public_key", None),
                "adapter": type(self.adapter).__name__ if self.adapter else None}

    def _loop(self, tf_len: int, next_close: int, stop) -> None:
        while not (stop is not None and stop.is_set()):
            now = int(time.time() * 1000)
            if now >= next_close + 15_000:      # give the feed 15 s to publish the closed bar
                self.step(now)
                next_close = (now // tf_len + 1) * tf_len
            self.reconcile()
            self._test_turn()
            self._expire_pending()
            # a turn every 30 s, but what the owner is waiting for (a test request, a test trade whose time is up)
            # wakes it within 2 s
            deadline = time.monotonic() + 30
            while time.monotonic() < deadline and not self._owner_waiting():
                if stop is not None:
                    if stop.wait(2):
                        break
                else:
                    time.sleep(2)

    def _owner_waiting(self) -> bool:
        if (self.cfg.run_dir / "test_request.json").exists():
            return True
        now = time.time()
        return any(t.data.get("test") and t.state in (S.POSITION_OPEN, S.PROTECTED) and now >= t.data.get("test_until", 0)
                   for m in self.markets.values() for t in m.trades)

    # ------------------------------------------------------------------ test trade (asked by the owner, signed)
    TEST_HOLD_S = 120
    TEST_MAX_NOTIONAL = 30.0

    def _test_turn(self) -> None:
        """Run a test trade the owner asked for (runs/<agent>/test_request.json, written by the fleet from the signed
        request on the site) and close test trades whose hold time is over."""
        if self.adapter is None:
            return
        for m in self.markets.values():
            for rec in [t for t in m.trades if t.data.get("test") and t.state in (S.POSITION_OPEN, S.PROTECTED)]:
                if time.time() >= rec.data.get("test_until", 0):
                    self._request_exit(m, rec, "test finished")
        f = self.cfg.run_dir / "test_request.json"
        if not f.exists():
            return
        try:
            req = json.loads(f.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            req = {}
        f.unlink(missing_ok=True)
        done = self._saved.setdefault("_tests", [])
        at = int(req.get("at") or 0)
        if not at or at in done or time.time() * 1000 - at > 15 * 60_000:
            return
        done.append(at)
        del done[:-20]
        self.journal.write("test", action="requested", at=at)
        self.test_trade()
        self._save_state()

    def test_trade(self) -> str:
        """The smallest long Strike accepts on one market, through the agent's own path (risk checks on the book and
        the balance, entry with its stop on Strike, confirmation, reconciliation), held TEST_HOLD_S and closed by the
        agent. Journaled as a test: the city never counts it in the strategy's results."""
        now_ms = int(time.time() * 1000)
        why = []
        short = None   # the smallest test the balance could not pay for: (needed, available)
        for m in self.markets.values():
            st = m.last_state
            if m.trades or m.blocked or not m.healthy or st is None or not (st.atr and st.atr > 0):
                why.append(f"{m.strike}: busy or no data")
                continue
            spec = self.adapter.market_spec(m.strike)
            q = self.adapter.quote(m.strike)
            spread = (q.ask - q.bid) / q.mid * 1e4 if q.mid else math.inf
            if spread > self.cfg.risk.max_spread_bps:
                why.append(f"{m.strike}: spread {spread:.1f} bps")
                continue
            qty = (Decimal(str(spec.min_notional * 1.1 / q.ask)) / spec.step).to_integral_value(ROUND_UP) * spec.step
            qty = max(qty, spec.min_qty)
            notional = float(qty) * q.ask
            acct = self.adapter.account()
            if notional > self.TEST_MAX_NOTIONAL or acct.available_balance < notional * 1.05:
                why.append(f"{m.strike}: needs {notional:.2f} $ (available {acct.available_balance:.2f} $)")
                if notional <= self.TEST_MAX_NOTIONAL and (short is None or notional * 1.05 < short[0]):
                    short = (round(notional * 1.05, 2), round(acct.available_balance, 2))
                continue
            stop = q.ask - self.cfg.params.stop_atr * st.atr
            rec = TradeRecord(f"{m.strike}-test-{now_ms}", m.strike, 1, now_ms)
            rec.data.update(signal_bar_index=m.runner.engine.bars - 1, signal_close=q.ask, atr=st.atr, stop=stop, tp=None,
                            feed="test", test=True, test_until=time.time() + self.TEST_HOLD_S)
            self.journal.write("signal", market=m.strike, trade_id=rec.trade_id, dir=1, close=q.ask, atr=st.atr, stop=stop,
                               tp=None, test=True)
            rec.to(S.SIGNAL_VALIDATED, "test trade asked by the owner")
            slip = self.cfg.max_entry_slippage_bps / 1e4
            plan = EntryPlan(rec.trade_id, m.strike, 1, qty, spec.round_price(q.ask * (1 + slip), side_up=True),
                             spec.round_price(stop, side_up=None), None, 1)
            self.journal.write("decision", trade_id=rec.trade_id, accepted=True, reasons=[], test=True,
                               summary=f"test trade: {qty} {m.strike} (~{notional:.2f} $), stop {plan.stop}, "
                                       f"held {self.TEST_HOLD_S} s")
            rec.to(S.ORDER_PREPARED, "test")
            rec.data.update(qty=float(qty), limit=str(plan.limit_price), plan_stop=str(plan.stop), lev=1)
            m.trades.append(rec)
            self._execute(m, rec, plan)
            return f"test trade on {m.strike}"
        # the city tells the owner why in their language: the balance (and how much it needs) or a busy moment
        extra = {"code": "test_funds", "needs": short[0], "available": short[1]} if short else {"code": "test_busy"}
        self.journal.alert("warning", "test trade: no market ready (" + "; ".join(why)[:300] + ")", **extra)
        return "no market ready"

    def _expire_pending(self) -> None:
        pdir = self.cfg.run_dir / "pending"
        if not pdir.exists():
            return
        for f in pdir.glob("*.json"):
            p = json.loads(f.read_text())
            if time.time() > p["expires"]:
                m = self.markets.get(p["market"])
                rec = next((t for t in m.trades if t.trade_id == p["trade_id"]), None) if m else None
                if rec and rec.state == S.PENDING_AUTHORIZATION:
                    rec.to(S.CANCELLED, "approval window expired")
                    self._drop(m, rec)
                f.unlink()
                self.journal.write("decision", trade_id=p["trade_id"], action="expired without approval")

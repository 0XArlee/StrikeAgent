"""The script's own trade tracking and track-record panel (SmartFlowSignals.txt lines 171-325 and 357-396).

This is the **reference** model, reproduced quirks included, so its numbers can be compared one to one with the
panel on TradingView. It is not an execution model: it fills at the signal close and exactly at the stop, holds
overlapping and opposite trades at the same time and charges a flat round-trip fee on the entry price. The realistic
model lives in ``smartflow.backtest``.

Per closed bar, in this order (as in the script):
1. every open trade opened on an earlier bar is tested: hard stop (intrabar) first, then target (intrabar), then the
   exit (trailing channel close / money-flow cross / either), then the candle limit;
2. a new signal opens a new trade (entry = close, stop = entry -/+ stop_atr*ATR);
3. when more than ``keep_n`` trades are tracked the oldest is dropped, even if still open (it is then never counted).
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .config import ExitMode, Params
from .engine import BarState
from .pine import NA, ge, gt, isna, le, lt


class ExitReason:
    OPEN = 0
    TRAIL = 1      # closed by the exit (channel or money flow)
    STOP = -1
    TIME = 2
    TARGET = 3


@dataclass(slots=True)
class RefTrade:
    dir: int
    bar: int
    open_time: int
    entry: float
    sl: float
    risk: float
    tp: float = NA
    state: int = ExitReason.OPEN
    r: float = 0.0
    exit_price: float = NA
    exit_bar: int = -1
    exit_time: int = 0


@dataclass(slots=True)
class Record:
    closed: int = 0
    wins: int = 0
    total_r: float = 0.0
    gross_win_r: float = 0.0
    gross_loss_r: float = 0.0

    @property
    def win_rate(self) -> float:
        return self.wins / self.closed if self.closed else NA

    @property
    def avg_r(self) -> float:
        return self.total_r / self.closed if self.closed else NA

    @property
    def profit_factor(self) -> float:
        return self.gross_win_r / self.gross_loss_r if self.gross_loss_r > 0 else NA


@dataclass
class RefTradeBook:
    p: Params
    trades: list[RefTrade] = field(default_factory=list)
    closed: list[RefTrade] = field(default_factory=list)   # every trade the panel counted, in closing order
    dropped_open: list[RefTrade] = field(default_factory=list)  # quirk 3: dropped while open, never counted
    rec: Record = field(default_factory=Record)
    bar_index: int = -1

    def _close(self, t: RefTrade, state: int, px: float, s: BarState) -> None:
        t.state = state
        t.exit_price = px
        t.exit_bar = self.bar_index
        t.exit_time = s.open_time
        gross = (px - t.entry) * t.dir / t.risk
        t.r = gross - self.p.fee_pct / 100 * t.entry / t.risk
        self.rec.closed += 1
        win = gt(t.r, 0.0)
        self.rec.wins += 1 if win else 0
        self.rec.total_r += t.r
        if win:
            self.rec.gross_win_r += t.r
        else:
            self.rec.gross_loss_r -= t.r
        self.closed.append(t)

    def on_bar(self, s: BarState, high: float, low: float) -> list[RefTrade]:
        """Advance one closed bar. Returns the trades closed on it (the script's ``exitEvt``)."""
        self.bar_index += 1
        p, bi = self.p, self.bar_index
        exits: list[RefTrade] = []
        for t in self.trades:
            if t.state != ExitReason.OPEN or bi <= t.bar:
                continue
            hit_sl = le(low, t.sl) if t.dir == 1 else ge(high, t.sl)
            ch = s.chan_lo if t.dir == 1 else s.chan_hi
            chan_hit = bi > t.bar + 1 and (lt(s.close, ch) if t.dir == 1 else gt(s.close, ch))
            flow_hit = (not isna(s.flow) and not isna(s.flow_prev) and
                        ((ge(s.flow_prev, 0) and lt(s.flow, 0)) if t.dir == 1 else
                         (le(s.flow_prev, 0) and gt(s.flow, 0))))
            if p.exit_mode == ExitMode.TRAILING_CHANNEL:
                chan_out = chan_hit
            elif p.exit_mode == ExitMode.FLOW_CROSS:
                chan_out = flow_hit
            else:
                chan_out = chan_hit or flow_hit
            hit_tp = not isna(t.tp) and (ge(high, t.tp) if t.dir == 1 else le(low, t.tp))
            if hit_sl:
                self._close(t, ExitReason.STOP, t.sl, s)
            elif hit_tp:
                self._close(t, ExitReason.TARGET, t.tp, s)
            elif chan_out:
                self._close(t, ExitReason.TRAIL, s.close, s)
            elif bi - t.bar >= p.max_open:
                self._close(t, ExitReason.TIME, s.close, s)
            else:
                continue
            exits.append(t)

        if s.sig_dir != 0:
            entry = s.close
            risk = p.stop_atr * s.atr
            t = RefTrade(dir=s.sig_dir, bar=bi, open_time=s.open_time, entry=entry,
                         sl=entry - s.sig_dir * risk, risk=risk)
            t.tp = entry + s.sig_dir * p.tp_r * risk if p.tp_r > 0 else NA
            self.trades.append(t)
            if len(self.trades) > p.keep_n:
                old = self.trades.pop(0)
                if old.state == ExitReason.OPEN:
                    self.dropped_open.append(old)
        return exits

    @property
    def open_trades(self) -> list[RefTrade]:
        return [t for t in self.trades if t.state == ExitReason.OPEN]

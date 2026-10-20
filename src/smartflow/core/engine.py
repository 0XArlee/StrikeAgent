"""Smart Flow signal engine: SmartFlowSignals.txt lines 72-168, one closed bar at a time.

``SignalEngine.update(candle, htf_trend)`` returns a ``BarState`` holding every series the script computes on that
bar plus the decision (``sig_dir``) and, for the agent, the reasons behind it. The engine only ever sees closed bars,
which is what ``barstate.isconfirmed`` guarantees in the script, so it cannot repaint.

Volume: the script uses the chart's own volume, falls back to a reference symbol's volume, and when neither exists
the volume filter steps aside (``volOk`` true) and the money-flow terms that need volume become na. Here the caller
passes the volume it has (``nan`` = none) and labels its origin in ``Candle.source``; a fallback feed is the caller's
explicit choice, never implicit.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

from .config import BiasSource, Params
from .pine import (NA, Atr, Ema, Highest, Lowest, Sma, Sum, ge, gt, isna, lt, ne)
from .types import Candle


@dataclass(slots=True)
class BarState:
    open_time: int
    close: float
    atr: float
    hi_n: float            # highest high of the previous look_n bars
    lo_n: float
    vol: float
    vol_avg: float         # SMA(vol, 20) including this bar
    rel_vol: float
    ema_f: float
    ema_s: float
    ema_trend: int
    flow: float            # composite money-flow wave
    flow_prev: float
    mfi: float
    cmf: float
    chan_lo: float         # lowest low of the previous chan_n bars (exit test level)
    chan_hi: float
    chan_lo_next: float    # lowest low of the last chan_n bars incl. this one (level the NEXT bar is tested against)
    chan_hi_next: float
    rng: float
    body: float
    disp: bool
    vol_ok: bool
    raw_buy: bool
    raw_sell: bool
    range100: float
    wide_rng: bool
    htf_trend: int | None
    bias_up: bool
    bias_dn: bool
    sig_raw: int           # signal before the optional skip filters
    skip_reason: str       # "" or why sig_raw was skipped
    sig_dir: int           # final signal: 1 buy, -1 sell, 0 none
    notes: list[str] = field(default_factory=list)

    def why_no_signal(self, p: Params) -> list[str]:
        """Human-readable list of the conditions that kept this bar from signalling (empty if it signalled)."""
        if self.sig_dir != 0:
            return []
        out: list[str] = []
        if self.sig_raw != 0 and self.skip_reason:
            return [f"signal skipped: {self.skip_reason}"]
        if isna(self.atr):
            return ["warming up: ATR not available yet"]
        r_atr = self.rng / self.atr if self.atr else NA
        if not self.disp:
            out.append(f"no displacement: range {r_atr:.2f} ATR (min {p.range_min}), body "
                       f"{(100 * self.body / self.rng) if self.rng else 0:.0f}% of range (min {100 * p.body_min:.0f}%)")
        up = self.close > self.hi_n if not isna(self.hi_n) else False
        dn = self.close < self.lo_n if not isna(self.lo_n) else False
        if not self.raw_buy and not self.raw_sell and self.disp:
            out.append(f"no breakout: close inside the {p.look_n}-candle range [{self.lo_n:g}, {self.hi_n:g}]"
                       if not (up or dn) else "breakout candle closes against its own direction")
        if not self.vol_ok:
            out.append(f"volume too low: x{self.rel_vol:.2f} of its 20-candle average (min x{p.vol_min})")
        if self.raw_buy and not self.bias_up:
            out.append(f"buy setup against the bias ({_bias_txt(self, p)})")
        if self.raw_sell and not self.bias_dn:
            out.append(f"sell setup against the bias ({_bias_txt(self, p)})")
        return out or ["no setup"]


def _bias_txt(s: BarState, p: Params) -> str:
    st = {1: "HTF structure bullish", -1: "HTF structure bearish", 0: "HTF structure without trend",
          None: "HTF structure unknown"}[s.htf_trend]
    em = "n/a" if isna(s.ema_s) else ("price above slow EMA" if s.close > s.ema_s else "price below slow EMA")
    return {BiasSource.HTF_STRUCTURE: st, BiasSource.SLOW_EMA: em, BiasSource.EITHER: f"{st} / {em}",
            BiasSource.NONE: "none"}[p.bias_source]


class SignalEngine:
    def __init__(self, params: Params, htf_ok: bool = True):
        """``htf_ok`` = the script's ``tfOk`` (HTF strictly longer than the chart TF); without it the structure bias
        is never satisfied."""
        params.validate()
        self.p = p = params
        self.htf_ok = htf_ok
        self._atr = Atr(p.atr_len)
        self._hi_n, self._lo_n = Highest(p.look_n), Lowest(p.look_n)
        self._hi_100, self._lo_100 = Highest(100), Lowest(100)
        self._ch_hi, self._ch_lo = Highest(p.chan_n), Lowest(p.chan_n)
        self._vol_av = Sma(20)
        self._ema_f, self._ema_s = Ema(p.ema_fast), Ema(p.ema_slow)
        self._mf_pos, self._mf_neg = Sum(14), Sum(14)
        self._vol_av21, self._mfv_av21 = Sma(21), Sma(21)
        self._mf_ema, self._mf_dev, self._flow_ema = Ema(10), Ema(10), Ema(21)
        # previous-bar values ([1] in Pine)
        self._prev = dict(hi_n=NA, lo_n=NA, hi100=NA, lo100=NA, ch_hi=NA, ch_lo=NA, hlc3=NA, flow=NA)
        self._has_vol = False
        self.bars = 0
        self.last_time: int | None = None

    def update(self, c: Candle, htf_trend: int | None) -> BarState:
        if self.last_time is not None and c.open_time <= self.last_time:
            raise ValueError(f"bars must be strictly increasing in time ({c.open_time} after {self.last_time})")
        self.last_time = c.open_time
        p, prev = self.p, self._prev
        atr = self._atr.update(c.high, c.low, c.close)

        # [1]-shifted window extremes: compute this bar's value, serve last bar's
        hi_now, lo_now = self._hi_n.update(c.high), self._lo_n.update(c.low)
        hi100_now, lo100_now = self._hi_100.update(c.high), self._lo_100.update(c.low)
        ch_hi_now, ch_lo_now = self._ch_hi.update(c.high), self._ch_lo.update(c.low)
        hi_n, lo_n = prev["hi_n"], prev["lo_n"]
        chan_hi, chan_lo = prev["ch_hi"], prev["ch_lo"]
        range100 = (prev["hi100"] - prev["lo100"]) / atr if not isna(atr) and atr != 0 else NA

        # volume (lines 107-119): sticky "this symbol has volume"
        v = c.volume
        if not isna(v) and v > 0:
            self._has_vol = True
        vol = v if self._has_vol else NA
        vol_avg = self._vol_av.update(vol)

        # trend EMAs
        ema_f, ema_s = self._ema_f.update(c.close), self._ema_s.update(c.close)
        ema_trend = 1 if gt(ema_f, ema_s) else -1 if lt(ema_f, ema_s) else 0

        # composite money flow (lines 125-139)
        src = c.hlc3
        raw = src * vol
        mf_pos = self._mf_pos.update(raw if ge(src, prev["hlc3"]) else 0.0)
        mf_neg = self._mf_neg.update(raw if lt(src, prev["hlc3"]) else 0.0)
        mfi = 100 - 100 / (1 + mf_pos / mf_neg) if ne(mf_neg, 0) else 100.0
        mf_mult = ((c.close - c.low) - (c.high - c.close)) / (c.high - c.low) if ne(c.high, c.low) else 0.0
        vol_av21 = self._vol_av21.update(vol)
        mfv_av21 = self._mfv_av21.update(mf_mult * vol)
        cmf = mfv_av21 / vol_av21 if ne(vol_av21, 0) else 0.0
        vw_in = (vol / vol_av21 if ne(vol_av21, 0) else 1.0) + 1
        vol_w = math.log(vw_in) if not isna(vw_in) and vw_in > 0 else NA
        mf_ema = self._mf_ema.update(src)
        mf_dev = self._mf_dev.update(abs(src - mf_ema))
        mf_ci = (src - mf_ema) / (0.015 * mf_dev) * (1 + vol_w * 0.5) if ne(mf_dev, 0) else 0.0
        flow = self._flow_ema.update(mf_ci) * 0.5 + cmf * 100 * 0.3 + (mfi - 50) * 1.2 * 0.2
        flow_prev = prev["flow"]

        # displacement + breakout (lines 146-152)
        rng = c.high - c.low
        body = abs(c.close - c.open)
        disp = not isna(atr) and ge(rng, p.range_min * atr) and ge(body, p.body_min * rng)
        vol_ok = p.vol_min == 0 or isna(vol) or (not isna(vol_avg) and ge(vol, p.vol_min * vol_avg))
        rel_vol = NA if isna(vol_avg) or vol_avg == 0 else vol / vol_avg
        raw_buy = disp and gt(c.close, c.open) and not isna(hi_n) and gt(c.close, hi_n)
        raw_sell = disp and lt(c.close, c.open) and not isna(lo_n) and lt(c.close, lo_n)
        wide_rng = p.range_filter and not isna(range100) and gt(range100, p.range_max)

        # bias (lines 157-162)
        st_up = self.htf_ok and htf_trend == 1
        st_dn = self.htf_ok and htf_trend == -1
        em_up = not isna(ema_s) and gt(c.close, ema_s)
        em_dn = not isna(ema_s) and lt(c.close, ema_s)
        bs = p.bias_source
        if bs == BiasSource.NONE:
            bias_up = bias_dn = True
        elif bs == BiasSource.HTF_STRUCTURE:
            bias_up, bias_dn = st_up, st_dn
        elif bs == BiasSource.SLOW_EMA:
            bias_up, bias_dn = em_up, em_dn
        else:
            bias_up, bias_dn = st_up or em_up, st_dn or em_dn

        sig_raw = (1 if raw_buy and bias_up else -1 if raw_sell and bias_dn else 0) if vol_ok else 0
        skip = ""
        if sig_raw != 0:
            if wide_rng:
                skip = (f"born inside a wide range (last 100 candles span {range100:.1f} ATR, "
                        f"filter {p.range_max:g})")
            elif p.ema_filter and ema_trend == -sig_raw:
                skip = "against the EMA cloud (fast EMA on the wrong side of the slow one)"
            elif p.flow_filter and not isna(flow) and lt(flow * sig_raw, 0.0):
                skip = f"against the money flow ({flow:+.0f})"
        sig_dir = 0 if skip else sig_raw

        prev.update(hi_n=hi_now, lo_n=lo_now, hi100=hi100_now, lo100=lo100_now, ch_hi=ch_hi_now, ch_lo=ch_lo_now,
                    hlc3=src, flow=flow)
        self.bars += 1
        notes = [] if self._has_vol else ["no volume on this feed: volume filter off, money flow n/a"]
        return BarState(
            open_time=c.open_time, close=c.close, atr=atr, hi_n=hi_n, lo_n=lo_n, vol=vol, vol_avg=vol_avg,
            rel_vol=rel_vol, ema_f=ema_f, ema_s=ema_s, ema_trend=ema_trend, flow=flow, flow_prev=flow_prev,
            mfi=mfi, cmf=cmf, chan_lo=chan_lo, chan_hi=chan_hi, chan_lo_next=ch_lo_now, chan_hi_next=ch_hi_now,
            rng=rng, body=body, disp=disp, vol_ok=vol_ok, raw_buy=raw_buy, raw_sell=raw_sell, range100=range100,
            wide_rng=wide_rng, htf_trend=htf_trend, bias_up=bias_up, bias_dn=bias_dn, sig_raw=sig_raw,
            skip_reason=skip, sig_dir=sig_dir, notes=notes,
        )

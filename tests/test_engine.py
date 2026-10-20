"""Engine behaviour: hand-built signal scenarios, no lookahead, HTF alignment, reference trade rules."""

import math
from dataclasses import fields, replace

from conftest import HOUR, aggregate, synthetic

from smartflow.core.config import BiasSource, ExitMode, Params
from smartflow.core.engine import SignalEngine
from smartflow.core.htf import HtfBias
from smartflow.core.reference_trades import ExitReason, RefTradeBook
from smartflow.core.runner import run_history
from smartflow.core.types import Candle

NO_BIAS = replace(Params(), bias_source=BiasSource.NONE)


def same_state(a, b) -> bool:
    """Field-wise equality where nan == nan."""
    for f in fields(a):
        x, y = getattr(a, f.name), getattr(b, f.name)
        if isinstance(x, float) and isinstance(y, float) and math.isnan(x) and math.isnan(y):
            continue
        if x != y:
            return False
    return True


def flat_then_impulse(n_flat=60, impulse=(100.0, 103.0, 99.9, 102.8), vol=500.0):
    """n_flat quiet bars oscillating in 99.5..100.5 with volume 100, then one impulsive bar."""
    bars = []
    for i in range(n_flat):
        o = 100.0 + (0.3 if i % 2 else -0.3)
        c = 100.0 - (0.3 if i % 2 else -0.3)
        bars.append(Candle(i * HOUR, o, 100.5, 99.5, c, 100.0))
    o, h, l, c = impulse
    bars.append(Candle(n_flat * HOUR, o, h, l, c, vol))
    return bars


def run(bars, p=NO_BIAS, trend=None):
    eng = SignalEngine(p)
    return [eng.update(b, trend) for b in bars]


def test_clean_breakout_signals_buy():
    s = run(flat_then_impulse())[-1]
    assert s.disp and s.raw_buy and s.vol_ok and s.sig_dir == 1
    assert s.hi_n == 100.5
    assert s.why_no_signal(NO_BIAS) == []


def test_low_volume_blocks_signal_and_explains():
    s = run(flat_then_impulse(vol=120.0))[-1]
    assert s.raw_buy and not s.vol_ok and s.sig_dir == 0
    assert any("volume too low" in r for r in s.why_no_signal(NO_BIAS))


def test_small_body_is_not_displacement():
    s = run(flat_then_impulse(impulse=(100.0, 103.0, 99.9, 101.0)))[-1]  # body 1.0 of range 3.1
    assert not s.disp and s.sig_dir == 0
    assert any("no displacement" in r for r in s.why_no_signal(NO_BIAS))


def test_close_inside_range_is_not_breakout():
    s = run(flat_then_impulse(impulse=(97.5, 100.6, 97.4, 100.4)))[-1]  # strong body but close < 100.5
    assert s.disp and not s.raw_buy and s.sig_dir == 0


def test_bias_blocks_counter_trend_signal():
    p = Params()  # HTF structure bias
    bars = flat_then_impulse()
    assert run(bars, p, trend=-1)[-1].sig_dir == 0
    assert run(bars, p, trend=None)[-1].sig_dir == 0
    assert run(bars, p, trend=1)[-1].sig_dir == 1
    s = run(bars, p, trend=-1)[-1]
    assert any("against the bias" in r for r in s.why_no_signal(p))


def test_no_volume_feed_disables_volume_filter():
    bars = [Candle(b.open_time, b.open, b.high, b.low, b.close, float("nan")) for b in flat_then_impulse(vol=1.0)]
    s = run(bars)[-1]
    assert s.vol_ok and s.sig_dir == 1 and s.notes


def test_ema_filter_skip_reason():
    p = replace(NO_BIAS, ema_filter=True, ema_fast=10, ema_slow=30, look_n=5)
    bars = [Candle(i * HOUR, 100 - i * 0.5, 100.2 - i * 0.5, 99.4 - i * 0.5, 100 - i * 0.5 - 0.45, 100.0)
            for i in range(60)]  # steady downtrend: fast EMA well below the slow one
    last = bars[-1].close
    bars.append(Candle(60 * HOUR, last, last + 4.0, last - 0.1, last + 3.8, 500.0))
    s = run(bars, p)[-1]
    assert s.ema_trend == -1
    assert s.sig_raw == 1 and s.sig_dir == 0 and "EMA cloud" in s.skip_reason
    assert s.why_no_signal(p) == ["signal skipped: " + s.skip_reason]


def test_no_lookahead_prefix_invariance():
    """Every state must be identical whether or not future bars exist (the core anti-repaint property)."""
    base = synthetic(3000, seed=11)
    htf = aggregate(base, 4 * HOUR)
    full = run_history(base, htf, Params(), "60").states
    cut = 1800
    part = run_history(base[:cut], [h for h in htf if h.open_time < base[cut].open_time], Params(), "60").states
    assert len(part) == cut
    for a, b in zip(full[:cut], part):
        assert same_state(a, b)


def test_htf_bias_uses_previous_closed_htf_bar():
    bias = HtfBias("240", 2)
    # 4h bars at 00, 04, 08 ... ; build an up-break on the bar opening at 08:00
    closes = [100, 101, 102, 101, 100, 99, 105]  # pivot high 102 (bar 2) confirmed at bar 4, broken at bar 6
    for i, c in enumerate(closes):
        bias.add_bar(Candle(i * 4 * HOUR, c, c + 0.5 if i != 2 else 103, c - 0.5, c, 1.0))
    t6 = 6 * 4 * HOUR
    assert bias.trends[6] == 1
    # chart bars inside HTF bar 6 still see bar 5's trend; the trend appears from HTF bar 7 on
    assert bias.trend_for(t6) == 0 and bias.trend_for(t6 + 3 * HOUR) == 0
    assert bias.trend_for(t6 + 4 * HOUR) == 1
    assert not bias.ready_for(t6 + 8 * HOUR)  # HTF bar 7 not fed yet -> live guard says not ready


def test_reference_trade_stop_first_and_r_net_of_fees():
    p = replace(NO_BIAS, fee_pct=0.10)
    bars = flat_then_impulse()
    eng, book = SignalEngine(p), RefTradeBook(p)
    states = []
    for b in bars:
        s = eng.update(b, None)
        book.on_bar(s, b.high, b.low)
        states.append(s)
    t = book.trades[-1]
    assert t.entry == 102.8 and t.risk == p.stop_atr * states[-1].atr
    # next bar spikes to a new high AND through the stop: the stop wins (conservative intrabar order)
    nb = Candle(bars[-1].open_time + HOUR, 102.8, 110.0, t.sl - 1, 105.0, 100.0)
    book.on_bar(eng.update(nb, None), nb.high, nb.low)
    assert t.state == ExitReason.STOP
    assert abs(t.r - (-1 - 0.001 * t.entry / t.risk)) < 1e-12


def test_reference_overlapping_trades_and_channel_exit():
    p = replace(NO_BIAS, exit_mode=ExitMode.TRAILING_CHANNEL)
    res = run_history(synthetic(5000, seed=5), [], p, "60")
    closed = res.book.closed
    assert closed, "synthetic series should produce trades"
    assert any(t.state == ExitReason.TRAIL for t in closed)
    for t in closed:
        if t.state == ExitReason.TRAIL:
            assert t.exit_bar >= t.bar + 2  # the channel exit cannot fire on the bar right after entry
        assert t.exit_bar > t.bar

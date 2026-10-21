"""The account as the live agent runs it over backtest trades: size with the slippage margin, loss limits on the
marked-to-market equity, drawdown with the open trades in it (backtest/account.py)."""

import pytest

from smartflow.backtest.account import agent_account
from smartflow.backtest.sim import SimTrade

H = 3_600_000
T0 = 1_767_225_600_000          # 2026-01-01 00:00 UTC
WIN = (T0, T0 + 365 * 24 * H)


def trade(sym, entry_t, exit_t, r, entry=100.0, sl=90.0, d=1):
    t = SimTrade(sym, d, 0, entry_t, entry, sl, float("nan"))
    t.entry_time, t.exit_time, t.entry, t.exit_bar, t.r_gross = entry_t, exit_t, entry, 1, r
    return t


def test_size_has_the_slippage_margin():
    run = agent_account([trade("BTCUSDT", T0 + 4 * H, T0 + 8 * H, 2.0)], {}, 0.01, WIN)
    assert run.final == pytest.approx(1 + 0.008 * 2)      # a clean stop costs 1 % / 1.25 = 0.8 %


def test_a_stop_in_the_entry_candle_is_closed():
    run = agent_account([trade("BTCUSDT", T0 + 4 * H, T0 + 4 * H, -1.0)], {}, 0.01, WIN)
    assert run.taken == 1 and run.final == pytest.approx(1 - 0.008)


def test_daily_limit_skips_entries_after_a_bad_day_and_not_the_next_day():
    ts = [trade("BTCUSDT", T0 + 4 * H, T0 + 8 * H, -3.0),        # -2.4 % closed at 08:00
          trade("ETHUSDT", T0 + 12 * H, T0 + 16 * H, 1.0),        # same UTC day: skipped
          trade("SOLUSDT", T0 + 28 * H, T0 + 32 * H, 1.0)]        # next day: taken
    run = agent_account(ts, {}, 0.01, WIN)
    assert run.taken == 2 and run.skipped == [1.0]
    assert agent_account(ts, {}, 0.01, WIN, limits=False).taken == 3


def test_drawdown_counts_the_open_trade():
    # long at 100, stop 90: the 08:00 close at 95 is -0.5 R open; it exits later at +1 R
    t = trade("BTCUSDT", T0 + 4 * H, T0 + 16 * H, 1.0)
    run = agent_account([t], {"BTCUSDT": {T0 + 4 * H: 100.0, T0 + 8 * H: 95.0, T0 + 12 * H: 105.0}}, 0.01, WIN)
    assert run.max_dd == pytest.approx(0.008 * 0.5, rel=1e-9) and run.final == pytest.approx(1.008)

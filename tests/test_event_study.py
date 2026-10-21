"""The macro release calendar and the event study's classification (backtest/event_study.py)."""
import datetime as dt
from types import SimpleNamespace

from smartflow.backtest.event_study import MIN_REMOVED, classify, load_events

H = 3_600_000


def utc(ms: int) -> str:
    return dt.datetime.fromtimestamp(ms / 1000, dt.timezone.utc).strftime("%Y-%m-%d %H:%M")


def test_release_times_follow_new_york_daylight_saving():
    ev = {(utc(t), k) for t, k in load_events()}
    assert ("2022-01-12 13:30", "cpi") in ev          # winter: 08:30 EST
    assert ("2022-06-15 18:00", "fomc") in ev         # summer: 14:00 EDT
    assert ("2024-11-01 12:30", "nfp") in ev          # the Friday before the switch back
    assert ("2024-11-07 19:00", "fomc") in ev         # the week after it
    assert ("2025-03-12 12:30", "cpi") in ev          # three days after the switch forward


def test_calendar_has_every_release_and_no_duplicates():
    ev = load_events()
    kinds = [k for _, k in ev]
    assert kinds.count("fomc") == 40 and kinds.count("cpi") == 57 and kinds.count("nfp") == 57
    assert len({t for t, _ in ev}) == len(ev)


def test_classify_tells_before_signal_and_open_apart():
    t0 = int(dt.datetime(2024, 6, 12, 12, tzinfo=dt.timezone.utc).timestamp() * 1000)   # CPI 12:30 UTC that day
    events = [(t0 + 30 * 60_000, "cpi")]
    before = SimpleNamespace(entry_time=t0, exit_time=t0 + 12 * H, reason="stop")
    after = SimpleNamespace(entry_time=t0 + 4 * H, exit_time=t0 + 40 * H, reason="channel exit")
    through = SimpleNamespace(entry_time=t0 - 8 * H, exit_time=t0 + 24 * H, reason="chandelier stop")
    stopped = SimpleNamespace(entry_time=t0 - 8 * H, exit_time=t0, reason="stop")
    assert classify(before, events, 4 * H)["pre"] == ["cpi"]
    assert classify(after, events, 4 * H)["signal"] == ["cpi"] and not classify(after, events, 4 * H)["pre"]
    assert classify(through, events, 4 * H)["open"] == ["cpi"]
    assert classify(stopped, events, 4 * H)["stop_on_release"]
    assert MIN_REMOVED >= 10

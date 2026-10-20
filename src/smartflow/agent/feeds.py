"""Live candle feed for the agent: closed Binance spot bars (signal feed), with staleness checks.

Signals are computed on Binance spot (the feed the indicator was designed on and its own volume fallback); Strike's
own candles are not used for signals because its traded volume is ~1e-4 of Binance's and many of its candles are
zero-volume gap fills (measured 2026-10-19). Every candle carries ``source=binance-spot:<SYMBOL>``.
"""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass

from ..core.timeframes import bar_close_time, floor_time, to_binance_interval
from ..core.types import Candle
from ..data.binance import SPOT
from ..net import get_json


@dataclass
class FeedStatus:
    ok: bool
    last_closed_open: int | None
    expected_open: int
    age_s: float
    message: str = ""


_CACHE: dict[tuple, tuple[float, list]] = {}
_LOCKS: dict[tuple, threading.Lock] = {}
_GUARD = threading.Lock()
CACHE_S = 20.0   # at a candle close every user's agent asks for the same bars: one download serves them all


def _rows(symbol: str, tf: str, limit: int, start_ms: int | None) -> list:
    key = (symbol, tf, limit, start_ms)
    with _GUARD:
        lock = _LOCKS.setdefault(key, threading.Lock())
    with lock:   # the first caller downloads, the others wait for it and reuse the answer
        hit = _CACHE.get(key)
        if hit and time.monotonic() - hit[0] < CACHE_S:
            return hit[1]
        params = {"symbol": symbol, "interval": to_binance_interval(tf), "limit": limit}
        if start_ms is not None:
            params["startTime"] = start_ms
        rows = get_json(SPOT, params)
        _CACHE[key] = (time.monotonic(), rows)
        if len(_CACHE) > 500:   # old keys (start_ms differs per warm-up) do not pile up
            for k in sorted(_CACHE, key=lambda k: _CACHE[k][0])[:250]:
                _CACHE.pop(k, None)
        return rows


def fetch_closed(symbol: str, tf: str, limit: int = 1000, now_ms: int | None = None,
                 start_ms: int | None = None) -> list[Candle]:
    now_ms = now_ms or int(time.time() * 1000)
    rows = _rows(symbol, tf, limit, start_ms)
    out = []
    for k in rows:
        t = int(k[0])
        if bar_close_time(t, tf) <= now_ms:  # drop the bar still forming
            out.append(Candle(t, float(k[1]), float(k[2]), float(k[3]), float(k[4]), float(k[5]),
                              f"binance-spot:{symbol}"))
    return out


def status(candles: list[Candle], tf: str, now_ms: int | None = None) -> FeedStatus:
    now_ms = now_ms or int(time.time() * 1000)
    current_open = floor_time(now_ms, tf)
    # the most recent bar that should be closed is the one right before the current one
    expected = None
    t = current_open - 1
    expected = floor_time(t, tf)
    if not candles:
        return FeedStatus(False, None, expected, float("inf"), "no candles")
    last = candles[-1].open_time
    age = (now_ms - bar_close_time(last, tf)) / 1000
    if last != expected:
        return FeedStatus(False, last, expected, age, "latest closed bar missing (feed lagging or gap)")
    return FeedStatus(True, last, expected, age)

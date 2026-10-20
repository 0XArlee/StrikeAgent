"""Timeframes, TradingView-style: "60" = 1 h, "240" = 4 h, "D", "W", "M". Bars are UTC-aligned (crypto, 24/7).

Weekly bars open on Monday 00:00 UTC and monthly bars on the 1st, as on TradingView for BINANCE symbols.
"""

from __future__ import annotations

import calendar
import datetime as dt

MIN = 60_000
HOUR = 60 * MIN
DAY = 24 * HOUR
WEEK = 7 * DAY

_ALIASES = {"1h": "60", "2h": "120", "4h": "240", "6h": "360", "8h": "480", "12h": "720", "1d": "D", "1w": "W",
            "1M": "M", "15m": "15", "30m": "30", "5m": "5", "1m": "1", "3m": "3"}


def normalize(tf: str) -> str:
    return _ALIASES.get(tf, tf)


def tf_ms(tf: str) -> int:
    """Nominal length (months count as 30 days, only used for ordering and in_seconds comparisons)."""
    tf = normalize(tf)
    if tf == "D":
        return DAY
    if tf == "W":
        return WEEK
    if tf == "M":
        return 30 * DAY
    return int(tf) * MIN


def to_binance_interval(tf: str) -> str:
    tf = normalize(tf)
    m = {"D": "1d", "W": "1w", "M": "1M"}
    if tf in m:
        return m[tf]
    minutes = int(tf)
    return f"{minutes // 60}h" if minutes % 60 == 0 else f"{minutes}m"


def auto_htf(chart_tf: str) -> str:
    """``autoHtf()`` (line 75): 1 h for charts up to 15 min, 4 h for 30 min and 1 h, D for 2 h and 4 h, W for D."""
    tf = normalize(chart_tf)
    if tf == "D":
        return "W"
    if tf in ("W", "M"):
        return "M"
    minutes = int(tf)
    if minutes <= 15:
        return "60"
    if minutes <= 60:
        return "240"
    return "D"


def floor_time(t_ms: int, tf: str) -> int:
    """Opening time of the ``tf`` bar that contains ``t_ms``."""
    tf = normalize(tf)
    if tf == "W":
        days = t_ms // DAY
        monday = days - ((days + 3) % 7)  # 1970-01-01 was a Thursday
        return monday * DAY
    if tf == "M":
        d = dt.datetime.fromtimestamp(t_ms / 1000, tz=dt.timezone.utc)
        return int(dt.datetime(d.year, d.month, 1, tzinfo=dt.timezone.utc).timestamp() * 1000)
    step = tf_ms(tf)
    return (t_ms // step) * step


def bar_close_time(open_ms: int, tf: str) -> int:
    """Time at which the bar opened at ``open_ms`` closes (exclusive end)."""
    tf = normalize(tf)
    if tf == "M":
        d = dt.datetime.fromtimestamp(open_ms / 1000, tz=dt.timezone.utc)
        days = calendar.monthrange(d.year, d.month)[1]
        return open_ms + days * DAY
    return open_ms + tf_ms(tf)

"""Higher-timeframe bias (SmartFlowSignals.txt lines 74-101), with no lookahead.

``structure()`` runs on the HTF bars: confirmed swing pivots (``htf_swing`` bars each side) are remembered; a close
beyond the last swing high turns the trend up (and forgets that high), a close beyond the last swing low turns it
down. The value is sticky until the opposite break.

The script reads it with ``request.security(..., structure()[1], lookahead_on)``: every chart bar inside HTF bar *k*
sees the trend as it stood at the close of HTF bar *k-1*. ``HtfBias.trend_for(t)`` reproduces exactly that: the
trend of the latest HTF bar that opened before the HTF bar containing ``t``. Note it lags one more HTF bar than
strictly necessary on the last chart bar of each HTF bar; that is the reference behaviour and is kept.
"""

from __future__ import annotations

import bisect

from .pine import NA, Pivot, gt, isna, lt
from .timeframes import bar_close_time, floor_time
from .types import Candle


class HtfStructure:
    """``structure()`` evaluated on consecutive closed HTF bars."""

    def __init__(self, swing: int):
        self.ph = Pivot(swing, swing, is_high=True)
        self.pl = Pivot(swing, swing, is_high=False)
        self.last_h = NA
        self.last_l = NA
        self.trend = 0

    def update(self, bar: Candle) -> int:
        ph = self.ph.update(bar.high)
        pl = self.pl.update(bar.low)
        if not isna(ph):
            self.last_h = ph
        if not isna(pl):
            self.last_l = pl
        if not isna(self.last_h) and gt(bar.close, self.last_h):
            self.trend = 1
            self.last_h = NA
        if not isna(self.last_l) and lt(bar.close, self.last_l):
            self.trend = -1
            self.last_l = NA
        return self.trend


class HtfBias:
    """Feeds closed HTF bars in order and answers the lookahead-free trend for any chart bar time."""

    def __init__(self, htf: str, swing: int):
        self.htf = htf
        self.structure = HtfStructure(swing)
        self.open_times: list[int] = []
        self.trends: list[int] = []

    def add_bar(self, bar: Candle) -> None:
        if self.open_times and bar.open_time <= self.open_times[-1]:
            raise ValueError("HTF bars must be fed in strictly increasing time order")
        self.open_times.append(bar.open_time)
        self.trends.append(self.structure.update(bar))

    def trend_for(self, chart_open_time: int) -> int | None:
        """Trend seen by the chart bar opening at ``chart_open_time``; ``None`` when no prior HTF bar is known yet.

        ``None`` maps to Pine's na: the script's ``htfTrend == 1`` is then false (no bias, no signal).
        """
        htf_open = floor_time(chart_open_time, self.htf)
        i = bisect.bisect_left(self.open_times, htf_open) - 1  # latest HTF bar opening strictly before
        if i < 0:
            return None
        return self.trends[i]

    def ready_for(self, chart_open_time: int) -> bool:
        """True when the HTF bar right before ``chart_open_time``'s HTF bar has been fed (live-trading guard: a
        missing HTF bar would silently serve a stale trend)."""
        if not self.open_times:
            return False
        htf_open = floor_time(chart_open_time, self.htf)
        i = bisect.bisect_left(self.open_times, htf_open) - 1
        return i >= 0 and bar_close_time(self.open_times[i], self.htf) == htf_open

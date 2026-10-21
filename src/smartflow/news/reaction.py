"""How the price moved after each headline, measured on Strike (1 minute candles of its mark price, public API): from
the last close before it came out to 15 minutes and 1 hour later, in %. The model never says this: it is read from the
price.

Strike's klines by end time return exactly the ``limit`` candles up to it (checked 2026-10-21: by start time they
begin 2-19 minutes late), so the closes are fetched backwards from now, 1500 minutes (25 h) per request.
"""

from __future__ import annotations

MIN = 60_000
CHUNK = 1500
LOOKBACK = 10   # a market without trades in a minute: the last close within 10 minutes


class Prices:
    """Strike 1m closes per market, fetched once per cycle and kept for it."""

    def __init__(self, klines):
        """``klines(symbol, end_ms, limit)`` -> Strike kline rows ([open time, open, high, low, close, ...])."""
        self.klines = klines
        self.closes: dict[str, dict[int, float]] = {}
        self.lo: dict[str, int] = {}

    def cover(self, market: str, since: int, now: int) -> None:
        """Make sure the closes of ``market`` from ``since`` to ``now`` are here."""
        have = self.closes.setdefault(market, {})
        self.lo.setdefault(market, now // MIN * MIN + MIN)   # the oldest minute fetched (nothing yet: from now)
        while self.lo[market] > since:
            rows = self.klines(market, self.lo[market] - MIN, CHUNK)   # candles opened up to that minute
            if not rows:
                break
            for r in rows:
                have[int(r[0])] = float(r[4])
            first = min(int(r[0]) for r in rows)
            if first >= self.lo[market]:
                break   # no older candles
            self.lo[market] = first

    def at(self, market: str, t: int) -> float | None:
        """The price at time t: the close of the last minute that ended at or before it."""
        have = self.closes.get(market, {})
        o = t // MIN * MIN - MIN
        for k in range(LOOKBACK):
            p = have.get(o - k * MIN)
            if p is not None:
                return p
        return None


def measure(prices: Prices, market: str, t: int, now: int) -> dict:
    """{"m", "p0", "r15", "r60", "done"}: what is known so far (r15/r60 None until that time has passed; done once the
    hour has, found or not); {"none": True} when Strike has no price around it."""
    p0 = prices.at(market, t)
    if p0 is None or p0 <= 0:
        return {"m": market, "none": True, "done": True}
    out: dict = {"m": market, "p0": p0, "r15": None, "r60": None, "done": t + 60 * MIN <= now}
    for key, mins in (("r15", 15), ("r60", 60)):
        if t + mins * MIN <= now:
            p = prices.at(market, t + mins * MIN)
            if p is not None:
                out[key] = round((p / p0 - 1) * 100, 3)
    return out

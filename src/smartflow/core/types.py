"""Plain data types shared by every layer."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class Candle:
    """A closed OHLCV bar. ``open_time`` is the bar's opening time in Unix milliseconds (UTC).

    ``volume`` is base-asset volume, or ``nan`` when the feed carries none. ``source`` names the feed
    (e.g. ``binance-spot:BTCUSDT``, ``strike-index:BTC-USD``) so a number can never be taken for another venue's.
    """

    open_time: int
    open: float
    high: float
    low: float
    close: float
    volume: float
    source: str = ""

    @property
    def hlc3(self) -> float:
        return (self.high + self.low + self.close) / 3.0

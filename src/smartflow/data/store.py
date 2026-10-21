"""CSV candle store and data validation. One file per (source, symbol, interval); times are UTC milliseconds."""

from __future__ import annotations

import csv
import math
from dataclasses import dataclass, field
from pathlib import Path

from ..core.timeframes import bar_close_time, normalize
from ..core.types import Candle

COLUMNS = ["open_time", "open", "high", "low", "close", "volume", "quote_volume", "trades"]


def write_rows(path: Path, rows: list[list]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    with tmp.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(COLUMNS)
        w.writerows(rows)
    tmp.replace(path)


def read_rows(path: Path) -> list[list]:
    if not path.exists():
        return []
    with path.open(newline="", encoding="utf-8") as f:
        r = csv.reader(f)
        next(r, None)
        return [row for row in r if row]


def load_candles(path: Path, source: str, start_ms: int | None = None, end_ms: int | None = None) -> list[Candle]:
    out = []
    for row in read_rows(path):
        t = int(row[0])
        if (start_ms is not None and t < start_ms) or (end_ms is not None and t >= end_ms):
            continue
        vol = float(row[5]) if row[5] != "" else math.nan
        out.append(Candle(t, float(row[1]), float(row[2]), float(row[3]), float(row[4]), vol, source))
    return out


@dataclass
class DataReport:
    bars: int = 0
    first: int | None = None
    last: int | None = None
    duplicates: int = 0
    out_of_order: int = 0
    missing_bars: int = 0
    gaps: list[tuple[int, int]] = field(default_factory=list)   # (last_open_before_gap, next_open)
    bad_ohlc: int = 0
    zero_volume: int = 0
    flat_zero_volume: int = 0   # O=H=L=C and V=0: typical exchange gap-fill, carries no information

    @property
    def ok(self) -> bool:
        return self.duplicates == 0 and self.out_of_order == 0 and self.bad_ohlc == 0

    def summary(self) -> str:
        return (f"bars={self.bars} dup={self.duplicates} disorder={self.out_of_order} missing={self.missing_bars} "
                f"in {len(self.gaps)} gaps, bad_ohlc={self.bad_ohlc}, zero_vol={self.zero_volume} "
                f"(flat {self.flat_zero_volume})")


def validate(candles: list[Candle], tf: str) -> DataReport:
    rep = DataReport(bars=len(candles))
    if not candles:
        return rep
    rep.first, rep.last = candles[0].open_time, candles[-1].open_time
    tf = normalize(tf)
    prev = None
    for c in candles:
        if not (c.low <= min(c.open, c.close) and c.high >= max(c.open, c.close) and c.low > 0):
            rep.bad_ohlc += 1
        if not math.isnan(c.volume) and c.volume == 0:
            rep.zero_volume += 1
            if c.open == c.high == c.low == c.close:
                rep.flat_zero_volume += 1
        if prev is not None:
            if c.open_time == prev.open_time:
                rep.duplicates += 1
            elif c.open_time < prev.open_time:
                rep.out_of_order += 1
            else:
                expected = bar_close_time(prev.open_time, tf)
                if c.open_time != expected:
                    # count the missing bars between the two
                    n, t = 0, expected
                    while t < c.open_time and n < 10_000_000:
                        n += 1
                        t = bar_close_time(t, tf)
                    rep.missing_bars += n
                    rep.gaps.append((prev.open_time, c.open_time))
        prev = c
    return rep

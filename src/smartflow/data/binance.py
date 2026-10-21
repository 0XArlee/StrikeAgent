"""Binance public market data (no key needed): spot klines and USD-M perpetual funding rates.

Binance spot is the feed the indicator was designed and measured on (TradingView ``BINANCE:<base>USDT``) and the
script's own fallback volume source. Its volume is Binance's, never Strike's: every candle is tagged
``binance-spot:<SYMBOL>``. Perpetual funding is only a *proxy* for Strike funding before Strike existed.

Endpoints (official, public): ``GET https://api.binance.com/api/v3/klines`` (max 1000 rows/request) and
``GET https://fapi.binance.com/fapi/v1/fundingRate`` (max 1000 rows/request).
"""

from __future__ import annotations

import time
from pathlib import Path

from ..core.timeframes import bar_close_time, to_binance_interval
from ..net import get_json
from .store import read_rows, write_rows

SPOT = "https://api.binance.com/api/v3/klines"
FUNDING = "https://fapi.binance.com/fapi/v1/fundingRate"


def kline_path(root: Path, symbol: str, tf: str) -> Path:
    return root / "binance" / "spot" / f"{symbol}_{to_binance_interval(tf)}.csv"


def funding_path(root: Path, symbol: str) -> Path:
    return root / "binance" / "funding" / f"{symbol}.csv"


def sync_klines(root: Path, symbol: str, tf: str, start_ms: int, now_ms: int | None = None, log=print) -> Path:
    """Download (or extend) the CSV of CLOSED klines for ``symbol``/``tf`` from ``start_ms``. Idempotent."""
    path = kline_path(root, symbol, tf)
    rows = read_rows(path)
    have = {int(r[0]) for r in rows}
    cursor = (max(have) + 1) if have else start_ms
    if rows and int(rows[0][0]) > start_ms:  # extend backwards: simplest correct option is a full refetch
        rows, have, cursor = [], set(), start_ms
    now_ms = now_ms or int(time.time() * 1000)
    interval = to_binance_interval(tf)
    new = 0
    while True:
        batch = get_json(SPOT, {"symbol": symbol, "interval": interval, "startTime": cursor, "limit": 1000})
        if not batch:
            break
        for k in batch:
            t = int(k[0])
            if bar_close_time(t, tf) > now_ms:  # still forming: never store an open bar
                continue
            if t not in have:
                rows.append([t, k[1], k[2], k[3], k[4], k[5], k[7], k[8]])
                have.add(t)
                new += 1
        last_t = int(batch[-1][0])
        if len(batch) < 1000 or bar_close_time(last_t, tf) > now_ms:
            break
        cursor = last_t + 1
    rows.sort(key=lambda r: int(r[0]))
    write_rows(path, rows)
    log(f"binance {symbol} {interval}: +{new} bars, {len(rows)} total -> {path}")
    return path


def sync_funding(root: Path, symbol: str, start_ms: int, log=print) -> Path:
    """USD-M perpetual funding history (``fundingTime`` ms, ``fundingRate`` per settlement)."""
    import csv
    path = funding_path(root, symbol)
    rows: list[list] = []
    if path.exists():
        with path.open(newline="", encoding="utf-8") as f:
            r = csv.reader(f)
            next(r, None)
            rows = [x for x in r if x]
    have = {int(r[0]) for r in rows}
    cursor = (max(have) + 1) if have else start_ms
    new = 0
    while True:
        batch = get_json(FUNDING, {"symbol": symbol, "startTime": cursor, "limit": 1000})
        if not batch:
            break
        for e in batch:
            t = int(e["fundingTime"])
            if t not in have:
                rows.append([t, e["fundingRate"]])
                have.add(t)
                new += 1
        if len(batch) < 1000:
            break
        cursor = int(batch[-1]["fundingTime"]) + 1
    rows.sort(key=lambda r: int(r[0]))
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["funding_time", "funding_rate"])
        w.writerows(rows)
    log(f"binance funding {symbol}: +{new}, {len(rows)} total -> {path}")
    return path


def load_funding(root: Path, symbol: str) -> list[tuple[int, float]]:
    import csv
    path = funding_path(root, symbol)
    if not path.exists():
        return []
    with path.open(newline="", encoding="utf-8") as f:
        r = csv.reader(f)
        next(r, None)
        return [(int(a), float(b)) for a, b in r if a]

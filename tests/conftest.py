import math
import random
from pathlib import Path

import pytest

from smartflow.core.types import Candle

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
HOUR = 3_600_000


def synthetic(n: int, seed: int = 1, start: int = 1_640_995_200_000, step: int = HOUR, vol_base: float = 100.0):
    """Random-walk candles with occasional impulsive bars, deterministic."""
    rnd = random.Random(seed)
    out, px = [], 100.0
    for i in range(n):
        o = px
        shock = rnd.gauss(0, 0.006) + (rnd.choice([-1, 1]) * 0.03 if rnd.random() < 0.03 else 0)
        c = o * math.exp(shock)
        h = max(o, c) * (1 + abs(rnd.gauss(0, 0.002)))
        l = min(o, c) * (1 - abs(rnd.gauss(0, 0.002)))
        v = vol_base * (1 + abs(rnd.gauss(0, 0.5))) * (4 if abs(shock) > 0.02 else 1)
        out.append(Candle(start + i * step, round(o, 4), round(h, 4), round(l, 4), round(c, 4), round(v, 3), "syn"))
        px = c
    return out


def aggregate(candles, tf_ms):
    out, cur = [], None
    for c in candles:
        k = (c.open_time // tf_ms) * tf_ms
        if cur is None or cur[0] != k:
            if cur:
                out.append(Candle(*cur, "syn"))
            cur = [k, c.open, c.high, c.low, c.close, c.volume]
        else:
            cur[2], cur[3], cur[4], cur[5] = max(cur[2], c.high), min(cur[3], c.low), c.close, cur[5] + c.volume
    if cur:
        out.append(Candle(*cur, "syn"))
    return out


@pytest.fixture
def need_data():
    p = DATA / "binance" / "spot" / "BTCUSDT_1h.csv"
    if not p.exists():
        pytest.skip("Binance data not downloaded (run: smartflow data sync)")
    return DATA

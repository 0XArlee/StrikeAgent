import math
import random

from smartflow.trend.backtest import Data, Fast, self_check
from smartflow.trend.model import (PRESETS, TrendParams, apply_rebalance_threshold, asset_weight, exit_ladder,
                                   sub_strategy_positions)


def test_donchian_sub_strategy_enters_at_the_high_and_trails_the_mid():
    close = [10.0, 11.0, 12.0, 11.0, 13.0, 14.0, 13.0, 12.0, 11.0, 10.0, 12.0, 15.0]
    pos, stop = sub_strategy_positions(close, 3)
    assert pos == [0, 0, 1, 0, 1, 1, 0, 0, 0, 0, 1, 1]
    assert stop[2] == 11.0 and stop[5] == 12.5 and math.isnan(stop[6])   # mid of the channel, never falling
    # the mirror side only with shorts
    pos_s, _ = sub_strategy_positions([12.0, 11.0, 10.0, 9.0, 10.5], 3, allow_shorts=True)
    assert pos_s[2] == -0.5 and pos_s[4] == 0.0


def test_weight_is_vol_targeted_and_capped():
    p = TrendParams()
    steady = [100 * 1.001 ** i for i in range(200)]   # very low vol: the scalar hits the cap
    assert abs(asset_weight(steady, p)[-1] - p.leverage_cap) < 1e-12
    assert asset_weight(steady, p)[50] == 0.0          # no vol estimate yet -> no position


def test_rebalance_threshold_saves_small_resizes():
    prev = {"BTC": 0.30, "ETH": 0.20}
    out = apply_rebalance_threshold({"BTC": 0.33, "ETH": 0.0, "SOL": 0.1}, prev, 0.20)
    assert out == {"BTC": 0.30, "ETH": 0.0, "SOL": 0.1}   # +10 % kept, exit and entry executed


def test_exit_ladder_nearest_stop_first():
    close = [100 + i for i in range(120)]
    levels = exit_ladder(close, PRESETS["standard"])
    assert len(levels) == 6 and [s for _, s in levels] == sorted([s for _, s in levels], reverse=True)


def test_fast_backtest_path_matches_the_model():
    rnd = random.Random(7)
    hist, opens = {}, {}
    for sym in ("AAA", "BBB", "CCC", "DDD"):
        px, rows = 100.0, []
        for d in range(800):
            px *= math.exp(rnd.gauss(0.0005, 0.03))
            rows.append((19000 + d, px, rnd.uniform(1e6, 9e6)))
        hist[sym] = rows
        opens[sym] = {d: c for d, c, _ in rows}
    data = Data(sorted({d for r in hist.values() for d, _, _ in r}), hist, opens, {s: ([], []) for s in hist})
    assert self_check(data, PRESETS["standard"])
    assert Fast(data, PRESETS["standard"]).universe(19799, []) != []

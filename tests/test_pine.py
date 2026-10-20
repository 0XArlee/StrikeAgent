"""Pine primitives vs straightforward reference formulas on random series."""

import math
import random

import pytest

from smartflow.core.pine import (NA, Atr, Ema, Highest, Lowest, Pivot, Rma, Sma, Sum, eq, ge, gt, isna, le, lt,
                                 ne)


def series(n=400, seed=7):
    rnd = random.Random(seed)
    x, out = 100.0, []
    for _ in range(n):
        x *= math.exp(rnd.gauss(0, 0.01))
        out.append(round(x, 2))
    return out


def test_tolerant_comparisons():
    assert gt(1.0, 0.5) and not gt(1.0, 1.0 - 5e-11) and not gt(NA, 0)
    assert ge(1.0, 1.0 + 5e-11) and not ge(NA, 1)
    assert lt(0.5, 1.0) and not lt(1.0, 1.0 + 5e-11)
    assert le(1.0 + 5e-11, 1.0)
    assert eq(1.0, 1.0 + 5e-11) and not eq(NA, NA)
    assert ne(1.0, 1.1) and not ne(NA, 0.0) and not ne(1.0, 1.0)


def test_sma_and_sum():
    xs = series()
    sma, s = Sma(20), Sum(14)
    for i, x in enumerate(xs):
        a, b = sma.update(x), s.update(x)
        if i < 19:
            assert isna(a)
        else:
            assert a == pytest.approx(sum(xs[i - 19:i + 1]) / 20, rel=1e-12)
        if i >= 13:
            assert b == pytest.approx(sum(xs[i - 13:i + 1]), rel=1e-12)


def test_sum_window_with_na_is_na():
    s = Sum(3)
    vals = [s.update(v) for v in (1.0, NA, 2.0, 3.0, 4.0, 5.0)]
    assert [isna(v) for v in vals] == [True, True, True, True, False, False]
    assert vals[-1] == 12.0


def naive_ema(xs, n, alpha):
    out, val = [], NA
    for i, x in enumerate(xs):
        if i < n - 1:
            out.append(NA)
            continue
        if i == n - 1:
            val = sum(xs[:n]) / n
        else:
            val = alpha(val, x)
        out.append(val)
    return out


@pytest.mark.parametrize("n", [2, 10, 21, 100])
def test_ema_seeded_by_sma(n):
    xs = series()
    a = 2 / (n + 1)
    ref = naive_ema(xs, n, lambda v, x: v + a * (x - v))
    e = Ema(n)
    for x, r in zip(xs, ref):
        v = e.update(x)
        assert (isna(v) and isna(r)) or v == pytest.approx(r, rel=1e-12)


def test_rma_and_atr():
    xs = series()
    hs = [x * 1.01 for x in xs]
    ls = [x * 0.99 for x in xs]
    trs = [hs[0] - ls[0]] + [max(hs[i] - ls[i], abs(hs[i] - xs[i - 1]), abs(ls[i] - xs[i - 1]))
                             for i in range(1, len(xs))]
    ref = naive_ema(trs, 14, lambda v, x: (v * 13 + x) / 14)
    atr, rma = Atr(14), Rma(14)
    for i in range(len(xs)):
        v, w = atr.update(hs[i], ls[i], xs[i]), rma.update(trs[i])
        if isna(ref[i]):
            assert isna(v) and isna(w)
        else:
            assert v == pytest.approx(ref[i], rel=1e-12) and w == pytest.approx(ref[i], rel=1e-12)


def test_ema_skips_na_without_advancing():
    e = Ema(3)
    vals = [e.update(v) for v in (NA, NA, 1.0, 2.0, 3.0, NA, 4.0)]
    assert [isna(v) for v in vals] == [True, True, True, True, False, True, False]
    assert vals[4] == 2.0                      # seed = sma(1,2,3)
    assert vals[6] == pytest.approx(2.0 + 0.5 * (4.0 - 2.0))


@pytest.mark.parametrize("n", [3, 10, 20, 100])
def test_highest_lowest(n):
    xs = series(600, seed=n)
    hi, lo = Highest(n), Lowest(n)
    for i, x in enumerate(xs):
        h, l = hi.update(x), lo.update(x)
        if i < n - 1:
            assert isna(h) and isna(l)
        else:
            assert h == max(xs[i - n + 1:i + 1]) and l == min(xs[i - n + 1:i + 1])


def test_pivot_tie_rule():
    # window of 5 (2 left, 2 right). Centre ties an OLDER bar -> pivot; ties a NEWER bar -> no pivot.
    ph = Pivot(2, 2, is_high=True)
    out = [ph.update(v) for v in (5, 9, 9, 3, 2)]
    assert out[-1] == 9  # centre (index 2) = 9 ties index 1 (older): pivot confirmed
    ph = Pivot(2, 2, is_high=True)
    out = [ph.update(v) for v in (5, 3, 9, 9, 2)]
    assert isna(out[-1])  # centre (index 2) ties index 3 (newer): not a pivot
    pl = Pivot(2, 2, is_high=False)
    out = [pl.update(v) for v in (5, 1, 1, 3, 4)]
    assert out[-1] == 1


def test_pivot_matches_bruteforce():
    xs = series(800, seed=3)
    xs = [round(x) for x in xs]  # force ties
    L, R = 5, 5
    ph, pl = Pivot(L, R, True), Pivot(L, R, False)
    for i, x in enumerate(xs):
        a, b = ph.update(x), pl.update(x)
        if i < L + R:
            assert isna(a) and isna(b)
            continue
        c = xs[i - R]
        older, newer = xs[i - R - L:i - R], xs[i - R + 1:i + 1]
        exp_h = c if all(c >= v for v in older) and all(c > v for v in newer) else NA
        exp_l = c if all(c <= v for v in older) and all(c < v for v in newer) else NA
        assert (isna(a) and isna(exp_h)) or a == exp_h
        assert (isna(b) and isna(exp_l)) or b == exp_l

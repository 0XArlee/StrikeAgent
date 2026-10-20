"""Pine Script v6 semantics needed by Smart Flow Signals, as small incremental (bar-by-bar) machines.

Every machine is fed exactly once per bar, in bar order, and returns the value Pine would return on that bar.
Semantics follow TradingView as measured by PyneCore (Apache-2.0, https://github.com/PyneSys/pynecore,
commit 9360388, 2026-10-18), which this module re-implements independently, without copying its code:

* ``na`` is ``math.nan``. Arithmetic propagates it, every comparison involving it is ``False`` (v6 bools are never na).
* User-level float comparisons are tolerant with an absolute epsilon of 1e-10 (equality owns the boundary).
  Built-ins (``highest``/``lowest``/``pivothigh``/``pivotlow``) compare bit-exactly.
* ``ta.ema`` / ``ta.rma`` are seeded with the SMA of the first ``length`` non-na values; na inputs return na and
  do not advance the state. Steps: ema ``prev + alpha*(x-prev)``, rma ``(prev*(len-1)+x)/len``.
* ``ta.sma`` / ``math.sum`` need ``length`` values; a window containing na gives na.
* ``ta.highest``/``ta.lowest`` return na until ``length`` bars exist.
* ``ta.pivothigh(src, L, R)`` reports ``src[R]`` when it is the window maximum and no newer bar in the window ties it
  (left side ``>=``, right side ``>``); ``pivotlow`` mirrors it.
"""

from __future__ import annotations

import math
from collections import deque

NA = math.nan
EPS = 1e-10


def isna(x: float | None) -> bool:
    return x is None or x != x


def nz(x: float, repl: float = 0.0) -> float:
    return repl if isna(x) else x


# ---- tolerant user-level comparisons (Pine v6: na -> False) ----

def gt(a: float, b: float) -> bool:
    return a - b > EPS  # nan - x > EPS is False


def lt(a: float, b: float) -> bool:
    return b - a > EPS


def ge(a: float, b: float) -> bool:
    if isna(a) or isna(b):
        return False
    return a >= b or a - b >= -EPS


def le(a: float, b: float) -> bool:
    if isna(a) or isna(b):
        return False
    return a <= b or b - a >= -EPS


def eq(a: float, b: float) -> bool:
    if isna(a) or isna(b):
        return False
    return abs(a - b) <= EPS


def ne(a: float, b: float) -> bool:
    if isna(a) or isna(b):
        return False
    return abs(a - b) > EPS


# ---- incremental machines ----

class Window:
    """Last ``length`` raw values (na allowed)."""

    __slots__ = ("length", "buf")

    def __init__(self, length: int):
        self.length = length
        self.buf: deque[float] = deque(maxlen=length)

    def push(self, x: float) -> None:
        self.buf.append(x)

    @property
    def full(self) -> bool:
        return len(self.buf) == self.length


class Sum:
    """``math.sum(x, length)``: na until ``length`` values, na if the window holds na. Exact (fsum)."""

    __slots__ = ("w",)

    def __init__(self, length: int):
        self.w = Window(length)

    def update(self, x: float) -> float:
        self.w.push(x)
        if not self.w.full or any(v != v for v in self.w.buf):
            return NA
        return math.fsum(self.w.buf)


class Sma:
    __slots__ = ("s", "length")

    def __init__(self, length: int):
        self.length = length
        self.s = Sum(length)

    def update(self, x: float) -> float:
        total = self.s.update(x)
        return NA if isna(total) else total / self.length


class _Seeded:
    """Shared seeding of ema / rma: SMA of the first ``length`` non-na inputs, na inputs skipped whole."""

    __slots__ = ("length", "value", "_seed")

    def __init__(self, length: int):
        self.length = length
        self.value = NA
        self._seed: list[float] = []

    def _step(self, x: float) -> float:  # pragma: no cover - abstract
        raise NotImplementedError

    def update(self, x: float) -> float:
        if isna(x):
            return NA
        if self.length == 1:
            self.value = x
            return x
        if isna(self.value):
            self._seed.append(x)
            if len(self._seed) < self.length:
                return NA
            self.value = math.fsum(self._seed) / self.length
            self._seed = []
            return self.value
        self.value = self._step(x)
        return self.value


class Ema(_Seeded):
    __slots__ = ("alpha",)

    def __init__(self, length: int):
        super().__init__(length)
        self.alpha = 2.0 / (length + 1)

    def _step(self, x: float) -> float:
        return self.value + self.alpha * (x - self.value)


class Rma(_Seeded):
    def _step(self, x: float) -> float:
        return (self.value * (self.length - 1) + x) / self.length


class TrueRange:
    """``ta.tr(true)``: high-low on the first bar (no previous close)."""

    __slots__ = ("prev_close",)

    def __init__(self) -> None:
        self.prev_close = NA

    def update(self, high: float, low: float, close: float) -> float:
        pc = self.prev_close
        self.prev_close = close
        if isna(pc):
            return high - low
        return max(high - low, abs(high - pc), abs(low - pc))


class Atr:
    __slots__ = ("tr", "rma")

    def __init__(self, length: int):
        self.tr = TrueRange()
        self.rma = Rma(length)

    def update(self, high: float, low: float, close: float) -> float:
        return self.rma.update(self.tr.update(high, low, close))


class _Extreme:
    """``ta.highest`` / ``ta.lowest`` over a fixed length with a monotonic deque (O(1) amortised).

    Inputs are prices and are never na in this project; a na input raises so it cannot slip through silently.
    """

    __slots__ = ("length", "n", "dq", "_better")

    def __init__(self, length: int, highest: bool):
        self.length = length
        self.n = 0
        self.dq: deque[tuple[int, float]] = deque()
        self._better = (lambda a, b: a >= b) if highest else (lambda a, b: a <= b)

    def update(self, x: float) -> float:
        if isna(x):
            raise ValueError("na price fed to highest/lowest")
        i = self.n
        self.n += 1
        while self.dq and self._better(x, self.dq[-1][1]):
            self.dq.pop()
        self.dq.append((i, x))
        while self.dq[0][0] <= i - self.length:
            self.dq.popleft()
        return self.dq[0][1] if self.n >= self.length else NA


class Highest(_Extreme):
    def __init__(self, length: int):
        super().__init__(length, highest=True)


class Lowest(_Extreme):
    def __init__(self, length: int):
        super().__init__(length, highest=False)


class Pivot:
    """``ta.pivothigh`` / ``ta.pivotlow``: the pivot price on the bar that confirms it (``right`` bars later), else na.

    Tie rule (measured on TradingView): the centre must be ``>=`` every older bar and strictly ``>`` every newer bar
    of the window (mirrored for lows).
    """

    __slots__ = ("left", "right", "is_high", "w")

    def __init__(self, left: int, right: int, is_high: bool):
        self.left, self.right, self.is_high = left, right, is_high
        self.w: deque[float] = deque(maxlen=left + right + 1)

    def update(self, x: float) -> float:
        self.w.append(x)
        if len(self.w) < self.w.maxlen:
            return NA
        vals = list(self.w)
        c = vals[self.left]
        older, newer = vals[: self.left], vals[self.left + 1:]
        if self.is_high:
            ok = all(c >= v for v in older) and all(c > v for v in newer)
        else:
            ok = all(c <= v for v in older) and all(c < v for v in newer)
        return c if ok else NA

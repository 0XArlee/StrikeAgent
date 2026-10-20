"""Runs the engine (+ HTF bias + reference trade book) over a candle history, feeding HTF bars only once closed."""

from __future__ import annotations

from dataclasses import dataclass

from .config import Params
from .engine import BarState, SignalEngine
from .htf import HtfBias
from .reference_trades import RefTradeBook
from .timeframes import auto_htf, bar_close_time, normalize, tf_ms
from .types import Candle


def resolve_htf(params: Params, chart_tf: str) -> tuple[str, bool]:
    htf = normalize(params.htf) if params.htf else auto_htf(chart_tf)
    return htf, tf_ms(htf) > tf_ms(chart_tf)


@dataclass
class RunResult:
    chart_tf: str
    htf: str
    htf_ok: bool
    states: list[BarState]
    book: RefTradeBook


class StreamingRunner:
    """Incremental form used both by the backtest and by the live agent: push closed bars as they arrive."""

    def __init__(self, params: Params, chart_tf: str):
        self.params = params
        self.chart_tf = normalize(chart_tf)
        self.htf, self.htf_ok = resolve_htf(params, self.chart_tf)
        self.engine = SignalEngine(params, htf_ok=self.htf_ok)
        self.bias = HtfBias(self.htf, params.htf_swing)
        self.book = RefTradeBook(params)

    def push_htf(self, bar: Candle) -> None:
        self.bias.add_bar(bar)

    def push(self, bar: Candle) -> BarState:
        trend = self.bias.trend_for(bar.open_time) if self.htf_ok else 0
        state = self.engine.update(bar, trend)
        self.book.on_bar(state, bar.high, bar.low)
        return state


def run_history(candles: list[Candle], htf_candles: list[Candle], params: Params, chart_tf: str) -> RunResult:
    r = StreamingRunner(params, chart_tf)
    states: list[BarState] = []
    j = 0
    for c in candles:
        close_t = bar_close_time(c.open_time, r.chart_tf)
        # feed every HTF bar that has closed by the time this chart bar closes (live-equivalent information set)
        while j < len(htf_candles) and bar_close_time(htf_candles[j].open_time, r.htf) <= close_t:
            r.push_htf(htf_candles[j])
            j += 1
        states.append(r.push(c))
    return RunResult(r.chart_tf, r.htf, r.htf_ok, states, r.book)

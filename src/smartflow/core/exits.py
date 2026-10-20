"""Close-based exit rule (SmartFlowSignals.txt lines 232-248), shared by the backtester and the live agent so both
decide exits identically. The hard stop and the optional target are intrabar levels handled by the exchange (live)
or the simulator; this function only covers what is decided on a candle close.
"""

from __future__ import annotations

from .config import ExitMode, Params
from .engine import BarState
from .pine import ge, gt, isna, le, lt


def close_exit(s: BarState, dir: int, bars_since_signal: int, p: Params) -> str:
    """Reason to exit at this close ("trailing exit" / "money-flow exit" / "candle limit") or "" to stay in.

    ``bars_since_signal`` = bar_index - signal bar_index. The channel exit needs at least 2 (the script's
    ``bar_index > t.bar + 1``); the money-flow cross can fire from the first bar after the signal.
    """
    if bars_since_signal <= 0:
        return ""
    ch = s.chan_lo if dir == 1 else s.chan_hi
    chan_hit = bars_since_signal > 1 and (lt(s.close, ch) if dir == 1 else gt(s.close, ch))
    flow_hit = (not isna(s.flow) and not isna(s.flow_prev) and
                ((ge(s.flow_prev, 0) and lt(s.flow, 0)) if dir == 1 else (le(s.flow_prev, 0) and gt(s.flow, 0))))
    if p.exit_mode == ExitMode.TRAILING_CHANNEL:
        hit, label = chan_hit, "trailing exit"
    elif p.exit_mode == ExitMode.FLOW_CROSS:
        hit, label = flow_hit, "money-flow exit"
    else:
        hit, label = chan_hit or flow_hit, ("trailing exit" if chan_hit else "money-flow exit")
    if hit:
        return label
    if bars_since_signal >= p.max_open:
        return "candle limit"
    return ""


def trailing_level(s: BarState, dir: int, stop: float, p: Params) -> float:
    """Level the NEXT candle's close is tested against (what the script draws as the exit line): the channel,
    never looser than the hard stop. For the money-flow exit mode it is just the stop."""
    if p.exit_mode == ExitMode.FLOW_CROSS:
        return stop
    return max(s.chan_lo_next, stop) if dir == 1 else min(s.chan_hi_next, stop)

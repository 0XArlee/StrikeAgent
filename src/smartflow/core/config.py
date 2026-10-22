"""Parameters of Smart Flow Signals, with the indicator's defaults and input bounds (SmartFlowSignals.txt lines 27-54).

Only inputs that change a signal or a trade are modelled; style/drawing inputs are not. ``Params()`` is the
**reference configuration**: the indicator exactly as shipped. Any other value is an experiment and must be labelled
as such (see ``Params.is_reference``).
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, fields
from enum import Enum


class BiasSource(str, Enum):
    HTF_STRUCTURE = "Higher-timeframe structure"
    SLOW_EMA = "Slow EMA on this chart"
    EITHER = "Either of them"
    NONE = "No bias"


class ExitMode(str, Enum):
    TRAILING_CHANNEL = "Trailing channel"
    FLOW_CROSS = "Money-flow cross"
    FIRST = "Whichever comes first"


@dataclass(frozen=True)
class Params:
    # Signal
    look_n: int = 20             # breakout: candles the close must exceed (5..200)
    range_min: float = 1.0       # displacement: min candle range in ATR (>= 0.3)
    body_min: float = 0.6        # displacement: min body / range (0.3..0.95)
    vol_min: float = 1.5         # min relative volume vs 20-candle SMA (0 = off)
    range_filter: bool = False   # skip signals born inside a wide range
    range_max: float = 12.0      # wide range = 100-candle range above this many ATR (4..40)
    # Bias
    bias_source: BiasSource = BiasSource.HTF_STRUCTURE
    htf: str = ""                # "" = automatic (see htf.auto_htf)
    htf_swing: int = 5           # pivot strength on the HTF (2..20)
    # Context filters
    ema_fast: int = 100          # 2..500
    ema_slow: int = 200          # 5..1000
    ema_filter: bool = False     # skip signals against the EMA cloud
    flow_filter: bool = False    # skip signals against the money flow
    # Trade management
    stop_atr: float = 1.5        # hard stop distance in ATR (>= 0.3); 1 R
    exit_mode: ExitMode = ExitMode.TRAILING_CHANNEL
    chan_n: int = 10             # trailing channel length (3..100)
    tp_r: float = 0.0            # fixed target in R, 0 = none
    # Smart Flow addition, not in the script: after each close the stop on the exchange rises to the best extreme
    # since the entry minus this many ATR (a chandelier trail; it only ever tightens). 0 = off (the script)
    chand_atr: float = 0.0
    max_open: int = 300          # max candles in a trade (10..2000)
    fee_pct: float = 0.10        # round-trip fees in % (the indicator's own cost model)
    keep_n: int = 80             # drawings kept; ALSO drops the oldest trade from tracking (reference quirk)
    atr_len: int = 14            # hard-coded in the script (ta.atr(14))

    def validate(self) -> None:
        bounds = {
            "look_n": (5, 200), "range_min": (0.3, None), "body_min": (0.3, 0.95), "vol_min": (0, None),
            "range_max": (4, 40), "htf_swing": (2, 20), "ema_fast": (2, 500), "ema_slow": (5, 1000),
            "stop_atr": (0.3, None), "chan_n": (3, 100), "tp_r": (0, None), "chand_atr": (0, None), "max_open": (10, 2000),
            "fee_pct": (0, None), "keep_n": (5, 200),
        }
        for name, (lo, hi) in bounds.items():
            v = getattr(self, name)
            if v < lo or (hi is not None and v > hi):
                raise ValueError(f"{name}={v} outside the indicator's input bounds [{lo}, {hi}]")
        BiasSource(self.bias_source)
        ExitMode(self.exit_mode)

    @property
    def is_reference(self) -> bool:
        return self == Params()

    def to_dict(self) -> dict:
        d = asdict(self)
        for f in fields(self):
            if isinstance(d[f.name], Enum):
                d[f.name] = d[f.name].value
        return d

    @classmethod
    def from_dict(cls, d: dict) -> "Params":
        d = dict(d)
        if "bias_source" in d:
            d["bias_source"] = BiasSource(d["bias_source"])
        if "exit_mode" in d:
            d["exit_mode"] = ExitMode(d["exit_mode"])
        p = cls(**d)
        p.validate()
        return p

    def fingerprint(self) -> str:
        """Short stable hash, logged with every decision so a result can be tied to its exact configuration."""
        return hashlib.sha256(json.dumps(self.to_dict(), sort_keys=True).encode()).hexdigest()[:12]


# The official Smart Flow configuration every user's agent runs, in both strategies (Edgar, 2026-10-20): the script's
# parameters plus the wide-range filter and a 4 ATR chandelier stop on the exchange (docs/STRATEGY.md).
OFFICIAL = Params(range_filter=True, chand_atr=4.0)


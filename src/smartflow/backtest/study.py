"""Loading, signal generation (cached) and evaluation helpers shared by the CLI and the research reports."""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass
from pathlib import Path

from ..core.config import Params
from ..core.runner import RunResult, run_history
from ..core.timeframes import auto_htf, normalize
from ..core.types import Candle
from ..data.binance import kline_path, load_funding
from ..data.store import load_candles
from .metrics import Stats, compute
from .sim import CostModel, ExecModel, FundingTable, SimResult, simulate


def ms(y: int, m: int = 1, d: int = 1) -> int:
    return int(dt.datetime(y, m, d, tzinfo=dt.timezone.utc).timestamp() * 1000)


# Fixed research windows (decided before looking at any result of the realistic model)
WINDOWS = {
    "full": (ms(2022), ms(2026, 10, 18)),
    "dev": (ms(2022), ms(2024)),            # 2022-2023: bear + recovery
    "val": (ms(2024), ms(2025, 7)),         # 2024-H1 2025
    "test": (ms(2025, 7), ms(2026, 10, 18)),  # H2 2025 - Oct 2026 (includes the Strike era)
    "strike": (ms(2026, 3, 20), ms(2026, 10, 18)),  # period with Strike market data
}
CORE = ("BTCUSDT", "ETHUSDT", "SOLUSDT")
OOS_ASSETS = ("XRPUSDT", "BNBUSDT", "ADAUSDT", "NEARUSDT", "ZECUSDT")


@dataclass
class Market:
    symbol: str
    tf: str
    candles: list[Candle]
    htf: list[Candle]
    funding: FundingTable


def load_market(root: Path, symbol: str, tf: str, params: Params | None = None) -> Market:
    tf = normalize(tf)
    htf = normalize(params.htf) if params and params.htf else auto_htf(tf)
    src = f"binance-spot:{symbol}"
    return Market(symbol, tf, load_candles(kline_path(root, symbol, tf), src),
                  load_candles(kline_path(root, symbol, htf), src), FundingTable(load_funding(root, symbol)))


_MARKETS: dict[tuple, Market] = {}
_RUNS: dict[tuple, RunResult] = {}


def market(root: Path, symbol: str, tf: str, params: Params) -> Market:
    htf = params.htf or auto_htf(normalize(tf))
    key = (str(root), symbol, normalize(tf), htf)
    if key not in _MARKETS:
        _MARKETS[key] = load_market(root, symbol, tf, params)
    return _MARKETS[key]


def signals(root: Path, symbol: str, tf: str, params: Params) -> tuple[Market, RunResult]:
    m = market(root, symbol, tf, params)
    key = (str(root), symbol, normalize(tf), params)
    if key not in _RUNS:
        _RUNS[key] = run_history(m.candles, m.htf, params, m.tf)
    return m, _RUNS[key]


def sim_market(root: Path, symbol: str, tf: str, params: Params, cost: CostModel, exe: ExecModel,
               window: tuple[int, int]) -> SimResult:
    m, run = signals(root, symbol, tf, params)
    return simulate(symbol, m.candles, run.states, params, cost, exe, m.funding, *window)


def evaluate(root: Path, symbols, tf: str, params: Params, cost: CostModel, exe: ExecModel,
             window: tuple[int, int], risk_per_trade: float = 0.005, boot: bool = True
             ) -> tuple[Stats, dict[str, Stats], list]:
    allt, per = [], {}
    for s in symbols:
        r = sim_market(root, s, tf, params, cost, exe, window)
        per[s] = compute(r.trades, *window, risk_per_trade=risk_per_trade, boot=False)
        allt += r.trades
    return compute(allt, *window, risk_per_trade=risk_per_trade, boot=boot), per, allt

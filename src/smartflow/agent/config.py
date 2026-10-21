"""Agent configuration (TOML). Defaults are the safe ones: analysis mode, testnet, no builder fee, autonomy off."""

from __future__ import annotations

import os
import tomllib
from dataclasses import dataclass, field, fields
from pathlib import Path

from ..core.config import Params, OFFICIAL
from .risk import RiskConfig

MODES = ("analysis", "simulation", "confirmation", "autonomous")
LIVE_ACK = "I ACCEPT REAL ORDERS"


@dataclass(frozen=True)
class MarketMap:
    strike: str        # e.g. BTC-USD (execution venue)
    signal: str        # e.g. BTCUSDT (Binance spot signal feed)


@dataclass
class AgentConfig:
    name: str = "smartflow"
    mode: str = "analysis"
    env: str = "testnet"                 # testnet | mainnet
    tf: str = "240"
    markets: list[MarketMap] = field(default_factory=lambda: [MarketMap("BTC-USD", "BTCUSDT"),
                                                              MarketMap("ETH-USD", "ETHUSDT")])
    params: Params = field(default_factory=Params)
    strategy: str = "smartflow"          # its entry in config/strategies.json (the safety hold and the city follow it)
    risk: RiskConfig = field(default_factory=RiskConfig)
    builder_code: str = ""
    builder_fee_bps: int = 0
    builder_fee_approved_bps: int | None = None
    paper_equity: float = 10_000.0
    max_entry_slippage_bps: float = 20.0  # protective IOC price beyond the touch
    confirm_ttl_s: int = 900
    max_entry_drift_r: float = 0.25       # confirmation: refuse if price moved more than this many R since signal
    allow_autonomous: bool = False
    allow_mainnet: bool = False
    sub_account_id: str | None = None
    # positions per market: "single" (one trade, the published strategy) or "pyramid" (up to max_stack trades in the
    # same direction, each with its own stop and exit; opposite signals are ignored while any is open)
    policy: str = "single"
    max_stack: int = 3
    data_root: str = "data"
    runs_root: str = "runs"

    @property
    def run_dir(self) -> Path:
        return Path(self.runs_root) / self.name

    def validate(self) -> None:
        if self.mode not in MODES:
            raise ValueError(f"mode must be one of {MODES}")
        if self.env not in ("testnet", "mainnet"):
            raise ValueError("env must be testnet or mainnet")
        self.params.validate()
        if not 0 <= self.builder_fee_bps <= 100:
            raise ValueError("builder_fee_bps must be 0..100")
        if self.policy not in ("single", "pyramid") or not 1 <= self.max_stack <= 5:
            raise ValueError("policy must be single or pyramid, max_stack 1..5")
        if self.mode == "autonomous":
            if not self.allow_autonomous:
                raise PermissionError("autonomous mode requires allow_autonomous = true in the config")
            if os.environ.get("SMARTFLOW_LIVE_ACK") != LIVE_ACK:
                raise PermissionError(f'autonomous mode requires the env var SMARTFLOW_LIVE_ACK="{LIVE_ACK}"')
        if self.mode in ("confirmation", "autonomous") and self.env == "mainnet" and not self.allow_mainnet:
            raise PermissionError("mainnet orders require allow_mainnet = true in the config")
        if not self.params.is_reference and self.params != OFFICIAL:
            print("WARNING: experimental parameters: neither the script's nor the official Smart Flow configuration")


def load(path: Path) -> AgentConfig:
    raw = tomllib.loads(path.read_text(encoding="utf-8"))
    cfg = AgentConfig()
    for f in fields(AgentConfig):
        if f.name in raw and f.name not in ("markets", "params", "risk"):
            setattr(cfg, f.name, raw[f.name])
    if "markets" in raw:
        cfg.markets = [MarketMap(m["strike"], m["signal"]) for m in raw["markets"]]
    if "params" in raw:
        cfg.params = Params.from_dict({**Params().to_dict(), **raw["params"]})
    if "risk" in raw:
        cfg.risk = RiskConfig(**{**RiskConfig().__dict__, **raw["risk"]})
    cfg.validate()
    return cfg

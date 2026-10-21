"""The strategy registry (``config/strategies.json``): every strategy users can pick, in one place.

The agents' host reads it here (the fleet builds each user's agent from the entry of the strategy they picked, the
health check and the safety hold follow each strategy's official paper agent, the figures generator writes
``config/figures/<id>.json``); the site imports the same file (web/src/strategies.ts, web/server/util.ts). Adding a
strategy is adding an entry, its paper agent and its figures: docs/08 "Estrategias (registro)".

``engine`` names the signal engine the agent runs; today the agent runs ``smartflow`` only, so a strategy is a
configuration of it (parameters, how positions stack, markets, risk cap). An entry with another engine is refused
until the agent can run it. ``creator`` and ``listed`` are kept for strategies by other authors; nothing shows them.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path

from .core.config import Params

ROOT = Path(__file__).resolve().parents[2]
REGISTRY = ROOT / "config" / "strategies.json"
FIGURES = ROOT / "config" / "figures"
ENGINES = {"smartflow"}                       # what agent/runner.py can run
POLICIES = {"single", "pyramid"}
RISK_PRESETS = ("conservative", "standard", "assertive")


@dataclass(frozen=True)
class Strategy:
    id: str
    name: str
    tag: str
    status: str                  # live | soon (soon: shown as coming, never startable)
    listed: bool
    engine: str
    timeframe: str
    params: Params
    policy: str
    max_stack: int
    max_open_positions: int
    max_risk: str                # the highest risk preset users may pick with it
    markets_core: tuple[str, ...]
    markets_allowed: tuple[str, ...]
    paper_city_id: str           # its official paper agent in the city ("" = none)
    paper_config: str
    creator: dict = field(default_factory=dict, compare=False)
    texts: dict = field(default_factory=dict, compare=False, repr=False)

    @property
    def runnable(self) -> bool:
        return self.status == "live" and self.engine in ENGINES


def _parse(d: dict) -> Strategy:
    params = Params.from_dict(dict(d.get("params") or {}))
    params.validate()
    s = Strategy(
        id=d["id"], name=d["name"], tag=d.get("tag", ""), status=d.get("status", "live"), listed=bool(d.get("listed", True)),
        engine=d.get("engine", "smartflow"), timeframe=str(d.get("timeframe", "240")), params=params,
        policy=d.get("policy", "single"), max_stack=int(d.get("max_stack", 1)), max_open_positions=int(d.get("max_open_positions", 8)),
        max_risk=d.get("max_risk", "standard"), markets_core=tuple(d["markets"]["core"]), markets_allowed=tuple(d["markets"]["allowed"]),
        paper_city_id=(d.get("paper") or {}).get("city_id", ""), paper_config=(d.get("paper") or {}).get("config", ""),
        creator=dict(d.get("creator") or {}), texts=dict(d.get("texts") or {}))
    problems = []
    if s.policy not in POLICIES:
        problems.append(f"policy {s.policy!r}")
    if s.max_risk not in RISK_PRESETS:
        problems.append(f"max_risk {s.max_risk!r}")
    if s.status == "live" and s.engine not in ENGINES:
        problems.append(f"engine {s.engine!r} is not one the agent runs")
    if not set(s.markets_core) <= set(s.markets_allowed):
        problems.append("core markets outside the allowed ones")
    for lang in ("en", "es"):
        t = s.texts.get(lang) or {}
        if not t.get("tagline") or not t.get("details"):
            problems.append(f"texts.{lang} incomplete")
    if problems:
        raise ValueError(f"strategy {s.id}: " + "; ".join(problems))
    return s


def load(path: Path | None = None) -> tuple[str, dict[str, Strategy]]:
    """(default id, {id: strategy}) in the registry's order (read once per file)."""
    return _load(str(path or REGISTRY))


@lru_cache(maxsize=8)
def _load(path: str) -> tuple[str, dict[str, Strategy]]:
    raw = json.loads(Path(path).read_text(encoding="utf-8"))
    out: dict[str, Strategy] = {}
    for d in raw["strategies"]:
        s = _parse(d)
        if s.id in out:
            raise ValueError(f"strategy {s.id} twice in the registry")
        out[s.id] = s
    if raw["default"] not in out or not out[raw["default"]].runnable:
        raise ValueError("the default strategy must exist and be live")
    return raw["default"], out


def default() -> Strategy:
    d, all_ = load()
    return all_[d]


def get(sid: str | None) -> Strategy:
    """The strategy with this id, or the default one for an unknown or missing id (what the site stores is checked
    there too: an unknown id never reaches the host)."""
    return load()[1].get(sid or "", default())


def all_strategies() -> list[Strategy]:
    return list(load()[1].values())


def figures(sid: str) -> dict | None:
    """The backtest figures of a strategy (config/figures/<id>.json, web/scripts/gen_strategy.py), if generated."""
    p = FIGURES / f"{sid}.json"
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None

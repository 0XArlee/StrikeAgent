"""Watchdog of the agents' host: tells the operator (smartflow.notify) when something stops working.

Run every 5 minutes inside the host (``deploy/smartflow-watchdog.timer``). Checks:

- every Smart Flow service that should run is active (the units whose settings file exists);
- each site it pushes to received a snapshot in the last 15 minutes (``/api/info`` ``pushedAt``);
- every agent of the city (official and users') still checks its candles (not ``offline``);
- the disk is not about to fill up.

A problem is sent when it appears, again every 6 hours while it lasts, and once more when it is solved. The state
lives in ``runs/watchdog.json``. When the whole host or its internet is down nothing here can speak: the site's
``/api/info`` is also checked from outside (``.github/workflows/watchdog.yml``).
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import time
import urllib.parse
import urllib.request
from pathlib import Path

from .. import notify

PAPER = ("reference", "pyramid", "recommended", "2h", "flowexit")
# unit -> its settings file (None: always expected)
UNITS = {**{f"smartflow-paper@{p}": None for p in PAPER}, "smartflow-api": None,
         "smartflow-push": "/etc/smartflow/push.env", "smartflow-push-qa": "/etc/smartflow/push-qa.env",
         "smartflow-fleet": "/etc/smartflow/fleet.env", "smartflow-fleet-mainnet": "/etc/smartflow/fleet-mainnet.env",
         "smartflow-data.timer": None, "smartflow-backup.timer": None}
SITES = {"production": "/etc/smartflow/push.env", "QA": "/etc/smartflow/push-qa.env"}
PUSH_STALE_MS = 15 * 60_000     # the push sends at least every 10 minutes
REMIND_S = 6 * 3600
DISK_FULL = 0.90
UA = "smartflow-watchdog/1.0"


def _env_file(path: str) -> dict:
    out = {}
    try:
        for ln in Path(path).read_text(encoding="utf-8").splitlines():
            if "=" in ln and not ln.lstrip().startswith("#"):
                k, v = ln.split("=", 1)
                out[k.strip()] = v.strip().strip('"')
    except OSError:
        pass
    return out


def _active(unit: str) -> bool:
    try:
        r = subprocess.run(["systemctl", "is-active", unit], capture_output=True, text=True, timeout=10)
        return r.stdout.strip() == "active"
    except (OSError, subprocess.TimeoutExpired):
        return False


def _info(url: str) -> dict:
    req = urllib.request.Request(url.rstrip("/") + "/api/info", headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=20) as r:
        return json.loads(r.read() or b"{}")


def problems(runs_root: Path, city_toml: Path, now_ms: int | None = None, active=_active, info=_info,
             exists=os.path.exists, disk=shutil.disk_usage) -> dict[str, str]:
    """{key: description} of everything wrong right now (empty: all good)."""
    from ..api.city import build, load_city, load_live
    now_ms = now_ms or int(time.time() * 1000)
    out: dict[str, str] = {}
    for unit, needs in UNITS.items():
        if (needs is None or exists(needs)) and not active(unit):
            out[f"unit:{unit}"] = f"service {unit} is not running"
    for site, env_file in SITES.items():
        push = _env_file(env_file).get("SMARTFLOW_PUSH_URL") if exists(env_file) else None
        if not push:
            continue
        u = urllib.parse.urlsplit(push)   # the push endpoint (…/api/internal/push): the site is its origin
        url = f"{u.scheme}://{u.netloc}"
        try:
            got = info(url)
        except Exception as e:
            out[f"site:{site}"] = f"the {site} site does not answer ({type(e).__name__})"
            continue
        at = got.get("pushedAt")
        if not isinstance(at, (int, float)) or now_ms - at > PUSH_STALE_MS:
            ago = f"{(now_ms - at) / 60_000:.0f} min" if isinstance(at, (int, float)) else "never"
            out[f"push:{site}"] = f"the {site} site got no data from the agents for {ago}"
    try:
        agents = load_city(city_toml) + [a for env in ("mainnet", "testnet") for a in load_live(runs_root, env)]
        for a in build(agents, now_ms)["agents"]:
            if a.get("status") == "offline":
                out[f"agent:{a['id']}"] = f"agent {a.get('name', a['id'])} is not checking its candles"
    except Exception as e:
        out["city"] = f"cannot read the agents' journals ({type(e).__name__}: {e})"[:200]
    try:
        u = disk(str(runs_root))
        if u.used / u.total >= DISK_FULL:
            out["disk"] = f"disk {100 * u.used / u.total:.0f} % full"
    except OSError:
        pass
    return out


def site_check(url: str, now_ms: int | None = None, info=_info) -> str | None:
    """From outside the host (.github/workflows/watchdog.yml): what is wrong with the site's agents, or None."""
    now_ms = now_ms or int(time.time() * 1000)
    try:
        got = info(url)
    except Exception as e:
        return f"{url} does not answer ({type(e).__name__})"
    at = got.get("pushedAt")
    if not isinstance(at, (int, float)):
        return f"{url} never got data from the agents' host"
    if now_ms - at > PUSH_STALE_MS:
        return f"{url} got no data from the agents' host for {(now_ms - at) / 60_000:.0f} min (host, its internet or the push is down)"
    if not got.get("agentHealthy"):
        return f"{url}: no agent is checking the market (every agent offline)"
    return None


def run_once(runs_root: Path, city_toml: Path, log=print, **kw) -> dict:
    """Checks once, alerts on what changed (and reminds of what lasts), keeps the state in runs/watchdog.json."""
    path = Path(runs_root) / "watchdog.json"
    try:
        state = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        state = {}
    now = time.time()
    found = problems(Path(runs_root), Path(city_toml), **kw)
    open_ = state.get("open", {})
    for k, text in found.items():
        was = open_.get(k)
        if was is None or now - was.get("told", 0) >= REMIND_S:
            since = was["since"] if was else now
            lasting = f" (for {(now - since) / 3600:.1f} h)" if was else ""
            notify.send("error", text + lasting, source="watchdog", cooldown_s=0)
            open_[k] = {"since": since, "told": now, "text": text}
        else:
            open_[k]["text"] = text
    for k in [k for k in open_ if k not in found]:
        notify.send("warning", f"solved: {open_[k]['text']}", source="watchdog", cooldown_s=0)
        open_.pop(k)
    doc = {"time": int(now * 1000), "open": open_}
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(doc, indent=1), encoding="utf-8")
    tmp.replace(path)
    log(f"watchdog: {len(found)} problem(s)" + "".join(f"\n  {v}" for v in found.values()))
    return doc

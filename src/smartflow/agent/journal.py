"""Append-only decision journal (JSONL) and operational alerts.

Every decision can be reconstructed: engine version, parameter fingerprint, mode, inputs, filters, risk outcome,
order payloads and exchange responses. Secrets are redacted defensively (keys, signatures, nonces) even though the
agent never passes them here. ``kind`` separates what was only simulated from what was actually sent/executed:
``analysis`` | ``signal`` | ``paper_order`` | ``live_order`` | ``fill`` | ``exit`` | ``reconcile`` | ``alert``, plus
``strike_call`` (every request that changes something on Strike, as sent and as answered), ``agent_start`` /
``agent_stop`` (the configuration it ran with) and ``host`` (what the fleet did with this agent).

The file is a tamper-evident chain (``smartflow.audit``): each line carries the hash of the line before it.
"""

from __future__ import annotations

import datetime as dt
import json
import re
from pathlib import Path

from .. import ENGINE_VERSION, notify
from ..audit import append

SECRET_KEYS = re.compile(r"(private|secret|signature|seed|mnemonic|nonce|password|token)", re.I)
HEX_SECRET = re.compile(r"\b[0-9a-f]{64,128}\b")


def redact(obj):
    if isinstance(obj, dict):
        return {k: ("<redacted>" if SECRET_KEYS.search(str(k)) else redact(v)) for k, v in obj.items()}
    if isinstance(obj, list):
        return [redact(v) for v in obj]
    if isinstance(obj, str) and HEX_SECRET.search(obj) and len(obj) >= 64:
        return HEX_SECRET.sub(lambda m: m.group(0)[:8] + "…", obj)
    return obj


class Journal:
    def __init__(self, path: Path, mode: str, params_fp: str):
        self.path = path
        self.mode = mode
        self.params_fp = params_fp
        path.parent.mkdir(parents=True, exist_ok=True)

    def write(self, kind: str, **fields) -> dict:
        rec = {"ts": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"), "kind": kind,
               "mode": self.mode, "engine": ENGINE_VERSION, "params": self.params_fp, **redact(fields)}
        return append(self.path, rec)

    def alert(self, level: str, message: str, **fields) -> None:
        self.write("alert", level=level, message=message, **fields)
        print(f"[ALERT {level}] {message}")
        # to the operator's phone (smartflow.notify): the same problem once per cooldown, whatever its numbers
        notify.send(level, message, source=self.path.parent.name, key=re.sub(r"[\d.,]+", "#", message)[:120])

    def read(self, kind: str | None = None) -> list[dict]:
        if not self.path.exists():
            return []
        out = []
        for ln in self.path.read_text(encoding="utf-8").splitlines():
            try:
                r = json.loads(ln)
            except json.JSONDecodeError:
                continue
            if kind is None or r.get("kind") == kind:
                out.append(r)
        return out

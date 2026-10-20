"""Alerts to the operator's phone: one webhook URL, any of the usual chat services.

``SMARTFLOW_ALERT_WEBHOOK`` (in ``/etc/smartflow/alert.env`` on the agents' host, loaded by every unit) picks the
format from the URL:

- Telegram: ``https://api.telegram.org/bot<token>/sendMessage?chat_id=<chat>``
- Discord:  ``https://discord.com/api/webhooks/<id>/<token>``
- Slack:    ``https://hooks.slack.com/services/...``
- anything else gets ``{"text", "level", "source"}`` as JSON.

Only ``SMARTFLOW_ALERT_LEVEL`` and above are sent (default ``warning``). The same alert (same source and key) is sent
at most once every ``SMARTFLOW_ALERT_COOLDOWN_S`` seconds (default 30 min) per process: with many users' agents a
problem of Strike would otherwise arrive once per agent. Sending never raises: an alert must not stop an agent.
"""

from __future__ import annotations

import json
import os
import threading
import time
import urllib.parse
import urllib.request

LEVELS = {"info": 0, "warning": 1, "error": 2, "critical": 3}
ICON = {"info": "ℹ️", "warning": "⚠️", "error": "🛑", "critical": "🚨"}
UA = "smartflow-alert/1.0"

_sent: dict[tuple[str, str], float] = {}
_lock = threading.Lock()


def configured() -> bool:
    return bool(os.environ.get("SMARTFLOW_ALERT_WEBHOOK", "").strip())


def payload(url: str, level: str, text: str, source: str) -> tuple[str, dict]:
    """(URL to POST to, JSON body) for this webhook's service."""
    line = f"{ICON.get(level, '')} [{level}] {source + ': ' if source else ''}{text}".strip()
    u = urllib.parse.urlsplit(url)
    if u.netloc == "api.telegram.org":
        q = dict(urllib.parse.parse_qsl(u.query))
        return urllib.parse.urlunsplit((u.scheme, u.netloc, u.path, "", "")), {
            "chat_id": q.get("chat_id", ""), "text": line[:4000], "disable_web_page_preview": True}
    if u.netloc in ("discord.com", "discordapp.com"):
        return url, {"content": line[:1900]}
    if u.netloc == "hooks.slack.com":
        return url, {"text": line[:3000]}
    return url, {"text": line[:3000], "level": level, "source": source}


def send(level: str, text: str, source: str = "", key: str | None = None, cooldown_s: float | None = None) -> bool:
    """Send one alert. True if it went out; False if not configured, below the level, cooled down or failed."""
    url = os.environ.get("SMARTFLOW_ALERT_WEBHOOK", "").strip()
    if not url:
        return False
    if LEVELS.get(level, 0) < LEVELS.get(os.environ.get("SMARTFLOW_ALERT_LEVEL", "warning"), 1):
        return False
    cool = float(os.environ.get("SMARTFLOW_ALERT_COOLDOWN_S", 1800)) if cooldown_s is None else cooldown_s
    k = (source, key if key is not None else text[:120])
    now = time.time()
    with _lock:
        if now - _sent.get(k, -1e18) < cool:
            return False
        _sent[k] = now
    target, body = payload(url, level, text, source)
    try:
        req = urllib.request.Request(target, data=json.dumps(body).encode(), method="POST",
                                     headers={"Content-Type": "application/json", "User-Agent": UA})
        urllib.request.urlopen(req, timeout=8).read()
        return True
    except Exception as e:   # never break the caller
        print(f"[alert webhook failed: {type(e).__name__}]")
        return False

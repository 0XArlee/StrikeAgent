"""Minimal HTTP JSON client (stdlib only): explicit User-Agent, timeouts, bounded retries with backoff.

Strike and Binance both sit behind CDNs that reject default library User-Agents (Strike returns Cloudflare 403/1010
for ``Python-urllib``), so every request carries ours.
"""

from __future__ import annotations

import json
import random
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass

USER_AGENT = "smartflow-agent/0.1 (+EdgeCraft)"
RETRY_STATUS = {408, 425, 429, 500, 502, 503, 504}


@dataclass
class HttpError(Exception):
    status: int
    body: str
    url: str

    def __str__(self) -> str:
        return f"HTTP {self.status} for {self.url}: {self.body[:300]}"


def request_json(method: str, url: str, params: dict | None = None, body: bytes | None = None,
                 headers: dict | None = None, timeout: float = 20.0, retries: int = 4,
                 retry_non_idempotent: bool = False):
    """Returns ``(status, parsed_json_or_text, response_headers)``. Raises ``HttpError`` on a final non-2xx.

    Non-idempotent requests (POST/DELETE) are NOT retried unless ``retry_non_idempotent`` is set: a timed-out order
    may have reached the engine, so the caller must reconcile by client_order_id instead of blindly resending.
    """
    if params:
        url = f"{url}?{urllib.parse.urlencode(params)}"
    hdrs = {"User-Agent": USER_AGENT, "Accept": "application/json"}
    if headers:
        hdrs.update(headers)
    idempotent = method.upper() == "GET" or retry_non_idempotent
    attempt = 0
    while True:
        attempt += 1
        req = urllib.request.Request(url, data=body, method=method.upper(), headers=hdrs)
        try:
            with urllib.request.urlopen(req, timeout=timeout) as r:
                raw = r.read().decode("utf-8")
                return r.status, _parse(raw), dict(r.headers)
        except urllib.error.HTTPError as e:
            raw = e.read().decode("utf-8", "replace")
            if idempotent and e.code in RETRY_STATUS and attempt <= retries:
                _sleep(attempt, e.headers.get("Retry-After"))
                continue
            raise HttpError(e.code, raw, url) from None
        except (urllib.error.URLError, TimeoutError, ConnectionError) as e:
            if idempotent and attempt <= retries:
                _sleep(attempt, None)
                continue
            raise HttpError(0, repr(e), url) from None


def _parse(raw: str):
    try:
        return json.loads(raw) if raw else None
    except json.JSONDecodeError:
        return raw


def _sleep(attempt: int, retry_after: str | None) -> None:
    if retry_after:
        try:
            time.sleep(min(60.0, float(retry_after)))
            return
        except ValueError:
            pass
    time.sleep(min(30.0, 0.5 * 2 ** (attempt - 1)) * (0.8 + 0.4 * random.random()))


def get_json(url: str, params: dict | None = None, **kw):
    status, data, _ = request_json("GET", url, params=params, **kw)
    return data

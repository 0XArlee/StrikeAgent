"""Smart Flow public API, read-only: ``/api/health``, ``/api/info``, ``/api/city`` and ``/api/news`` (the News Tower's
news.json, when given).

Standard library only (``http.server``). It serves small JSON documents built from local files and holds no keys, so
it can run next to the paper agents. TLS and the public hostname come from a reverse proxy or a named Cloudflare
Tunnel in front of it.

Wallet onboarding (``/api/connect/*``, ``/api/me``, ``/api/action*``) answers 501 until the Smart Flow builder code is
registered on Strike (docs/03): the page shows that error instead of pretending the account was linked.
"""

from __future__ import annotations

import json
import threading
import time
import tomllib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

from .. import ENGINE_VERSION
from .city import CityAgent, build, load_city

CONNECT_PATHS = ("/api/connect/challenge", "/api/connect/verify", "/api/me", "/api/action/challenge", "/api/action")
MAX_BODY = 64 * 1024


class CityCache:
    """Rebuilds the city document at most every ``ttl`` seconds, whatever the request rate."""

    def __init__(self, agents: list[CityAgent], ttl: float = 10.0):
        self.agents = agents
        self.ttl = ttl
        self._lock = threading.Lock()
        self._at = 0.0
        self._doc: dict = {}
        self._body = b""

    def get(self) -> tuple[dict, bytes]:
        with self._lock:
            if time.monotonic() - self._at > self.ttl or not self._body:
                self._doc = build(self.agents)
                self._body = json.dumps(self._doc, separators=(",", ":"), allow_nan=False).encode()
                self._at = time.monotonic()
            return self._doc, self._body


def app_info(raw: dict, city: dict) -> dict:
    i = raw.get("info", {})
    return {
        "env": i.get("env", "mainnet"), "builderCode": i.get("builder_code", ""), "feeBps": int(i.get("fee_bps", 20)),
        "takerFeeBps": int(i.get("taker_fee_bps", 5)), "markets": i.get("markets", []),
        "riskPresets": i.get("risk_presets", {"conservative": 0.5, "standard": 1.0, "assertive": 2.0}),   # live/fleet.py RISK
        "agentHealthy": bool(city.get("agents")) and all(a.get("status") != "offline" for a in city["agents"]),
        "engine": ENGINE_VERSION, "connect": bool(i.get("builder_code")),
    }


def make_handler(cache: CityCache, raw: dict, allow_origin: str = "*", news: Path | None = None):
    class Handler(BaseHTTPRequestHandler):
        server_version = "smartflow-api"
        sys_version = ""

        def log_message(self, fmt, *args):   # one short line per request, no query strings or bodies
            print(f"{self.command} {urlparse(self.path).path} -> {args[1] if len(args) > 1 else ''}")

        def _send(self, code: int, body: bytes | dict, cache_control: str = "no-store") -> None:
            data = body if isinstance(body, bytes) else json.dumps(body).encode()
            self.send_response(code)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Cache-Control", cache_control)
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Access-Control-Allow-Origin", allow_origin)
            self.end_headers()
            if self.command != "HEAD":
                self.wfile.write(data)

        def do_OPTIONS(self):   # CORS preflight for the onboarding POSTs
            self.send_response(204)
            self.send_header("Access-Control-Allow-Origin", allow_origin)
            self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
            self.send_header("Access-Control-Allow-Headers", "Content-Type")
            self.send_header("Access-Control-Max-Age", "600")
            self.send_header("Content-Length", "0")
            self.end_headers()

        def do_GET(self):
            path = urlparse(self.path).path.rstrip("/")
            if path == "/api/health":
                self._send(200, {"ok": True, "engine": ENGINE_VERSION, "time": int(time.time() * 1000)})
            elif path == "/api/city":
                _, body = cache.get()
                self._send(200, body, "public, max-age=10")
            elif path == "/api/info":
                doc, _ = cache.get()
                self._send(200, app_info(raw, doc), "public, max-age=30")
            elif path == "/api/news":
                try:
                    self._send(200, b'{"pushedAt":%d,"stale":false,' % int(time.time() * 1000) + news.read_bytes()[1:], "public, max-age=30")
                except (OSError, AttributeError):
                    self._send(200, {"none": True})
            elif path in CONNECT_PATHS:
                self._not_enabled()
            else:
                self._send(404, {"error": "not found"})

        do_HEAD = do_GET

        def do_POST(self):
            n = int(self.headers.get("Content-Length") or 0)
            if n > MAX_BODY:
                self._send(413, {"error": "request too large"})
                return
            self.rfile.read(n)   # drain; nothing is stored
            if urlparse(self.path).path.rstrip("/") in CONNECT_PATHS:
                self._not_enabled()
            else:
                self._send(405 if urlparse(self.path).path.startswith("/api/") else 404, {"error": "method not allowed"})

        def _not_enabled(self):
            self._send(501, {"error": "Wallet onboarding is not enabled yet: the Smart Flow builder code is pending "
                                      "registration on Strike."})

    return Handler


def serve(city_toml: Path, host: str = "127.0.0.1", port: int = 8787, root: Path = Path("."),
          allow_origin: str = "*", news: Path | None = None) -> ThreadingHTTPServer:
    raw = tomllib.loads(city_toml.read_text(encoding="utf-8"))
    cache = CityCache(load_city(city_toml, root))
    srv = ThreadingHTTPServer((host, port), make_handler(cache, raw, allow_origin, news))
    srv.daemon_threads = True
    return srv

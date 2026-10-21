"""Pushes the public city snapshot to the Strike City site (Cloudflare Pages Functions, ``/api/internal/push``).

Outbound only: the agents' host opens no port. Each push is signed with HMAC-SHA256 over ``"{ms}.{body}"`` using
``SMARTFLOW_PUSH_SECRET`` (the same value is a Pages secret); the site rejects bad signatures and timestamps more than
2 minutes off. A snapshot is sent when it changes and at least every ``heartbeat`` seconds, so the site can tell a
live host from a dead one.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import time
import urllib.error
import urllib.request
from pathlib import Path

from .. import audit
from ..live.health import holds
from .city import build, load_city, load_live

UA = "smartflow-push/1.0"


def sign(secret: str, ts: str, body: bytes) -> str:
    return hmac.new(secret.encode(), ts.encode() + b"." + body, hashlib.sha256).hexdigest()


def encode(doc: dict) -> bytes:
    return json.dumps(doc, separators=(",", ":"), allow_nan=False).encode()


def post(url: str, secret: str, body: bytes, timeout: float = 20) -> tuple[int, str]:
    ts = str(int(time.time() * 1000))
    req = urllib.request.Request(url, data=body, method="POST", headers={
        "Content-Type": "application/json", "User-Agent": UA, "X-SF-Time": ts, "X-SF-Signature": sign(secret, ts, body)})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, r.read().decode()[:200]
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode(errors="replace")[:200]


def files_signature(agents) -> tuple:
    """What the city is built from: each agent's config, journal, state and account files (path, mtime, size)."""
    out = []
    for a in agents:
        for f in (a.config, a.run_dir / "journal.jsonl", a.run_dir / "state.json", a.run_dir / "account.json"):
            try:
                st = f.stat()
                out.append((str(f), st.st_mtime_ns, st.st_size))
            except OSError:
                out.append((str(f), 0, 0))
    return tuple(out)


class Anchors:
    """The head of every audit chain on this host (smartflow.audit), sent to the site's ``/api/internal/anchors``
    when it changes and at most once a minute: the site keeps each one, so the history here can be checked against
    a copy outside this host (a removed or rewritten line no longer matches what the site saw)."""

    EVERY_S = 60

    def __init__(self, push_url: str, secret: str, runs_root: Path, log=print):
        self.url = push_url.rsplit("/", 1)[0] + "/anchors"
        self.secret, self.root, self.log = secret, runs_root, log
        self.sent: dict[str, list] = {}
        self.at = 0.0

    def maybe_send(self) -> None:
        if time.time() - self.at < self.EVERY_S:
            return
        self.at = time.time()
        try:
            now = audit.heads(audit.files(self.root), self.root)
            changed = {k: v for k, v in now.items() if self.sent.get(k) != v}
            if not changed:
                return
            items = sorted(changed.items())
            for k in range(0, len(items), 200):   # the site takes up to 200 per request
                code, text = post(self.url, self.secret, encode({"heads": dict(items[k:k + 200])}))
                if code != 200:
                    self.log(f"anchors refused: HTTP {code} {text}")
                    return
            self.sent.update(changed)
        except Exception as e:   # the next minute tries again; the chains themselves are on disk
            self.log(f"anchors failed: {e!r}")


class News:
    """The News Tower's document (news.json, written by ``smartflow news``), sent to the site's ``/api/internal/news``
    when the file changes and at least every ``heartbeat`` seconds. A missing or unreadable file is skipped quietly:
    the city never waits for the news."""

    def __init__(self, push_url: str, secret: str, path: Path, heartbeat: float = 600, log=print):
        self.url = push_url.rsplit("/", 1)[0] + "/news"
        self.secret, self.path, self.heartbeat, self.log = secret, Path(path), heartbeat, log
        self.sent_mtime, self.at, self.retry_at = 0, 0.0, 0.0

    def maybe_send(self) -> None:
        now = time.time()
        if now < self.retry_at:
            return
        try:
            mtime = self.path.stat().st_mtime_ns
        except OSError:
            return
        if mtime == self.sent_mtime and now - self.at < self.heartbeat:
            return
        try:
            code, text = post(self.url, self.secret, self.path.read_bytes())
            if code == 200:
                self.sent_mtime, self.at = mtime, now
                return
            self.log(f"news refused: HTTP {code} {text}")
        except Exception as e:
            self.log(f"news push failed: {e!r}")
        self.retry_at = now + 60   # refused or failed: again in a minute, not every turn of the loop


def fingerprint(doc: dict) -> str:
    """What changes the city: everything except the build time."""
    return hashlib.sha256(encode({k: v for k, v in doc.items() if k != "generated"})).hexdigest()


def run(city_toml: Path, url: str, secret: str, every: float = 30, heartbeat: float = 600, log=print,
        live_env: str | None = None, runs_root: Path = Path("runs"), news: Path | None = None) -> None:
    """``live_env``: also the users' agents of that network's fleet (they come and go: re-read every turn).
    ``news``: also send the News Tower's news.json."""
    official = load_city(city_toml)
    last_fp, last_at, last_sig, built_at = "", 0.0, None, 0.0
    anchors = Anchors(url, secret, Path(runs_root), log)
    tower = News(url, secret, news, heartbeat, log) if news else None
    while True:
        anchors.maybe_send()
        if tower:
            tower.maybe_send()
        try:
            agents = official + (load_live(runs_root, live_env) if live_env else [])
            sig = files_signature(agents)
            if sig == last_sig and time.time() - built_at < 60 and time.time() - last_at <= heartbeat:
                time.sleep(every)   # nothing changed: no rebuild, no request
                continue
            last_sig, built_at = sig, time.time()
            doc = build(agents)
            doc["holds"] = holds(runs_root)   # strategies on a safety hold (live/health.py): the site tells their users
            fp = fingerprint(doc)
            if fp != last_fp or time.time() - last_at > heartbeat:
                code, text = post(url, secret, encode(doc))
                if code == 200:
                    log(f"pushed {len(doc['agents'])} agents ({'changed' if fp != last_fp else 'heartbeat'})")
                    last_fp, last_at = fp, time.time()
                else:
                    log(f"push refused: HTTP {code} {text}")
        except Exception as e:   # network hiccups must not stop the loop
            log(f"push failed: {e!r}")
        time.sleep(every)

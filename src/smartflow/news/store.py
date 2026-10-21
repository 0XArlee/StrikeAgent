"""The headlines kept on the host (sqlite, /var/lib/smartflow/news/news.db): each with what the model said (cls) and
the reaction measured on Strike (react), plus the hourly readings the scoreboard checks 4 h later.

A headline's time ``t`` is when the feed says it came out, unless that is in the future (then when it was first
seen): the reaction is measured from there.
"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from .feeds import Headline, norm

SCHEMA = """
CREATE TABLE IF NOT EXISTS items (
  id TEXT PRIMARY KEY, t INTEGER NOT NULL, seen INTEGER NOT NULL, title TEXT NOT NULL, url TEXT NOT NULL,
  source TEXT NOT NULL, feed TEXT NOT NULL, hint TEXT NOT NULL, cls TEXT, tries INTEGER NOT NULL DEFAULT 0, react TEXT,
  summary TEXT NOT NULL DEFAULT '', tier INTEGER NOT NULL DEFAULT 2, story TEXT);
CREATE INDEX IF NOT EXISTS items_t ON items (t);
CREATE TABLE IF NOT EXISTS readings (
  t INTEGER NOT NULL, market TEXT NOT NULL, net REAL NOT NULL, price REAL NOT NULL, ret4 REAL, PRIMARY KEY (t, market));
CREATE TABLE IF NOT EXISTS notes (market TEXT PRIMARY KEY, t INTEGER NOT NULL, body TEXT NOT NULL);
"""
VERSION = 2
KEEP_ITEMS_MS = 14 * 86400_000
KEEP_READINGS_MS = 365 * 86400_000
SAME_STORY = 0.8          # two titles sharing this share of their words (in a day) are the same story
FUTURE_SLACK_MS = 5 * 60_000


def _words(title: str) -> set[str]:
    return {w for w in norm(title).split() if len(w) > 2}


class Store:
    def __init__(self, path: Path | str):
        if str(path) != ":memory:":
            Path(path).parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(str(path))
        self.db.row_factory = sqlite3.Row
        self.db.executescript(SCHEMA)
        if self.db.execute("PRAGMA user_version").fetchone()[0] < VERSION:
            # 1: reactions on Strike's mark price (the first ones, on its last-trade price, are measured again)
            # 2: sources by tier, the feeds' summaries, stories, the calibrated model and reactions against the normal
            #    move: every headline is classified and measured again, the scoreboard starts over
            have = {r[1] for r in self.db.execute("PRAGMA table_info(items)")}
            for col, decl in (("summary", "TEXT NOT NULL DEFAULT ''"), ("tier", "INTEGER NOT NULL DEFAULT 2"), ("story", "TEXT")):
                if col not in have:
                    self.db.execute(f"ALTER TABLE items ADD COLUMN {col} {decl}")
            self.db.execute("UPDATE items SET react = NULL, cls = NULL, tries = 0, story = NULL")
            self.db.execute("DELETE FROM readings")
            self.db.execute("DELETE FROM notes")
            self.db.execute(f"PRAGMA user_version = {VERSION}")
            self.db.commit()
        self._recent: list[tuple[int, set[str]]] | None = None

    def close(self) -> None:
        self.db.close()

    # ------------------------------------------------------------------ headlines
    def add(self, items: list[Headline], now: int, keep_ms: int) -> int:
        """New headlines (already kept, too old or the same story under another title: left out). Returns how many."""
        if self._recent is None:
            rows = self.db.execute("SELECT t, title FROM items WHERE t >= ?", (now - 86400_000,)).fetchall()
            self._recent = [(r["t"], _words(r["title"])) for r in rows]
        added = 0
        for h in items:
            t = h.published if h.published is not None and h.published <= now + FUTURE_SLACK_MS else now
            t = min(t, now)
            if t < now - keep_ms:
                continue
            if self.db.execute("SELECT 1 FROM items WHERE id = ?", (h.id,)).fetchone():
                continue
            w = _words(h.title)
            if w and any(abs(t - t2) < 86400_000 and len(w & w2) / len(w | w2) >= SAME_STORY for t2, w2 in self._recent):
                continue
            self.db.execute("INSERT INTO items (id, t, seen, title, url, source, feed, hint, summary, tier) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                            (h.id, t, now, h.title, h.url, h.source, h.feed, json.dumps(h.markets), h.summary, h.tier))
            self._recent.append((t, w))
            added += 1
        self.db.commit()
        return added

    def unclassified(self, since: int, limit: int, max_tries: int = 6) -> list[sqlite3.Row]:
        return self.db.execute("SELECT * FROM items WHERE cls IS NULL AND tries < ? AND t >= ? ORDER BY t DESC LIMIT ?",
                               (max_tries, since, limit)).fetchall()

    def set_cls(self, ids: list[str], result: dict[str, dict]) -> None:
        for i in ids:
            if i in result:
                self.db.execute("UPDATE items SET cls = ?, story = ? WHERE id = ?", (json.dumps(result[i]), result[i].get("story"), i))
            else:   # the model left it out or the call failed: tried again later, at most a few times
                self.db.execute("UPDATE items SET tries = tries + 1 WHERE id = ?", (i,))
        self.db.commit()

    def retry_unclassified(self) -> None:
        self.db.execute("UPDATE items SET tries = 0 WHERE cls IS NULL")
        self.db.commit()

    def keep_outlets(self, feed: str, allow: list[str]) -> int:
        """A feed limited to some outlets: what came from others before the limit goes."""
        marks = ",".join("?" * len(allow))
        n = self.db.execute(f"DELETE FROM items WHERE feed = ? AND source NOT IN ({marks})", [feed, *allow]).rowcount
        self.db.commit()
        self._recent = None
        return n

    def sync_feeds(self, tiers: dict[str, int]) -> int:
        """Only the configured feeds stay (a dropped feed's headlines go), each headline with its feed's tier."""
        marks = ",".join("?" * len(tiers))
        gone = self.db.execute(f"DELETE FROM items WHERE feed NOT IN ({marks})", list(tiers)).rowcount if tiers else 0
        for feed, tier in tiers.items():
            self.db.execute("UPDATE items SET tier = ? WHERE feed = ? AND tier != ?", (tier, feed, tier))
        self.db.commit()
        self._recent = None
        return gone

    def recent_stories(self, since: int, limit: int = 80) -> list[tuple[str, str]]:
        """The stories of the last days (key, one of its titles), newest first: the model reuses a key for the same event."""
        rows = self.db.execute("SELECT story, MAX(t) AS t, MIN(title) AS title FROM items WHERE story IS NOT NULL AND t >= ? "
                               "GROUP BY story ORDER BY t DESC LIMIT ?", (since, limit)).fetchall()
        return [(r["story"], r["title"]) for r in rows]

    def unmeasured(self, since: int, now: int) -> list[sqlite3.Row]:
        """Headlines whose 1 h reaction is not measured yet (15 min or more old)."""
        rows = self.db.execute("SELECT * FROM items WHERE t >= ? AND t <= ? ORDER BY t", (since, now - 15 * 60_000)).fetchall()
        return [r for r in rows if r["react"] is None or not json.loads(r["react"]).get("done")]

    def set_react(self, id_: str, react: dict) -> None:
        self.db.execute("UPDATE items SET react = ? WHERE id = ?", (json.dumps(react), id_))

    def commit(self) -> None:
        self.db.commit()

    def window(self, since: int) -> list[dict]:
        """The headlines since ``since``, newest first, with what the model said and the reaction decoded."""
        out = []
        for r in self.db.execute("SELECT * FROM items WHERE t >= ? ORDER BY t DESC", (since,)).fetchall():
            d = dict(r)
            d["hint"] = json.loads(d["hint"])
            d["cls"] = json.loads(d["cls"]) if d["cls"] else None
            d["react"] = json.loads(d["react"]) if d["react"] else None
            out.append(d)
        return out

    def prune(self, now: int) -> None:
        self.db.execute("DELETE FROM items WHERE t < ?", (now - KEEP_ITEMS_MS,))
        self.db.execute("DELETE FROM readings WHERE t < ?", (now - KEEP_READINGS_MS,))
        self.db.commit()
        self._recent = None

    # ------------------------------------------------------------------ the scoreboard's readings
    def last_reading_t(self) -> int | None:
        r = self.db.execute("SELECT MAX(t) AS t FROM readings").fetchone()
        return r["t"] if r else None

    def add_reading(self, t: int, market: str, net: float, price: float) -> None:
        self.db.execute("INSERT OR IGNORE INTO readings (t, market, net, price) VALUES (?, ?, ?, ?)", (t, market, net, price))

    def open_readings(self, before: int) -> list[sqlite3.Row]:
        return self.db.execute("SELECT * FROM readings WHERE ret4 IS NULL AND t <= ? ORDER BY t", (before,)).fetchall()

    def resolve(self, t: int, market: str, ret4: float) -> None:
        self.db.execute("UPDATE readings SET ret4 = ? WHERE t = ? AND market = ?", (ret4, t, market))

    def readings(self, since: int) -> list[sqlite3.Row]:
        return self.db.execute("SELECT * FROM readings WHERE t >= ? AND ret4 IS NOT NULL ORDER BY t", (since,)).fetchall()

    # ------------------------------------------------------------------ the model's notes (what would flip a reading)
    def note(self, market: str) -> tuple[int, dict] | None:
        r = self.db.execute("SELECT t, body FROM notes WHERE market = ?", (market,)).fetchone()
        return (r["t"], json.loads(r["body"])) if r else None

    def set_note(self, market: str, t: int, body: dict) -> None:
        self.db.execute("INSERT INTO notes (market, t, body) VALUES (?, ?, ?) ON CONFLICT(market) DO UPDATE SET t = excluded.t, "
                        "body = excluded.body", (market, t, json.dumps(body)))
        self.db.commit()

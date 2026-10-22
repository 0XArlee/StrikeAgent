"""Strike's copy trading, kept on the host (sqlite, /var/lib/smartflow/copy/copy.db). Strike's API shows each trader's
last 30 days; this keeps every day it has seen, so the history keeps growing:

- ``traders``: the latest of every lead trader seen (Strike accounts and Hyperliquid wallets Strike lets you copy)
- ``daily``: one row per trader per day (account value, PnL, copy score, followers): its long history
- ``equity``: the trader's equity per day, merged from every 30-day curve Strike gave (never overwritten by a gap)
- ``subs``: every copy subscription of the public leaderboard, with how it went (active, stopped, liquidated)
- ``stats``: Strike's daily copy-trading totals (volume, new subscriptions, profits, allocated, open interest)
- ``positions`` and ``events``: the open positions of the leads the city shows, and what changed (open, close, flip)

Only public data; nothing about the agents or the site's users.
"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

SCHEMA = """
CREATE TABLE IF NOT EXISTS traders (
  address TEXT PRIMARY KEY, platform TEXT NOT NULL, chain TEXT, first_seen INTEGER NOT NULL, last_seen INTEGER NOT NULL,
  body TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS daily (
  address TEXT NOT NULL, day INTEGER NOT NULL, account_value REAL, pnl_all REAL, pnl_30d REAL, roi_30d REAL,
  volume_30d REAL, score INTEGER, followers INTEGER, PRIMARY KEY (address, day));
CREATE TABLE IF NOT EXISTS equity (address TEXT NOT NULL, day INTEGER NOT NULL, value REAL NOT NULL, PRIMARY KEY (address, day));
CREATE TABLE IF NOT EXISTS pnl (address TEXT NOT NULL, day INTEGER NOT NULL, value REAL NOT NULL, PRIMARY KEY (address, day));
CREATE TABLE IF NOT EXISTS subs (
  lead TEXT NOT NULL, follower TEXT NOT NULL, created_at INTEGER NOT NULL, platform TEXT, mode TEXT, copy_amount REAL,
  status TEXT, realized_pnl REAL, closed_pnl REAL, volume REAL, orders INTEGER, follower_count INTEGER,
  first_seen INTEGER NOT NULL, last_seen INTEGER NOT NULL, PRIMARY KEY (lead, follower, created_at));
CREATE TABLE IF NOT EXISTS stats (metric TEXT NOT NULL, day INTEGER NOT NULL, symbol TEXT NOT NULL, value REAL NOT NULL,
  PRIMARY KEY (metric, day, symbol));
CREATE TABLE IF NOT EXISTS positions (address TEXT PRIMARY KEY, t INTEGER NOT NULL, body TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS events (t INTEGER NOT NULL, address TEXT NOT NULL, market TEXT NOT NULL, kind TEXT NOT NULL,
  side TEXT, size REAL, price REAL);
CREATE INDEX IF NOT EXISTS events_t ON events (t);
CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT NOT NULL);
"""
DAY = 86_400_000
KEEP_EVENTS_MS = 30 * DAY


def num(v) -> float | None:
    try:
        return None if v is None or v == "" else float(v)
    except (TypeError, ValueError):
        return None


class Store:
    def __init__(self, path: Path | str):
        if str(path) != ":memory:":
            Path(path).parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(str(path))
        self.db.row_factory = sqlite3.Row
        self.db.executescript(SCHEMA)

    def close(self) -> None:
        self.db.close()

    def commit(self) -> None:
        self.db.commit()

    # ------------------------------------------------------------------ meta
    def get(self, key: str, default: str | None = None) -> str | None:
        r = self.db.execute("SELECT value FROM meta WHERE key = ?", (key,)).fetchone()
        return r["value"] if r else default

    def set(self, key: str, value: str) -> None:
        self.db.execute("INSERT INTO meta (key, value) VALUES (?, ?) ON CONFLICT(key) DO UPDATE SET value = excluded.value", (key, value))

    # ------------------------------------------------------------------ traders
    def add_traders(self, items: list[dict], now: int, followers: dict[str, int]) -> int:
        """The traders Strike's Discover listed now: their latest, their row of today, their equity days."""
        day = now // DAY * DAY
        for it in items:
            a = str(it.get("address") or "")
            if not a:
                continue
            body = json.dumps(it, separators=(",", ":"))
            self.db.execute(
                "INSERT INTO traders (address, platform, chain, first_seen, last_seen, body) VALUES (?, ?, ?, ?, ?, ?) "
                "ON CONFLICT(address) DO UPDATE SET platform = excluded.platform, chain = excluded.chain, last_seen = excluded.last_seen, "
                "body = excluded.body", (a, it.get("platform") or "", it.get("blockchain_address"), now, now, body))
            pnl, roi, vol = it.get("pnl") or {}, it.get("roi") or {}, it.get("volume") or {}
            score = num(it.get("copy_score"))
            self.db.execute(
                "INSERT INTO daily (address, day, account_value, pnl_all, pnl_30d, roi_30d, volume_30d, score, followers) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?) ON CONFLICT(address, day) DO UPDATE SET account_value = excluded.account_value, "
                "pnl_all = excluded.pnl_all, pnl_30d = excluded.pnl_30d, roi_30d = excluded.roi_30d, volume_30d = excluded.volume_30d, "
                "score = excluded.score, followers = excluded.followers",
                (a, day, num(it.get("account_value")), num(pnl.get("all")), num(pnl.get("30d")), num(roi.get("30d")),
                 num(vol.get("30d")), None if score is None else int(score), followers.get(a, 0)))
            for table, curve in (("equity", it.get("equity_curve_30d")), ("pnl", it.get("pnl_curve_30d"))):
                for t, v in curve or []:
                    val = num(v)
                    if val is None:
                        continue
                    d = int(t) // DAY * DAY
                    # a day's last value wins: the curve's point for a day is its closing value
                    self.db.execute(f"INSERT INTO {table} (address, day, value) VALUES (?, ?, ?) "
                                    "ON CONFLICT(address, day) DO UPDATE SET value = excluded.value", (a, d, val))
        return len(items)

    def trader(self, address: str) -> dict | None:
        r = self.db.execute("SELECT * FROM traders WHERE address = ?", (address,)).fetchone()
        return {**json.loads(r["body"]), "first_seen": r["first_seen"], "last_seen": r["last_seen"]} if r else None

    def traders(self, platform: str | None = None, since: int = 0) -> list[dict]:
        q = "SELECT * FROM traders WHERE last_seen >= ?" + (" AND platform = ?" if platform else "")
        rows = self.db.execute(q, (since, platform) if platform else (since,)).fetchall()
        return [{**json.loads(r["body"]), "first_seen": r["first_seen"], "last_seen": r["last_seen"]} for r in rows]

    def equity(self, address: str, limit: int = 365) -> list[tuple[int, float]]:
        rows = self.db.execute("SELECT day, value FROM equity WHERE address = ? ORDER BY day DESC LIMIT ?", (address, limit)).fetchall()
        return [(r["day"], r["value"]) for r in reversed(rows)]

    def pnl(self, address: str, limit: int = 365) -> list[tuple[int, float]]:
        rows = self.db.execute("SELECT day, value FROM pnl WHERE address = ? ORDER BY day DESC LIMIT ?", (address, limit)).fetchall()
        return [(r["day"], r["value"]) for r in reversed(rows)]

    def metrics(self, address: str) -> dict:
        """From every day kept (not just Strike's 30): the deepest fall of its cumulative PnL as a share of its equity at
        the peak, the share of days that ended up, and how many days that covers. Deposits and withdrawals move equity,
        not PnL, so the falls are measured on PnL."""
        pnl, eq = self.pnl(address), dict(self.equity(address))
        if len(pnl) < 2:
            return {"days": len(pnl), "dd": None, "upDays": None}
        peak, peak_eq, dd, ups = pnl[0][1], eq.get(pnl[0][0]), 0.0, 0
        for (d0, v0), (d, v) in zip(pnl, pnl[1:]):
            ups += v > v0
            if v > peak:
                peak, peak_eq = v, eq.get(d) or peak_eq
            elif peak_eq:
                dd = max(dd, (peak - v) / peak_eq)
        return {"days": len(pnl), "dd": round(dd, 4), "upDays": round(ups / (len(pnl) - 1), 3)}

    def copiers(self) -> dict[str, dict]:
        """Per lead, every copy kept: how many ended (or are) in profit."""
        out: dict[str, dict] = {}
        for r in self.db.execute("SELECT lead, COUNT(*) AS n, SUM(COALESCE(realized_pnl, 0) > 0) AS won FROM subs GROUP BY lead").fetchall():
            out[r["lead"]] = {"n": int(r["n"]), "won": int(r["won"] or 0)}
        return out

    def history_days(self) -> int:
        r = self.db.execute("SELECT MIN(day) AS a, MAX(day) AS b FROM equity").fetchone()
        return 0 if not r or r["a"] is None else int((r["b"] - r["a"]) // DAY) + 1

    # ------------------------------------------------------------------ subscriptions
    def add_subs(self, entries: list[dict], now: int) -> int:
        for e in entries:
            f = (e.get("follower") or {}).get("account_id") or (e.get("follower") or {}).get("address") or ""
            lead = str(e.get("lead_account_id") or "")
            if not f or not lead:
                continue
            self.db.execute(
                "INSERT INTO subs (lead, follower, created_at, platform, mode, copy_amount, status, realized_pnl, closed_pnl, volume, orders, "
                "follower_count, first_seen, last_seen) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?) "
                "ON CONFLICT(lead, follower, created_at) DO UPDATE SET status = excluded.status, realized_pnl = excluded.realized_pnl, "
                "closed_pnl = excluded.closed_pnl, volume = excluded.volume, orders = excluded.orders, follower_count = excluded.follower_count, "
                "copy_amount = excluded.copy_amount, last_seen = excluded.last_seen",
                (lead, f, int(e.get("created_at") or 0), e.get("platform"), e.get("copy_mode"), num(e.get("copy_amount")), e.get("status"),
                 num(e.get("realized_pnl")), num(e.get("closed_pnl")), num(e.get("total_volume")), int(e.get("filled_order_count") or 0),
                 int(e.get("follower_count") or 0), now, now))
        return len(entries)

    def subs(self, status: str | None = None) -> list[dict]:
        q = "SELECT * FROM subs" + (" WHERE status = ?" if status else "")
        return [dict(r) for r in self.db.execute(q, (status,) if status else ()).fetchall()]

    def followers(self) -> dict[str, dict]:
        """Per lead: active copiers, and what every copy of it (active or not) made and traded."""
        out: dict[str, dict] = {}
        for r in self.db.execute("SELECT lead, SUM(status = 'active') AS active, COUNT(*) AS ever, SUM(COALESCE(realized_pnl, 0)) AS pnl, "
                                 "SUM(COALESCE(volume, 0)) AS volume FROM subs GROUP BY lead").fetchall():
            out[r["lead"]] = {"active": int(r["active"] or 0), "ever": int(r["ever"]), "pnl": round(r["pnl"] or 0, 2),
                              "volume": round(r["volume"] or 0, 2)}
        return out

    # ------------------------------------------------------------------ Strike's totals
    def add_stats(self, metric: str, rows: list, value_index: int = 2) -> int:
        """Daily series as Strike gives them: [day_ms, symbol, value] (or [day_ms, value])."""
        n = 0
        for row in rows or []:
            try:
                day = int(row[0]) // DAY * DAY
                symbol = str(row[1]) if len(row) > 2 else "*"
                value = num(row[value_index if len(row) > 2 else 1])
            except (TypeError, ValueError, IndexError):
                continue
            if value is None:
                continue
            self.db.execute("INSERT INTO stats (metric, day, symbol, value) VALUES (?, ?, ?, ?) "
                            "ON CONFLICT(metric, day, symbol) DO UPDATE SET value = excluded.value", (metric, day, symbol, value))
            n += 1
        return n

    def daily_totals(self, metric: str, since: int) -> list[tuple[int, float]]:
        rows = self.db.execute("SELECT day, SUM(value) AS v FROM stats WHERE metric = ? AND day >= ? GROUP BY day ORDER BY day",
                               (metric, since)).fetchall()
        return [(r["day"], round(r["v"], 2)) for r in rows]

    # ------------------------------------------------------------------ positions and what changed
    def positions(self, address: str) -> list[dict] | None:
        r = self.db.execute("SELECT body FROM positions WHERE address = ?", (address,)).fetchone()
        return json.loads(r["body"]) if r else None

    def set_positions(self, address: str, positions: list[dict], now: int) -> list[dict]:
        """Keeps the lead's open positions and returns what changed since the last look (none on the first look)."""
        before = self.positions(address)
        self.db.execute("INSERT INTO positions (address, t, body) VALUES (?, ?, ?) ON CONFLICT(address) DO UPDATE SET t = excluded.t, "
                        "body = excluded.body", (address, now, json.dumps(positions, separators=(",", ":"))))
        if before is None:
            return []
        old = {p["market"]: p for p in before}
        new = {p["market"]: p for p in positions}
        ev = []
        for m, p in new.items():
            o = old.get(m)
            if not o:
                ev.append({"market": m, "kind": "open", "side": p["side"], "size": p["size"], "price": p.get("entry")})
            elif o["side"] != p["side"]:
                ev.append({"market": m, "kind": "flip", "side": p["side"], "size": p["size"], "price": p.get("entry")})
            elif o["size"] and abs(p["size"] - o["size"]) / o["size"] >= 0.2:
                ev.append({"market": m, "kind": "add" if p["size"] > o["size"] else "reduce", "side": p["side"], "size": p["size"],
                           "price": p.get("mark") or p.get("entry")})
        for m, o in old.items():
            if m not in new:
                ev.append({"market": m, "kind": "close", "side": o["side"], "size": o["size"], "price": o.get("mark")})
        for e in ev:
            self.db.execute("INSERT INTO events (t, address, market, kind, side, size, price) VALUES (?, ?, ?, ?, ?, ?, ?)",
                            (now, address, e["market"], e["kind"], e["side"], e["size"], e["price"]))
        self.db.execute("DELETE FROM events WHERE t < ?", (now - KEEP_EVENTS_MS,))
        return ev

    def events(self, address: str | None = None, limit: int = 40) -> list[dict]:
        q = "SELECT * FROM events" + (" WHERE address = ?" if address else "") + " ORDER BY t DESC LIMIT ?"
        return [dict(r) for r in self.db.execute(q, (address, limit) if address else (limit,)).fetchall()]

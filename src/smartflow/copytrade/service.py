"""Strike's copy trading for Strike City: who the leads are, who copies them and how it went, live.

Every few minutes it reads Strike's public copy-trading API (Discover, the subscriptions leaderboard, the daily
dashboard) and the open positions of the leads the city shows (Strike's public positions; a Hyperliquid lead's from
Hyperliquid's public API), keeps everything in ``store.py`` (so the history outlives Strike's 30-day window) and writes
``copy.json``, which the push services send to the site like the news. Outbound HTTPS only; public data only; it never
copies anyone and never touches the agents or a user's account.
"""

from __future__ import annotations

import json
import math
import os
import random
import time
from pathlib import Path

from ..net import HttpError, request_json
from .store import DAY, Store, num

STRIKE = "https://api.strikefinance.org"
HYPERLIQUID = "https://api.hyperliquid.xyz/info"
APP = "https://app.strikefinance.org"
DISCOVER_EVERY_MS = 10 * 60_000
STATS_EVERY_MS = 30 * 60_000
POSITIONS_EVERY_MS = 2 * 60_000
STRIKE_LEADS, HL_LEADS, MAX_LEADS = 14, 6, 24    # the leads that walk the city (and whose positions it follows)
PICK_STRIKE, PICK_HL = 60, 30                       # the traders the Copy Arena lets you choose from
EQUITY_POINTS = 365
# Strike City's score: each part 0-100, weighed; a part that cannot be known yet (fewer than 3 copiers, no fall measured,
# no account value) is left out and the others share its weight
SCORE_WEIGHTS = {"strike": 45, "copiers": 20, "fall": 15, "record": 10, "size": 10}
RECORD_DAYS = 60                                       # days of history kept for full marks on track record
STATS = {   # Strike's daily copy-trading series: (path, key in the answer, metric)
    "volume": ("/stat/v1/dashboard/copy-trading-volumes", "total_volume_daily"),
    "subscriptions": ("/stat/v1/dashboard/copy-trading-subscriptions", "daily_subscriptions"),
    "profits": ("/stat/v1/dashboard/copy-trading-profits", "daily_realized_pnl"),
    "liquidations": ("/stat/v1/dashboard/copy-trading-liquidations", None),
    "allocated": ("/stat/v1/dashboard/copy-trading-allocated", "total_allocated"),
    "open_interest": ("/stat/v1/dashboard/copy-trading-open-interest", None),
}


def _get(path: str, params: dict | None = None):
    _, doc, _ = request_json("GET", STRIKE + path, params=params, timeout=25, retries=2)
    return doc


def app_url(platform: str, address: str, chain: str | None) -> str:
    """The trader's public page in Strike's app, where Copy is one click away."""
    if platform == "hyperliquid":
        return f"{APP}/public-portfolio/{address}?platform=hyperliquid"
    return f"{APP}/public-portfolio/{chain or address}"


def recommended(coverage: list | None) -> float | None:
    """Strike's guidance: the smallest copy amount that would have reproduced >= 80 % of the lead's recent entries."""
    for c in coverage or []:
        if (num(c.get("coverage")) or 0) >= 0.8:
            return num(c.get("copy_amount"))
    return None


class CopyService:
    def __init__(self, store: Store, out: Path, get=None, hl=None, log=print):
        self.store, self.out, self.log = store, Path(out), log
        self.get = get or _get
        self.hl = hl or self._hl
        self.at = {"discover": 0, "stats": 0, "positions": 0}
        self.last_fp = ""
        self.summary: dict = {}

    @staticmethod
    def _hl(user: str) -> dict:
        _, doc, _ = request_json("POST", HYPERLIQUID, body=json.dumps({"type": "clearinghouseState", "user": user}).encode(),
                                 headers={"Content-Type": "application/json"}, timeout=20, retries=1, retry_non_idempotent=True)
        return doc or {}

    # ------------------------------------------------------------------ reading
    def discover(self, platform: str, pages: int) -> list[dict]:
        items, cursor = [], None
        for _ in range(pages):
            params = {"platform": platform, "sort": "copy_score", "order": "desc", "limit": 200}
            if cursor:
                params["cursor"] = cursor
            doc = self.get("/v2/copy/discover", params) or {}
            items += doc.get("items") or []
            cursor = doc.get("next_cursor")
            if not cursor:
                break
        return items

    def leads(self, now: int) -> list[dict]:
        """The leads the city shows: the best Strike traders to copy, the best Hyperliquid wallets Strike can copy, and
        every lead people copy most right now."""
        fol = self.store.followers()
        recent = now - 3 * DISCOVER_EVERY_MS
        strike = [t for t in self.store.traders("strike", recent) if t.get("recommended_direction") == "copy"]
        hl = [t for t in self.store.traders("hyperliquid", recent) if t.get("recommended_direction") == "copy"]
        key = lambda t: -(num(t.get("copy_score")) or 0)
        chosen = sorted(strike, key=key)[:STRIKE_LEADS] + sorted(hl, key=key)[:HL_LEADS]
        have = {t["address"] for t in chosen}
        known = {t["address"]: t for t in self.store.traders(None, recent)}
        popular = sorted((a for a, f in fol.items() if f["active"] and a in known and a not in have), key=lambda a: -fol[a]["active"])
        chosen += [known[a] for a in popular]
        return chosen[:MAX_LEADS]

    def positions_of(self, t: dict) -> list[dict]:
        if t.get("platform") == "hyperliquid":
            st = self.hl(t["address"])
            out = []
            for ap in st.get("assetPositions") or []:
                p = ap.get("position") or {}
                size = num(p.get("szi"))
                if not size:
                    continue
                out.append({"market": f"{p.get('coin')}-USD", "side": "long" if size > 0 else "short", "size": abs(size),
                            "entry": num(p.get("entryPx")), "upnl": num(p.get("unrealizedPnl")),
                            "leverage": num((p.get("leverage") or {}).get("value"))})
            return out
        doc = self.get("/v2/positions", {"account_id": t["address"]}) or {}
        out = []
        for p in doc.get("positions") or []:
            size = num(p.get("size"))
            if not size:
                continue
            out.append({"market": p.get("symbol"), "side": "long" if size > 0 else "short", "size": abs(size),
                        "entry": num(p.get("entry_price")), "upnl": num(p.get("upnl")), "leverage": num(p.get("leverage"))})
        return out

    # ------------------------------------------------------------------ one turn
    def cycle(self, now: int | None = None) -> dict:
        now = now or int(time.time() * 1000)
        s = {"traders": 0, "subs": 0, "stats": 0, "positions": 0, "events": 0, "errors": []}
        if now - self.at["discover"] >= DISCOVER_EVERY_MS:
            try:
                lb = []
                for status in ("active", "stopped", "liquidated"):
                    lb += (self.get("/v2/copy/leaderboard", {"status": status}) or {}).get("entries") or []
                s["subs"] = self.store.add_subs(lb, now)
                active = {}
                for e in lb:
                    if e.get("status") == "active":
                        active[e.get("lead_account_id")] = active.get(e.get("lead_account_id"), 0) + 1
                s["traders"] = self.store.add_traders(self.discover("strike", 2) + self.discover("hyperliquid", 1), now, active)
                self.at["discover"] = now
            except (HttpError, ValueError, TypeError) as e:
                s["errors"].append(f"discover: {e!s}"[:200])
        if now - self.at["stats"] >= STATS_EVERY_MS:
            try:
                summary = self.get("/stat/v1/dashboard/copy-trading-summary") or {}
                self.summary = {"open_interest": num(summary.get("open_interest_usd")), "allocated": num(summary.get("total_allocated_usd")),
                                "at": summary.get("updated_at")}
                for metric, (path, key) in STATS.items():
                    doc = self.get(path) or {}
                    rows = doc.get(key) if key else next((v for v in doc.values() if isinstance(v, list)), [])
                    s["stats"] += self.store.add_stats(metric, rows)
                self.store.set("summary", json.dumps(self.summary))
                self.at["stats"] = now
            except (HttpError, ValueError, TypeError) as e:
                s["errors"].append(f"stats: {e!s}"[:200])
        if now - self.at["positions"] >= POSITIONS_EVERY_MS:
            for t in self.leads(now):
                try:
                    ev = self.store.set_positions(t["address"], self.positions_of(t), now)
                    s["positions"] += 1
                    s["events"] += len(ev)
                except (HttpError, ValueError, TypeError) as e:
                    s["errors"].append(f"positions {t['address'][:10]}: {e!s}"[:200])
            self.at["positions"] = now
        self.store.commit()
        s["written"] = self.write(self.document(now))
        return s

    # ------------------------------------------------------------------ the document
    def candidates(self, now: int) -> list[dict]:
        """Everyone the Copy Arena lets you choose from: Strike's traders and the Hyperliquid wallets Strike can copy that
        Strike recommends copying, best first by Strike's copy score."""
        recent = now - 3 * DISCOVER_EVERY_MS
        key = lambda t: -(num(t.get("copy_score")) or 0)
        strike = sorted((t for t in self.store.traders("strike", recent) if t.get("recommended_direction") == "copy"), key=key)
        hl = sorted((t for t in self.store.traders("hyperliquid", recent) if t.get("recommended_direction") == "copy"), key=key)
        return strike[:PICK_STRIKE] + hl[:PICK_HL]

    @staticmethod
    def score_parts(score: float | None, copiers: dict, metrics: dict, value: float | None) -> dict[str, float | None]:
        """The parts of Strike City's score, each 0-100 (None: not known yet): Strike's copy score; the share of the
        people who copied the trader that ended in profit (once at least 3 did); how deep its PnL fell over every day
        kept (0 % -> 100, 25 % -> 50, 50 %+ -> 0); how long a record Strike City holds (RECORD_DAYS for full marks);
        and its account's size (1 k$ -> 0, 100 k$+ -> 100: tiny accounts often gamble)."""
        dd = metrics.get("dd")
        n = copiers.get("n", 0)
        return {
            "strike": score,
            "copiers": round(100.0 * copiers.get("won", 0) / n, 1) if n >= 3 else None,
            "fall": None if dd is None else round(max(0.0, 100.0 - 200.0 * dd), 1),
            "record": round(min(100.0, 100.0 * (metrics.get("days") or 0) / RECORD_DAYS), 1),
            "size": None if not value or value <= 0 else round(min(100.0, max(0.0, 50.0 * (math.log10(value) - 3))), 1),
        }

    @staticmethod
    def city_score(parts: dict[str, float | None]) -> float | None:
        """Strike City's score for choosing whom to copy (0-100): the weighed mean of the parts known."""
        if parts.get("strike") is None:
            return None
        known = {k: v for k, v in parts.items() if v is not None}
        weight = sum(SCORE_WEIGHTS[k] for k in known)
        return round(sum(SCORE_WEIGHTS[k] * v for k, v in known.items()) / weight, 1)

    def document(self, now: int) -> dict:
        fol, won = self.store.followers(), self.store.copiers()
        summary = self.summary or json.loads(self.store.get("summary", "{}") or "{}")
        walkers = self.leads(now)
        walking = {t["address"] for t in walkers}
        pool = self.candidates(now)
        have = {t["address"] for t in pool}
        pool += [t for t in walkers if t["address"] not in have]
        traders = []
        for t in pool:
            a, platform = t["address"], t.get("platform") or "strike"
            f = fol.get(a, {"active": 0, "ever": 0, "pnl": 0, "volume": 0})
            w = won.get(a, {"n": 0, "won": 0})
            m = self.store.metrics(a)
            score, value = num(t.get("copy_score")), num(t.get("account_value"))
            parts = self.score_parts(score, w, m, value)
            x = {
                "id": a, "platform": platform, "url": app_url(platform, a, t.get("blockchain_address")),
                "score": score, "scores": t.get("copy_scores") or {}, "direction": t.get("recommended_direction"),
                "city": self.city_score(parts), "parts": parts, "style": t.get("style"), "bias": t.get("bias"), "value": value,
                "pnl": {k: num(v) for k, v in (t.get("pnl") or {}).items()}, "roi": {k: num(v) for k, v in (t.get("roi") or {}).items()},
                "volume": {k: num(v) for k, v in (t.get("volume") or {}).items()},
                "assets": [y.get("asset") for y in t.get("top_assets") or []][:6], "recommended": recommended(t.get("copy_amount_coverage")),
                "copiers": {**f, "won": w["won"], "n": w["n"]}, "metrics": m,
                # its PnL, every day kept (deposits and withdrawals move its equity, not this)
                "curve": [[d, round(v, 2)] for d, v in self.store.pnl(a, EQUITY_POINTS if a in walking else 120)],
                "lastTrade": t.get("last_traded_at_ms"), "since": t.get("first_seen"), "walks": a in walking,
            }
            if a in walking:
                x["positions"] = self.store.positions(a) or []
                x["events"] = [{k: e[k] for k in ("t", "market", "kind", "side", "size", "price")} for e in self.store.events(a, 8)]
            traders.append(x)
        traders.sort(key=lambda y: -(y["city"] or 0))
        since30 = now - 30 * DAY
        totals = lambda m: self.store.daily_totals(m, now - 60 * DAY)
        subs = self.store.subs()
        best = sorted((y for y in subs if (y.get("realized_pnl") or 0) > 0), key=lambda y: -(y["realized_pnl"] or 0))[:12]
        return {
            "v": 1, "generated": now, "historyDays": self.store.history_days(),
            "strike": {"allocated": summary.get("allocated"), "openInterest": summary.get("open_interest"),
                       "volume30d": round(sum(v for d, v in totals("volume") if d >= since30), 2),
                       "subscriptions30d": int(sum(v for d, v in totals("subscriptions") if d >= since30)),
                       "profits30d": round(sum(v for d, v in totals("profits") if d >= since30), 2),
                       "daily": {"volume": totals("volume"), "subscriptions": totals("subscriptions"), "profits": totals("profits")}},
            "counts": {"traders": len(self.store.traders()), "active": sum(1 for y in subs if y["status"] == "active"), "subs": len(subs),
                       "inProfit": sum(1 for y in subs if (y.get("realized_pnl") or 0) > 0)},
            "traders": traders,
            "copiers": [{"lead": y["lead"], "follower": y["follower"][:8], "platform": y["platform"], "mode": y["mode"], "status": y["status"],
                         "pnl": round(y["realized_pnl"] or 0, 2), "volume": round(y["volume"] or 0, 2), "since": y["created_at"]} for y in best],
            "about": "Strike's public copy-trading data, kept by Strike City (the history goes beyond Strike's 30 days). "
                     "Past results do not predict future ones.",
        }

    def write(self, doc: dict) -> bool:
        fp = json.dumps({k: v for k, v in doc.items() if k != "generated"}, sort_keys=True)
        if fp == self.last_fp and self.out.exists():
            return False
        self.out.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.out.with_suffix(".tmp")
        tmp.write_text(json.dumps(doc, separators=(",", ":"), ensure_ascii=False), encoding="utf-8")
        os.replace(tmp, self.out)
        self.last_fp = fp
        return True

    def run(self, every: float = 60) -> None:
        while True:
            try:
                s = self.cycle()
                if s["traders"] or s["stats"] or s["events"] or s["errors"]:
                    self.log(f"copy: {s['traders']} traders, {s['subs']} subscriptions, {s['stats']} stat rows, "
                             f"{s['positions']} leads' positions, {s['events']} changes{', written' if s['written'] else ''}"
                             + (f"; errors: {s['errors'][:3]}" if s["errors"] else ""))
            except Exception as e:   # the next turn tries again
                self.log(f"copy cycle failed: {e!r}")
            time.sleep(every * (0.9 + 0.2 * random.random()))

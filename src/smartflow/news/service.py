"""The news service on the agents' host (``smartflow news``, deploy/smartflow-news.service): every 5 minutes it reads
the feeds, classifies what is new, measures the reactions on Strike, takes the hourly reading for the scoreboard and
writes ``news.json``, the public document the push loops send to the sites (api/push.py).

It runs on its own, with its own data: it never reads or touches the agents.
"""

from __future__ import annotations

import json
import os
import random
import time
from pathlib import Path

from ..backtest.event_study import EVENTS_FILE, load_events
from . import score
from .feeds import fetch, load_sources, parse
from .reaction import NORMAL_H, Prices, measure
from .store import Store

H = 3_600_000
MARKETS = ["BTC-USD", "ETH-USD", "SOL-USD", "XRP-USD", "BNB-USD", "ADA-USD", "NEAR-USD", "ZEC-USD"]
SHOWN_OTHER = 80            # besides every story that counts: the newest headlines that do not (recaps, unscored...)
CLASSIFY_PER_CYCLE = 300   # steady state: a few dozen a cycle; this lets a fresh start catch up in a few cycles
FLIP_EVERY_MS = H
READ_EVERY_MS = H           # the scoreboard's readings: on the hour
AHEAD_MS = 4 * H            # ... checked 4 h later
CALENDAR_WARN_DAYS = 60


def calendar(now: int, path: Path = EVENTS_FILE) -> dict:
    """The next scheduled releases (and one that just came out, for 2 h), from the official calendar."""
    doc = json.loads(Path(path).read_text(encoding="utf-8"))
    names = {k: v["name"] for k, v in doc["kinds"].items()}
    events = load_events(path, kinds=None)
    nxt = [{"t": t, "kind": k, "name": names[k]} for t, k in events if t > now][:6]
    just = [{"t": t, "kind": k, "name": names[k]} for t, k in events if now - 2 * H <= t <= now][-1:]
    ends = {k: max(t for t, kk in events if kk == k) for k in names if any(kk == k for _, kk in events)}
    short = sorted(k for k, t in ends.items() if t - now < CALENDAR_WARN_DAYS * 86400_000)
    last = min(ends.values()) if ends else 0
    return {"next": nxt, "just": just, "until": last, "short": short}


def strike_klines():
    """Strike's 1 m candles of the MARK price: its last-trade price stays flat most minutes (no trade in them: 84 % of
    BTC's minutes, 62-89 % of the others', measured 2026-10-21), which would read as "the market did not move"."""
    from ..strike.client import StrikeClient
    c = StrikeClient()
    return lambda market, end, limit: c.klines(market, "1m", end_ms=end, limit=limit, price_type="mark")


def as_of(headlines: list[dict], t: int) -> list[dict]:
    """The headlines as they were known at time t: none newer, and no 1 h reaction that ended after it (the
    scoreboard's readings must not see the hours they are checked against)."""
    out = []
    for h in headlines:
        if h["t"] > t:
            continue
        if h.get("react") and h["t"] + H > t:
            h = {**h, "react": {**h["react"], "r60": None, "z60": None}}
        out.append(h)
    return out


class NewsService:
    def __init__(self, store: Store, out: Path, classifier=None, klines=None, sources: dict | None = None,
                 fetcher=fetch, log=print, events_file: Path = EVENTS_FILE):
        self.store, self.out, self.classifier = store, Path(out), classifier
        self.klines = klines or strike_klines()
        self.sources = sources or load_sources()
        self.fetcher, self.log, self.events_file = fetcher, log, events_file
        self.feeds: dict[str, dict] = {f["id"]: {"id": f["id"], "name": f["name"], "tier": f.get("tier", 2), "ok": None, "at": None, "error": None}
                                       for f in self.sources["feeds"]}
        self.store.retry_unclassified()   # each start gives the headlines the model could not answer another chance
        gone = self.store.sync_feeds({f["id"]: int(f.get("tier", 2)) for f in self.sources["feeds"]})
        gone += sum(self.store.keep_outlets(f["id"], f["allow"]) for f in self.sources["feeds"] if f.get("allow"))
        if gone:
            self.log(f"news: {gone} headlines from feeds or outlets no longer configured removed")
        self.classify_error: str | None = None
        self.last_fp = ""
        self.warned_at = 0

    # ------------------------------------------------------------------ steps
    def ingest(self, now: int) -> int:
        keep = self.sources.get("keep_h", 72) * H
        added = 0
        for f in self.sources["feeds"]:
            st = self.feeds[f["id"]]
            try:
                items = parse(self.fetcher(f["url"]), f)
                added += self.store.add(items, now, keep)
                st.update(ok=True, at=now, error=None)
            except Exception as e:   # one feed down never stops the others
                st.update(ok=False, error=type(e).__name__)
                self.log(f"feed {f['id']}: {e!r}")
        return added

    def classify(self, now: int) -> int:
        if not self.classifier:
            return 0
        rows = self.store.unclassified(now - self.sources.get("keep_h", 72) * H, CLASSIFY_PER_CYCLE)
        if not rows:
            return 0
        items = [{"id": r["id"], "title": r["title"], "source": r["source"], "summary": r["summary"]} for r in rows]
        try:
            got = self.classifier.classify(items, self.store.recent_stories(now - 48 * H))
            errs = getattr(self.classifier, "errors", [])
            self.classify_error = errs[0].split(":")[0] if errs and not got else None
            for e in errs[:3]:
                self.log(f"classify: {e}")
        except Exception as e:
            got = {}
            self.classify_error = type(e).__name__
            self.log(f"classify: {e!r}")
        self.store.set_cls([i["id"] for i in items], got)
        return len(got)

    def react(self, now: int, prices: Prices) -> int:
        rows = self.store.unmeasured(now - self.sources.get("keep_h", 72) * H, now)
        done = 0
        for r in rows:
            cls = json.loads(r["cls"]) if r["cls"] else None
            hint = json.loads(r["hint"])
            m = ((cls or {}).get("markets") or hint or ["BTC-USD"])[0]   # the whole market: BTC
            if m not in MARKETS:
                continue
            try:
                prices.cover(m, r["t"] - (NORMAL_H * 60 + 15) * 60_000, now)   # and the day before: its normal move
            except Exception as e:
                self.log(f"strike klines {m}: {e!r}")
                continue
            self.store.set_react(r["id"], measure(prices, m, r["t"], now))
            done += 1
        self.store.commit()
        return done

    def readings(self, now: int, headlines: list[dict], prices: Prices) -> None:
        """On the hour: each market's NET and Strike price; 4 h later, how the price went."""
        hour = now // READ_EVERY_MS * READ_EVERY_MS
        if (self.store.last_reading_t() or 0) < hour:
            known = as_of(headlines, hour)
            for m in MARKETS:
                rd = score.reading(known, m, hour)
                if rd["net"] is None:
                    continue
                try:
                    prices.cover(m, hour - 15 * 60_000, now)
                except Exception as e:
                    self.log(f"strike klines {m}: {e!r}")
                    continue
                p = prices.at(m, hour)
                if p:
                    self.store.add_reading(hour, m, rd["net"], p)
        for r in self.store.open_readings(now - AHEAD_MS):
            try:
                prices.cover(r["market"], r["t"] - 15 * 60_000, now)
            except Exception as e:
                self.log(f"strike klines {r['market']}: {e!r}")
                continue
            p = prices.at(r["market"], r["t"] + AHEAD_MS)
            if p:
                self.store.resolve(r["t"], r["market"], round((p / r["price"] - 1) * 100, 3))
            elif now - r["t"] > 48 * H:
                self.store.resolve(r["t"], r["market"], 0.0)   # never measurable: counted as no move
        self.store.commit()

    def flips(self, now: int, groups: list[dict], readings: dict[str, dict], events: list[dict]) -> None:
        if not self.classifier:
            return
        for m in ("BTC-USD", "ETH-USD", "SOL-USD"):
            rd = readings.get(m)
            note = self.store.note(m)
            if not rd or rd["net"] is None or (note and now - note[0] < FLIP_EVERY_MS and note[1].get("label") == rd["label"]):
                continue
            drivers = [st["best"] for st in sorted((st for st in groups if score.about(st, m)),
                                                   key=lambda st: -score.weight(st, m, now) * abs(st["score"]))]
            try:
                got = self.classifier.flip(m, rd, drivers, events)
            except Exception as e:
                self.log(f"flip {m}: {e!r}")
                continue
            if got:
                self.store.set_note(m, now, {**got, "label": rd["label"]})

    # ------------------------------------------------------------------ the public document
    def document(self, now: int, headlines: list[dict], readings: dict[str, dict], cal: dict, groups: list[dict]) -> dict:
        by_id = {h["id"]: h for h in headlines}
        story_of = {i: g for g in groups for i in g["members"]}

        def view(h: dict) -> dict:
            c, r = h.get("cls"), h.get("react") or {}
            out = {"id": h["id"], "t": h["t"], "title": h["title"], "source": h["source"], "url": h["url"], "tier": h.get("tier", 2),
                   "markets": (c or {}).get("markets") or h["hint"], "r15": r.get("r15"), "r60": r.get("r60"),
                   "z15": r.get("z15"), "z60": r.get("z60"), "rm": r.get("m")}
            if score.scored(h):
                out.update(es=c["es"], broad=c["broad"], cat=c["cat"], score=c["score"], impact=c["impact"], conf=c["conf"],
                           catalyst=score.catalyst(h), region=c.get("region") or "global")
                g = story_of.get(h["id"])
                if g:   # a catalyst: its story, the other outlets that told it, and its weight now
                    m = (g["markets"] or ["BTC-USD"])[0]
                    others = [by_id[i]["source"] for i in g["members"] if i != h["id"] and i in by_id]
                    out.update(story=g["key"], sources=g["sources"], also=list(dict.fromkeys(o for o in others if o != h["source"]))[:4],
                               against=score.against(g), w=round(score.weight(g, m, now), 3))
            elif c:
                out.update(es=c.get("es", ""), skip=True)   # not market news (the model said so)
            return out

        # one entry per story (its best headline): every story the readings count is listed, so what a page lists
        # adds up to the reading; then the newest of what does not count; newest first
        shown, seen, others = [], set(), 0
        for h in headlines:
            g = story_of.get(h["id"])
            if g:
                if g["key"] in seen:
                    continue
                seen.add(g["key"])
                h = by_id[g["id"]]
            elif others >= SHOWN_OTHER:
                continue
            else:
                others += 1
            shown.append(h)

        notes = {m: n[1] for m in readings if (n := self.store.note(m)) and n[1].get("label") == readings[m]["label"]}
        board = score.scoreboard(self.store.readings(now - 90 * 86400_000))
        return {
            "v": 1, "generated": now,
            "classifier": {"on": bool(self.classifier), "model": getattr(self.classifier, "model", None), "error": self.classify_error},
            "markets": {m: {**rd, "flip": {k: v for k, v in notes[m].items() if k in ("en", "es")} if m in notes else None}
                        for m, rd in readings.items()},
            "following": score.following(headlines, now, groups),
            "headlines": [view(h) for h in shown],
            "counts": {"72h": len(headlines), "scored": sum(1 for h in headlines if score.scored(h)),
                       "catalysts": sum(len(g["members"]) for g in groups), "stories": len(groups)},
            "events": {"next": cal["next"], "just": cal["just"]},
            "scoreboard": board,
            "feeds": list(self.feeds.values()),
            "about": "Headlines from public feeds, classified by a model; reactions measured on Strike's price. "
                     "Information only: the agents do not use it to trade.",
        }

    def write(self, doc: dict) -> bool:
        """Writes news.json when something other than its time changed (atomically: the push loops read it)."""
        fp = json.dumps({k: v for k, v in doc.items() if k != "generated"}, sort_keys=True)
        if fp == self.last_fp and self.out.exists():
            return False
        self.out.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.out.with_suffix(".tmp")
        tmp.write_text(json.dumps(doc, separators=(",", ":"), ensure_ascii=False), encoding="utf-8")
        os.replace(tmp, self.out)
        self.last_fp = fp
        return True

    def cycle(self, now: int | None = None) -> dict:
        now = now or int(time.time() * 1000)
        added = self.ingest(now)
        classified = self.classify(now)
        prices = Prices(self.klines)
        measured = self.react(now, prices)
        keep = self.sources.get("keep_h", 72) * H
        headlines = self.store.window(now - keep)
        self.readings(now, headlines, prices)
        groups = score.stories(headlines)
        readings = {m: score.reading(headlines, m, now, groups) for m in MARKETS}
        cal = calendar(now, self.events_file)
        self.flips(now, groups, readings, cal["next"])
        if cal["short"] and now - self.warned_at > 24 * H:
            self.warned_at = now
            self.log(f"the macro calendar runs out soon for {', '.join(cal['short'])}: "
                     "add the next dates from the official schedules to config/macro_events.json")
        changed = self.write(self.document(now, headlines, readings, cal, groups))
        if now % (6 * H) < self.sources.get("every_s", 300) * 1000:
            self.store.prune(now)
        return {"added": added, "classified": classified, "measured": measured, "headlines": len(headlines), "written": changed,
                "tokens": list(getattr(self.classifier, "tokens", [0, 0]))}

    def run(self) -> None:
        every = self.sources.get("every_s", 300)
        while True:
            try:
                s = self.cycle()
                self.log(f"news: +{s['added']} headlines, {s['classified']} classified, {s['measured']} measured, "
                         f"{s['headlines']} in 72 h{', written' if s['written'] else ''}; model tokens since start "
                         f"{s['tokens'][0]} in / {s['tokens'][1]} out")
            except Exception as e:   # the next cycle tries again
                self.log(f"news cycle failed: {e!r}")
            time.sleep(every * (0.9 + 0.2 * random.random()))

"""The reading of each market from its news, as in the oil trader's panel the plan copies (docs/08), done the way a
desk would do it:

- Only catalysts count: price recaps, predictions, items the model calls irrelevant, the ones it is unsure about
  (confidence under 0.5) and the ones with no direction (|score| under 10) are shown but never move the reading (a
  recap of a rise "predicts" the rise it describes; a news item with no direction only dilutes the ones with one).
- One event, one vote: the headlines that tell the same story (the model's story key) count once, with the score of
  its best source; more independent sources confirm it (x1.25 each, up to x1.75).
- Sources by tier (config/news_sources.json): official and wires 1, serious crypto press 0.8, the rest 0.5.

    weight = impact (high 1, medium 0.6, low 0.3) x tier x confirmation x 0.5 ^ (age / 6 h)
             x 0.3 if Strike's price then went clearly the other way (at least half its normal hourly move against it)
    NET 72h = sum(weight x score) / sum(weight)
    NET = 0.6 x NET 72h + 0.4 x NET of the last 12 h of high impact (only NET 72h when there is none)

Whipsaw: high-impact stories both ways in the last 12 h with similar weight. Drivers: each category's share of the NET.
Stories about the whole market count for every market (in full for BTC, at half weight for the others), and a market
other than BTC needs a couple of its own stories to have a reading. Shown to people; none of it reaches the agents.
"""

from __future__ import annotations

BTC = "BTC-USD"
IMPACT = {"high": 1.0, "medium": 0.6, "low": 0.3}
TIER = {1: 1.0, 2: 0.8, 3: 0.5}
NOT_CATALYSTS = {"price", "other"}
MIN_CONF = 0.5
MIN_SCORE = 10           # under it, no direction: the scale's "no new information" band (classify.py)
CONFIRM, CONFIRM_MAX = 0.25, 1.75
HALF_LIFE_H = 6.0
REJECTED = 0.3
AGAINST_Z = 0.5          # "clearly against": half the market's normal 1 h move, the other way
WINDOW_H, HIGH_H = 72, 12
BLEND = 0.6
BROAD_ALT = 0.5
MIN_OWN = 2
LEVELS = (15, 50)        # |NET| from 15: bullish / bearish; from 50: very
WHIP_SCORE, WHIP_RATIO = 20, 0.5
FOLLOW_SCORE, FOLLOW_MIN = 20, 3
H = 3_600_000


def scored(h: dict) -> bool:
    c = h.get("cls")
    return bool(c) and c.get("relevant", True) and isinstance(c.get("score"), int) and c.get("impact") in IMPACT


def catalyst(h: dict) -> bool:
    c = h["cls"] if scored(h) else None
    return bool(c) and c["cat"] not in NOT_CATALYSTS and c.get("conf", 1) >= MIN_CONF and abs(c["score"]) >= MIN_SCORE


def stories(headlines: list[dict]) -> list[dict]:
    """The catalysts grouped by event: one entry per story with its best headline (best tier, then the first out),
    every outlet that told it, its markets and the time it first came out."""
    groups: dict[str, list[dict]] = {}
    for h in headlines:
        if catalyst(h):
            groups.setdefault(h["cls"].get("story") or h["id"], []).append(h)
    out = []
    for key, hs in groups.items():
        best = min(hs, key=lambda h: (h.get("tier", 2), h["t"]))
        c = best["cls"]
        out.append({
            "key": key, "id": best["id"], "best": best, "members": [h["id"] for h in hs],
            "t": min(h["t"] for h in hs), "tier": best.get("tier", 2), "sources": len({h["source"] for h in hs}),
            "score": c["score"], "impact": c["impact"], "cat": c["cat"],
            "markets": sorted({m for h in hs for m in h["cls"]["markets"]}), "broad": any(h["cls"].get("broad") for h in hs),
            "react": best.get("react"),
        })
    return out


def about(s: dict, market: str) -> bool:
    return market in s["markets"] or s["broad"]


def against(s: dict) -> bool | None:
    """Did the price go clearly against the story in the hour after it? None: not known yet, or a neutral story."""
    r = s.get("react") or {}
    z = r.get("z60")
    if z is None or s["score"] == 0:
        return None
    return (z > 0) != (s["score"] > 0) and abs(z) >= AGAINST_Z


def weight(s: dict, market: str, now: int) -> float:
    w = IMPACT[s["impact"]] * TIER.get(s["tier"], 0.5) * min(CONFIRM_MAX, 1 + CONFIRM * (s["sources"] - 1))
    w *= 0.5 ** (max(0, now - s["t"]) / H / HALF_LIFE_H)
    if against(s):
        w *= REJECTED
    if market != BTC and market not in s["markets"]:
        w *= BROAD_ALT
    return w


def _net(pairs: list[tuple[float, int]]) -> float | None:
    tw = sum(w for w, _ in pairs)
    return sum(w * s for w, s in pairs) / tw if tw > 0 else None


def label(net: float | None) -> str | None:
    if net is None:
        return None
    a = abs(net)
    side = "bullish" if net > 0 else "bearish"
    return "neutral" if a < LEVELS[0] else ("very_" + side if a >= LEVELS[1] else side)


def reading(headlines: list[dict], market: str, now: int, groups: list[dict] | None = None) -> dict:
    rel = [s for s in (groups if groups is not None else stories(headlines)) if about(s, market) and now - s["t"] <= WINDOW_H * H]
    own = sum(1 for s in rel if market in s["markets"])
    ws = [(weight(s, market, now), s) for s in rel]
    n72 = _net([(w, s["score"]) for w, s in ws])
    high = [(w, s) for w, s in ws if s["impact"] == "high" and now - s["t"] <= HIGH_H * H]
    nh = _net([(w, s["score"]) for w, s in high])
    enough = n72 is not None and (market == BTC or own >= MIN_OWN)
    net = (BLEND * n72 + (1 - BLEND) * nh if nh is not None else n72) if enough else None
    up = sum(w for w, s in high if s["score"] >= WHIP_SCORE)
    down = sum(w for w, s in high if s["score"] <= -WHIP_SCORE)
    total = sum(w for w, _ in ws)
    cats: dict[str, dict] = {}
    for w, s in ws:
        v = w * s["score"] / total if total else 0.0
        c = cats.setdefault(s["cat"], {"cat": s["cat"], "push": 0.0, "n": 0, "best": 0.0, "top": None})
        c["push"] += v
        c["n"] += 1
        if abs(v) > abs(c["best"]):
            c["best"], c["top"] = v, s["id"]
    row = lambda c: {"cat": c["cat"], "push": round(c["push"], 1), "n": c["n"], "top": c["top"]}
    return {
        "net": None if net is None else round(net, 1), "net72": None if n72 is None else round(n72, 1),
        "netHigh": None if nh is None else round(nh, 1), "label": label(net), "n": len(rel), "own": own,
        "whipsaw": up > 0 and down > 0 and min(up, down) / max(up, down) >= WHIP_RATIO,
        "upWeight": round(up, 2), "downWeight": round(down, 2),
        "drivers": {
            "up": [row(c) for c in sorted(cats.values(), key=lambda c: -c["push"]) if c["push"] > 0.5][:3],
            "down": [row(c) for c in sorted(cats.values(), key=lambda c: c["push"]) if c["push"] < -0.5][:3],
        },
        # every category's share of the reading and its stories (the tower's floors: each sums its own categories)
        "cats": {c["cat"]: {"push": round(c["push"], 1), "n": c["n"]} for c in cats.values()},
    }


def following(headlines: list[dict], now: int, groups: list[dict] | None = None) -> list[dict]:
    """Which themes the price is following: per category, the average 1 h move in the story's direction, in multiples
    of the market's normal 1 h move (positive: the market went the way those stories said). Stories with a clear
    direction and a measured reaction, and categories with a few of them."""
    by: dict[str, list[float]] = {}
    for s in groups if groups is not None else stories(headlines):
        if abs(s["score"]) < FOLLOW_SCORE or now - s["t"] > WINDOW_H * H:
            continue
        z = (s.get("react") or {}).get("z60")
        if z is None:
            continue
        by.setdefault(s["cat"], []).append(z if s["score"] > 0 else -z)
    out = [{"cat": k, "follow": round(sum(v) / len(v), 2), "n": len(v)} for k, v in by.items() if len(v) >= FOLLOW_MIN]
    return sorted(out, key=lambda x: -x["follow"])


def scoreboard(rows) -> dict:
    """Did the readings predict the next 4 h on Strike? Per market: readings with a side (|NET| >= 15), how many got
    the direction right, and how often the price simply went up (what always saying "up" would score)."""
    out: dict[str, dict] = {}
    for r in rows:
        s = out.setdefault(r["market"], {"readings": 0, "called": 0, "hits": 0, "up": 0})
        s["readings"] += 1
        s["up"] += r["ret4"] > 0
        if abs(r["net"]) >= LEVELS[0]:
            s["called"] += 1
            s["hits"] += (r["ret4"] > 0) == (r["net"] > 0) and r["ret4"] != 0
    return out

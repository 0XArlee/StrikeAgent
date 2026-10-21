"""The reading of each market from its scored headlines, as in the oil trader's panel the plan copies (docs/08):

    weight = impact (high 1, medium 0.6, low 0.3) x 0.5 ^ (age / 6 h) x (0.3 if Strike's price went against it in 1 h)
    NET 72h = sum(weight x score) / sum(weight)            score: -100..+100, what the model said
    NET = 0.6 x NET 72h + 0.4 x NET of the last 12 h of high impact (only NET 72h when there is none)

Whipsaw: high-impact headlines both ways in the last 12 h with similar weight (the smaller side at least half the
bigger). Drivers: each category's share of the NET, up and down. Headlines about the whole market count for every
market (in full for BTC, at half weight for the others), and a market other than BTC needs a couple of its own
headlines to have a reading. All of it is shown to people; none of it reaches the agents.
"""

from __future__ import annotations

BTC = "BTC-USD"
IMPACT = {"high": 1.0, "medium": 0.6, "low": 0.3}
HALF_LIFE_H = 6.0
REJECTED = 0.3
WINDOW_H, HIGH_H = 72, 12
BLEND = 0.6
BROAD_ALT = 0.5
FLAT = 0.05              # % in 1 h: smaller is no move in either direction (not a confirmation)
MIN_OWN = 2
LEVELS = (15, 50)        # |NET| from 15: bullish / bearish; from 50: very
WHIP_SCORE, WHIP_RATIO = 20, 0.5
FOLLOW_SCORE, FOLLOW_MIN = 20, 3
H = 3_600_000


def scored(h: dict) -> bool:
    c = h.get("cls")
    return bool(c) and c.get("relevant", True) and isinstance(c.get("score"), int) and c.get("impact") in IMPACT


def about(h: dict, market: str) -> bool:
    c = h["cls"]
    return market in c["markets"] or bool(c.get("broad"))


def rejected(h: dict) -> bool | None:
    """Did the price go against the headline in the hour after it? None: not known yet, or a neutral headline."""
    r = (h.get("react") or {}).get("r60")
    s = h["cls"]["score"]
    if r is None or s == 0:
        return None
    return not (abs(r) >= FLAT and (r > 0) == (s > 0))


def weight(h: dict, market: str, now: int) -> float:
    c = h["cls"]
    w = IMPACT[c["impact"]] * 0.5 ** (max(0, now - h["t"]) / H / HALF_LIFE_H)
    if rejected(h):
        w *= REJECTED
    if market != BTC and market not in c["markets"]:
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


def reading(headlines: list[dict], market: str, now: int) -> dict:
    rel = [h for h in headlines if scored(h) and about(h, market) and now - h["t"] <= WINDOW_H * H]
    own = sum(1 for h in rel if market in h["cls"]["markets"])
    ws = [(weight(h, market, now), h) for h in rel]
    n72 = _net([(w, h["cls"]["score"]) for w, h in ws])
    high = [(w, h) for w, h in ws if h["cls"]["impact"] == "high" and now - h["t"] <= HIGH_H * H]
    nh = _net([(w, h["cls"]["score"]) for w, h in high])
    enough = n72 is not None and (market == BTC or own >= MIN_OWN)
    net = (BLEND * n72 + (1 - BLEND) * nh if nh is not None else n72) if enough else None
    up = sum(w for w, h in high if h["cls"]["score"] >= WHIP_SCORE)
    down = sum(w for w, h in high if h["cls"]["score"] <= -WHIP_SCORE)
    total = sum(w for w, _ in ws)
    cats: dict[str, dict] = {}
    for w, h in ws:
        v = w * h["cls"]["score"] / total if total else 0.0
        c = cats.setdefault(h["cls"]["cat"], {"cat": h["cls"]["cat"], "push": 0.0, "n": 0, "best": 0.0, "top": None})
        c["push"] += v
        c["n"] += 1
        if abs(v) > abs(c["best"]):
            c["best"], c["top"] = v, h["id"]
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
    }


def following(headlines: list[dict], now: int) -> list[dict]:
    """Which themes the price is following: per category, the average 1 h move in the headline's direction, in %
    (positive: the market went the way those headlines said). Only headlines with a clear direction and a measured
    reaction, and categories with a few of them."""
    by: dict[str, list[float]] = {}
    for h in headlines:
        if not scored(h) or abs(h["cls"]["score"]) < FOLLOW_SCORE or now - h["t"] > WINDOW_H * H:
            continue
        r = (h.get("react") or {}).get("r60")
        if r is None:
            continue
        by.setdefault(h["cls"]["cat"], []).append(r if h["cls"]["score"] > 0 else -r)
    out = [{"cat": k, "follow": round(sum(v) / len(v), 3), "n": len(v)} for k, v in by.items() if len(v) >= FOLLOW_MIN]
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

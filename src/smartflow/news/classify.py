"""Each headline classified by Claude Haiku (Anthropic Messages API, forced tool call so the answer is structured):
the markets it is about, whether it moves the whole crypto market, a category, where in the world it happens (the
News Tower's map), a direction and strength (-100..+100) for the next hours, the impact, the model's confidence, and
the headline in Spanish for the site.

Only the headline, its outlet and the feed's short summary are sent, never anything about the agents or the users.
The prompt fixes the scale with anchors (the same kind of news, the same score) and asks for a story key, so one event
told by several outlets counts once (score.py). The key is
``ANTHROPIC_API_KEY`` (/etc/smartflow/news.env on the host, root:smartflow 0640). Without it the headlines are still
collected and their reaction measured; they just have no score.
"""

from __future__ import annotations

import json
import re

from ..net import HttpError, request_json

API = "https://api.anthropic.com/v1/messages"
MODEL = "claude-haiku-5-5"
MARKETS = {"BTC": "BTC-USD", "ETH": "ETH-USD", "SOL": "SOL-USD", "XRP": "XRP-USD", "BNB": "BNB-USD", "ADA": "ADA-USD",
           "NEAR": "NEAR-USD", "ZEC": "ZEC-USD"}
CATEGORIES = ["macro", "geopolitics", "regulation", "etf", "institutional", "exchange", "security", "legal", "tech", "flows",
              "price", "other"]
REGIONS = ["us", "canada", "latam", "uk", "europe", "russia", "ukraine", "middle_east", "africa", "india", "china", "japan",
           "korea", "southeast_asia", "oceania", "global"]
IMPACTS = ["high", "medium", "low"]
BATCH = 10
PER_ITEM_TOKENS = 320   # the answer per headline (with its story key and Spanish title): 25 at 220 were cut (2026-10-21)

SYSTEM = """You classify crypto news for a market dashboard read by traders. Each headline comes with its outlet and,
when the feed gives one, a short summary. For each headline decide:
- markets: the tickers it is specifically about, from BTC, ETH, SOL, XRP, BNB, ADA, NEAR, ZEC (empty if none of them).
- broad: true if it moves the whole crypto market (US macro data, the Fed, rates, the dollar, equities, a war or
  tariff shock, crypto-wide regulation, ETF flows in general, a major exchange failing), false otherwise.
- category: macro (Fed, rates, inflation, jobs, dollar, equities), geopolitics (wars and military conflicts,
  sanctions, tariffs and trade disputes, elections, political crises, government shutdowns, diplomacy), regulation
  (laws, regulators, government policy on crypto),
  etf (ETF filings, approvals, flows), institutional (companies, banks, funds buying, selling or adopting), exchange
  (exchanges, listings, outages, insolvency), security (hacks, exploits, scams), legal (lawsuits, courts, arrests),
  tech (upgrades, forks, network news), flows (whales, on-chain flows, liquidations, derivatives positioning), price
  (a recap of a move that already happened, or someone's price prediction), other.
- region: where the news happens or comes from: us, canada, latam, uk, europe, russia, ukraine, middle_east, africa,
  india, china, japan, korea, southeast_asia, oceania, or global (no single place: crypto-wide, online, worldwide).
- score: the likely effect of the NEWS on the price of those markets over the next few hours, -100 to +100. Use this
  scale and these anchors, so the same kind of news always gets the same score:
    0: no new information about supply, demand or risk: price recaps ("Bitcoin rises 3% as stocks rally": the move
       already happened), predictions ("analyst sees BTC at $150K"), explainers, opinion, routine updates.
    10 to 25: mild. A company buys $50M of BTC (+15), a minor listing, an upgrade date set (+10), a small hack under $10M
       (-15), a routine regulatory comment, a ceasefire agreed in a regional war (+15).
    30 to 55: meaningful. Notable ETF inflows or outflows, a corporate purchase over $500M, an exchange outage, a hack of
       $10M to $100M (-40), a major lawsuit against a large firm, US data clearly off the forecast (hot CPI: -45), new
       US tariffs on a major economy announced (-40), a military escalation that shakes markets (-45).
    60 to 80: strong. A Fed decision that surprises (an unexpected 50 bp cut: +60), regulators approving or blocking
       major products (SEC approves the first spot SOL ETFs: SOL +70), a hack over $100M or an exchange halting
       withdrawals (-65).
    85 to 100: exceptional and rare: a systemic failure (an FTX-size collapse: -90), a government buying bitcoin for
       its reserves (+90).
  Judge the news, not the headline's tone; for a story already priced in, score the remaining effect.
- impact: high (can move the market within hours: the 60+ kind), medium (the 30-55 kind), low (the rest).
- confidence: 0 to 1, how sure you are of the direction (below 0.5 when it could go either way).
- relevant: false for items that are not news about crypto markets or the macro that moves them (ads, sponsored or
  press-release pieces, guides, podcasts, unrelated stories).
- story: a short lowercase key for the EVENT, 3 to 6 words joined by hyphens (e.g. spacex-tesla-merger-btc-treasury).
  Headlines about the same event, worded differently or from different outlets, share the key; if one of the recent
  stories listed is the same event, reuse its key exactly.
- es: the headline translated to natural Spanish (Spain), same meaning, no additions.
Return every headline by its id."""

TOOL = {
    "name": "classify_headlines",
    "description": "Record the classification of every headline given.",
    "input_schema": {
        "type": "object",
        "properties": {"items": {"type": "array", "items": {
            "type": "object",
            "properties": {
                "id": {"type": "string"},
                "markets": {"type": "array", "items": {"type": "string", "enum": list(MARKETS)}},
                "broad": {"type": "boolean"},
                "category": {"type": "string", "enum": CATEGORIES},
                "region": {"type": "string", "enum": REGIONS},
                "score": {"type": "integer", "minimum": -100, "maximum": 100},
                "impact": {"type": "string", "enum": IMPACTS},
                "confidence": {"type": "number", "minimum": 0, "maximum": 1},
                "relevant": {"type": "boolean"},
                "story": {"type": "string"},
                "es": {"type": "string"},
            },
            "required": ["id", "markets", "broad", "category", "region", "score", "impact", "confidence", "relevant", "story", "es"],
        }}},
        "required": ["items"],
    },
}

FLIP_SYSTEM = """You write one line of a crypto news dashboard: given a market's current news reading and the
headlines driving it, name what kind of news would turn the reading the other way. Two short items at most, concrete
and plausible, each under 12 words, no advice, no predictions of price. Give them in English and in Spanish (Spain)."""

FLIP_TOOL = {
    "name": "flip",
    "description": "Record what would turn the reading around.",
    "input_schema": {"type": "object", "properties": {
        "en": {"type": "array", "items": {"type": "string"}, "maxItems": 2},
        "es": {"type": "array", "items": {"type": "string"}, "maxItems": 2},
    }, "required": ["en", "es"]},
}


def _clean(v: dict) -> dict | None:
    """The model's answer for one headline, checked (anything malformed: None, tried again later)."""
    try:
        score = int(v["score"])
        impact, cat = v["impact"], v["category"]
        if impact not in IMPACTS or cat not in CATEGORIES:
            return None
        return {
            "markets": [MARKETS[m] for m in dict.fromkeys(v.get("markets") or []) if m in MARKETS],
            "broad": bool(v.get("broad")), "cat": cat, "score": max(-100, min(100, score)), "impact": impact,
            "region": v.get("region") if v.get("region") in REGIONS else "global",   # only for the map: never worth a retry
            "conf": round(max(0.0, min(1.0, float(v.get("confidence", 0)))), 2), "relevant": bool(v.get("relevant", True)),
            "story": "-".join(re.findall(r"[a-z0-9]+", str(v.get("story") or "").lower()))[:60] or None,
            "es": str(v.get("es") or "")[:300],
        }
    except (KeyError, TypeError, ValueError):
        return None


class Haiku:
    def __init__(self, key: str, model: str = MODEL, post=None, timeout: float = 60):
        self.key, self.model, self.timeout = key, model, timeout
        self.post = post or self._post
        self.tokens = [0, 0]   # input, output: what it has cost so far (the service logs it every cycle)
        self.errors: list[str] = []   # what went wrong in the last classify call

    def _post(self, payload: dict) -> dict:
        _, doc, _ = request_json("POST", API, body=json.dumps(payload).encode(), timeout=self.timeout, retries=2,
                                 retry_non_idempotent=True,   # classifying twice changes nothing
                                 headers={"x-api-key": self.key, "anthropic-version": "2023-06-01",
                                          "content-type": "application/json"})
        return doc

    def _tool(self, system: str, tool: dict, text: str, max_tokens: int) -> dict:
        doc = self.post({"model": self.model, "max_tokens": max_tokens, "system": system, "tools": [tool],
                         "tool_choice": {"type": "tool", "name": tool["name"]},
                         "messages": [{"role": "user", "content": text}]})
        u = (doc or {}).get("usage") or {}
        self.tokens[0] += int(u.get("input_tokens") or 0)
        self.tokens[1] += int(u.get("output_tokens") or 0)
        if (doc or {}).get("stop_reason") == "max_tokens":   # the answer was cut: its last items are missing
            self.errors.append("cut at max_tokens")
        for block in (doc or {}).get("content", []):
            if block.get("type") == "tool_use" and block.get("name") == tool["name"]:
                return block.get("input") or {}
        raise ValueError(f"no {tool['name']} answer (stop: {(doc or {}).get('stop_reason')})")

    def classify(self, items: list[dict], stories: list[tuple[str, str]] = ()) -> dict[str, dict]:
        """{id: classification} for the headlines it answered well ({"id", "title", "source", "summary"} each).
        ``stories``: recent (key, title) pairs, so the same event keeps its key across batches and cycles. A batch
        that fails (or is cut) loses only its own headlines, tried again later; ``errors`` says what happened."""
        out: dict[str, dict] = {}
        self.errors = []
        known = ("Recent stories (key: one of its headlines):\n" + "\n".join(f"{k}: {t}" for k, t in list(stories)[:60]) + "\n\n"
                 if stories else "")
        for k in range(0, len(items), BATCH):
            todo = items[k:k + BATCH]
            # the model sometimes shortens a long list ("...": it answered 1 of 20, 2026-10-21): it is told how many to
            # return, and the ones it left out are asked again once
            for _ in range(2):
                text = known + f"Headlines ({len(todo)}, one JSON per line; return exactly {len(todo)} items, one for each, " \
                               "never shortened or with placeholders):\n" + "\n".join(
                    json.dumps({"id": i["id"], "title": i["title"], "source": i["source"],
                                **({"summary": i["summary"][:300]} if i.get("summary") else {})}, ensure_ascii=False) for i in todo)
                try:
                    got = self._tool(SYSTEM, TOOL, text, PER_ITEM_TOKENS * len(todo) + 400)
                except Exception as e:   # the other batches still count
                    self.errors.append(f"{type(e).__name__}: {str(e)[:120]}")
                    break
                ids = {i["id"] for i in todo}
                for v in got.get("items") or []:
                    c = _clean(v) if isinstance(v, dict) and v.get("id") in ids else None
                    if c:
                        out[v["id"]] = {**c, "model": self.model}
                todo = [i for i in todo if i["id"] not in out]
                if not todo:
                    break
            if todo:
                self.errors.append(f"left out {len(todo)} of a batch")
        return out

    def flip(self, market: str, reading: dict, headlines: list[dict], events: list[dict]) -> dict | None:
        """What would turn this market's reading around, in both languages (None if it did not answer well)."""
        lines = [f"Market: {market.split('-')[0]}. Reading: {reading['net']:+.0f} ({reading['label']}).",
                 "Headlines driving it (score, category, title):"]
        lines += [f"{h['cls']['score']:+d} {h['cls']['cat']}: {h['title']}" for h in headlines[:12]]
        if events:
            lines.append("Next scheduled releases: " + ", ".join(e["name"] for e in events[:3]))
        got = self._tool(FLIP_SYSTEM, FLIP_TOOL, "\n".join(lines), 300)
        en = [str(x)[:120] for x in got.get("en") or []][:2]
        es = [str(x)[:120] for x in got.get("es") or []][:2]
        return {"en": en, "es": es} if en and es else None


def from_env(env: dict) -> Haiku | None:
    key = (env.get("ANTHROPIC_API_KEY") or "").strip()
    return Haiku(key, env.get("SMARTFLOW_NEWS_MODEL") or MODEL) if key else None


__all__ = ["Haiku", "from_env", "HttpError", "MODEL", "REGIONS"]

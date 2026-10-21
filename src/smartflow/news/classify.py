"""Each headline classified by Claude Haiku (Anthropic Messages API, forced tool call so the answer is structured):
the markets it is about, whether it moves the whole crypto market, a category, a direction and strength (-100..+100)
for the next hours, the impact, the model's confidence, and the headline in Spanish for the site.

Only the headline and its source are sent, never anything about the agents or the users. The key is
``ANTHROPIC_API_KEY`` (/etc/smartflow/news.env on the host, root:smartflow 0640). Without it the headlines are still
collected and their reaction measured; they just have no score.
"""

from __future__ import annotations

import json

from ..net import HttpError, request_json

API = "https://api.anthropic.com/v1/messages"
MODEL = "claude-haiku-5-5"
MARKETS = {"BTC": "BTC-USD", "ETH": "ETH-USD", "SOL": "SOL-USD", "XRP": "XRP-USD", "BNB": "BNB-USD", "ADA": "ADA-USD",
           "NEAR": "NEAR-USD", "ZEC": "ZEC-USD"}
CATEGORIES = ["macro", "regulation", "etf", "institutional", "exchange", "security", "legal", "tech", "flows", "price", "other"]
IMPACTS = ["high", "medium", "low"]
BATCH = 25

SYSTEM = """You classify crypto news headlines for a market dashboard. For each headline decide:
- markets: the tickers it is specifically about, from BTC, ETH, SOL, XRP, BNB, ADA, NEAR, ZEC (empty if none of them).
- broad: true if it moves the whole crypto market (US macro data, the Fed, rates, the dollar, stocks, crypto-wide
  regulation, ETF flows in general, a major exchange failing), false otherwise.
- category: macro (Fed, rates, inflation, jobs, dollar, equities), regulation (laws, regulators, government policy),
  etf (ETF filings, approvals, flows), institutional (companies, banks, funds buying, selling or adopting), exchange
  (exchanges, listings, outages, insolvency), security (hacks, exploits, scams), legal (lawsuits, courts, arrests),
  tech (upgrades, forks, network news), flows (whales, on-chain flows, liquidations, derivatives positioning), price
  (a recap of a move that already happened, or an analyst's price prediction), other.
- score: the likely effect on the price of those markets over the next few hours, -100 (strongly bearish) to +100
  (strongly bullish), 0 if neutral or unclear. Price recaps and predictions describe the past or an opinion: score
  them near 0. Do not let the headline's tone alone decide: judge the news.
- impact: high (can move the market within hours: Fed decisions, major hacks, ETF approvals, big regulatory actions),
  medium, low (opinion, recaps, minor projects, promotional pieces).
- confidence: 0 to 1, how sure you are of the direction.
- relevant: false for headlines that are not news about crypto markets or the macro that moves them (ads, guides,
  podcasts, unrelated stories).
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
                "score": {"type": "integer", "minimum": -100, "maximum": 100},
                "impact": {"type": "string", "enum": IMPACTS},
                "confidence": {"type": "number", "minimum": 0, "maximum": 1},
                "relevant": {"type": "boolean"},
                "es": {"type": "string"},
            },
            "required": ["id", "markets", "broad", "category", "score", "impact", "confidence", "relevant", "es"],
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
            "conf": round(max(0.0, min(1.0, float(v.get("confidence", 0)))), 2), "relevant": bool(v.get("relevant", True)),
            "es": str(v.get("es") or "")[:300],
        }
    except (KeyError, TypeError, ValueError):
        return None


class Haiku:
    def __init__(self, key: str, model: str = MODEL, post=None, timeout: float = 60):
        self.key, self.model, self.timeout = key, model, timeout
        self.post = post or self._post
        self.tokens = [0, 0]   # input, output: what it has cost so far (the service logs it every cycle)

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
        for block in (doc or {}).get("content", []):
            if block.get("type") == "tool_use" and block.get("name") == tool["name"]:
                return block.get("input") or {}
        raise ValueError(f"no {tool['name']} answer (stop: {(doc or {}).get('stop_reason')})")

    def classify(self, items: list[dict]) -> dict[str, dict]:
        """{id: classification} for the headlines it answered well ({"id", "title", "source"} each)."""
        out: dict[str, dict] = {}
        for k in range(0, len(items), BATCH):
            part = items[k:k + BATCH]
            text = "Headlines (one JSON per line):\n" + "\n".join(
                json.dumps({"id": i["id"], "title": i["title"], "source": i["source"]}, ensure_ascii=False) for i in part)
            got = self._tool(SYSTEM, TOOL, text, 220 * len(part) + 200)
            ids = {i["id"] for i in part}
            for v in got.get("items") or []:
                c = _clean(v) if isinstance(v, dict) and v.get("id") in ids else None
                if c:
                    out[v["id"]] = {**c, "model": self.model}
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


__all__ = ["Haiku", "from_env", "HttpError", "MODEL"]

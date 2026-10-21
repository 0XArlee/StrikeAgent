"""Headlines from free public feeds (config/news_sources.json): crypto media RSS and Google News searches per market.

Only the headline, its source, link and time are kept, never the article (the media's rights); the feed's own short
summary is kept for the model only. The same title from two feeds is one headline: its id is the hash of the
normalised title (Google News appends " - Publisher"); the same event told by different outlets is grouped later, by
the model (its story key).
"""

from __future__ import annotations

import datetime as dt
import email.utils
import hashlib
import html
import json
import re
import urllib.request
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from pathlib import Path

SOURCES = Path(__file__).resolve().parents[3] / "config" / "news_sources.json"
UA = "Mozilla/5.0 (compatible; smartflow-news/1.0; +https://edgecraft-strikecity.pages.dev)"
MAX_BYTES = 4_000_000
ATOM = "{http://www.w3.org/2005/Atom}"


@dataclass
class Headline:
    id: str
    title: str
    url: str
    source: str            # the publisher (for Google News, the one it links to)
    feed: str              # the feed it came from (config id)
    published: int | None  # ms, as the feed says (None: it did not say)
    markets: list[str] = field(default_factory=list)   # what the feed or the title says it is about (before the model)
    summary: str = ""      # the feed's own summary: only for the model, never shown (the media's rights)
    tier: int = 2          # 1 official / wires, 2 serious crypto press, 3 the rest (config)


def load_sources(path: Path = SOURCES) -> dict:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def fetch(url: str, timeout: float = 20) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "application/rss+xml, application/xml, text/xml, */*"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        data = r.read(MAX_BYTES + 1)
    if len(data) > MAX_BYTES:
        raise ValueError(f"feed larger than {MAX_BYTES} bytes")
    return data


_TAGS = re.compile(r"<[^>]+>")
_SPACE = re.compile(r"\s+")


def clean(text: str | None) -> str:
    return _SPACE.sub(" ", _TAGS.sub(" ", html.unescape(text or ""))).strip()


def norm(title: str) -> str:
    """The comparable form of a title: lower case, letters and digits only."""
    return " ".join(re.findall(r"[a-z0-9]+", title.lower()))


def headline_id(title: str) -> str:
    return hashlib.sha1(norm(title).encode()).hexdigest()[:16]


# the market a title names, when the feed does not say (the model decides later; this only tags unclassified ones)
_NAMES = [
    ("BTC-USD", re.compile(r"\b(bitcoin|btc)\b", re.I)),
    ("ETH-USD", re.compile(r"\b(ethereum|ether|eth)\b", re.I)),
    ("SOL-USD", re.compile(r"\b[Ss]olana\b|\bSOL\b")),
    ("XRP-USD", re.compile(r"\b(xrp|ripple)\b", re.I)),
    ("BNB-USD", re.compile(r"\bBNB\b")),
    ("ADA-USD", re.compile(r"\b[Cc]ardano\b|\bADA\b")),
    ("NEAR-USD", re.compile(r"\bNEAR [Pp]rotocol\b|\bNEAR\b")),
    ("ZEC-USD", re.compile(r"\b(zcash|zec)\b", re.I)),
]


def title_markets(title: str) -> list[str]:
    return [m for m, rx in _NAMES if rx.search(title)]


def _time(text: str | None) -> int | None:
    if not text:
        return None
    try:
        d = email.utils.parsedate_to_datetime(text.strip())   # RSS: RFC 822
    except (TypeError, ValueError):
        try:
            d = dt.datetime.fromisoformat(text.strip().replace("Z", "+00:00"))   # Atom: RFC 3339
        except ValueError:
            return None
    if d.tzinfo is None:
        return None   # a time without a zone could be hours off: the first time it was seen is safer
    return int(d.timestamp() * 1000)


def parse(xml: bytes, feed: dict) -> list[Headline]:
    """RSS 2.0 items or Atom entries -> headlines (the ones without a title or an https link are left out)."""
    root = ET.fromstring(xml)
    out: list[Headline] = []
    entries = list(root.iter("item")) or list(root.iter(f"{ATOM}entry"))
    for e in entries:
        title = clean(e.findtext("title") or e.findtext(f"{ATOM}title"))
        link = (e.findtext("link") or "").strip()
        if not link:
            a = e.find(f"{ATOM}link")
            link = (a.get("href") if a is not None else "") or ""
        source = feed["name"]
        src = e.find("source")   # Google News: the publisher
        if src is not None and clean(src.text):
            source = clean(src.text)
            if title.endswith(f" - {source}"):
                title = title[: -len(source) - 3].rstrip()
        if not title or not link.startswith("https://") or len(link) > 2000:
            continue
        published = _time(e.findtext("pubDate") or e.findtext(f"{ATOM}published") or e.findtext(f"{ATOM}updated"))
        markets = list(dict.fromkeys(feed.get("markets", []) + title_markets(title)))
        summary = clean(e.findtext("description") or e.findtext(f"{ATOM}summary") or "")
        if summary.startswith(title) or summary.endswith(source) and len(summary) <= len(title) + len(source) + 3:
            summary = ""          # Google News: the summary is the title again
        out.append(Headline(headline_id(title), title[:300], link, source[:80], feed["id"], published, markets,
                            summary[:400], int(feed.get("tier", 2))))
    return out

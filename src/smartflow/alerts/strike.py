"""Strike Finance, watched for everyone: the moments worth a message, read from Strike's public API every minute.

Each alert is public (the city shows them on the building they concern and the bot sends them to whoever subscribed):
a market moving hard in an hour, funding at an extreme, a large position close to liquidation (Strike publishes every
live position with its liquidation price), a whale opening a position, a market crowded on one side, a new market or
one halted, and from the News Tower its security alarm, the big US releases and a market's reading turning extreme;
from the Copy Arena, a top copy trader opening a position. Every alert carries its text in English and Spanish.
"""

from __future__ import annotations

import json
import time
from collections import deque
from pathlib import Path

from ..net import HttpError, get_json

MAINNET = "https://api.strikefinance.org"
TESTNET = "https://api-v2-testnet.strikefinance.org"
HOUR = 3_600_000
KEEP = 60                       # alerts in the public document

STOCKS = {"AAOI", "COIN", "CRCL", "CXMT", "DRAM", "GOOGL", "MINIMAX", "MU", "NVDA", "SKHYNIX", "SNDK", "SPCX", "TSLA", "UNITREE", "ZHIPU"}
INDICES, METALS, OIL = {"NAS100", "SP500"}, {"XAU", "XAG"}, {"WTI"}
NAMES = {"XAU": "Gold", "XAG": "Silver", "WTI": "Oil (WTI)", "SP500": "S&P 500", "NAS100": "Nasdaq 100"}
TOWER = {"BTC": "btc", "ETH": "eth", "SOL": "sol", "XRP": "alts", "BNB": "alts", "ADA": "alts", "NEAR": "alts", "ZEC": "alts"}

# how far a market must move in an hour to be news: by how much it usually moves
def move_threshold(base: str) -> float:
    if base == "BTC":
        return 2.0
    if base in ("ETH", "SOL"):
        return 3.0
    if base in INDICES or base == "XAU":
        return 1.5
    if base in METALS or base in OIL:
        return 2.5
    if base in STOCKS:
        return 4.0
    return 5.0


FUNDING_EXTREME = 0.0003         # per hour (0.03 %/h, about 260 % a year)
NEAR_LIQ, LIQ_MIN_USD = 0.03, 50_000
WHALE_USD = 150_000
CROWD_SHARE, CROWD_MIN_N, CROWD_MIN_USD = 0.8, 12, 100_000   # every long has a short: a crowd is counted in positions
ALARM_CATS, ALARM_SCORE = ("security", "exchange"), -30
MACRO_KINDS = ("fomc", "cpi", "nfp", "pce", "gdp")
MACRO_NAMES = {"fomc": ("the Fed's rate decision", "la decisión de tipos de la Fed"), "cpi": ("US CPI (inflation)", "el IPC de EE. UU. (inflación)"),
               "nfp": ("US jobs (payrolls)", "el empleo de EE. UU. (nóminas)"), "pce": ("US PCE (inflation)", "el PCE de EE. UU. (inflación)"),
               "gdp": ("US GDP", "el PIB de EE. UU.")}
EXTREME_READINGS = ("very bullish", "very bearish")


def num(v) -> float | None:
    try:
        return None if v in (None, "") else float(v)
    except (TypeError, ValueError):
        return None


def base_of(symbol: str) -> str:
    return symbol.replace("-USD", "")


def label(symbol: str) -> str:
    b = base_of(symbol)
    return NAMES.get(b, b)


def place_of(symbol: str) -> str:
    return TOWER.get(base_of(symbol), "exchange")


def usd(v: float) -> str:
    v = abs(v)
    return f"{v / 1e6:.2f} M$" if v >= 1e6 else f"{v / 1e3:.0f}k $" if v >= 1e4 else f"{v:,.0f} $"


def price(v: float) -> str:
    return f"{v:,.0f}" if v >= 1000 else f"{v:,.2f}" if v >= 10 else f"{v:.4f}" if v >= 0.1 else f"{v:.6f}"


def pct(v: float, signed: bool = True) -> str:
    return f"{'+' if signed and v > 0 else '−' if v < 0 else ''}{abs(v):.1f}%"


class StrikePublic:
    """Strike's public reads (no keys), one network."""

    def __init__(self, base: str = MAINNET, http=get_json):
        self.base, self.http = base, http

    def get(self, path: str, params: dict | None = None, timeout: float = 15):
        return self.http(f"{self.base}{path}", params, timeout=timeout, retries=1)

    def tickers(self) -> dict[str, dict]:
        out = {}
        for t in self.get("/price/v2/ticker/24hr") or []:
            p = num(t.get("lastPrice"))
            if t.get("symbol") and p:
                out[t["symbol"]] = {"price": p, "change": num(t.get("priceChangePercent")) or 0.0, "volume": num(t.get("quoteVolume")) or 0.0}
        return out

    def markets(self) -> dict[str, dict]:
        doc = self.get("/v2/markets") or {}
        out = {}
        for s, m in (doc.get("markets") or {}).items():
            tiers = m.get("margin_tiers") or [{}]
            out[s] = {"status": m.get("status"), "name": m.get("name") or s, "leverage": tiers[0].get("max_leverage")}
        return out

    def funding(self) -> dict[str, float]:
        return {x["symbol"]: num(x.get("fundingRate")) or 0.0 for x in (self.get("/price/v2/premiumIndex") or []) if x.get("symbol")}

    def live_positions(self) -> list[dict]:
        return (self.get("/stat/v1/stats/live-positions", timeout=25) or {}).get("positions") or []

    def positions(self, account: str) -> list[dict]:
        return (self.get("/v2/positions", {"account_id": account}) or {}).get("positions") or []

    def account(self, account: str | None = None, address: str | None = None) -> dict:
        return self.get("/v2/account", {"account_id": account} if account else {"blockchain_address": address}) or {}


def position_view(p: dict, mark: float | None = None) -> dict | None:
    """A Strike position as the alerts see it: side, size, notional, mark, liquidation and its distance (None: none)."""
    size = num(p.get("size"))
    if not size:
        return None
    entry = num(p.get("entry_price")) or 0.0
    m = num(p.get("mark_price")) or mark
    if not m:
        upnl = num(p.get("upnl"))
        m = entry + (upnl / size if upnl is not None and size else 0.0)
    liq = num(p.get("liquidation_price")) or 0.0
    dist = abs(m - liq) / m if liq > 0 and m else None
    return {"id": p.get("id"), "account": p.get("account_id"), "symbol": p.get("symbol"), "side": "long" if size > 0 else "short",
            "size": abs(size), "entry": entry, "mark": m, "liq": liq or None, "dist": dist, "notional": abs(size) * (m or entry),
            "leverage": num(p.get("leverage"))}


def alert(kind: str, now: int, en: tuple[str, str], es: tuple[str, str], level: str = "info", market: str | None = None,
          place: str = "exchange", key: str = "", **data) -> dict:
    return {"id": f"{kind}:{key or market or ''}:{now}", "t": now, "kind": kind, "level": level, "market": market, "place": place,
            "title": {"en": en[0], "es": es[0]}, "body": {"en": en[1], "es": es[1]}, **({"data": data} if data else {})}


class StrikeWatch:
    """Reads Strike once a minute and keeps what it needs to tell a moment from noise (an hour of prices, which positions
    it already reported, which markets exist). ``tick`` returns the new alerts; ``doc`` is the public document."""

    def __init__(self, state_path: Path, strike: StrikePublic | None = None, news=lambda: None, copy=lambda: None, log=print):
        self.path, self.strike, self.news, self.copy, self.log = state_path, strike or StrikePublic(), news, copy, log
        self.prices: dict[str, deque] = {}
        self.last: dict = {}            # cooldowns and what was already said, by key: when
        self.moved: dict = {}           # each market's last reported hourly move (%)
        self.seen_pos: set = set()      # position ids already looked at (whales are new ones only)
        self.near: dict = {}            # positions reported close to liquidation: id -> distance then
        self.markets: dict | None = None
        self.readings: dict = {}
        self.arena: dict = {}           # top traders' open markets
        self.alerts: list[dict] = []
        self.tickers: dict = {}
        self.funding_now: dict = {}
        self.positions_now: list = []
        self._load()

    # ---------------------------------------------------------------- state
    def _load(self) -> None:
        try:
            d = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return
        self.last, self.markets, self.readings, self.arena = d.get("last") or {}, d.get("markets"), d.get("readings") or {}, d.get("arena") or {}
        self.alerts = d.get("alerts") or []
        self.near, self.moved = d.get("near") or {}, d.get("moved") or {}

    def save(self) -> None:
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(json.dumps({"last": self.last, "markets": self.markets, "readings": self.readings, "arena": self.arena,
                                   "alerts": self.alerts[-KEEP:], "near": self.near, "moved": self.moved}), encoding="utf-8")
        tmp.replace(self.path)

    def doc(self, now: int) -> dict:
        return {"v": 1, "generated": now, "alerts": self.alerts[-KEEP:][::-1]}

    def _cool(self, key: str, now: int, ms: int) -> bool:
        """True when `key` was said less than `ms` ago (and so must wait); otherwise records it now."""
        if now - self.last.get(key, 0) < ms:
            return True
        self.last[key] = now
        return False

    # ---------------------------------------------------------------- one minute
    def tick(self, now: int | None = None) -> list[dict]:
        now = now or int(time.time() * 1000)
        new: list[dict] = []
        for step in (self._moves, self._funding, self._positions, self._markets, self._news, self._arena):
            try:
                new += step(now)
            except (HttpError, OSError, ValueError, KeyError, TypeError) as e:   # one source down never stops the others
                self.log(f"strike watch: {step.__name__} failed: {str(e)[:160]}")
        self.alerts += new
        self.alerts = self.alerts[-KEEP:]
        self.last = {k: v for k, v in self.last.items() if now - v < 48 * HOUR}
        return new

    def _moves(self, now: int) -> list[dict]:
        self.tickers = self.strike.tickers()
        out = []
        for s, t in self.tickers.items():
            q = self.prices.setdefault(s, deque(maxlen=90))
            q.append((now, t["price"]))
            old = next((p for ts, p in q if now - ts <= HOUR + 90_000), None) if now - q[0][0] >= 50 * 60_000 else None
            if not old:
                continue
            ch = (t["price"] / old - 1) * 100
            thr = move_threshold(base_of(s))
            if abs(ch) < thr:
                continue
            # once per move: again only if it goes another threshold further, or two hours later
            key, prev = f"move:{s}", self.moved.get(s)
            if prev is not None and now - self.last.get(key, 0) < 2 * HOUR and abs(ch) < abs(prev) + thr:
                continue
            self.last[key], self.moved[s] = now, ch
            up, n = ch > 0, label(s)
            lvl = "alert" if abs(ch) >= 2 * thr else "warn"
            out.append(alert("move", now, (f"{n} {pct(ch)} in the last hour", f"{price(t['price'])} now on Strike · {pct(t['change'])} in 24 h. "
                                           + ("A sharp move up: shorts are being squeezed." if up else "A sharp move down: longs are under pressure.")),
                             (f"{n} {pct(ch)} en la última hora", f"{price(t['price'])} ahora en Strike · {pct(t['change'])} en 24 h. "
                              + ("Subida brusca: los cortos sufren." if up else "Caída brusca: los largos sufren.")),
                             lvl, s, place_of(s), change=round(ch, 2)))
        return out

    def _funding(self, now: int) -> list[dict]:
        self.funding_now = self.strike.funding()
        out = []
        for s, r in self.funding_now.items():
            if abs(r) < FUNDING_EXTREME or self._cool(f"funding:{s}:{r > 0}", now, 8 * HOUR):
                continue
            year = abs(r) * 24 * 365 * 100
            who_en, who_es = ("longs pay shorts", "los largos pagan a los cortos") if r > 0 else ("shorts pay longs", "los cortos pagan a los largos")
            out.append(alert("funding", now, (f"Extreme funding on {label(s)}", f"{who_en} {abs(r) * 100:.3f}% an hour (about {year:,.0f}% a year): "
                                              "holding that side costs a lot, and crowded trades tend to unwind."),
                             (f"Funding extremo en {label(s)}", f"{who_es} {abs(r) * 100:.3f}% por hora (unos {year:,.0f}% al año): "
                              "mantener ese lado sale caro y las posiciones abarrotadas suelen deshacerse."),
                             "warn", s, "cafe", rate=r))
        return out

    def _positions(self, now: int) -> list[dict]:
        raw = self.strike.live_positions()
        ps = [v for v in (position_view(p, (self.tickers.get(p.get("symbol")) or {}).get("price")) for p in raw) if v]
        self.positions_now = ps
        out, first = [], not self.seen_pos
        ids = set()
        for p in ps:
            pid = str(p["id"])
            ids.add(pid)
            n, side = label(p["symbol"]), p["side"].upper()
            # a whale: a new position this big (on the first reading, everything is already there)
            if not first and pid not in self.seen_pos and p["notional"] >= WHALE_USD:
                out.append(alert("whale", now, (f"Whale: {usd(p['notional'])} {side} {n}", f"A new {side.lower()} of {usd(p['notional'])} at "
                                                f"{price(p['entry'])}" + (f", {p['leverage']:.0f}x" if p["leverage"] else "") + " just opened on Strike."),
                                 (f"Ballena: {side} {n} de {usd(p['notional'])}", f"Se acaba de abrir en Strike un {side.lower()} de {usd(p['notional'])} a "
                                  f"{price(p['entry'])}" + (f", {p['leverage']:.0f}x" if p["leverage"] else "") + "."),
                                 "info", p["symbol"], place_of(p["symbol"]), key=pid, notional=round(p["notional"])))
            # close to liquidation: once when it comes within 3 %, again if it halves the distance
            d = p["dist"]
            if d is not None and d <= NEAR_LIQ and p["notional"] >= LIQ_MIN_USD:
                was = self.near.get(pid)
                if was is None or d <= was / 2:
                    self.near[pid] = d
                    out.append(alert("liquidation", now, (f"{usd(p['notional'])} {side} {n} {d * 100:.1f}% from liquidation",
                                                          f"Liquidation at {price(p['liq'])}, mark {price(p['mark'])}. A liquidation this size can "
                                                          "move the price further " + ("up." if p["side"] == "short" else "down.")),
                                     (f"{side} {n} de {usd(p['notional'])} a {d * 100:.1f}% de la liquidación",
                                      f"Liquidación a {price(p['liq'])}, mark {price(p['mark'])}. Una liquidación de este tamaño puede empujar "
                                      "el precio aún más " + ("arriba." if p["side"] == "short" else "abajo.")),
                                     "alert" if d <= 0.01 else "warn", p["symbol"], "alley", key=pid, notional=round(p["notional"])))
        # those that were close and are gone: closed or liquidated
        for pid in [k for k in self.near if k not in ids]:
            del self.near[pid]
        self.seen_pos = ids
        # one side crowding a market: open interest is the same on both sides, so the crowd is how many positions
        # are long against how many are short (as Strike Finance's hall shows it)
        by: dict[str, list[float]] = {}
        for p in ps:
            v = by.setdefault(p["symbol"], [0, 0, 0.0])
            v[0 if p["side"] == "long" else 1] += 1
            v[2] += p["notional"] if p["side"] == "long" else 0.0
        for s, (lo, sh, oi) in by.items():
            n = lo + sh
            if n < CROWD_MIN_N or oi < CROWD_MIN_USD:
                continue
            share, side = max(lo, sh) / n, "long" if lo >= sh else "short"
            if share < CROWD_SHARE or self._cool(f"crowd:{s}:{side}", now, 12 * HOUR):
                continue
            out.append(alert("crowd", now, (f"{label(s)}: {share * 100:.0f}% of positions are {side}",
                                            f"{max(lo, sh)} of {n} accounts on one side, {usd(oi)} open on Strike. A crowded side is fuel for a squeeze the other way."),
                             (f"{label(s)}: el {share * 100:.0f}% de las posiciones son {'largos' if side == 'long' else 'cortos'}",
                              f"{max(lo, sh)} de {n} cuentas en un lado, {usd(oi)} abiertos en Strike. Un lado abarrotado es combustible para un squeeze en contra."),
                             "info", s, place_of(s), share=round(share, 3)))
        return out

    def _markets(self, now: int) -> list[dict]:
        cur = self.strike.markets()
        out = []
        if self.markets is not None:
            for s, m in cur.items():
                before = self.markets.get(s)
                if before is None:
                    lev = f", up to {m['leverage']}x" if m.get("leverage") else ""
                    out.append(alert("listing", now, (f"New on Strike: {label(s)}", f"{m['name']} is now listed{lev}."),
                                     (f"Nuevo en Strike: {label(s)}", f"{m['name']} ya cotiza" + (f", hasta {m['leverage']}x" if m.get("leverage") else "") + "."),
                                     "info", s, "exchange"))
                elif before.get("status") != m.get("status") and m.get("status"):
                    trading = m["status"] == "trading"
                    out.append(alert("status", now, (f"{label(s)} is {'trading again' if trading else m['status'].replace('_', ' ')}",
                                                     "Strike changed this market's status." + ("" if trading else " New orders may be refused.")),
                                     (f"{label(s)}: {'vuelve a cotizar' if trading else m['status'].replace('_', ' ')}",
                                      "Strike cambió el estado de este mercado." + ("" if trading else " Puede rechazar órdenes nuevas.")),
                                     "info" if trading else "warn", s, "exchange"))
        self.markets = cur
        return out

    def _news(self, now: int) -> list[dict]:
        doc = self.news() or {}
        out = []
        for h in doc.get("headlines") or []:
            t = h.get("t") or 0
            if h.get("cat") in ALARM_CATS and h.get("catalyst") and (h.get("score") or 0) <= ALARM_SCORE and 0 <= now - t <= 24 * HOUR:
                title = str(h.get("title") or "")[:160]
                if self._cool(f"alarm:{title}", now, 48 * HOUR):
                    continue
                out.append(alert("security", now, ("Security alarm: " + title, "The News Tower scored it a security event "
                                                   f"({h.get('score')}). Copies run by agents pause while it lasts. Source: {h.get('source', '')}."),
                                 ("Alarma de seguridad: " + str(h.get("es") or title)[:160], "La News Tower lo puntuó como evento de seguridad "
                                  f"({h.get('score')}). Las copias de los agentes se pausan mientras dure. Fuente: {h.get('source', '')}."),
                                 "alert", None, "news", key=str(t)))
        for e in (doc.get("events") or {}).get("next") or []:
            t, k = e.get("t") or 0, e.get("kind")
            if k in MACRO_KINDS and 0 < t - now <= 30 * 60_000 and not self._cool(f"macro:{k}:{t}", now, 2 * HOUR):
                en, es = MACRO_NAMES[k]
                mins = max(1, round((t - now) / 60_000))
                out.append(alert("macro", now, (f"{en[0].upper() + en[1:]} in {mins} min", "Big US releases move every market fast. Copies with "
                                                "the macro pause wait from 30 minutes before to an hour after."),
                                 (f"{es[0].upper() + es[1:]} en {mins} min", "Los grandes datos de EE. UU. mueven todos los mercados rápido. Las copias "
                                  "con la pausa macro esperan de 30 minutos antes a una hora después."),
                                 "warn", None, "news", key=f"{k}{t}"))
        for m, r in (doc.get("markets") or {}).items():
            lab = (r or {}).get("label")
            before, self.readings[m] = self.readings.get(m), lab
            if before is not None and lab != before and lab in EXTREME_READINGS and not self._cool(f"reading:{m}:{lab}", now, 12 * HOUR):
                bull = lab == "very bullish"
                out.append(alert("reading", now, (f"News on {label(m)} turned {lab}", f"The News Tower's reading of {label(m)} moved from {before} to {lab}."),
                                 (f"Las noticias de {label(m)} pasan a {'muy alcistas' if bull else 'muy bajistas'}",
                                  f"La lectura de la News Tower sobre {label(m)} pasó de {before} a {lab}."), "info", m, "news"))
        return out

    def _arena(self, now: int) -> list[dict]:
        doc = self.copy() or {}
        tops = sorted((t for t in doc.get("traders") or [] if t.get("city") is not None), key=lambda t: -t["city"])[:5]
        out = []
        for rank, t in enumerate(tops, 1):
            mk = {p["market"]: p for p in t.get("positions") or []}
            before = self.arena.get(t["id"])
            self.arena[t["id"]] = sorted(mk)
            if before is None:
                continue
            for m in sorted(set(mk) - set(before)):
                p = mk[m]
                notional = (p.get("size") or 0) * (p.get("entry") or 0)
                if notional < 5_000 or self._cool(f"arena:{t['id']}:{m}", now, 6 * HOUR):
                    continue
                name, side = t.get("name") or (t["id"][:6] + "…" + t["id"][-4:]), p["side"].upper()
                out.append(alert("arena", now, (f"Top copy trader #{rank} opened {side} {label(m)}", f"{name} (Strike City score {t['city']:.0f}) "
                                                f"opened {usd(notional)}. Its copiers follow it now."),
                                 (f"El trader #{rank} de la Copy Arena abrió {side} {label(m)}", f"{name} (puntuación Strike City {t['city']:.0f}) "
                                  f"abrió {usd(notional)}. Sus copiadores lo siguen ahora."), "info", m, "arena", key=t["id"]))
        return out

    # ---------------------------------------------------------------- the moment, for /strike
    def snapshot(self) -> dict:
        tk = self.tickers
        movers = sorted((s for s in tk if tk[s]["volume"] > 0), key=lambda s: -abs(tk[s]["change"]))[:3]
        fund = sorted(self.funding_now.items(), key=lambda kv: -abs(kv[1]))[:1]
        near = sorted((p for p in self.positions_now if p["dist"] is not None and p["notional"] >= LIQ_MIN_USD), key=lambda p: p["dist"])[:1]
        oi = sum(p["notional"] for p in self.positions_now if p["side"] == "long")
        n_long = sum(1 for p in self.positions_now if p["side"] == "long")
        return {"majors": {s: tk[s] for s in ("BTC-USD", "ETH-USD", "SOL-USD") if s in tk}, "movers": [(s, tk[s]["change"]) for s in movers],
                "funding": fund, "near": near, "oi": oi, "long_share": n_long / len(self.positions_now) if self.positions_now else None,
                "volume": sum(t["volume"] for t in tk.values())}

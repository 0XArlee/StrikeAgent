"""The documentation's diagrams, drawn as SVG in the project's own colours (docs/images/diagram-*.svg).

    python web/scripts/build_diagrams.py

Each diagram is 900 px wide so its text stays readable in the README and printed in the project book. Boxes carry a
data-box attribute, which lets a browser check that no text spills out of its box.
"""

from html import escape
from pathlib import Path

OUT = Path(__file__).resolve().parents[2] / "docs" / "images"

SANS = "'Plex Sans','IBM Plex Sans','Segoe UI',Helvetica,Arial,sans-serif"
MONO = "'Plex Mono','IBM Plex Mono',Consolas,Menlo,monospace"
BG, PANEL, BOX, LINE = "#0b0d0c", "#121614", "#171c19", "#2a3530"
TEXT, MUTED, FAINT, CODE = "#e8ecea", "#a3aca7", "#7e8883", "#cfe9dd"
MINT, MINT_DIM, STRIKE = "#4efab0", "#2a8f66", "#0f2a1f"
GOLD, ROSE, SKY = "#f8931a", "#f472b6", "#60a5fa"
HEADS = {"mint": MINT, "faint": FAINT, "gold": GOLD, "rose": ROSE, "sky": SKY}


class Svg:
    def __init__(self, w: int, h: int, label: str):
        self.w, self.h, self.label, self.parts = w, h, label, []

    def add(self, s: str):
        self.parts.append(s)

    def rect(self, x, y, w, h, fill=BOX, stroke=LINE, rx=10, sw=1, dash=None, box=False):
        d = f' stroke-dasharray="{dash}"' if dash else ""
        b = ' data-box="1"' if box else ""
        self.add(f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="{rx}" fill="{fill}" stroke="{stroke}" stroke-width="{sw}"{d}{b}/>')

    def text(self, x, y, s, size=11, fill=MUTED, weight=400, anchor="start", mono=False, halo=False):
        fam = MONO if mono else SANS
        h = f' stroke="{BG}" stroke-width="4" paint-order="stroke" stroke-linejoin="round"' if halo else ""
        a = f' text-anchor="{anchor}"' if anchor != "start" else ""
        self.add(f'<text x="{x}" y="{y}" font-family="{fam}" font-size="{size}" font-weight="{weight}" fill="{fill}"{a}{h}>{escape(s)}</text>')

    def box(self, x, y, w, h, title, lines=(), color=TEXT, fill=BOX, stroke=LINE, size=11, title_size=12.5, lh=15, mono_lines=False, center=False):
        """A box with a title and lines under it, grouped so a browser can check the text fits."""
        self.add('<g data-group="1">')
        self.rect(x, y, w, h, fill=fill, stroke=stroke, rx=8, box=True)
        tx, anchor = (x + w / 2, "middle") if center else (x + 12, "start")
        self.text(tx, y + 21 if h >= 34 else y + h / 2 + 4, title, size=title_size, fill=color, weight=600, anchor=anchor)
        for i, s in enumerate(lines):
            self.text(tx, y + 21 + 17 + i * lh, s, size=size, fill=CODE if mono_lines else MUTED, mono=mono_lines, anchor=anchor)
        self.add("</g>")

    def arrow(self, d, color="mint", dash=False, both=False, sw=1.4):
        c = HEADS[color]
        ds = ' stroke-dasharray="5 4"' if dash else ""
        st = f' marker-start="url(#s-{color})"' if both else ""
        self.add(f'<path d="{d}" fill="none" stroke="{c}" stroke-width="{sw}"{ds} marker-end="url(#h-{color})"{st}/>')

    def num(self, x, y, n, color=MINT):
        self.add(f'<circle cx="{x}" cy="{y}" r="9" fill="{BG}" stroke="{color}" stroke-width="1.3"/>')
        self.text(x, y + 3.6, str(n), size=10, fill=color, weight=600, anchor="middle", mono=True)

    def legend(self, x, y, items):
        for label, color, dash in items:
            self.arrow(f"M{x},{y} H{x + 34}", color=color, dash=dash)
            self.text(x + 42, y + 4, label, size=10.5, fill=FAINT)
            x += 52 + len(label) * 6

    def save(self, name: str):
        defs = "".join(
            f'<marker id="h-{k}" markerWidth="9" markerHeight="9" refX="8" refY="4.5" orient="auto" markerUnits="userSpaceOnUse">'
            f'<path d="M0,0 L9,4.5 L0,9 z" fill="{c}"/></marker>'
            f'<marker id="s-{k}" markerWidth="9" markerHeight="9" refX="1" refY="4.5" orient="auto" markerUnits="userSpaceOnUse">'
            f'<path d="M9,0 L0,4.5 L9,9 z" fill="{c}"/></marker>' for k, c in HEADS.items())
        svg = (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {self.w} {self.h}" width="{self.w}" height="{self.h}" '
               f'role="img" aria-label="{escape(self.label)}">\n<title>{escape(self.label)}</title>\n<defs>{defs}</defs>\n'
               f'<rect width="{self.w}" height="{self.h}" rx="16" fill="{BG}"/>\n' + "\n".join(self.parts) + "\n</svg>\n")
        (OUT / f"diagram-{name}.svg").write_text(svg, encoding="utf-8")


def panel(s: Svg, x, y, w, h, title, sub, color=TEXT, fill=PANEL, stroke=LINE):
    s.rect(x, y, w, h, fill=fill, stroke=stroke, rx=12)
    s.text(x + 18, y + 26, title, size=15, fill=color, weight=700)
    s.text(x + 18, y + 44, sub, size=11, fill=FAINT)


# ------------------------------------------------------------------ 1. the system
def architecture():
    s = Svg(900, 676, "How EdgeCraft-StrikeCity is built: the browser, Cloudflare, the agents' host and Strike")
    panel(s, 20, 20, 600, 128, "Browser", "React + Vite · English and Spanish · desktop and phone")
    s.text(602, 46, "CIP-30 wallet signs", size=11, fill=MINT, anchor="end")
    for i, (t, l) in enumerate([("Landing", "strategy catalogue"), ("Onboarding", "one signature"), ("My agent", "plans, settings"),
                                ("The city", "own canvas engine")]):
        s.box(38 + i * 143, 78, 135, 54, t, [l])

    panel(s, 20, 196, 600, 150, "Cloudflare", "Pages · Functions · D1 (SQLite)")
    for i, (t, ls) in enumerate([("Public API", ["city · copy · news", "edge-cached 15-30 s", "open JSON"]),
                                 ("Owner API", ["CIP-30 sign-in", "signed actions", "builder connect"]),
                                 ("Host API · HMAC", ["snapshots in", "plans and keys out", "chain anchors"]),
                                 ("D1 database", ["users, public keys", "copy plans", "audit (append-only)"])]):
        s.box(38 + i * 143, 244, 135, 88, t, ls)

    panel(s, 20, 394, 600, 226, "Agents' host", "Linux container · Python 3.13 · hardened systemd units · outbound only", fill=STRIKE, stroke=MINT_DIM)
    groups = [("Trading agents", MINT, ["official paper agents", "users' agents (fleet)", "testnet + mainnet"]),
              ("Copy trading", GOLD, ["Copy Arena collector", "copy pilot: signed plans", "testnet + mainnet"]),
              ("News Tower", SKY, ["feeds, model, reactions", "a reading per market", "every 5 minutes"]),
              ("Push", TEXT, ["signed snapshots", "city, news, Copy Arena", "production + staging"]),
              ("Watch", TEXT, ["watchdog, every 5 min", "strategy health, hourly", "candle sync, daily"]),
              ("Keys and evidence", ROSE, ["encrypted key pool", "hash-chained journals", "verified daily backups"])]
    for i, (t, c, ls) in enumerate(groups):
        s.box(38 + (i % 3) * 190, 444 + (i // 3) * 88, 182, 80, t, ls, color=c, fill="#101a15")

    s.rect(660, 394, 220, 118, fill=STRIKE, stroke=MINT, rx=12)
    s.text(676, 420, "Strike Finance", size=16, fill="#fff", weight=700)
    s.text(676, 438, "mainnet + testnet", size=11, fill=MINT)
    for i, l in enumerate(["trading API v2", "copy trading", "builder connect · market data"]):
        s.text(676, 460 + i * 16, l, size=11, fill=MUTED)
    for i, l in enumerate(["Binance candles · signals", "Hyperliquid public data", "News feeds · Claude Haiku"]):
        s.box(660, 528 + i * 32, 220, 26, l, title_size=10.5)

    s.arrow("M320,150 V194", both=True)
    s.text(330, 176, "HTTPS, same origin", size=10.5, fill=FAINT)
    s.arrow("M320,392 V350")
    s.text(330, 375, "outbound only · HMAC-SHA256 · 2-minute window", size=10.5, fill=FAINT)
    s.arrow("M620,450 H658")
    s.text(624, 468, "signed", size=10, fill=FAINT)
    s.arrow("M620,290 H700 V392")
    s.text(628, 282, "builder connect", size=10.5, fill=FAINT)
    s.arrow("M620,84 H860 V392", color="faint", dash=True)
    s.text(628, 76, "Strike's public data, read in the browser", size=10, fill=FAINT)
    s.text(628, 100, "prices, book, trades and its statistics", size=10, fill=FAINT)
    for i in range(3):
        s.arrow(f"M620,{541 + i * 32} H658", color="faint", dash=True)
    s.legend(24, 650, [("signed requests", "mint", False), ("public reads", "faint", True)])
    s.save("architecture")


# ------------------------------------------------------------------ 2. every Strike integration
def card(s: Svg, x, y, w, h, n, title, who, rows=(), note=(), color=MINT, fill=PANEL, stroke=LINE):
    s.add('<g data-group="1">')
    s.rect(x, y, w, h, fill=fill, stroke=stroke, rx=12, box=True)
    if n:
        s.num(x + 24, y + 24, n, color=color)
    s.text(x + (42 if n else 16), y + 29, title, size=14, fill="#fff", weight=600)
    s.text(x + 16, y + 50, who, size=10.5, fill=color)
    yy = y + 76
    for ep, why in rows:
        s.text(x + 16, yy, ep, size=10.5, fill=CODE, mono=True)
        s.text(x + w - 16, yy, why, size=10.5, fill=FAINT, anchor="end")
        yy += 17
    if rows:
        yy += 8
    for l in note:
        s.text(x + 16, yy, l, size=11, fill=MUTED)
        yy += 16
    s.add("</g>")
    return yy


def integration():
    s = Svg(900, 1350, "Every Strike integration in EdgeCraft-StrikeCity: 46 endpoints in six areas")
    s.rect(230, 20, 440, 74, fill=STRIKE, stroke=MINT, rx=12)
    s.text(450, 50, "Strike Finance", size=19, fill="#fff", weight=700, anchor="middle")
    s.text(450, 74, "46 endpoints in use · six integrations · mainnet and testnet", size=11.5, fill=MINT, anchor="middle")

    card(s, 20, 118, 420, 398, 1, "Builder connect and builder code", "called by the site's Functions, at onboarding", [
        ("POST /auth/builder/request-signature", "message"),
        ("POST /auth/builder/verify-signature", "authorise"),
        ("X-Builder-Fee-Bps: 20", "on every order"),
    ], ["One wallet signature creates an agent on the user's own",
        "Strike account. Before saving anything, the site checks",
        "that Strike linked exactly our key, our builder code",
        "SmartFlowAgent-EdgeCraft and 20 bps. If anything differs,",
        "the key is burnt and the attempt is recorded."])
    for i, (t, l) in enumerate([("Your wallet", "signs once"), ("Strike", "links an API wallet"), ("Your agent", "trades your account")]):
        s.box(36 + i * 134, 352, 120, 50, t, [l], size=10.5, center=True, fill="#101a15", stroke=MINT_DIM)
        if i < 2:
            s.arrow(f"M{156 + i * 134},377 H{168 + i * 134}")
    s.text(36, 436, "Revenue: 0.20 % per execution, credited by Strike to", size=11, fill=MUTED)
    s.text(36, 452, "the builder. Funds never leave the user's account, and", size=11, fill=MUTED)
    s.text(36, 468, "the user approves the fee in Strike's own message.", size=11, fill=MUTED)

    card(s, 460, 118, 420, 398, 2, "Trading API v2", "called by every agent on the host · Ed25519-signed", [
        ("GET /v2/time", "signing clock"),
        ("GET /v2/markets", "limits, sizes"),
        ("GET /v2/fee-tiers", "fees"),
        ("GET /price/v2/ticker/bookTicker", "executable price"),
        ("GET /price/v2/depth", "book impact"),
        ("GET /price/v2/premiumIndex", "mark price, stops"),
        ("GET /v2/account", "balance, margin"),
        ("GET /v2/positions", "positions"),
        ("GET /v2/openOrders", "open orders"),
        ("GET /v2/order", "look up before a retry"),
        ("POST /v2/order/strategy", "entry with its stop"),
        ("POST /v2/order", "stop move, exit"),
        ("DELETE /v2/order/cancel", "old stop"),
        ("POST /v2/leverage", "fits the margin"),
        ("GET /v2/history/fill", "fills, results"),
        ("GET /v2/history/transaction", "deposits kept out"),
    ], ["Every order-creating request carries the builder fee,",
        "so each execution is credited to our builder code."])

    card(s, 20, 532, 420, 300, 3, "Copy trading", "called by the collector (read only) and the copy pilot", [
        ("GET /v2/copy/discover", "traders to copy"),
        ("GET /v2/copy/leaderboard", "every copy, its end"),
        ("GET /v2/copy/subscriptions", "who copies whom"),
        ("GET /stat/v1/dashboard/copy-trading-*", "7 series"),
        ("POST /v2/copy/subscribe", "start a copy"),
        ("PATCH /v2/copy/subscribe/{id}", "change limits"),
        ("DELETE /v2/copy/subscribe/{id}", "stop it"),
        ("GET /v2/copy/subscriptions?scope=all", "status"),
    ], ["Collector: no keys, history kept beyond Strike's 30 days.",
        "Pilot: Strike creates and funds a sub-account for each",
        "copy, and enforces its stop-loss on Strike's side.",
        "Traders' names, badges and positions: /v2/account and",
        "/v2/positions; Hyperliquid's public API for its traders."], color=GOLD)

    card(s, 460, 532, 420, 300, 4, "Market data, live in the city", "read straight from the browser (news: on the host)", [
        ("GET /price/v2/ticker/24hr", "towers, top bar"),
        ("GET /v2/markets", "all 33 markets"),
        ("GET /price/v2/premiumIndex", "the fountain"),
        ("GET /price/v2/depth", "the order book"),
        ("GET /price/v2/trades", "the cars"),
        ("GET /price/v2/klines", "news reactions"),
    ], ["Every car is a real trade on Strike. The towers carry",
        "TradingView's live chart of their market, and Strike",
        "Finance's building STRIKE, its own token (Cardano),",
        "through DEX Screener: TradingView has no chart of it."], color=SKY)

    card(s, 20, 848, 420, 316, 5, "Strike's own statistics", "read inside the Strike Finance building · /stat/v1", [
        ("GET …/dashboard/summary", "the totals"),
        ("GET …/dashboard/volumes", "volume a day"),
        ("GET …/dashboard/open-interest", "OI a day"),
        ("GET …/dashboard/trades", "trades a day"),
        ("GET …/dashboard/users", "active, new users"),
        ("GET …/dashboard/revenue", "revenue a day"),
        ("GET …/dashboard/liquidations", "liquidations"),
        ("GET …/dashboard/treasury", "TVL by asset"),
        ("GET …/stats/live-positions", "every position"),
        ("GET …/stats/coin/funding-rate-comparison", "vs others"),
        ("GET /v2/vaults", "Strike's vaults"),
    ], ["Volume, users, TVL, open interest, revenue and funding,", "live, as nobody shows them on Strike today."], color=MINT)

    card(s, 460, 848, 420, 316, 6, "Into Strike's app, and our checks", "links for everyone · checks before every release", [
        ("Copy on Strike", "a trader's portfolio"),
        ("Builder codes", "from the landing"),
        ("smartflow strike-check", "public formats"),
        ("smartflow auth-check", "signed reads"),
        ("GET /v2/sub-accounts", "in auth-check"),
        ("testnet order probe", "brackets, cancel-all"),
        ("mainnet test trade", "loop with the fee"),
    ], color=ROSE)

    card(s, 20, 1180, 860, 150, 0, "What Strike gets back", "from every user and every agent", [], [], color=MINT, fill=STRIKE, stroke=MINT_DIM)
    for i, l in enumerate(["Volume and fees through the builder code, on every execution",
                           "Money and copiers for Strike's copy trading",
                           "New users from Cardano wallets, trading from their first minute",
                           "A measured way to choose whom to copy",
                           "Its own numbers, shown live and in public",
                           "Open data: /api/copy and /api/city"]):
        x, y = (36 if i < 3 else 466), 1253 + (i % 3) * 22
        s.rect(x, y - 7, 5, 5, fill=MINT, stroke=MINT, rx=1)
        s.text(x + 12, y, l, size=11.5, fill=TEXT)
    s.save("integration")


# ------------------------------------------------------------------ 3 and 4. sequences
def lifelines(s: Svg, names, top=20, bottom=None):
    xs = []
    for i, (t, sub, c) in enumerate(names):
        x = 110 + i * 226
        xs.append(x)
        s.box(x - 92, top, 184, 48, t, [sub], color=c, size=10.5, center=True, fill=PANEL)
        s.add(f'<path d="M{x},{top + 48} V{bottom}" stroke="{LINE}" stroke-width="1.2" stroke-dasharray="3 4"/>')
    return xs


def step(s: Svg, xs, y, n, a, b, label, sub=(), color="mint", dash=False):
    x1, x2 = xs[a], xs[b]
    d = 1 if x2 > x1 else -1
    s.arrow(f"M{x1 + d * 6},{y} H{x2 - d * 4}", color=color, dash=dash)
    lx = min(x1, x2) + 30   # the step's number at the left end, its words after it
    s.num(min(x1, x2) + 16, y - 14, n, color=HEADS[color])
    s.text(lx, y - 7, label, size=11.5, fill="#fff", weight=500, halo=True)
    for i, l in enumerate(sub):
        s.text(lx, y + 15 + i * 14, l, size=10.5, fill=FAINT, halo=True)


def note(s: Svg, x, y, w, lines, color=MINT, title=None):
    h = 14 + len(lines) * 15 + (17 if title else 0)
    s.add('<g data-group="1">')
    s.rect(x, y, w, h, fill="#101a15", stroke=color, rx=8, box=True)
    yy = y + 19
    if title:
        s.text(x + 12, yy, title, size=11.5, fill=color, weight=600)
        yy += 17
    for l in lines:
        s.text(x + 12, yy, l, size=10.5, fill=MUTED)
        yy += 15
    s.add("</g>")


def onboarding():
    s = Svg(900, 640, "Creating an agent with one signature, through Strike's builder connect")
    xs = lifelines(s, [("You", "a Cardano wallet", TEXT), ("The site", "browser + Functions", TEXT),
                       ("Agents' host", "the fleet", MINT), ("Strike", "builder connect, API v2", MINT)], bottom=620)
    step(s, xs, 112, 1, 2, 1, "keeps fresh API-wallet keys on offer", ["public keys only: private keys stay encrypted on the host"], color="faint", dash=True)
    step(s, xs, 172, 2, 0, 1, "build the agent, then review it", ["character, personality, strategy,", "markets, risk, the 0.20 % fee"])
    step(s, xs, 240, 3, 1, 3, "POST /auth/builder/request-signature", ["your address, chain cardano, our code, fee_share_bps 20"])
    step(s, xs, 296, 4, 3, 1, "the exact message to sign", color="faint")
    step(s, xs, 346, 5, 1, 0, "one signature (CIP-30 signData)", ["in your own wallet"])
    step(s, xs, 404, 6, 1, 3, "POST /auth/builder/verify-signature", ["Strike authorises the API wallet on your account"])
    note(s, xs[1] - 92, 444, 300, ["Strike linked exactly our key, our builder code", "and 20 bps? Otherwise the key is burnt.",
                                    "Saved with an audit row: the exact message", "and your signature."], title="The site checks before saving")
    step(s, xs, 574, 7, 2, 1, "the fleet reads the new link", ["HMAC-signed, outbound"], color="faint", dash=True)
    step(s, xs, 604, 8, 2, 3, "your agent trades your account", ["Ed25519 · builder fee on every order"])
    s.save("onboarding")


def copy_flow():
    s = Svg(900, 676, "Copy with your agent: a signed plan carried out on Strike's own copy trading")
    xs = lifelines(s, [("You", "the agent's owner", TEXT), ("The site", "browser + Functions", TEXT),
                       ("Copy pilot", "on the agents' host", GOLD), ("Strike", "copy trading", MINT)], bottom=656)
    step(s, xs, 112, 1, 0, 1, "sign the copy plan, in plain words", ["one trader, or \"my agent chooses\" by", "your rules; amount, stop-loss, leverage,",
                                                                     "markets to avoid, an end date"], color="gold")
    note(s, xs[1] + 14, 128, 196, ["checks the signature,", "stores the plan,", "writes an audit row"], color=MUTED)
    step(s, xs, 236, 2, 2, 1, "reads the signed plans", ["HMAC-signed, outbound"], color="faint", dash=True)
    note(s, xs[2] - 92, 262, 184, ["Strike City score, platforms,", "review period, changes a week"], color=GOLD, title="Chooses by your rules")
    step(s, xs, 352, 3, 2, 3, "POST /v2/copy/subscribe", ["auto_create_sub_account, stop_loss_amount,", "excluded_symbols, isolated margin, request_id"], color="gold")
    note(s, xs[3] - 94, 404, 188, ["creates a sub-account,", "funds it from your account,", "copies the trader,", "enforces the stop-loss"], title="Strike")
    step(s, xs, 520, 4, 2, 3, "GET /v2/copy/subscriptions?scope=all", ["where each copy really is"], color="faint", dash=True)
    step(s, xs, 576, 5, 2, 1, "the copy's status", ["in My agent, and in the city: your", "agent stands with the trader"], color="gold")
    step(s, xs, 644, 6, 3, 2, "stopped at its stop-loss, or refused", ["the plan halts until you sign again"], color="rose", dash=True)
    s.save("copy")


# ------------------------------------------------------------------ 5. what the city shows, and where it comes from
def city_data():
    s = Svg(900, 790, "Where everything in the city comes from: the host's snapshots, Strike's public data and the chart providers")
    s.text(20, 34, "Sources", size=13, fill=FAINT, weight=600)
    s.text(316, 34, "On the way", size=13, fill=FAINT, weight=600)
    s.text(600, 34, "What you see in the city", size=13, fill=FAINT, weight=600)
    src = [("Agents' journals", "every check, order and fill", MINT), ("Copy Arena collector", "traders, copiers, the score", GOLD),
           ("News service", "readings and reactions", SKY)]
    for i, (t, l, c) in enumerate(src):
        s.box(20, 52 + i * 74, 256, 60, t, [l], color=c)
        s.arrow(f"M276,{82 + i * 74} H296 V102 H314", color="faint")
    s.text(20, 290, "on the agents' host", size=10.5, fill=FAINT)
    s.box(20, 388, 256, 92, "Strike's public data", ["tickers, markets, funding, order", "book, trades, and Strike's own", "statistics (/stat/v1, vaults)"], color="#fff", fill=STRIKE, stroke=MINT)
    s.box(20, 508, 256, 60, "Chart providers", ["TradingView · DEX Screener"], color=SKY)
    s.text(20, 590, "read by your browser", size=10.5, fill=FAINT)

    s.box(316, 72, 244, 60, "smartflow-push", ["signed, only when something changed"])
    s.box(316, 168, 244, 60, "Cloudflare edge", ["/api/city · /api/copy · /api/news"], mono_lines=True)
    s.box(316, 300, 244, 60, "The city's store", ["polls, merges in Strike's live data"])
    s.arrow("M438,132 V166")
    s.arrow("M438,228 V298")
    s.arrow("M276,426 H296 V330 H314", color="faint", dash=True)
    s.arrow("M276,538 H296 V346 H314", color="faint", dash=True)
    s.arrow("M560,330 H594")

    rows = [("Agents walk by their real state", "Signal Lab, Strike Finance, towers", MINT),
            ("Strike's traders and their copiers", "towers, Strike Finance, the Copy Arena", GOLD),
            ("The News Tower", "agents walk in when a reading turns", SKY),
            ("Prices on the towers, the top bar", "/price/v2/ticker/24hr", TEXT),
            ("Strike Finance's order book", "/price/v2/depth: BTC, live", TEXT),
            ("Strike Finance's screen", "STRIKE, its token (DEX Screener)", SKY),
            ("A chart on every tower", "TradingView, live, its market", SKY),
            ("Inside Strike Finance", "/stat/v1: volume, OI, users, TVL", TEXT),
            ("The fountain's colour", "/price/v2/premiumIndex: BTC funding", TEXT),
            ("Markets: all 33 of them", "/v2/markets: names, maximum leverage", TEXT),
            ("Cars: each one a real trade", "/price/v2/trades: bought green, sold red", TEXT),
            ("The weather", "BTC's move over 24 hours", TEXT)]
    for i, (t, l, c) in enumerate(rows):
        s.add('<g data-group="1">')
        s.rect(600, 52 + i * 60, 280, 52, fill=BOX, stroke=LINE, rx=8, box=True)
        s.rect(600, 52 + i * 60, 4, 52, fill=c, stroke=c, rx=2)
        s.text(616, 52 + i * 60 + 21, t, size=12, fill="#fff", weight=600)
        s.text(616, 52 + i * 60 + 39, l, size=10.5, fill=FAINT, mono=l.startswith("/"))
        s.add("</g>")
    s.add(f'<path d="M594,78 V740" stroke="{MINT_DIM}" stroke-width="1.2"/>')
    s.save("city-data")


# ------------------------------------------------------------------ 6. two measured pipelines
def pipelines():
    s = Svg(900, 352, "Two measured pipelines: the News Tower's reading and the Strike City score")
    lanes = [("The News Tower: news, measured on Strike", SKY, "sky", [
        ("Tiered sources", ["official, tier-one,", "filtered searches"]),
        ("Model scoring", ["fixed scale,", "catalysts only"]),
        ("One vote a story", ["however many", "outlets carry it"]),
        ("Strike reaction", ["1-minute mark candles", "vs the normal move"]),
        ("Market reading", ["very bearish to very", "bullish, scoreboard"]),
        ("In the city", ["six floors; agents", "walk in to read"])]),
             ("The Strike City score: tested on every copy", GOLD, "gold", [
        ("Every copy", ["Strike's leaderboard,", "kept past 30 days"]),
        ("Scored blind", ["only with what was", "known before it"]),
        ("Profit or loss", ["ranking 0.59, Strike's", "own score 0.50"]),
        ("Weights", ["copies 30 · Strike 30", "record 20 · size 20"]),
        ("Hourly re-test", ["live, shown in", "the Copy Arena"]),
        ("Put to use", ["arena ranking and", "the pilot's choice"])])]
    for li, (title, c, ck, stages) in enumerate(lanes):
        y = 20 + li * 152
        s.rect(20, y, 860, 140, fill=PANEL, stroke=LINE, rx=12)
        s.text(38, y + 30, title, size=14, fill=c, weight=700)
        for i, (t, ls) in enumerate(stages):
            x = 38 + i * 140
            s.box(x, y + 48, 124, 74, t, ls, color="#fff", size=10.5)
            if i < len(stages) - 1:
                s.arrow(f"M{x + 124},{y + 85} H{x + 138}", color=ck, sw=1.3)
    s.text(24, 336, "Agents never trade on news. The score's test reruns every hour in public, so its numbers move as copies add up.", size=10.5, fill=FAINT)
    s.save("pipelines")


# ------------------------------------------------------------------ 7. evidence
def evidence():
    s = Svg(900, 360, "Tamper-evident records: signed actions on the site, hash-chained logs on the host, anchored together")
    s.rect(20, 20, 860, 120, fill=PANEL, stroke=LINE, rx=12)
    s.text(38, 46, "On the site", size=14, fill="#fff", weight=700)
    site = [("You sign an action", ["a fresh message for every", "change, in plain words"]),
            ("The site verifies it", ["COSE signature, key hashes", "to your address, payload"]),
            ("D1 audit row", ["exact message + signature;", "triggers refuse edits"])]
    for i, (t, ls) in enumerate(site):
        s.box(38 + i * 286, 58, 250, 70, t, ls)
        if i < 2:
            s.arrow(f"M{288 + i * 286},93 H{322 + i * 286}")
    s.rect(20, 170, 860, 170, fill=STRIKE, stroke=MINT_DIM, rx=12)
    s.text(38, 196, "On the agents' host", size=14, fill=MINT, weight=700)
    host = [("Everything recorded", ["candle checks, orders,", "Strike requests as sent", "and answered, fills"]),
            ("Hash-chained", ["each line carries the", "SHA-256 of all before"]),
            ("Anchored", ["chain heads sent to the", "site every minute"]),
            ("Backed up daily", ["90 days, with a check", "of every chain"]),
            ("Audit report", ["a user's full history,", "rebuilt on demand"])]
    for i, (t, ls) in enumerate(host):
        s.box(38 + i * 170, 210, 154, 100, t, ls, fill="#101a15")
        if i < 4:
            s.arrow(f"M{192 + i * 170},260 H{206 + i * 170}")
    s.arrow("M463,210 V154 H735 V130", color="rose")
    s.text(40, 160, "chain heads kept in D1: a rewrite on the host would no longer match", size=10.5, fill=ROSE)
    s.text(38, 330, "smartflow audit verify · smartflow audit report <user>", size=10.5, fill=FAINT, mono=True)
    s.save("evidence")


if __name__ == "__main__":
    OUT.mkdir(parents=True, exist_ok=True)
    for f in (architecture, integration, onboarding, copy_flow, city_data, pipelines, evidence):
        f()
        print("drew", f.__name__)

"""Does every part of the city show the right data, and keep it fresh? Read-only, on any site (production too).

    python web/scripts/audit_city_data.py <base_url>

Cross-checks what the page shows against the site's own /api/city and Strike's public prices: the top bar's totals,
the Agents panel (every agent, its real status), Ranks and Activity (every agent there, the latest events), Markets
(prices against Strike's mark price, long/short against the real positions), the card of an agent that waits (every
market it trades is checked, not just one) and that the page keeps asking for new data (city every 10 s, prices
every 15 s). Exit 1 if anything does not match.
"""
import json
import re
import sys
import time
import urllib.request

from playwright.sync_api import sync_playwright

BASE = sys.argv[1].rstrip("/")
UA = {"User-Agent": "smartflow-audit/1.0"}
ok_all = True


def check(name, ok, detail=""):
    global ok_all
    ok_all &= bool(ok)
    print(("PASS " if ok else "FAIL ") + name + (f" · {detail}" if detail else ""))


def get(url):
    return json.load(urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=20))


def num(s):
    s = s.replace("−", "-").replace("R", "").replace("%", "").strip()
    return float(s.replace(".", "").replace(",", ".")) if re.search(r"\d,\d", s) else float(s.replace(",", ""))


STATUS = {"analyzing": "Analysing", "waiting": "Waiting for a setup", "signal": "Signal found", "risk": "Blocked by risk check",
          "entering": "Sending order", "in_trade": "In a trade", "exiting": "Trade closed", "paused": "Paused", "offline": "Offline",
          "unfunded": "Waiting for a deposit"}

with sync_playwright() as p:
    b = p.chromium.launch()
    ctx = b.new_context(viewport={"width": 1440, "height": 900}, locale="en-US")
    ctx.add_init_script("try { localStorage.setItem('sf-city-welcome', '1'); localStorage.setItem('sf-lang', 'en'); } catch (e) {}")
    pg = ctx.new_page()
    calls = {"city": 0, "prices": 0}
    pg.on("request", lambda r: calls.__setitem__("city", calls["city"] + 1) if r.url.endswith("/api/city") else
          calls.__setitem__("prices", calls["prices"] + 1) if "premiumIndex" in r.url or "ticker/24hr" in r.url else None)
    pg.route("https://s3.tradingview.com/**", lambda r: r.abort())
    pg.goto(f"{BASE}/#/city", wait_until="domcontentloaded")
    pg.wait_for_selector(".city[data-ready]", timeout=40000)
    pg.wait_for_timeout(3000)
    doc = get(f"{BASE}/api/city")
    agents = doc["agents"]
    now = time.time() * 1000

    # ---- the city's figures (Results' summary)
    pg.locator(".city-dock-btn", has_text="Results").click()
    pg.wait_for_selector("#city-panel .rs-tile[data-k=online]")
    dd = [pg.locator(f"#city-panel .rs-tile[data-k={k}] b").inner_text() for k in ("online", "inTrade", "trades24", "r24")]
    pg.locator("#city-panel .city-panel-head .icon-btn").click()
    live = sum(1 for a in agents if a["status"] not in ("paused", "offline"))
    in_trade = sum(1 for a in agents if a.get("positions"))
    day = [t for a in agents for t in a.get("trades", []) if not t.get("test") and t["time"] >= now - 86400_000]
    check("top bar: agents online", int(dd[0]) == live, f"page {dd[0]}, API {live}")
    check("top bar: in a trade", int(dd[1]) == in_trade, f"page {dd[1]}, API {in_trade}")
    check("top bar: trades 24h", int(dd[2]) == len(day), f"page {dd[2]}, API {len(day)}")
    check("top bar: result 24h", abs(num(dd[3]) - sum(t["r"] for t in day)) < 0.011, f"page {dd[3]}, API {sum(t['r'] for t in day):.2f}R")

    # ---- Agents: every agent, its real status
    pg.locator(".city-dock-btn", has_text="Agents").click()
    pg.wait_for_selector(".city-panel")
    pg.wait_for_timeout(400)
    rows = pg.locator(".city-row").all_inner_texts()
    for a in agents:
        row = next((r for r in rows if a["name"] in r), None)
        want = STATUS.get(a["status"], a["status"])
        check(f"agents: {a['name']} listed with its status", row is not None and want in row, f"wants '{want}'" + ("" if row else " · missing"))

    # ---- Ranks and Activity
    pg.locator(".city-dock-btn", has_text="Ranks").click()
    pg.wait_for_timeout(500)
    ranks = pg.locator(".city-panel").inner_text()
    check("ranks: every agent is ranked", all(a["name"] in ranks for a in agents), f"{sum(a['name'] in ranks for a in agents)} of {len(agents)}")
    pg.locator(".city-dock-btn", has_text="Feed").click()
    pg.wait_for_timeout(500)
    feed = pg.locator(".city-panel").inner_text()
    latest = max((d["time"] for a in agents for d in a.get("decisions", [])), default=0)
    check("activity: shows events", len(feed.strip()) > 40 and latest > 0, f"latest event {round((now - latest) / 60000)} min ago")
    check("activity: newest first, at most minutes old", "ago" in feed and (now - latest) < 5 * 3600_000)

    # ---- Markets: Strike's prices, long/short from the real positions
    pg.locator(".city-dock-btn", has_text="Markets").click()
    pg.wait_for_timeout(600)
    marks = {r["symbol"]: float(r["markPrice"]) for r in get("https://api.strikefinance.org/price/v2/premiumIndex")}
    items = pg.locator(".city-markets li").all_inner_texts()
    for txt in items:
        m = re.match(r"\s*([A-Z]+)", txt)
        if not m:
            continue
        sym = m.group(1) + "-USD"
        nums = re.findall(r"[\d][\d,]*\.?\d*", txt.replace("−", "-"))
        px = float(nums[0].replace(",", "")) if nums else None
        ref = marks.get(sym)
        check(f"markets: {sym} price is Strike's", px is not None and ref and abs(px / ref - 1) < 0.01, f"page {px}, Strike mark {ref}")
        longs = sum(1 for a in agents for q in a.get("positions", []) if q["market"] == sym and q["side"] == "long")
        shorts = sum(1 for a in agents for q in a.get("positions", []) if q["market"] == sym and q["side"] == "short")
        ls = re.search(r"(\d+)\s*long\D+(\d+)\s*short", txt, re.I)
        if ls:
            check(f"markets: {sym} long/short", (int(ls.group(1)), int(ls.group(2))) == (longs, shorts), f"page {ls.groups()}, API {(longs, shorts)}")

    # ---- the card of an agent that waits with several markets: every market it trades is checked
    waiting = [a for a in agents if a["status"] == "waiting" and len(a.get("markets", [])) > 1]
    if waiting:
        a = waiting[0]
        pg.locator(".city-dock-btn", has_text="Agents").click()
        pg.wait_for_timeout(300)
        pg.locator(".city-row", has_text=a["name"]).first.click()
        pg.wait_for_selector(".city-card")
        pg.wait_for_timeout(800)
        card = pg.locator(".city-card").inner_text()
        shown = pg.locator(".city-checks li").count()
        check(f"card: {a['name']} shows every market it checked", f"its {len(a['markets'])} markets" in card and shown == len(a["markets"]),
              f"{shown} markets listed of {len(a['markets'])}")
    else:
        print("SKIP card: no agent waiting with several markets right now")

    # ---- it keeps the data fresh
    c0, p0 = calls["city"], calls["prices"]
    pg.wait_for_timeout(32000)
    check("refresh: the agents are asked for again (every 10 s)", calls["city"] - c0 >= 2, f"{calls['city'] - c0} requests in 32 s")
    check("refresh: prices are asked for again (every 15 s)", calls["prices"] - p0 >= 2, f"{calls['prices'] - p0} requests in 32 s")
    b.close()
print("ALL OK" if ok_all else "SOMETHING DOES NOT MATCH")
sys.exit(0 if ok_all else 1)

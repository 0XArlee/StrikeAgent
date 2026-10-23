"""Real-browser verification of EdgeCraft-StrikeCity in live mode (real agents from /api/city), production bundle.

    python web/scripts/verify_city_live.py <axe.min.js> <out_dir> <real_base_url> [<fixture_base_url>]

real_base_url: a preview whose /api points at the real agents' journals. It checks the LIVE badge and note, the
real/demo sections, the demo toggle, a real agent's card (its latest real check, next candle, paper account), details
and feed, at 1440 and 390 px, with axe-core on each surface, plus the fallback to the demo city when the API is down.
fixture_base_url (optional): a preview whose API serves a fixture agent with an open position and closed trades, to
check open R against the live Strike price and the trades table.
"""

import json
import re
import os
import sys
from pathlib import Path

from playwright.sync_api import sync_playwright

AXE, OUT, REAL = Path(sys.argv[1]), Path(sys.argv[2]), sys.argv[3]
FIX = sys.argv[4] if len(sys.argv) > 4 else None
OUT.mkdir(parents=True, exist_ok=True)
report = {"checks": [], "axe": {}}


def check(name, ok, detail=""):
    report["checks"].append({"name": name, "ok": bool(ok), "detail": detail})
    print(("PASS " if ok else "FAIL ") + name + (f" · {detail}" if detail else ""))


def axe(page, label):
    page.add_script_tag(path=str(AXE))
    res = page.evaluate("""async () => {
        const r = await axe.run(document, { runOnly: { type: 'tag', values: ['wcag2a','wcag2aa','wcag21a','wcag21aa','wcag22aa'] } });
        return r.violations.map(v => ({ id: v.id, nodes: v.nodes.length, target: v.nodes[0].target }));
    }""")
    report["axe"][label] = res
    check(f"axe {label}: 0 violations", not res, "; ".join(f"{v['id']}({v['nodes']}) {v['target']}" for v in res))


def overflow(page):
    return page.evaluate("() => document.documentElement.scrollWidth - window.innerWidth")


def open_city(browser, base, viewport, mobile, welcome=True, block_api=False, hash="#/city"):
    ctx = browser.new_context(viewport=viewport, locale="en-US", device_scale_factor=2 if mobile else 1, is_mobile=mobile, has_touch=mobile)
    if os.environ.get("SF_ART"):   # the city's art to check (new: LimeZu's, web/scripts/build_city.py)
        ctx.add_init_script("try { sessionStorage.setItem('sf-art', '%s') } catch (e) {}" % os.environ["SF_ART"])
    if block_api:
        ctx.route("**/api/city", lambda r: r.abort())
    page = ctx.new_page()
    errors = []
    page.on("console", lambda m: errors.append(m.text) if m.type == "error" and "api/city" not in m.text and "telemetry.tradingview.com" not in m.text
            and "dexscreener.com" not in m.text and "dexscreener.com" not in (m.location or {}).get("url", "") else None)   # DEX Screener's chart iframe: its own analytics, refused by its own server
    page.on("pageerror", lambda e: errors.append(str(e)))
    if not welcome:
        page.add_init_script("localStorage.setItem('sf-city-welcome', '1')")
    page.goto(f"{base}/{hash}", wait_until="load")   # not "networkidle": TradingView keeps requests of its own open
    if not block_api:   # without its data the city shows its error instead
        page.wait_for_selector(".city[data-ready]", timeout=40000)
    return ctx, page, errors


def real_mode(p, name, viewport, mobile):
    browser = p.chromium.launch()
    ctx, page, errors = open_city(browser, REAL, viewport, mobile)
    api = page.evaluate("() => fetch('/api/city').then(r => r.json())")
    real = [a for a in api["agents"] if a.get("markets")]
    page.wait_for_selector("dialog.city-welcome[open]", timeout=20000)
    page.wait_for_timeout(300)
    page.screenshot(path=str(OUT / f"l01_welcome_{name}.png"))
    check(f"{name}: welcome explains LIVE vs demo", page.locator("dialog.city-welcome .alert-live").count() == 1)
    axe(page, f"{name} live welcome")
    page.keyboard.press("Escape")
    page.wait_for_timeout(1500)
    check(f"{name}: LIVE badge in the header", page.locator(".city-top .city-live").is_visible())
    stats = page.locator(".city-stats dt").all_inner_texts()
    online = page.locator(".city-stats dd").first.inner_text()
    n_online = sum(1 for a in real if a["status"] != "offline")
    check(f"{name}: header counts the agents online", online.strip() == str(n_online), f"{stats[0]} = {online} (api: {n_online})")
    page.screenshot(path=str(OUT / f"l02_map_{name}.png"))

    # agents panel: real section first, LIVE tags, the demo switch
    page.get_by_role("button", name="Agents", exact=True).click()
    page.wait_for_selector(".city-panel")
    page.wait_for_timeout(300)
    # the agents, then the Strike traders in their own section: the ones walking the city first, then every other
    # trader people can copy (its profile opens on a press)
    leads = page.locator(".city-leads .city-row").count()
    in_city = page.locator(".city-leads ul").first.locator(".city-row").count()
    rows = page.locator(".city-row").count() - leads
    traders = page.request.get(f"{REAL}/api/copy").json().get("traders", [])
    walking = sum(1 for t in traders if t.get("walks"))
    check(f"{name}: every agent is listed", rows == len(real), f"{rows} rows")
    check(f"{name}: the Strike traders walking the city are listed first", in_city == walking, f"{in_city} rows (api: {walking})")
    check(f"{name}: every trader people can copy is listed", leads == len(traders), f"{leads} rows (api: {len(traders)})")
    page.screenshot(path=str(OUT / f"l03_agents_{name}.png"))
    axe(page, f"{name} agents panel (live)")
    check(f"{name}: only real agents, no demo population", rows == len(real)
          and page.locator(".city-demo, .city-switch").count() == 0, f"{rows} rows")

    # a real agent's card: its latest real check, schedule and paper account. An agent in a trade shows its position
    # instead, so the first one that is not in a trade (when all are, its position is checked)
    # (one of Smart Flow's own paper agents: the checks below are about those)
    def open_card(i):
        if not page.locator(".city-panel").count():   # phones: picking an agent closes the panel
            page.locator(".city-dock-btn", has_text="Agents").click()
            page.wait_for_selector(".city-panel")
        page.locator(".city-row.real").nth(i).click()
        page.wait_for_selector(".city-card")
        page.wait_for_timeout(1500)
        return page.locator(".city-card").inner_text()
    card, first_paper = "", None
    for i in range(len(real)):
        card = open_card(i)
        if "PAPER" not in card.upper():
            continue
        first_paper = i if first_paper is None else first_paper
        if "Open position" not in card:
            break
    else:
        card = open_card(first_paper or 0)
    page.screenshot(path=str(OUT / f"l05_card_{name}.png"))
    # Smart Flow's own agents are tagged "Paper" (the header says LIVE); users' real ones "Real · Strike" (2026-10-20)
    check(f"{name}: card tags the agent as paper", "PAPER" in card.upper() or "PAPEL" in card.upper())
    check(f"{name}: card shows the latest real check", "No trade on" in card or "Opened" in card or "BUY" in card or "SELL" in card
          or ("Checked its" in card and "at the last candle close" in card))
    if "Open position" in card:
        print(f"  ({name}: every agent is in a trade: its open position is checked instead of the next check)")
        check(f"{name}: card shows the open position", all(k in card for k in ("Entry", "Stop")), card.replace("\n", " | ")[-200:])
        check(f"{name}: card shows its open result", bool(re.search(r"Open result\s+[+−-]?\d", card)), card.replace("\n", " | ")[-120:])
    else:
        nxt = re.search(r"Next check\s+(in [^\n]+)", card)
        check(f"{name}: card shows the next candle check", bool(nxt), nxt.group(1) if nxt else card.replace("\n", " | ")[-200:])
        check(f"{name}: card shows the paper account", "Paper account" in card and "$" in card)
    page.get_by_role("button", name="Details").click()
    page.wait_for_selector("dialog.city-details[open]")
    page.wait_for_timeout(300)
    det = page.locator("dialog.city-details").inner_text()
    page.screenshot(path=str(OUT / f"l06_details_{name}.png"))
    check(f"{name}: activity renders the journal reasons", "candle range" in det or "volume" in det, det[:160].replace("\n", " | "))
    check(f"{name}: details carry the paper note (not the demo one)", "Paper agent" in det and "simulated agents" not in det)
    axe(page, f"{name} live details")
    page.get_by_role("tab", name="Stats").click()
    page.wait_for_timeout(200)
    st = page.locator("dialog.city-details").inner_text()
    check(f"{name}: stats show parameters and the Smart Flow fee", "Parameters" in st and "20 bps (0.20%) per fill" in st)
    page.screenshot(path=str(OUT / f"l07_stats_{name}.png"))
    page.keyboard.press("Escape")
    page.wait_for_timeout(200)

    # feed: real section with LIVE tags; ranks: real table
    page.locator(".city-dock-btn", has_text="Feed").click()
    page.wait_for_timeout(400)
    live_items = page.locator(".city-feed li").count()
    check(f"{name}: feed shows the journal events", live_items > 0, f"{live_items} items")
    page.screenshot(path=str(OUT / f"l08_feed_{name}.png"))
    page.locator(".city-dock-btn", has_text="Ranks").click()
    page.wait_for_timeout(300)
    # real accounts and paper agents in their own tables (real accounts without a closed trade yet: a note instead)
    real_rows = page.locator("section[aria-labelledby=ranks-real-title] tbody tr").count()
    paper_rows = page.locator("section[aria-labelledby=ranks-paper-title] tbody tr").count()
    users = [a for a in real if a.get("kind") == "live"]
    shown = real_rows if real_rows else (len(users) if page.locator("section[aria-labelledby=ranks-real-title] p.muted").count() else 0)
    check(f"{name}: ranks list real accounts and paper agents apart", paper_rows == len(real) - len(users) and shown == len(users),
          f"{real_rows} real rows, {paper_rows} paper rows")
    check(f"{name}: no horizontal overflow", overflow(page) <= 0, f"{overflow(page)} px")
    check(f"{name}: no console errors", not errors, " | ".join(errors[:5]))
    ctx.close()

    # deep link to a real agent; API down -> an honest empty city
    ctx, page, errors = open_city(browser, REAL, viewport, mobile, welcome=False, hash=f"#/city?agent={real[0]['id']}")
    page.wait_for_selector(".city-card", timeout=20000)
    check(f"{name}: deep link opens a real agent", page.locator("#agent-card-title").inner_text() == real[0]["name"], page.locator("#agent-card-title").inner_text())
    ctx.close()
    ctx, page, errors = open_city(browser, REAL, viewport, mobile, welcome=True, block_api=True)
    page.wait_for_selector("dialog.city-welcome[open]", timeout=20000)
    page.keyboard.press("Escape")
    page.wait_for_selector(".city-empty", timeout=20000)
    check(f"{name}: API down -> says so, no invented agents", page.locator(".city-empty").count() == 1
          and page.locator(".city-live").count() == 0, " | ".join(page.locator(".city-empty").inner_text().splitlines()))
    ctx.close()
    browser.close()


def fixture_mode(p, name, viewport, mobile):
    browser = p.chromium.launch()
    ctx, page, errors = open_city(browser, FIX, viewport, mobile, welcome=False)
    page.wait_for_selector(".city-dock-btn", timeout=20000)
    api = page.evaluate("() => fetch('/api/city').then(r => r.json())")
    pos = api["agents"][0]["positions"][0]
    page.locator(".city-dock-btn", has_text="Agents").click()
    page.locator(".city-row.real").first.click()
    page.wait_for_selector(".city-card")
    page.wait_for_timeout(2500)
    mark = page.evaluate("() => fetch('https://api.strikefinance.org/price/v2/premiumIndex').then(r => r.json()).then(x => +x.find(m => m.symbol === 'BTC-USD').markPrice)")
    want = (mark - pos["entry"]) / (pos["entry"] - pos["stop"])
    card = page.locator(".city-card").inner_text()
    page.screenshot(path=str(OUT / f"f01_card_in_trade_{name}.png"))
    m = re.search(r"Open result\s*([+−-]?\d+\.\d+)R", card)
    got = float(m.group(1).replace("−", "-")) if m else None
    check(f"{name}: open position on the card (LONG BTC)", "LONG BTC" in card, card.replace("\n", " | ")[:200])
    check(f"{name}: open R follows the live Strike price", got is not None and abs(got - want) < 0.15, f"card {got} vs (mark-entry)/(entry-stop) {want:.2f}")
    check(f"{name}: dynamic exit level shown", "Dynamic exit" in card)
    page.get_by_role("button", name="Details").click()
    page.wait_for_selector("dialog.city-details[open]")
    page.get_by_role("tab", name="Trades").click()
    page.wait_for_timeout(200)
    rows = page.locator("dialog.city-details tbody tr").all_inner_texts()
    page.screenshot(path=str(OUT / f"f02_trades_{name}.png"))
    want_r = [f"{'+' if t['r'] > 0 else '−'}{abs(t['r']):.2f}R" for t in api["agents"][0]["trades"]]
    net = all(t["r"] < t["rGross"] for t in api["agents"][0]["trades"])
    check(f"{name}: closed trades in R, net of fees", len(rows) == 2 and net and all(w in r for w, r in zip(want_r, rows)),
          " / ".join(r.replace("\t", " ") for r in rows) + f" (api net {want_r})")
    page.get_by_role("tab", name="Activity").click()
    page.wait_for_timeout(200)
    act = page.locator("dialog.city-details").inner_text()
    check(f"{name}: activity shows the risk rejection and the order", "spread 14" in act and "Opened LONG BTC" in act)
    page.keyboard.press("Escape")
    page.locator(".city-dock-btn", has_text="Markets").click()
    page.wait_for_timeout(300)
    btc = page.locator(".city-markets li", has_text="BTC-USD").inner_text()
    check(f"{name}: markets count the real long", "1 long" in btc, btc.replace("\n", " | "))
    page.screenshot(path=str(OUT / f"f03_markets_{name}.png"))
    check(f"{name}: no console errors (fixture)", not errors, " | ".join(errors[:5]))
    ctx.close()
    browser.close()


with sync_playwright() as p:
    for nm, vp, mob in (("desktop", {"width": 1440, "height": 900}, False), ("mobile", {"width": 390, "height": 844}, True)):
        real_mode(p, nm, vp, mob)
        if FIX:
            fixture_mode(p, nm, vp, mob)

(OUT / "city_live_report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
fails = [c for c in report["checks"] if not c["ok"]]
print(f"\n{len(report['checks']) - len(fails)}/{len(report['checks'])} checks passed")
sys.exit(1 if fails else 0)

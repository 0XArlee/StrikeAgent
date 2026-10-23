"""Real-browser check of Strike Finance's building and the city's screens, at 1440 and 390 px, with axe-core.

    python web/scripts/verify_city_hq.py <axe.min.js> <out_dir> <base_url>

The building's screen shows STRIKE (Strike Finance's token, through DEX Screener), each market tower's screen loads
TradingView's chart of its market once it comes on screen, the building's card takes you inside, and inside Strike's own
numbers are all there (the figures, the daily volume as bars, the open interest), every spot answers, nothing overflows,
axe finds nothing, the deep link (#/city?strike) works and the way out returns to the city. Read only.
"""
import sys
from pathlib import Path

from playwright.sync_api import sync_playwright

AXE, OUT, BASE = Path(sys.argv[1]), Path(sys.argv[2]), sys.argv[3].rstrip("/")
OUT.mkdir(parents=True, exist_ok=True)
results = []


def check(name, ok, detail=""):
    results.append(bool(ok))
    print(("PASS " if ok else "FAIL ") + name + (f" · {detail}" if detail else ""), flush=True)


def axe(pg, scope):
    pg.add_script_tag(content=AXE.read_text(encoding="utf-8"))
    r = pg.evaluate("""async (scope) => { const r = await axe.run(scope, { runOnly: ["wcag2a", "wcag2aa", "wcag21a", "wcag21aa", "wcag22aa"] });
      return r.violations.map(v => v.id + " (" + v.nodes.length + ")"); }""", scope)
    return r


with sync_playwright() as p:
    b = p.chromium.launch()
    for name, vp, mob in (("desktop", {"width": 1440, "height": 900}, False), ("mobile", {"width": 390, "height": 844}, True)):
        c = b.new_context(viewport=vp, locale="en-US", device_scale_factor=1, is_mobile=mob, has_touch=mob)
        c.add_init_script("localStorage.setItem('sf-city-welcome', '1'); localStorage.setItem('sf-lang', 'en')")
        pg = c.new_page()
        errors = []
        pg.on("pageerror", lambda e: errors.append(str(e)))
        pg.goto(f"{BASE}/#/city", wait_until="load")
        pg.wait_for_selector(".city[data-ready]", timeout=45000)
        pg.wait_for_timeout(4000)
        strike = pg.locator(".city-tv iframe[src*='dexscreener.com/cardano/']")
        check(f"{name}: Strike Finance's screen shows STRIKE (DEX Screener)", strike.count() == 1, strike.first.get_attribute("src")[:80] if strike.count() else "-")
        # the towers' charts load once they come on screen
        pg.focus(".city-canvas")
        for _ in range(8): pg.keyboard.press("ArrowUp")
        for _ in range(3 if not mob else 0): pg.keyboard.press("ArrowRight")
        pg.wait_for_timeout(4000)
        if mob:   # a phone sees one tower at a time: walk along them
            for _ in range(12):
                pg.keyboard.press("ArrowRight"); pg.wait_for_timeout(250)
            pg.wait_for_timeout(3000)
        tv = pg.evaluate("() => [...document.querySelectorAll('.city-tv iframe')].map(f => f.src).filter(s => s.includes('tradingview')).map(s => (s.match(/CRYPTO%3A(\\w+)|CRYPTO:(\\w+)/) || [])[1] || (s.match(/symbol%22%3A%22CRYPTO%3A(\\w+)/) || [])[1] || 'tv')")
        check(f"{name}: the towers' screens load TradingView once seen", len(tv) >= (3 if not mob else 1), str(tv))
        pg.screenshot(path=str(OUT / f"{name}_towers.png"))
        # in: on a desktop through the building's card (its front pressed on the map), on a phone by its address
        pg.reload(wait_until="load")   # the camera back where the city opens
        pg.wait_for_selector(".city[data-ready]", timeout=45000)
        pg.wait_for_timeout(1500)
        if not mob:
            r = pg.locator(".city-canvas").bounding_box()
            pg.mouse.click(r["x"] + 1000, r["y"] + 530)   # the building's front, right of its door, under the sign
            pg.wait_for_selector("#bld-title", timeout=8000)
            title = pg.locator("#bld-title").inner_text()
            enter = pg.locator(".city-card .btn-primary", has_text="Go inside")
            check(f"{name}: Strike Finance's card offers to go inside", title == "STRIKE FINANCE" and enter.count() == 1, title)
            enter.click()
        else:
            pg.goto(f"{BASE}/#/city?strike", wait_until="load"); pg.reload(wait_until="load")   # a fresh load with the address
        pg.wait_for_selector(".tw.hq", timeout=45000)
        pg.wait_for_selector(".hq-kpi", timeout=30000)
        pg.wait_for_timeout(1500)
        kpis = pg.locator(".hq-kpi").all_inner_texts()
        filled = [k for k in kpis if not k.strip().endswith("—")]
        check(f"{name}: inside, Strike's headline figures", len(kpis) == 8 and len(filled) >= 7, " | ".join(k.replace("\n", " ") for k in kpis))
        bars = pg.locator(".hq-chart rect").count()
        check(f"{name}: the daily trading volume as bars", bars >= 30, f"{bars} days")
        check(f"{name}: the open interest chart", pg.locator(".hq-chart path").count() >= 2)
        v = axe(pg, ".tw.hq")
        check(f"{name}: axe (WCAG 2.2 AA) on the hall", not v, ", ".join(v))
        check(f"{name}: no horizontal overflow", pg.evaluate("() => document.documentElement.scrollWidth - innerWidth") <= 0)
        pg.screenshot(path=str(OUT / f"{name}_board.png"))
        for i, spot in enumerate(["oi", "users", "treasury", "funding"]):
            pg.locator(".tw-spots button").nth(i + 1).click()
            pg.wait_for_timeout(700)
            body = pg.locator(".tw-panel").inner_text()
            ok = {"oi": "positions open", "users": "Active today", "treasury": "TVL", "funding": "Binance"}[spot] in body
            check(f"{name}: {spot} shows its numbers", ok and pg.locator(".tw-spots button").nth(i + 1).get_attribute("aria-pressed") == "true")
            pg.screenshot(path=str(OUT / f"{name}_{spot}.png"))
        check(f"{name}: the hall's address", "strike" in pg.evaluate("() => location.hash"))
        pg.locator(".tw.hq .tw-exit").click()
        pg.wait_for_timeout(600)
        check(f"{name}: the way out returns to the city", pg.locator(".tw.hq").count() == 0 and pg.locator(".city-canvas").count() == 1)
        check(f"{name}: no JS errors", not errors, " | ".join(errors[:3]))
        c.close()
    b.close()
print(f"{sum(results)}/{len(results)} checks passed")

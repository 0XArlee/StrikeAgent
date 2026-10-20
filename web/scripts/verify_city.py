"""Real-browser verification of EdgeCraft-StrikeCity (production bundle served by `vite preview`).

    python web/scripts/verify_city.py <axe.min.js> <out_dir> [base_url]

Opens #/city at 1440 px and 390 px, walks the welcome dialog, every dock panel, an agent card and its details tabs,
takes screenshots, runs axe-core (WCAG 2.2 A/AA) on the page and on each dialog, checks the canvas really paints and
changes over time, live Strike prices, the deep link, keyboard control, reduced motion and horizontal overflow.
"""

import json
import sys
import time
from pathlib import Path

from playwright.sync_api import sync_playwright

AXE, OUT = Path(sys.argv[1]), Path(sys.argv[2])
BASE = sys.argv[3] if len(sys.argv) > 3 else "http://localhost:4173"
OUT.mkdir(parents=True, exist_ok=True)
report = {"checks": [], "axe": {}}


def check(name, ok, detail=""):
    report["checks"].append({"name": name, "ok": bool(ok), "detail": detail})
    print(("PASS " if ok else "FAIL ") + name + (f" · {detail}" if detail else ""))


def axe(page, label, include=None):
    page.add_script_tag(path=str(AXE))
    ctx = json.dumps(include) if include else "document"
    res = page.evaluate(f"""async () => {{
        const r = await axe.run({ctx}, {{ runOnly: {{ type: 'tag', values: ['wcag2a','wcag2aa','wcag21a','wcag21aa','wcag22aa'] }} }});
        return r.violations.map(v => ({{ id: v.id, impact: v.impact, nodes: v.nodes.length, help: v.help, target: v.nodes[0].target }}));
    }}""")
    report["axe"][label] = res
    check(f"axe {label}: 0 violations", not res, "; ".join(f"{v['id']}({v['nodes']}) {v['target']}" for v in res))


CANVAS_SIG = """() => {
  const c = document.querySelector('.city-canvas');
  const g = c.getContext('2d');
  const d = g.getImageData(0, 0, c.width, c.height).data;
  const colors = new Set(); let sum = 0;
  for (let i = 0; i < d.length; i += 4 * 997) { colors.add(d[i] << 16 | d[i+1] << 8 | d[i+2]); sum += d[i] * 3 + d[i+1] * 7 + d[i+2]; }
  return { colors: colors.size, sum, w: c.width, h: c.height };
}"""


def overflow(page):
    return page.evaluate("() => document.documentElement.scrollWidth - window.innerWidth")


def run(p, name, viewport, mobile):
    browser = p.chromium.launch()
    ctx = browser.new_context(viewport=viewport, locale="en-US", device_scale_factor=2 if mobile else 1, is_mobile=mobile, has_touch=mobile)
    page = ctx.new_page()
    errors = []
    page.on("console", lambda m: errors.append(m.text) if m.type == "error" else None)
    page.on("pageerror", lambda e: errors.append(str(e)))

    page.goto(f"{BASE}/#/city", wait_until="networkidle")
    page.wait_for_selector("dialog.city-welcome[open]", timeout=20000)
    page.wait_for_timeout(400)
    page.screenshot(path=str(OUT / f"c01_welcome_{name}.png"))
    focused = page.evaluate("() => document.activeElement?.textContent")
    check(f"{name}: welcome dialog focuses its action", focused in ("Enter the city", "Entrar en la ciudad"), str(focused))
    axe(page, f"{name} welcome dialog")
    page.keyboard.press("Escape")
    page.wait_for_timeout(300)
    check(f"{name}: Esc closes the welcome dialog", page.locator("dialog.city-welcome").count() == 0)

    check(f"{name}: live Strike prices (no fallback warning)", page.locator(".city-source-warn").count() == 0)
    a = page.evaluate(CANVAS_SIG)
    page.wait_for_timeout(2500)
    b = page.evaluate(CANVAS_SIG)
    check(f"{name}: canvas paints the city", a["colors"] > 40, f"{a['colors']} colours sampled at {a['w']}x{a['h']}")
    check(f"{name}: canvas animates", a["sum"] != b["sum"])
    page.screenshot(path=str(OUT / f"c02_map_{name}.png"))
    check(f"{name}: no horizontal overflow", overflow(page) <= 0, f"{overflow(page)} px")

    stats = page.locator(".city-stats dd").all_inner_texts()
    check(f"{name}: top stats filled", len(stats) >= 3 and stats[0].strip() not in ("", "0"), " | ".join(stats))

    # keyboard: focus the map and zoom / pan
    page.focus(".city-canvas")
    s0 = page.evaluate(CANVAS_SIG)["sum"]
    for k in ["+", "+", "ArrowRight", "ArrowDown"]:
        page.keyboard.press(k)
    page.wait_for_timeout(200)
    check(f"{name}: keyboard pans and zooms the map", page.evaluate(CANVAS_SIG)["sum"] != s0)

    # every dock panel
    for label, shot in [("Agents", "agents"), ("Ranks", "ranks"), ("Feed", "feed"), ("Markets", "markets"), ("Guide", "guide")]:
        page.locator(".city-dock-btn", has_text=label).click()
        page.wait_for_selector(".city-panel")
        page.wait_for_timeout(350)
        page.screenshot(path=str(OUT / f"c03_{shot}_{name}.png"))
        check(f"{name}: {label} panel opens", page.locator("#city-panel-title").inner_text().strip() != "")
        if label in ("Agents", "Guide"):
            axe(page, f"{name} {label.lower()} panel")
    page.locator(".city-dock-btn", has_text="Markets").click()
    rows = page.locator(".city-markets li").count()
    check(f"{name}: markets list shows Strike markets", rows >= 3, f"{rows} markets")
    page.locator(".city-dock-btn", has_text="Feed").click()
    page.wait_for_timeout(300)
    feed = page.locator(".city-feed li").count()
    check(f"{name}: feed has events", feed > 0, f"{feed} items")

    # pick an agent from the directory -> card -> details
    page.locator(".city-dock-btn", has_text="Agents").click()
    page.locator(".city-row").first.click()
    page.wait_for_selector(".city-card")
    page.wait_for_timeout(1200)
    page.screenshot(path=str(OUT / f"c04_agent_{name}.png"))
    nm = page.locator("#agent-card-title").inner_text()
    check(f"{name}: agent card opens from the directory", bool(nm), nm)
    check(f"{name}: deep link written", "agent=" in page.evaluate("() => location.hash"), page.evaluate("() => location.hash"))
    page.get_by_role("button", name="Details").click()
    page.wait_for_selector("dialog.city-details[open]")
    page.wait_for_timeout(300)
    page.screenshot(path=str(OUT / f"c05_details_activity_{name}.png"))
    axe(page, f"{name} details dialog")
    page.keyboard.press("ArrowRight")
    page.wait_for_timeout(200)
    check(f"{name}: arrow keys move between tabs", page.evaluate("() => document.activeElement?.id") == "tab-trades")
    page.screenshot(path=str(OUT / f"c05_details_trades_{name}.png"))
    page.get_by_role("tab", name="Stats").click()
    page.wait_for_timeout(200)
    page.screenshot(path=str(OUT / f"c05_details_stats_{name}.png"))
    page.keyboard.press("Escape")
    page.wait_for_timeout(200)
    check(f"{name}: Esc closes details", page.locator("dialog.city-details").count() == 0)
    check(f"{name}: no overflow with card open", overflow(page) <= 0, f"{overflow(page)} px")

    # click on the map: a building
    page.get_by_role("button", name="Close").first.click()
    page.get_by_role("button", name="Recenter").click()
    page.wait_for_timeout(200)

    # spanish
    page.get_by_role("button", name="ES", exact=True).click()
    page.wait_for_timeout(1300)
    page.screenshot(path=str(OUT / f"c06_es_{name}.png"))
    check(f"{name}: Spanish UI", page.locator(".city-dock-btn", has_text="Agentes").count() == 1)

    check(f"{name}: no console errors", not errors, " | ".join(errors[:5]))
    ctx.close()

    # deep link + reduced motion in a fresh context
    ctx = browser.new_context(viewport=viewport, locale="en-US", reduced_motion="reduce", device_scale_factor=1, is_mobile=mobile, has_touch=mobile)
    page = ctx.new_page()
    errs2 = []
    page.on("pageerror", lambda e: errs2.append(str(e)))
    page.add_init_script("localStorage.setItem('sf-city-welcome', '1')")
    first = page.request.get(f"{BASE}/api/city").json()["agents"][0]["id"]
    page.goto(f"{BASE}/#/city?agent={first}", wait_until="networkidle")
    page.wait_for_selector(".city-card", timeout=20000)
    check(f"{name}: deep link opens the agent", page.locator("#agent-card-title").count() == 1, page.locator("#agent-card-title").inner_text())
    page.wait_for_timeout(1500)
    page.screenshot(path=str(OUT / f"c07_reduced_motion_{name}.png"))
    check(f"{name}: reduced motion runs without errors", not errs2, " | ".join(errs2[:3]))
    ctx.close()
    browser.close()


with sync_playwright() as p:
    run(p, "desktop", {"width": 1440, "height": 900}, False)
    run(p, "mobile", {"width": 390, "height": 844}, True)

(OUT / "city_report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
fails = [c for c in report["checks"] if not c["ok"]]
print(f"\n{len(report['checks']) - len(fails)}/{len(report['checks'])} checks passed")
sys.exit(1 if fails else 0)

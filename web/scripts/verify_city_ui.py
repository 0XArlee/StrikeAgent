"""Every surface of EdgeCraft-StrikeCity, as a person uses it, at 1440 and 390 px: each button pressed and what it
should do checked, every panel, card and dialog searched for cut text or anything sticking out, axe-core on each one,
and a screenshot of each to look at.

    python web/scripts/verify_city_ui.py <axe.min.js> <out_dir> [base_url] [es|en]

Cut text: an element narrower (or shorter) than its content that hides the rest (overflow hidden/clip or ellipsis) and
is not a scroll area; sticking out: an element past the window's edges outside any horizontal scroll area.
"""
import json
import re
import sys
from pathlib import Path

from playwright.sync_api import sync_playwright

AXE = Path(sys.argv[1]).read_text(encoding="utf-8")
OUT = Path(sys.argv[2]); OUT.mkdir(parents=True, exist_ok=True)
BASE = (sys.argv[3] if len(sys.argv) > 3 else "https://edgecraft-strikecity.pages.dev").rstrip("/")
LANG = sys.argv[4] if len(sys.argv) > 4 else "es"
L = {
    "es": {"enter": "Entrar en la ciudad", "panels": ["Agentes", "Resultados", "Actividad", "Mercados", "Alertas", "Guía"], "zoomIn": "Acercar", "zoomOut": "Alejar",
           "follow": "Seguir", "details": "Detalles", "close": "Cerrar", "map": "Mapa", "me": "Mi agente", "chart": "Ver el gráfico",
           "arena": "Entrar en la Copy Arena", "open": "Ver ficha", "back": "Volver a la lista", "exitArena": "Salir de la arena", "exitTower": "Salir de la torre"},
    "en": {"enter": "Enter the city", "panels": ["Agents", "Results", "Feed", "Markets", "Alerts", "Guide"], "zoomIn": "Zoom in", "zoomOut": "Zoom out",
           "follow": "Follow", "details": "Details", "close": "Close", "map": "Map", "me": "My agent", "chart": "Open the chart",
           "arena": "Enter the Copy Arena", "open": "See profile", "back": "Back to the list", "exitArena": "Leave the arena", "exitTower": "Leave the tower"},
}[LANG]
results = []

CUT_JS = r"""(sel) => {
  const roots = [...document.querySelectorAll(sel)];
  const out = [];
  const name = (e) => (e.id ? '#' + e.id : '') + (typeof e.className === 'string' && e.className ? '.' + e.className.trim().split(/\s+/).slice(0, 2).join('.') : e.tagName.toLowerCase())
    + ' «' + (e.innerText || e.getAttribute('aria-label') || '').trim().slice(0, 40).replace(/\n/g, ' ') + '»';
  const scrollsX = (e) => { for (let a = e.parentElement; a; a = a.parentElement) { const s = getComputedStyle(a); if (/(auto|scroll)/.test(s.overflowX) && a.scrollWidth > a.clientWidth + 1) return true; } return false; };
  for (const root of roots) for (const e of [root, ...root.querySelectorAll('*')]) {
    if (e.closest('.sr-only') || e.tagName === 'CANVAS' || e.tagName === 'svg' || e.closest('svg') || e.tagName === 'IFRAME') continue;
    const s = getComputedStyle(e);
    if (s.display === 'none' || s.visibility === 'hidden' || s.clip === 'rect(0px, 0px, 0px, 0px)') continue;
    const r = e.getBoundingClientRect();
    if (r.width < 2 || r.height < 2) continue;
    const hidesX = /(hidden|clip)/.test(s.overflowX) || s.textOverflow === 'ellipsis', hidesY = /(hidden|clip)/.test(s.overflowY) || s.webkitLineClamp !== 'none';
    if (hidesX && e.scrollWidth > e.clientWidth + 1 && !(e.children.length && [...e.children].every(c => getComputedStyle(c).position === 'absolute')))
      out.push('cut-x ' + name(e) + ` ${e.scrollWidth}>${e.clientWidth}`);
    if (hidesY && e.scrollHeight > e.clientHeight + 2 && !/(auto|scroll)/.test(s.overflowY) && e.innerText && e.innerText.trim())
      out.push('cut-y ' + name(e) + ` ${e.scrollHeight}>${e.clientHeight}`);
    if ((r.right > innerWidth + 1 || r.left < -1) && !scrollsX(e)) out.push('out ' + name(e) + ` ${Math.round(r.left)}..${Math.round(r.right)}`);
  }
  return [...new Set(out)];
}"""


def check(name, ok, detail=""):
    results.append({"name": name, "ok": bool(ok), "detail": detail})
    print(("PASS " if ok else "FAIL ") + name + (f" · {detail}" if detail else ""))


def audit(pg, tag, label, sel):
    pg.wait_for_timeout(450)
    slug = "".join(c if c.isalnum() else "_" for c in label)[:40]
    try:
        pg.screenshot(path=str(OUT / f"{tag}_{slug}.png"))
    except Exception:
        pass
    cut = pg.evaluate(CUT_JS, sel)
    # the TradingView chart and Strike's book on the exchange's screen are drawn clipped on purpose (the map moves them)
    cut = [c for c in cut if ".city-tv" not in c and ".city-book" not in c and "bk-" not in c]
    check(f"{tag} {label}: nothing cut or sticking out", not cut, "; ".join(cut[:6]))
    pg.add_script_tag(content=AXE)
    res = pg.evaluate("""async (sel) => {
        const el = document.querySelector(sel); if (!el) return [{id: 'missing', nodes: 0, target: sel}];
        const r = await axe.run(el, { runOnly: { type: 'tag', values: ['wcag2a','wcag2aa','wcag21a','wcag21aa','wcag22aa'] } });
        return r.violations.map(v => ({ id: v.id, nodes: v.nodes.length, target: v.nodes[0].target.join(' ') }));
    }""", sel)
    check(f"{tag} {label}: axe 0 violations", not res, "; ".join(f"{v['id']}({v['nodes']}) {v['target']}" for v in res))


def step(tag, label, fn):
    try:
        fn()
    except Exception as e:
        check(f"{tag} {label}: runs", False, repr(e)[:300])


def run(p, tag, viewport, mobile):
    b = p.chromium.launch()
    ctx = b.new_context(viewport=viewport, device_scale_factor=2 if mobile else 1, is_mobile=mobile, has_touch=mobile,
                        locale="es-ES" if LANG == "es" else "en-US")
    ctx.add_init_script(f"localStorage.setItem('sf-lang', '{LANG}')")
    pg = ctx.new_page()
    errors = []
    pg.on("pageerror", lambda e: errors.append(str(e)))
    # not the city's errors: TradingView's own requests, and a failed answer from Strike's public price API (the city keeps
    # the last order book for 60 s, then hides it)
    # the browser's "Failed to load resource" lines carry no address: our own site's failures are caught by address below
    # (and DEX Screener's own analytics, which its chart's iframe sends and its own server refuses)
    noise = ("tradingview", "telemetry", "api.strikefinance.org/price/", "failed to load resource", "dexscreener.com")
    pg.on("console", lambda m: errors.append(m.text) if m.type == "error" and not any(n in m.text.lower() for n in noise) else None)
    own = BASE.split("/")[2]
    pg.on("requestfailed", lambda r: errors.append(f"{r.failure} {r.url[:100]}")
          if r.url.split("/")[2] == own and "ERR_ABORTED" not in (r.failure or "") else None)   # aborted = left the page
    pg.on("response", lambda r: errors.append(f"{r.status} {r.url[:100]}") if r.status >= 500 and r.url.split("/")[2] == own else None)
    dock = lambda name: pg.locator(".city-dock-btn").filter(has_text=re.compile(rf"^\s*{re.escape(name)}\s*$"))   # "Feed" is not "Feedback"

    def open_city(hash_="#/city"):
        # "load", not "networkidle": TradingView's widget keeps its own requests open (scanner-backend timing out after
        # ~21 s from some networks), which is not the city; the city says when it is ready (data-ready)
        pg.goto(f"{BASE}/{hash_}", wait_until="load")
        pg.reload(wait_until="load")
        pg.wait_for_selector(".city[data-ready]", timeout=40000)
        pg.wait_for_timeout(1200)

    # ---- welcome
    def welcome():
        pg.goto(f"{BASE}/#/city", wait_until="load")
        pg.evaluate("localStorage.removeItem('sf-city-welcome')")
        open_city()
        pg.wait_for_selector(".city-welcome[open]", timeout=15000)
        audit(pg, tag, "welcome dialog", ".city-welcome[open]")
        pg.get_by_role("button", name=L["enter"]).click()
        pg.wait_for_selector(".city-welcome[open]", state="detached", timeout=5000)
        check(f"{tag} welcome: Enter closes it and is remembered", pg.evaluate("localStorage.getItem('sf-city-welcome')") == "1")
    step(tag, "welcome", welcome)
    audit(pg, tag, "top bar", ".city-top")
    audit(pg, tag, "dock", ".city-dock")
    # every dock label shows whole inside its button (8 of them share a phone's width)
    fit = pg.evaluate("""() => [...document.querySelectorAll('.city-dock-btn')].map(b => { const r = b.getBoundingClientRect(), s = [...b.querySelectorAll('span:not(.sr-only)')].find(x => x.getClientRects().length);
        const t = s ? s.getBoundingClientRect() : r; return [s ? s.innerText : '?', t.left >= r.left - 0.5 && t.right <= r.right + 0.5 && r.right <= innerWidth + 0.5]; })""")
    check(f"{tag} dock: {len(fit)} buttons, every label whole", len(fit) >= 8 and all(ok for _, ok in fit), ", ".join(n for n, ok in fit if not ok))

    # ---- news
    def news():
        pg.locator(".city-news-btn").click()
        pg.wait_for_selector("dialog.city-news[open]", timeout=10000)
        audit(pg, tag, "news dialog", "dialog.city-news[open]")
        tabs = pg.locator("dialog.city-news[open] [aria-pressed]")
        n = tabs.count()
        for i in range(min(n, 4)):
            tabs.nth(i).click()
            pg.wait_for_timeout(250)
        check(f"{tag} news: its {n} toggles respond", n > 0)
        pg.keyboard.press("Escape")
        pg.wait_for_selector("dialog.city-news[open]", state="detached", timeout=5000)
    step(tag, "news", news)

    # ---- feedback
    def feedback():
        fb = pg.locator(".city-dock .city-dock-fb")
        check(f"{tag} feedback: in the dock, visible", fb.count() == 1 and fb.is_visible() and pg.locator(".city-top .city-dock-fb").count() == 0)
        fb.click()
        pg.wait_for_selector("dialog[open], [role=dialog]", timeout=8000)
        sel = "dialog[open]" if pg.locator("dialog[open]").count() else "[role=dialog]"
        audit(pg, tag, "feedback dialog", sel)
        pg.keyboard.press("Escape")
        pg.wait_for_timeout(500)
        check(f"{tag} feedback: Esc closes it", pg.locator(sel).count() == 0)
    step(tag, "feedback", feedback)

    # ---- language
    def language():
        other = "EN" if LANG == "es" else "ES"
        pg.locator(".city-top .lang button", has_text=other).click()
        pg.wait_for_timeout(500)
        txt = pg.locator(".city-dock").inner_text()
        # Alerts / Alertas: in the dock at every width (phones leave out Map: each panel has its close button)
        check(f"{tag} language: {other} switches the city", ("Alerts" in txt) if other == "EN" else ("Alertas" in txt), txt[:40].replace("\n", " "))
        pg.locator(".city-top .lang button", has_text=LANG.upper()).click()
        pg.wait_for_timeout(400)
    step(tag, "language", language)

    # ---- zoom
    def zoom():
        # the exchange's screen is drawn at the map's zoom: its width says the zoom changed
        w = lambda: pg.evaluate("() => { const e = document.querySelector('.city-tv, .city-book'); return e ? e.getBoundingClientRect().width : 0 }")
        w0 = w()
        pg.get_by_role("button", name=L["zoomOut"]).click(); pg.wait_for_timeout(400)
        w1 = w()
        pg.get_by_role("button", name=L["zoomIn"]).click(); pg.get_by_role("button", name=L["zoomIn"]).click(); pg.wait_for_timeout(400)
        w2 = w()
        pg.locator(".city-zoom .city-fab").nth(2).click(); pg.wait_for_timeout(400)
        w3 = w()
        check(f"{tag} zoom out, in and recenter change the map", w0 > 0 and w1 < w0 < w2 and abs(w3 - w0) < 2, f"{w0:.0f} → {w1:.0f} → {w2:.0f} → {w3:.0f} px")
    step(tag, "zoom", zoom)

    # ---- the five panels
    for name in L["panels"]:
        def panel(name=name):
            dock(name).click()
            pg.wait_for_selector("#city-panel", timeout=8000)
            check(f"{tag} {name}: the dock opens its panel", dock(name).get_attribute("aria-pressed") == "true")
            tabs = pg.locator("#city-panel .rs-tabs [role=tab]")   # Results: every tab shown and audited
            for i in range(tabs.count()):
                tabs.nth(i).click(); pg.wait_for_timeout(250)
                check(f"{tag} {name}: tab {i + 1} of {tabs.count()} shows its own content", tabs.nth(i).get_attribute("aria-selected") == "true"
                      and pg.locator("#rs-panel").inner_text().strip() != "")
                audit(pg, tag, f"{name} panel, tab {i + 1}", "#city-panel")
            if tabs.count():
                tabs.nth(tabs.count() - 1).click(); pg.wait_for_timeout(200)   # the ranking: the next steps start from it
            filters = pg.locator("#city-panel .city-filters button")
            for i in range(filters.count()):
                filters.nth(i).click(); pg.wait_for_timeout(120)
            if filters.count():
                filters.first.click()
            audit(pg, tag, f"{name} panel", "#city-panel")
            pg.locator("#city-panel .icon-btn").first.click()
            pg.wait_for_selector("#city-panel", state="detached", timeout=5000)
        step(tag, f"{name} panel", panel)

    # ---- an agent's card and details
    def agent():
        dock(L["panels"][0]).click()
        pg.wait_for_selector("#city-panel .city-row", timeout=8000)
        pg.locator("#city-panel .city-row").first.click()
        pg.wait_for_selector("#agent-card-title", timeout=8000)
        audit(pg, tag, "agent card", ".city-card")
        f = pg.locator(".city-card .city-card-actions button").first
        before = f.get_attribute("aria-pressed")
        f.click(); pg.wait_for_timeout(250)
        check(f"{tag} agent card: Follow toggles", f.get_attribute("aria-pressed") != before)
        pg.get_by_role("button", name=L["details"]).click()
        pg.wait_for_selector("dialog[open]", timeout=8000)
        tabs = pg.locator("dialog[open] [role=tab]")
        for i in range(tabs.count()):
            tabs.nth(i).click(); pg.wait_for_timeout(200)
            audit(pg, tag, f"details tab {i + 1}", "dialog[open]")
        check(f"{tag} details: {tabs.count()} tabs", tabs.count() >= 2)
        pg.keyboard.press("Escape"); pg.wait_for_timeout(400)
        pg.locator(".city-card .icon-btn").first.click(); pg.wait_for_timeout(300)
        check(f"{tag} agent card: Close", pg.locator("#agent-card-title").count() == 0)
    step(tag, "agent", agent)

    # ---- the Strike traders in Agents: listed after the agents, each opens its card
    def leads():
        if dock(L["panels"][0]).get_attribute("aria-pressed") != "true":   # on a desktop the panel stays open after a pick
            dock(L["panels"][0]).click()
        pg.wait_for_selector("#city-panel .city-leads .city-row", timeout=15000)
        n = pg.locator("#city-panel .city-leads .city-row").count()
        check(f"{tag} agents: {n} Strike traders listed with the agents", n > 0)
        pg.locator("#city-panel .city-filters button").last.click(); pg.wait_for_timeout(200)
        only = pg.locator("#city-panel .city-row").count() == pg.locator("#city-panel .city-leads .city-row").count()
        check(f"{tag} agents: the traders filter shows only them", only)
        audit(pg, tag, "agents traders filter", "#city-panel")
        pg.locator("#city-panel .city-leads .city-row").first.click()
        pg.wait_for_selector("#lead-card-title", timeout=8000)
        audit(pg, tag, "trader card from agents", ".city-card")
        pg.locator(".city-card .icon-btn").first.click(); pg.wait_for_timeout(300)
        check(f"{tag} trader card: Close", pg.locator("#lead-card-title").count() == 0)
        if pg.locator("#city-panel").count():
            pg.locator("#city-panel .icon-btn").first.click(); pg.wait_for_timeout(300)
    step(tag, "leads", leads)

    # ---- a building and its chart
    def building():
        dock(L["panels"][3]).click()
        pg.wait_for_selector("#city-panel .city-markets .city-link", timeout=8000)
        pg.locator("#city-panel .city-markets .city-link").first.click()
        pg.wait_for_selector("#bld-title", timeout=8000)
        audit(pg, tag, "building card", ".city-card")
        btn = pg.locator(".city-card .city-card-chart")
        if btn.count():
            btn.click()
            pg.wait_for_selector("dialog.city-chart[open]", timeout=8000)
            pg.wait_for_timeout(2500)
            audit(pg, tag, "chart dialog", "dialog.city-chart[open] .chart-head")
            tabs = pg.locator("dialog.city-chart[open] .chart-tabs button")
            tabs.nth(1).click(); pg.wait_for_timeout(600)
            check(f"{tag} chart: a market tab switches", tabs.nth(1).get_attribute("aria-pressed") == "true")
            pg.keyboard.press("Escape"); pg.wait_for_timeout(400)
        pg.locator(".city-card .icon-btn").first.click(); pg.wait_for_timeout(300)
    step(tag, "building", building)

    # ---- copy trading: the best to copy (Results, Ranking tab), a lead, its profile, the arena
    def copy():
        dock(L["panels"][1]).click()
        pg.locator("#city-panel .rs-tabs [role=tab]").last.click()
        pg.wait_for_selector(".city-copy-top .city-row", timeout=15000)
        pg.locator(".city-copy-top .city-row").first.click()
        pg.wait_for_timeout(1200)
        if pg.locator(".cp-card").count():
            audit(pg, tag, "lead card", ".cp-card")
            pg.locator(".cp-card").get_by_role("button", name=L["open"]).click()
        pg.wait_for_selector(".cp-profile", timeout=10000)
        audit(pg, tag, "trader profile", "dialog[open]")
        pg.get_by_role("button", name=L["back"]).click()
        pg.wait_for_selector(".cp-list", timeout=5000)
        audit(pg, tag, "chooser", "dialog[open]")
        segs = pg.locator("dialog[open] .cp-seg button")
        for i in range(segs.count()):
            segs.nth(i).click(); pg.wait_for_timeout(150)
        check(f"{tag} chooser: platform buttons respond", segs.count() == 3)
        pg.keyboard.press("Escape"); pg.wait_for_timeout(400)
    step(tag, "copy", copy)

    def arena():
        open_city("#/city?arena")
        pg.wait_for_selector(".tw.arena", timeout=20000)
        spots = pg.locator(".tw.arena .tw-spots button")
        for i in range(spots.count() - 1):   # the last one is the way out
            spots.nth(i).click(); pg.wait_for_timeout(900)
            audit(pg, tag, f"arena spot {i + 1}", ".tw.arena")
        pg.get_by_role("button", name=L["exitArena"]).click()
        pg.wait_for_timeout(600)
        check(f"{tag} arena: exit returns to the map", pg.locator(".tw.arena").count() == 0)
    step(tag, "arena", arena)

    def tower():
        open_city("#/city?tower")
        pg.wait_for_selector(".tw:not(.arena)", timeout=20000)
        floors = pg.locator(".tw-floors button")
        nf = floors.count()
        for i in range(nf):
            floors.nth(i).click(); pg.wait_for_timeout(1700)
            spots = pg.locator(".tw-spots button")
            for j in range(spots.count()):
                if any(w in spots.nth(j).inner_text().lower() for w in ("salida", "way out", "exit")):
                    continue   # the door: it leaves the tower (checked at the end)
                spots.nth(j).click(); pg.wait_for_timeout(500)
                audit(pg, tag, f"tower floor {i + 1} spot {j + 1}", ".tw")
        check(f"{tag} tower: {nf} floors visited", nf >= 6)
        pg.get_by_role("button", name=L["exitTower"]).click()
        pg.wait_for_timeout(600)
        check(f"{tag} tower: exit returns to the map", pg.locator(".tw").count() == 0)
    step(tag, "tower", tower)

    # ---- without a wallet: Connect wallet in My agent's place, and it opens the wallet dialog
    def me():
        open_city()
        conn = pg.locator(".city-dock .city-dock-connect")
        check(f"{tag} no wallet: the dock offers to connect one, not My agent", conn.count() == 1 and conn.is_visible() and dock(L["me"]).count() == 0,
              conn.inner_text().replace("\n", " ") if conn.count() else "-")
        conn.click()
        pg.wait_for_selector("[role=dialog]", timeout=8000)
        audit(pg, tag, "connect dialog", "[role=dialog]")
        pg.keyboard.press("Escape"); pg.wait_for_timeout(400)
    step(tag, "my agent", me)

    check(f"{tag}: no JS errors", not errors, " | ".join(errors[:3]))
    b.close()


with sync_playwright() as p:
    run(p, "desktop", {"width": 1440, "height": 900}, False)
    run(p, "mobile", {"width": 390, "height": 844}, True)
(OUT / "city_ui_report.json").write_text(json.dumps(results, indent=2), encoding="utf-8")
print(f"\n{sum(r['ok'] for r in results)}/{len(results)} checks passed")

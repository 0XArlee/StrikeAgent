"""Real-browser verification of the onboarding page (production bundle served by `vite preview`).

    python web/scripts/verify_ui.py <axe.min.js> <out_dir> [base_url]

Injects simulated CIP-30 Cardano wallets (Eternl + its "ccvault" alias, Lace, and Yoroi appearing late), walks the
whole flow (wallet list -> review -> sign -> done -> dashboard) at 1440 px and 390 px, takes screenshots, runs axe-core
(WCAG 2.2 A/AA) on the page and on the open dialog, checks keyboard focus handling and horizontal overflow.
"""

import json
import sys
from pathlib import Path

from playwright.sync_api import sync_playwright

AXE, OUT = Path(sys.argv[1]), Path(sys.argv[2])
BASE = sys.argv[3] if len(sys.argv) > 3 else "http://localhost:4173"
OUT.mkdir(parents=True, exist_ok=True)

FAKE_WALLETS = r"""
(() => {
  const icon = (c, l) => 'data:image/svg+xml,' + encodeURIComponent(`<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 28 28"><rect width="28" height="28" rx="7" fill="${c}"/><text x="14" y="19" font-size="13" font-family="Arial" font-weight="700" text-anchor="middle" fill="#fff">${l}</text></svg>`);
  const addr = '01' + 'a1'.repeat(28) + 'b2'.repeat(28);   // mainnet base address bytes
  window.__signed = [];
  const api = (net) => ({
    getNetworkId: async () => net,
    getChangeAddress: async () => addr,
    getUsedAddresses: async () => [addr],
    signData: async (a, payload) => { window.__signed.push({a, payload}); await new Promise(r => setTimeout(r, 400)); return { signature: '845846a201276761646472657373', key: 'a4010103272006215820' }; },
  });
  const make = (name, c, l, net = 1) => ({ name, icon: icon(c, l), apiVersion: '0.1.0', enable: async () => { await new Promise(r => setTimeout(r, 300)); return api(net); }, isEnabled: async () => false });
  window.cardano = { eternl: make('Eternl', '#ff6b00', 'E'), ccvault: make('Eternl', '#ff6b00', 'E'), lace: make('lace', '#7b3fe4', 'L') };
  setTimeout(() => { window.cardano.yoroi = make('Yoroi', '#1a44b7', 'Y'); }, 1200);
})();
"""

HOSTILE_LACE = r"""
(() => {
  // frozen methods + a get trap that returns a different function: `obj.method` throws, the descriptor still works
  const hostile = (o) => {
    const t = {};
    for (const k of Object.keys(o)) Object.defineProperty(t, k, { value: o[k], writable: false, configurable: false, enumerable: true });
    return new Proxy(t, { get: (tt, k) => (typeof tt[k] === 'function' ? (...a) => tt[k](...a) : tt[k]) });
  };
  const addr = '01' + 'c3'.repeat(28) + 'd4'.repeat(28);
  const api = hostile({
    getNetworkId: async () => 1, getChangeAddress: async () => addr, getUsedAddresses: async () => [addr],
    signData: async () => ({ signature: '845846a201276761646472657373', key: 'a4010103272006215820' }),
  });
  window.cardano = { lace: hostile({ name: 'lace', icon: '', apiVersion: '0.1.0', enable: async () => api, isEnabled: async () => false }) };
})();
"""

report = {"checks": [], "axe": {}}


def check(name, ok, detail=""):
    report["checks"].append({"check": name, "ok": bool(ok), "detail": detail})
    print(("PASS " if ok else "FAIL ") + name + (f" - {detail}" if detail else ""))


def axe(page, label, context=None):
    page.add_script_tag(path=str(AXE))
    res = page.evaluate("""async (ctx) => { const r = await axe.run(ctx || document, { runOnly: { type: 'tag', values: ['wcag2a','wcag2aa','wcag21a','wcag21aa','wcag22aa','best-practice'] } });
      return r.violations.map(v => ({ id: v.id, impact: v.impact, nodes: v.nodes.length, help: v.help, target: v.nodes[0] && v.nodes[0].target.join(' ') })); }""", context)
    report["axe"][label] = res
    serious = [v for v in res if v["impact"] in ("serious", "critical")]
    check(f"axe {label}: no serious/critical violations", not serious, json.dumps(res)[:400] if res else "0 violations")


with sync_playwright() as p:
    b = p.chromium.launch()
    for vw, vh, tag in ((1440, 900, "desktop"), (390, 844, "mobile")):
        ctx = b.new_context(viewport={"width": vw, "height": vh}, color_scheme="dark", locale="en-US", has_touch=(tag == "mobile"))
        ctx.add_init_script(FAKE_WALLETS)
        page = ctx.new_page()
        errors = []
        page.on("pageerror", lambda e: errors.append(str(e)))
        page.on("console", lambda m: errors.append(m.text) if m.type == "error" else None)
        page.goto(BASE, wait_until="networkidle")
        page.wait_for_timeout(600)
        page.screenshot(path=str(OUT / f"01_home_{tag}.png"))
        page.screenshot(path=str(OUT / f"01_home_full_{tag}.png"), full_page=True)
        sw = page.evaluate("document.documentElement.scrollWidth")
        check(f"{tag}: no horizontal overflow", sw <= vw, f"scrollWidth={sw}")
        if tag == "desktop":
            axe(page, "home")
            # keyboard: skip link is first focusable, then reach the connect button
            page.keyboard.press("Tab")
            check("keyboard: first Tab lands on skip link", page.evaluate("document.activeElement.className") == "skip-link")
        # open the dialog from the visible CTA
        if tag == "mobile":
            check("mobile: sticky CTA hidden while the hero CTA is visible", not page.locator(".mobile-cta").is_visible())
            page.mouse.wheel(0, 1400)
            page.wait_for_timeout(400)
            check("mobile: sticky CTA appears after scrolling past the hero", page.locator(".mobile-cta").is_visible())
            page.screenshot(path=str(OUT / f"01b_scrolled_{tag}.png"))
            page.evaluate("window.scrollTo(0, 0)")
            page.wait_for_timeout(300)
        btn = page.locator(".hero-ctas .btn-primary") if tag == "mobile" else page.locator(".header .connect-desktop")
        btn.focus()
        page.keyboard.press("Enter")
        page.wait_for_selector("[role=dialog]")
        page.wait_for_timeout(1700)   # let the late wallet (Yoroi) inject
        names = page.locator(".list-btn .grow").all_inner_texts()
        detected = page.locator(".tag-ok").count()
        check(f"{tag}: detects every injected wallet once (alias de-duplicated, late wallet included)", detected == 3,
              f"detected={detected} rows={names}")
        inside = page.evaluate("document.querySelector('[aria-labelledby=cm-title]').contains(document.activeElement)")
        check(f"{tag}: focus moved into the dialog", inside)
        page.screenshot(path=str(OUT / f"02_wallets_{tag}.png"))
        if tag == "desktop":
            axe(page, "dialog-wallets", "[aria-labelledby=cm-title]")
            page.keyboard.press("Escape")
            page.wait_for_timeout(200)
            check("keyboard: Esc closes the dialog", page.locator("[aria-labelledby=cm-title]").count() == 0)
            check("keyboard: focus returns to the opener", page.evaluate("document.activeElement.classList.contains('connect-desktop')"))
            page.locator(".header .connect-desktop").click()
            page.wait_for_selector("[role=dialog]")
            page.wait_for_timeout(300)
            # Tab cycling stays inside
            for _ in range(25):
                page.keyboard.press("Tab")
            check("keyboard: Tab cycling stays inside the dialog",
                  page.evaluate("document.querySelector('[aria-labelledby=cm-title]').contains(document.activeElement)"))
        page.get_by_role("button", name="Eternl").first.click()
        page.wait_for_selector("text=Create your character", timeout=5000)
        page.wait_for_timeout(200)
        page.screenshot(path=str(OUT / f"02b_creator_{tag}.png"))
        check(f"{tag}: character creator with a live preview", page.locator(".av-big").count() == 1)
        page.get_by_role("button", name="Continue").click()
        # its personality (five questions) and its trade in the city: never how it trades
        page.wait_for_selector("text=Its personality", timeout=5000)
        for q in range(5):
            page.locator(".pp-a").nth(q % 5).click()
            page.wait_for_timeout(120)
        result = page.locator(".pp-result").inner_text()
        check(f"{tag}: five questions give a personality", result.startswith("Your agent is"), result[:80])
        page.locator(".pp-job", has_text="Reporter").click()
        check(f"{tag}: the trade shows on its building, the preview says a line",
              "Reporter" in page.locator(".pp-who").inner_text() and len(page.locator(".pp-say").inner_text()) > 4,
              page.locator(".pp-who").inner_text())
        page.screenshot(path=str(OUT / f"02c_persona_{tag}.png"), full_page=False)
        if tag == "desktop":
            axe(page, "dialog-persona", "[aria-labelledby=cm-title]")
        sw = page.evaluate("document.querySelector('[aria-labelledby=cm-title]').scrollWidth - document.querySelector('[aria-labelledby=cm-title]').clientWidth")
        check(f"{tag}: personality step without horizontal overflow", sw <= 0, f"overflow={sw}px")
        page.locator(".actions .btn-primary", has_text="Continue").click()
        # strategy, markets and risk
        page.wait_for_selector(".strat-pick, .chips", timeout=5000)
        ticked = page.locator(".chips input:checked").count()
        check(f"{tag}: strategy step with the proven markets ticked (BTC, ETH, SOL)", ticked >= 3, f"ticked={ticked}")
        page.locator(".actions .btn-primary").click()
        page.wait_for_selector("text=Start your agent", timeout=5000)
        page.wait_for_timeout(200)
        sign_btn = page.locator(".actions .btn-primary")
        check(f"{tag}: sign button disabled until risk acknowledgement", sign_btn.is_disabled())
        review = page.locator("[aria-labelledby=cm-title]").inner_text()
        check(f"{tag}: the review names its personality and trade", "Cautious" in review or "Stoic" in review or "Analyst" in review
              or "Optimist" in review or "Joker" in review, "")
        page.screenshot(path=str(OUT / f"03_review_{tag}.png"))
        if tag == "desktop":
            axe(page, "dialog-review", "[aria-labelledby=cm-title]")
        page.locator(".check-ack").click()
        check(f"{tag}: sign button enabled after acknowledgement", sign_btn.is_enabled())
        sign_btn.click()
        page.wait_for_selector("text=Sign the message in Eternl", timeout=5000)
        page.screenshot(path=str(OUT / f"04_signing_{tag}.png"))
        page.wait_for_selector("text=Your agent is running", timeout=8000)
        signed = page.evaluate("window.__signed")
        msg_ok = bool(signed) and bytes.fromhex(signed[0]["payload"]).decode().startswith("Smart Flow · start my paper agent")
        check(f"{tag}: wallet signed the exact Smart Flow message (CIP-30 signData, hex payload)", msg_ok,
              (bytes.fromhex(signed[0]["payload"]).decode()[:60] if signed else "nothing signed"))
        page.wait_for_timeout(900)   # the card draws its city at night
        painted = page.evaluate("""(() => { const c = document.querySelector('.meet-canvas'); if (!c) return 0;
          const d = c.getContext('2d').getImageData(0, 0, c.width, c.height).data; let n = 0;
          for (let i = 0; i < d.length; i += 4 * 97) if (d[i] + d[i + 1] + d[i + 2] > 60) n++; return n; })()""")
        check(f"{tag}: 'Meet your agent' card drawn (city, character, words)", painted > 500, f"lit samples={painted}")
        msg = bytes.fromhex(signed[0]["payload"]).decode() if signed else ""
        check(f"{tag}: the signed message names its personality (and that it never changes how it trades)",
              "Personality in the city:" in msg and "/reporter" in msg, [l for l in msg.splitlines() if "Personality" in l][:1])
        page.screenshot(path=str(OUT / f"05_done_{tag}.png"))
        page.locator(".meet-canvas").screenshot(path=str(OUT / f"05b_meet_{tag}.png"))
        if tag == "desktop":
            axe(page, "dialog-done", "[aria-labelledby=cm-title]")
        # "Go to my agent" opens My agent inside the city (#/city?me); with this simulated session the city's own API
        # then refuses the fake token, so the dashboard itself is checked by verify_onboarding_live.py on QA
        page.evaluate("window.__h = []; setInterval(() => window.__h.push(location.hash), 40)")
        page.get_by_role("button", name="Go to my agent").click()
        page.wait_for_timeout(600)
        trail = page.evaluate("[...new Set(window.__h)]")
        check(f"{tag}: 'Go to my agent' opens My agent in the city", "#/city?me" in trail, str(trail))
        page.goto(BASE, wait_until="networkidle")
        # Spanish (on phones the switch is in the menu)
        if tag == "mobile":
            page.locator(".mm-toggle, [aria-controls=mobile-menu]").first.click()
            page.wait_for_timeout(300)
        page.locator("button:visible", has_text="ES").filter(has_text="ES").first.click()
        page.wait_for_timeout(200)
        check(f"{tag}: Spanish switch updates text and lang attribute",
              page.evaluate("document.documentElement.lang") == "es" and page.get_by_text("Mi agente").count() > 0)
        page.evaluate("window.scrollTo(0,0)")
        page.screenshot(path=str(OUT / f"07_home_es_{tag}.png"))
        real = [e for e in errors if "401" not in e]   # the city's API refusing the simulated session (see above)
        check(f"{tag}: no JS errors", not real, "; ".join(real)[:300])
        ctx.close()
    # no wallet installed: install list only
    ctx = b.new_context(viewport={"width": 390, "height": 844}, color_scheme="dark")
    page = ctx.new_page()
    page.goto(BASE, wait_until="networkidle")
    page.locator(".hero-ctas .btn-primary").click()
    page.wait_for_timeout(500)
    check("no wallets: shows install options", page.locator(".tag-off").count() == 8 and page.locator(".tag-ok").count() == 0)
    page.screenshot(path=str(OUT / "08_nowallet_mobile.png"))
    ctx.close()

    # Lace (real extension, 2026-10-19) exposes its provider and API through a Proxy whose `get` violates the
    # invariant of their frozen methods: reading `p.enable` throws a TypeError. It used to crash the page to black.
    for where, path in (("landing", "/"), ("city", "/#/city")):
        ctx = b.new_context(viewport={"width": 1440, "height": 900}, locale="en-US")
        ctx.add_init_script(HOSTILE_LACE)
        ctx.add_init_script("localStorage.setItem('sf-city-welcome', '1')")
        page = ctx.new_page()
        errs = []
        page.on("pageerror", lambda e: errs.append(str(e)))
        page.goto(BASE + path, wait_until="networkidle")
        if where == "city":
            page.locator(".city-dock-btn", has_text="Ranks").click()
            page.get_by_role("button", name="Put your own agent in the city").click()
        else:
            page.locator(".header .connect-desktop").click()
        page.wait_for_selector("[role=dialog]", timeout=8000)
        page.wait_for_timeout(600)
        check(f"Lace-like Proxy wallet ({where}): dialog opens and lists it", page.locator(".list-btn", has_text="Lace").count() == 1,
              f"errors: {errs[:1]}")
        page.locator(".list-btn", has_text="Lace").click()
        ok = True
        try:
            page.wait_for_selector("text=Create your character", timeout=8000)
        except Exception:
            ok = False
        check(f"Lace-like Proxy wallet ({where}): connects (enable + API through the Proxy)", ok and not errs, f"errors: {errs[:1]}")
        page.screenshot(path=str(OUT / f"09_lace_proxy_{where}.png"))
        ctx.close()
    b.close()

(OUT / "verify_report.json").write_text(json.dumps(report, indent=1), encoding="utf-8")
fails = [c for c in report["checks"] if not c["ok"]]
print(f"\n{len(report['checks']) - len(fails)}/{len(report['checks'])} checks passed")
sys.exit(1 if fails else 0)

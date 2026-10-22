"""Real-browser end-to-end check of the paper onboarding against the real site API (wrangler pages dev or production).

    python web/scripts/verify_onboarding_live.py <axe.min.js> <out_dir> <base_url>

A CIP-30 test wallet is injected into the page; its signData() is answered by a real Ed25519 key in Python
(cip30_test_wallet.py), so the server verifies a genuine signature. The flow, at 1440 and 390 px: open EdgeCraft-StrikeCity ->
"Put your own agent in the city" -> wallet -> review (name, markets, risk, show in the city) -> sign -> done ->
"See it in EdgeCraft-StrikeCity" (the city selects the new agent) -> My agent -> hide -> delete. axe-core on each dialog.
On a site that offers builder connect (the QA site, Strike testnet) My agent also connects to Strike and stops again.
The test agent is deleted at the end; its wallet never held anything.
"""

import json
import re
import sys
import urllib.request
from pathlib import Path

from playwright.sync_api import sync_playwright

sys.path.insert(0, str(Path(__file__).parent))
from cip30_test_wallet import TestWallet  # noqa: E402

AXE, OUT, BASE = Path(sys.argv[1]), Path(sys.argv[2]), sys.argv[3].rstrip("/")
OUT.mkdir(parents=True, exist_ok=True)
report = {"checks": [], "axe": {}}
with urllib.request.urlopen(urllib.request.Request(BASE + "/api/info", headers={"User-Agent": "smartflow-verify/1.0"}), timeout=30) as r:
    INFO = json.loads(r.read())
NET = 0 if INFO.get("env") == "testnet" else 1    # the QA site is the testnet world (Preprod wallets)
LIVE = (INFO.get("live") or {}).get("enabled", False)

WALLET_JS = r"""
(addrHex, net) => {
  const icon = 'data:image/svg+xml,' + encodeURIComponent('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 28 28"><rect width="28" height="28" rx="7" fill="#0033ad"/><text x="14" y="19" font-size="13" font-family="Arial" font-weight="700" text-anchor="middle" fill="#fff">T</text></svg>');
  const api = {
    getNetworkId: async () => net,
    getChangeAddress: async () => window.__twAddr || addrHex,    // a test may switch the selected account
    getUsedAddresses: async () => [window.__twAddr || addrHex],
    signData: async (a, payload) => { const [signature, key] = (await window.pySign(payload)).split(':'); return { signature, key }; },
  };
  window.cardano = { testwallet: { name: 'TestWallet', icon, apiVersion: '0.1.0', enable: async () => api, isEnabled: async () => true } };
}
"""


def check(name, ok, detail=""):
    report["checks"].append({"name": name, "ok": bool(ok), "detail": detail})
    print(("PASS " if ok else "FAIL ") + name + (f" · {detail}" if detail else ""))


def axe(page, label, selector):
    page.add_script_tag(path=str(AXE))
    res = page.evaluate("""async (sel) => {
        const r = await axe.run(sel, { runOnly: { type: 'tag', values: ['wcag2a','wcag2aa','wcag21a','wcag21aa','wcag22aa'] } });
        return r.violations.map(v => ({ id: v.id, nodes: v.nodes.length, target: v.nodes[0].target }));
    }""", selector)
    report["axe"][label] = res
    check(f"axe {label}: 0 violations", not res, "; ".join(f"{v['id']}({v['nodes']}) {v['target']}" for v in res))


def run(p, tag, viewport, mobile):
    w = TestWallet(network=NET, base=True)
    browser = p.chromium.launch()
    ctx = browser.new_context(viewport=viewport, locale="en-US", device_scale_factor=2 if mobile else 1, is_mobile=mobile, has_touch=mobile)
    ctx.add_init_script("localStorage.setItem('sf-city-welcome', '1')")
    page = ctx.new_page()
    errors = []
    page.on("pageerror", lambda e: errors.append(str(e)))
    page.on("console", lambda m: errors.append(m.text) if m.type == "error" and "telemetry.tradingview.com" not in m.text else None)   # TradingView's own telemetry is not ours
    signed = []

    def py_sign(payload_hex):
        msg = bytes.fromhex(payload_hex)
        signed.append(msg.decode())
        return w.sign_data(msg)

    page.expose_function("pySign", py_sign)
    page.add_init_script(f"({WALLET_JS})('{w.addr_bytes.hex()}', {NET})")
    page.goto(f"{BASE}/#/city", wait_until="networkidle")
    page.wait_for_selector(".city-dock-btn", timeout=30000)
    page.wait_for_timeout(1200)
    page.screenshot(path=str(OUT / f"o01_city_{tag}.png"))
    n0 = page.evaluate("() => fetch('/api/city').then(r => r.json()).then(d => d.agents.length)")
    check(f"{tag}: city loads its agents from the site API", n0 >= 1, f"{n0} agents")

    page.locator(".city-dock-btn", has_text="Ranks").click()
    page.get_by_role("button", name="Put your own agent in the city").click()
    page.wait_for_selector("[role=dialog]")
    page.get_by_role("button", name="TestWallet").click()
    page.wait_for_selector("text=Create your character", timeout=10000)
    page.wait_for_timeout(400)
    check(f"{tag}: the character creator opens after the wallet", page.locator(".av-big").count() == 1)
    page.screenshot(path=str(OUT / f"o02a_creator_{tag}.png"))
    axe(page, f"{tag} character creator", "[role=dialog]")
    # make a character: another hairstyle in its second colour, an accessory
    page.get_by_role("tab", name="Hair").click()
    page.locator(".av-tile").nth(3).click()
    page.locator(".av-swatch").nth(1).click()
    chosen_hair = page.locator("input[name='cm-av-hair-colour']:checked").get_attribute("value")
    page.get_by_role("tab", name="Accessories").click()
    page.locator(".av-tile").nth(2).click()
    page.wait_for_timeout(200)
    chosen_acc = page.locator("input[name='cm-av-acc-colour']:checked").get_attribute("value")
    page.wait_for_timeout(300)
    page.screenshot(path=str(OUT / f"o02b_creator_custom_{tag}.png"))
    focus_ok = page.evaluate("() => document.activeElement && document.activeElement.closest('.av-tile') !== null")
    check(f"{tag}: choosing a tile keeps the keyboard focus on it", focus_ok)
    page.fill("#cm-name", "Smart Flow")
    page.get_by_role("button", name="Continue").click()                  # character -> personality
    page.wait_for_selector("text=Its personality", timeout=10000)
    for q in range(5):                                                    # the five questions
        page.locator(".pp-a").nth((q * 2) % 5).click()
        page.wait_for_timeout(120)
    page.locator(".pp-job", has_text="Tape reader").click()
    temper_name = page.locator(".pp-who b").inner_text()
    want_persona = {"temper": {"Stoic": "stoic", "Analyst": "analyst", "Optimist": "optimist", "Joker": "joker", "Cautious": "cautious"}[temper_name],
                    "job": "tape"}
    check(f"{tag}: the quiz gives a personality and the trade is chosen", page.locator(".pp-result").inner_text().startswith("Your agent is")
          and "Tape reader" in page.locator(".pp-who").inner_text(), page.locator(".pp-who").inner_text())
    page.screenshot(path=str(OUT / f"o02p_persona_{tag}.png"))
    axe(page, f"{tag} personality step", "[aria-labelledby=cm-title]")
    page.locator(".actions .btn-primary", has_text="Continue").click()  # personality -> strategy
    page.wait_for_selector("text=Choose your strategy", timeout=10000)
    ticked = page.evaluate("() => [...document.querySelectorAll('[role=dialog] .chips input')].filter(i => i.checked)"
                           ".map(i => i.parentElement.textContent.trim())")
    check(f"{tag}: the strategy's own markets come ticked (BTC, ETH, SOL)", sorted(ticked) == ["BTC", "ETH", "SOL"], str(ticked))
    check(f"{tag}: opened from the city, 'show in EdgeCraft-StrikeCity' comes ticked", page.locator(".check-public input").is_checked())
    want = "pyramid" if tag == "desktop" else "smartflow"
    if want == "pyramid":
        page.locator(".sp-card", has_text="Smart Flow Pyramid").click()
    check(f"{tag}: picking a strategy shows its numbers", page.locator(".sp-card.on .sp-stats").count() == 1)
    page.wait_for_timeout(300)
    page.screenshot(path=str(OUT / f"o02c_strategy_{tag}.png"))
    axe(page, f"{tag} strategy step", "[role=dialog]")
    page.get_by_role("button", name="Continue").click()                  # strategy -> review
    page.wait_for_selector("text=Start your agent", timeout=10000)
    check(f"{tag}: the mode is explained before signing", page.locator("[role=dialog] .alert-info").count() == 1)
    review = page.locator("[role=dialog]").inner_text()
    check(f"{tag}: the review shows the chosen strategy and markets", ("Smart Flow Pyramid" in review) == (want == "pyramid")
          and "BTC · ETH · SOL" in review, review[:160].replace(chr(10), " | "))
    page.locator(".check-ack").click()
    page.locator(".actions .btn-primary").click()
    page.wait_for_selector(".field-err", timeout=10000)
    check(f"{tag}: reserved name refused by the server, back on the character step", "reserved" in page.locator(".field-err").inner_text()
          and page.locator(".av-big").count() == 1)
    name = f"QA Test {tag[:1].upper()}"   # throwaway agent, deleted at the end of the run
    page.fill("#cm-name", name)
    page.get_by_role("button", name="Continue").click()                  # the personality and strategy picked before are kept
    page.wait_for_selector("text=Its personality", timeout=10000)
    check(f"{tag}: the personality chosen is kept", temper_name in page.locator(".pp-who").inner_text())
    page.locator(".actions .btn-primary", has_text="Continue").click()
    page.wait_for_selector("text=Choose your strategy", timeout=10000)
    page.get_by_role("button", name="Continue").click()
    page.wait_for_selector("text=Start your agent", timeout=10000)
    page.screenshot(path=str(OUT / f"o02_review_{tag}.png"))
    axe(page, f"{tag} review dialog", "[role=dialog]")
    page.locator(".actions .btn-primary").click()
    if LIVE:   # creating the agent connects it to Strike: the only signature is Strike's builder message
        env = INFO["live"]["env"]
        try:
            page.wait_for_selector(f"text=Your agent is starting on your Strike {env} account", timeout=40000)
        except Exception:
            page.screenshot(path=str(OUT / f"o03_create_failed_{tag}.png"))
            print("create failed:", page.locator("[aria-labelledby=cm-title]").inner_text()[:400].replace(chr(10), " | "))
            raise
        check(f"{tag}: the only signature is Strike's builder connect", len(signed) == 1
              and signed[-1].startswith(f'Connect to Strike via builder "{INFO["live"]["code"]}"') and "0.2% fee" in signed[-1]
              and w.address in signed[-1], signed[-1][:70] if signed else "nothing signed")
    else:
        page.wait_for_selector("text=Your agent is running", timeout=15000)
        check(f"{tag}: the wallet signed the exact Smart Flow message", bool(signed) and signed[-1].startswith("Smart Flow · start my paper agent")
              and f"Agent name: {name}" in signed[-1] and "cannot move funds" in signed[-1], signed[-1][:70] if signed else "nothing signed")
    page.wait_for_timeout(1200)   # the card draws its city at night
    painted = page.evaluate("""(() => { const c = document.querySelector('.meet-canvas'); if (!c) return 0;
      const d = c.getContext('2d').getImageData(0, 0, c.width, c.height).data; let n = 0;
      for (let i = 0; i < d.length; i += 4 * 97) if (d[i] + d[i + 1] + d[i + 2] > 60) n++; return n; })()""")
    check(f"{tag}: 'Meet your agent' card drawn", painted > 500, f"lit samples={painted}")
    if not LIVE:
        check(f"{tag}: the signed message names its personality", f"Personality in the city: {want_persona['temper']}/tape" in signed[-1])
    page.screenshot(path=str(OUT / f"o03_done_{tag}.png"))
    page.locator(".meet-canvas").screenshot(path=str(OUT / f"o03b_meet_{tag}.png"))
    axe(page, f"{tag} done dialog", "[role=dialog]")
    page.get_by_role("button", name="See it in EdgeCraft-StrikeCity").click()
    page.wait_for_selector("#agent-card-title", timeout=45000)
    page.wait_for_timeout(1500)
    card = page.locator(".city-card").inner_text()
    page.screenshot(path=str(OUT / f"o04_in_city_{tag}.png"))
    check(f"{tag}: the new agent is selected in the city", name in page.locator("#agent-card-title").inner_text(), card[:120].replace("\n", " | "))
    check(f"{tag}: its owner shows as a Strike user, never the wallet", "Strike user" in card and w.address[:12] not in card)
    look = page.evaluate(f"() => fetch('/api/city').then(r => r.json()).then(d => (d.agents.find(a => a.name === {json.dumps(name)}) || {{}}).look)")
    check(f"{tag}: the city shows the character it was made with", bool(look) and look.get("hair") == chosen_hair and look.get("acc") == chosen_acc,
          json.dumps(look)[:120] + f" wanted hair={chosen_hair} acc={chosen_acc}")
    persona = page.evaluate(f"() => fetch('/api/city').then(r => r.json()).then(d => (d.agents.find(a => a.name === {json.dumps(name)}) || {{}}).persona)")
    check(f"{tag}: the city shows the personality and trade it was made with", bool(persona) and persona.get("temper") == want_persona["temper"]
          and persona.get("job") == "tape", json.dumps(persona))
    check(f"{tag}: its card speaks in that voice and names its trade", page.locator(".city-persona").count() == 1
          and "Tape reader" in page.locator(".city-persona").inner_text(), page.locator(".city-persona").inner_text()[:120] if page.locator(".city-persona").count() else "")
    strat = page.evaluate(f"() => fetch('/api/city').then(r => r.json()).then(d => (d.agents.find(a => a.name === {json.dumps(name)}) || {{}}).strategy)")
    check(f"{tag}: the agent runs the strategy its owner picked", strat == want, str(strat))
    tag_real = "STRIKE TESTNET" if (INFO.get("live") or {}).get("env") == "testnet" else "REAL"   # testnet trades test money
    check(f"{tag}: the city card says real, testnet or paper plainly", (tag_real in card.upper()) == LIVE and ("PYRAMID" in card.upper()) == (want == "pyramid"),
          card[:120].replace(chr(10), " | "))

    # "My agent" is in the city's navigation bar: it opens the dashboard over the map
    page.locator(".city-dock-btn", has_text="My agent").click()
    page.wait_for_selector("#agent-title", timeout=20000)
    check(f"{tag}: My agent opens from the city's navigation bar", page.locator(".city-me #agent-title").count() == 1
          and "?me" in page.evaluate("() => location.hash"))
    page.wait_for_timeout(500)
    page.screenshot(path=str(OUT / f"o05a_city_me_{tag}.png"))
    page.goto(f"{BASE}/#top", wait_until="networkidle")
    page.wait_for_selector("#hero-title", timeout=20000)
    check(f"{tag}: the landing no longer carries the dashboard", page.locator("#agent-title").count() == 0)
    page.get_by_role("button", name="My agent").first.click()
    page.wait_for_selector(".city-me #agent-title", timeout=45000)
    check(f"{tag}: the landing's My agent button opens it in the city", "?me" in page.evaluate("() => location.hash"))
    page.wait_for_timeout(800)
    dash = page.locator("#agent").inner_text()
    page.screenshot(path=str(OUT / f"o05_dashboard_{tag}.png"), full_page=False)
    if LIVE:
        check(f"{tag}: My agent shows it trading on Strike", name in dash and f"Strike {env}" in dash and "Shown" in dash
              and page.locator(".live-card.live-on").count() == 1, dash[:140].replace(chr(10), " | "))
        live_txt = page.locator(".live-card").inner_text()
        check(f"{tag}: right after connecting it says it is starting, never paper", ("Starting on your Strike" in live_txt or "portfolio" in live_txt)
              and "Paper account" not in dash, live_txt[:140].replace(chr(10), " | "))
        page.locator(".live-card").scroll_into_view_if_needed()
        page.wait_for_timeout(300)
        page.screenshot(path=str(OUT / f"o07_live_on_{tag}.png"))
        page.get_by_role("button", name="ES", exact=True).click()   # the same card in Spanish, for review
        page.wait_for_selector("text=Operando en tu cuenta de Strike", timeout=5000)
        page.locator(".live-card").scroll_into_view_if_needed()
        page.screenshot(path=str(OUT / f"o07_live_on_es_{tag}.png"))
        page.get_by_role("button", name="EN", exact=True).click()
        page.wait_for_selector(f"text=Trading on your Strike {env} account", timeout=5000)
        axe(page, f"{tag} my agent, connected to Strike", "#agent")
        page.get_by_role("button", name="Stop trading").click()
        page.wait_for_selector("text=Real trading is off", timeout=20000)
        card = page.locator(".live-card")
        check(f"{tag}: stopping needs no signature and offers to connect again", len(signed) == 1
              and page.get_by_role("button", name=f"Connect with Strike {env}").count() == 1
              and "only withdraw to your own wallet" in card.inner_text(), card.inner_text()[:160].replace(chr(10), " | "))
        card.scroll_into_view_if_needed()
        page.wait_for_timeout(300)
        page.screenshot(path=str(OUT / f"o06_live_off_{tag}.png"))
    else:
        check(f"{tag}: My agent shows the paper agent", name in dash and "Paper" in dash and "Shown" in dash, dash[:140].replace("\n", " | "))
    names = {"pyramid": "Smart Flow Pyramid", "smartflow": "Smart Flow"}
    check(f"{tag}: My agent shows its strategy", names[want] in page.locator("#agent").inner_text())
    # back after closing the browser or on another device: no session, the same wallet -> it only signs in
    page.evaluate("() => { localStorage.removeItem('sf-link'); sessionStorage.removeItem('sf-link') }")
    page.goto(f"{BASE}/#/city", wait_until="networkidle")
    page.reload(wait_until="networkidle")
    page.wait_for_selector(".city-dock-btn", timeout=30000)
    n_signed = len(signed)
    page.locator(".city-dock-btn", has_text="My agent").click()
    page.wait_for_selector("[role=dialog]")
    page.get_by_role("button", name="TestWallet").click()
    page.wait_for_selector("text=You already have an agent", timeout=15000)
    check(f"{tag}: the same wallet again is recognised: sign in, never a new agent", page.locator("#cm-name").count() == 0)
    page.wait_for_timeout(300)
    page.screenshot(path=str(OUT / f"o09_signin_{tag}.png"))
    axe(page, f"{tag} sign-in dialog", "[role=dialog]")
    page.evaluate("() => { window.__h = []; setInterval(() => window.__h.push(location.hash + '|' + !!document.querySelector('.city-me') + '|' + !!document.querySelector('[aria-labelledby=cm-title]')), 100) }")
    page.get_by_role("button", name="Sign in with TestWallet").click()
    try:
        page.wait_for_selector(".city-me #agent-title", timeout=30000)
    except Exception:
        page.screenshot(path=str(OUT / f"o09b_signin_failed_{tag}.png"))
        print("sign in failed:", page.evaluate("() => [...new Set(window.__h)]"), errors[-4:],
              page.locator("[aria-labelledby=cm-title]").inner_text()[:300].replace(chr(10), " | ") if page.locator("[aria-labelledby=cm-title]").count() else "no dialog")
        raise
    page.wait_for_timeout(800)
    again = page.locator("#agent").inner_text()
    check(f"{tag}: signing in opens My agent, the agent unchanged", len(signed) == n_signed + 1
          and signed[-1].startswith("Smart Flow · sign in to my agent") and "changes nothing" in signed[-1]
          and name in again and names[want] in again, signed[-1][:60] + " | " + again[:80].replace(chr(10), " | "))

    def sign_in_again():
        page.locator(".city-dock-btn", has_text="My agent").click()
        page.wait_for_selector("[role=dialog]")
        page.get_by_role("button", name="TestWallet").click()
        page.wait_for_selector("text=You already have an agent", timeout=15000)
        page.get_by_role("button", name="Sign in with TestWallet").click()
        try:
            page.wait_for_selector(".city-me #agent-title", timeout=30000)
        except Exception:
            page.screenshot(path=str(OUT / f"o11_signin_again_failed_{tag}.png"))
            print("sign in again failed:", page.evaluate("() => location.hash"), page.locator(".city-me").count(), page.locator("#agent-title").count(),
                  page.locator("[aria-labelledby=cm-title]").count(), errors[-3:])
            raise
        page.wait_for_timeout(500)

    # "Disconnect wallet": the session ends on this browser, the agent keeps running
    page.get_by_role("button", name="Disconnect wallet").click()
    page.wait_for_selector(".toast", timeout=5000)
    gone = page.evaluate("() => localStorage.getItem('sf-link') === null && !document.querySelector('#agent-title')")
    page.screenshot(path=str(OUT / f"o10_signed_out_{tag}.png"))
    check(f"{tag}: Disconnect wallet ends the session and says the agent keeps running", gone
          and "agent keeps running" in page.locator(".toast").inner_text(), page.locator(".toast").inner_text()[:80])
    page.locator(".city-dock-btn", has_text="My agent").click()
    page.wait_for_selector("[role=dialog]")
    check(f"{tag}: after disconnecting, My agent asks for a wallet again", page.get_by_role("button", name="TestWallet").count() == 1)
    page.keyboard.press("Escape")
    page.wait_for_timeout(300)
    sign_in_again()
    # another account selected in the extension while the page is open: the session closes on its own
    other = TestWallet(network=NET, base=True)
    page.evaluate(f"() => {{ window.__twAddr = '{other.addr_bytes.hex()}'; window.dispatchEvent(new Event('focus')) }}")
    page.wait_for_selector(".toast", timeout=10000)
    page.wait_for_timeout(300)
    page.screenshot(path=str(OUT / f"o11_wallet_switched_{tag}.png"))
    check(f"{tag}: another account selected in the wallet closes the session", page.locator("#agent-title").count() == 0
          and "another account selected" in page.locator(".toast").inner_text(), page.locator(".toast").inner_text()[:80])
    page.evaluate("() => { window.__twAddr = null }")
    sign_in_again()
    if tag == "desktop":   # change the strategy later, with a signature
        page.get_by_role("button", name="Strategy and markets").click()
        page.wait_for_selector("#plan-edit-title", timeout=10000)
        page.screenshot(path=str(OUT / f"o08_settings_{tag}.png"))
        page.locator("[aria-labelledby='plan-edit-title'] .sp-card", has_text="One position per market").click()
        page.get_by_role("button", name="Save, signing with your wallet").click()
        page.wait_for_selector("#plan-edit-title", state="detached", timeout=20000)
        check(f"{tag}: changing the strategy needs a signature", signed[-1].startswith("Smart Flow · change the strategy, markets and risk of")
              and "Strategy: Smart Flow" in signed[-1] and "Pyramid" not in signed[-1], signed[-1][:80])
        strat = page.evaluate(f"() => fetch('/api/city').then(r => r.json()).then(d => (d.agents.find(a => a.name === {json.dumps(name)}) || {{}}).strategy)")
        check(f"{tag}: the city shows the new strategy", strat == "smartflow", str(strat))
    page.get_by_role("button", name="Edit character").click()
    page.wait_for_selector("#av-edit-title", timeout=10000)
    page.get_by_role("tab", name="Hair").click()
    page.locator("[aria-labelledby='av-edit-title'] .av-tile").nth(5).click()
    new_hair = page.locator("input[name='dash-av-hair-colour']:checked").get_attribute("value")
    page.get_by_role("button", name="Save, signing with your wallet").click()
    page.wait_for_selector("#av-edit-title", state="detached", timeout=20000)
    check(f"{tag}: editing the character needs a signature and saves it", signed[-1].startswith("Smart Flow · change the character of"))
    hair = page.evaluate(f"() => fetch('/api/city').then(r => r.json()).then(d => ((d.agents.find(a => a.name === {json.dumps(name)}) || {{}}).look || {{}}).hair)")
    check(f"{tag}: the new character is in the city", hair == new_hair, f"{hair} (wanted {new_hair})")
    # its personality and trade, from My agent: signed like the character
    page.get_by_role("button", name="Edit personality").click()
    page.wait_for_selector("#pp-edit-title", timeout=10000)
    page.get_by_role("tab", name="Pick it directly").click()
    page.locator("[aria-labelledby='pp-edit-title'] .pp-card", has_text="Joker").click()
    page.locator("[aria-labelledby='pp-edit-title'] .pp-job", has_text="Chartist").click()
    axe(page, f"{tag} edit personality", "[aria-labelledby='pp-edit-title']")
    page.get_by_role("button", name="Save, signing with your wallet").click()
    page.wait_for_selector("#pp-edit-title", state="detached", timeout=20000)
    check(f"{tag}: editing the personality needs a signature that says it never changes how it trades",
          "Personality in the city: joker/chartist (never changes how it trades)" in signed[-1], signed[-1][:90])
    persona = page.evaluate(f"() => fetch('/api/city').then(r => r.json()).then(d => (d.agents.find(a => a.name === {json.dumps(name)}) || {{}}).persona)")
    check(f"{tag}: the new personality is in the city", bool(persona) and persona.get("temper") == "joker" and persona.get("job") == "chartist", json.dumps(persona))
    page.get_by_role("button", name="Hide from EdgeCraft-StrikeCity").click()
    page.wait_for_selector("text=Show in EdgeCraft-StrikeCity", timeout=20000)
    check(f"{tag}: hiding it needs and uses a fresh signature", signed[-1].startswith("Smart Flow · hide from EdgeCraft-StrikeCity"))
    gone = page.evaluate(f"() => fetch('/api/city').then(r => r.json()).then(d => !d.agents.some(a => a.name === {json.dumps(name)}))")
    check(f"{tag}: hidden agent no longer in the public city", gone)
    page.get_by_role("button", name="Delete agent").click()
    page.wait_for_function("() => !document.getElementById('agent-title')", timeout=20000)
    check(f"{tag}: deleting it removes My agent", page.locator("#agent-title").count() == 0)
    check(f"{tag}: no horizontal overflow", page.evaluate("() => document.documentElement.scrollWidth - innerWidth") <= 0)
    bad = [e for e in errors if not re.search(r"status of 4\d\d", e)]   # the reserved-name 400 is expected
    check(f"{tag}: no JS errors", not bad, " | ".join(bad[:3]))
    ctx.close()
    browser.close()


def review_es(p):
    """The review step in Spanish at 390 px, for a human to read (nothing is signed: no agent, no Strike request)."""
    w = TestWallet(network=NET, base=True)
    browser = p.chromium.launch()
    ctx = browser.new_context(viewport={"width": 390, "height": 844}, locale="es-ES", device_scale_factor=2, is_mobile=True, has_touch=True)
    ctx.add_init_script("localStorage.setItem('sf-city-welcome', '1'); localStorage.setItem('sf-lang', 'es')")
    page = ctx.new_page()
    page.expose_function("pySign", lambda payload_hex: w.sign_data(bytes.fromhex(payload_hex)))
    page.add_init_script(f"({WALLET_JS})('{w.addr_bytes.hex()}', {NET})")
    page.goto(f"{BASE}/#/city", wait_until="load")   # not "networkidle": TradingView keeps requests of its own open
    page.wait_for_selector(".city-dock-btn", timeout=30000)
    page.locator(".city-dock-btn", has_text="Ranking").click()
    page.get_by_role("button", name="Pon tu propio agente en la ciudad").click()
    page.get_by_role("button", name="TestWallet").click()
    page.get_by_role("button", name="Continuar").click()                 # character -> personality
    page.wait_for_selector("text=Su carácter", timeout=10000)
    for q in range(5):
        page.locator(".pp-a").nth((q * 2) % 5).click()
        page.wait_for_timeout(120)
    page.locator(".pp-job", has_text="Lector de cinta").click()
    page.locator(".actions .btn-primary", has_text="Continuar").click()  # personality -> strategy
    page.wait_for_selector("text=Elige tu estrategia", timeout=10000)
    page.wait_for_timeout(400)
    page.screenshot(path=str(OUT / "o02d_strategy_es_mobile.png"), full_page=True)
    page.get_by_role("button", name="Continuar").click()
    page.wait_for_selector("text=Inicia tu agente", timeout=10000)
    page.wait_for_timeout(400)
    page.screenshot(path=str(OUT / "o02_review_es_mobile.png"), full_page=True)
    dialog = page.locator("[role=dialog]").inner_text()
    if LIVE:
        check("es: the review explains the Strike connection before signing", "Tu cuenta de Strike" in dialog and "0,20" in dialog
              and "solo permite retirar a la tuya" in dialog, dialog[:120].replace(chr(10), " | "))
    ctx.close()
    browser.close()


ONLY = __import__("os").environ.get("SF_ONLY", "")   # desktop | mobile: one of the two runs
with sync_playwright() as p:
    if ONLY in ("", "desktop"):
        run(p, "desktop", {"width": 1440, "height": 900}, False)
    if ONLY in ("", "mobile"):
        run(p, "mobile", {"width": 390, "height": 844}, True)
    if not ONLY:
        review_es(p)

(OUT / "onboarding_live_report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
fails = [c for c in report["checks"] if not c["ok"]]
print(f"\n{len(report['checks']) - len(fails)}/{len(report['checks'])} checks passed")
sys.exit(1 if fails else 0)

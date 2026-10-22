"""Copy with your agent, end to end on the QA site (Strike testnet, test money): a throwaway agent made with a test
wallet, connected to Strike testnet, then "Copy with my agent" from a trader's card (the plan opens with that trader),
the pilot plan signed from My agent, the agents' host carrying it out on Strike testnet (smartflow copypilot) and
reporting back, "Stop copying" signed, and the agent deleted. The test wallet's Strike testnet account holds nothing, so
Strike is expected to refuse the copy: what is checked is that every step happens and that the owner is told why.

    python web/scripts/verify_copy_live.py <axe.min.js> <out_dir> <qa_base_url>
"""

import json
import sys
import time
import urllib.request
from pathlib import Path

from playwright.sync_api import sync_playwright

sys.path.insert(0, str(Path(__file__).parent))
from cip30_test_wallet import TestWallet  # noqa: E402

# the injected CIP-30 test wallet (as in verify_onboarding_live.py)
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

AXE, OUT, BASE = Path(sys.argv[1]), Path(sys.argv[2]), sys.argv[3].rstrip("/")
OUT.mkdir(parents=True, exist_ok=True)
get = lambda path: json.loads(urllib.request.urlopen(urllib.request.Request(BASE + path, headers={"User-Agent": "smartflow-verify/1.0"}), timeout=30).read())
INFO = get("/api/info")
assert INFO.get("env") == "testnet" and INFO.get("copyPilot"), "run this on the QA site (testnet, COPY_PILOT on)"
NET = 0
results = []


def check(name, ok, detail=""):
    results.append({"name": name, "ok": bool(ok), "detail": detail})
    print(("PASS " if ok else "FAIL ") + name + (f" · {detail}" if detail else ""))


def axe(page, label, selector):
    page.add_script_tag(path=str(AXE))
    res = page.evaluate("""async (sel) => {
        const r = await axe.run(sel, { runOnly: { type: 'tag', values: ['wcag2a','wcag2aa','wcag21a','wcag21aa','wcag22aa'] } });
        return r.violations.map(v => ({ id: v.id, nodes: v.nodes.length, target: v.nodes[0].target }));
    }""", selector)
    check(f"axe {label}: 0 violations", not res, "; ".join(f"{v['id']}({v['nodes']}) {v['target']}" for v in res))


doc = get("/api/copy")
hl = next((t for t in doc["traders"] if t["platform"] == "hyperliquid" and t["walks"]), None)
assert hl, "no Hyperliquid lead walks the city"

with sync_playwright() as p:
    w = TestWallet(network=NET, base=True)
    browser = p.chromium.launch()
    ctx = browser.new_context(viewport={"width": 1440, "height": 900}, locale="en-US")
    ctx.add_init_script("localStorage.setItem('sf-city-welcome', '1'); localStorage.setItem('sf-lang', 'en')")
    page = ctx.new_page()
    errors, signed = [], []
    page.on("pageerror", lambda e: errors.append(str(e)))

    def py_sign(payload_hex):
        msg = bytes.fromhex(payload_hex)
        signed.append(msg.decode())
        return w.sign_data(msg)

    page.expose_function("pySign", py_sign)
    ctx.add_init_script(f"({WALLET_JS})('{w.addr_bytes.hex()}', {NET})")
    # ---- a throwaway agent, connected to Strike testnet
    page.goto(f"{BASE}/#/city", wait_until="networkidle")
    page.wait_for_selector(".city-dock-btn", timeout=30000)
    page.locator(".city-dock-btn", has_text="Ranks").click()
    page.get_by_role("button", name="Put your own agent in the city").click()
    page.get_by_role("button", name="TestWallet").click()
    page.wait_for_selector("text=Create your character", timeout=15000)
    page.fill("#cm-name", "QA Copy D")
    page.get_by_role("button", name="Continue").click()
    page.wait_for_selector("text=Its personality", timeout=10000)
    for q in range(5):
        page.locator(".pp-a").nth((q * 2) % 5).click()
        page.wait_for_timeout(120)
    page.locator(".pp-job", has_text="Tape reader").click()
    page.locator(".actions .btn-primary", has_text="Continue").click()
    page.wait_for_selector("text=Choose your strategy", timeout=10000)
    page.get_by_role("button", name="Continue").click()
    page.wait_for_selector("text=Start your agent", timeout=10000)
    page.locator(".check-ack").click()
    page.locator(".actions .btn-primary").click()
    page.wait_for_selector("text=Your agent is starting on your Strike testnet account", timeout=45000)
    check("a test agent is connected to Strike testnet", True)
    page.get_by_role("button", name="See it in EdgeCraft-StrikeCity").click()   # the "Meet your agent" card closes
    page.wait_for_selector("#agent-card-title", timeout=45000)

    def go(hash_):   # a new hash in the same page is no navigation: load the page again (deep links are read on load)
        page.goto(f"{BASE}/{hash_}")
        page.reload(wait_until="networkidle")
    try:
        # ---- "Copy with my agent" on a trader's card: My agent opens the plan with that trader
        go(f"#/city?lead={hl['id']}")
        page.wait_for_selector(".cp-card", timeout=30000)
        btn = page.get_by_role("button", name="Copy with my agent")
        check("the trader's card offers to copy it with my agent", btn.count() == 1)
        page.screenshot(path=str(OUT / "c01_lead_card.png"))
        btn.click()
        page.wait_for_selector("#cp-plan-title", timeout=30000)
        page.wait_for_timeout(800)
        lead_sel = page.locator("#cp-lead").input_value()
        check("the plan opens with that trader, copied by hand", lead_sel.lower() == hl["id"].lower()
              and page.locator("input[name=cp-mode]").first.is_checked(), lead_sel)
        page.screenshot(path=str(OUT / "c02_plan_manual.png"))
        axe(page, "copy plan (manual)", "[aria-labelledby=cp-plan-title]")
        page.get_by_role("button", name="Cancel").click()
        # ---- the pilot from My agent
        page.locator(".copy-card").scroll_into_view_if_needed()
        page.screenshot(path=str(OUT / "c03_section_off.png"))
        page.get_by_role("button", name="Let my agent choose").click()
        page.wait_for_selector("#cp-plan-title")
        page.wait_for_timeout(1500)
        pick = page.locator(".copy-pick").inner_text()
        check("the pilot says whom it would choose now", "would choose" in pick or "would wait" in pick, pick)
        page.screenshot(path=str(OUT / "c04_plan_pilot.png"), full_page=False)
        axe(page, "copy plan (pilot)", "[aria-labelledby=cp-plan-title]")
        sign = page.get_by_role("button", name="Sign with my wallet and start")
        check("it cannot be signed before accepting the risk", sign.is_disabled())
        page.locator(".copy-dialog .check-ack").click()
        sign.click()
        page.wait_for_selector("#cp-plan-title", state="detached", timeout=30000)
        msg = signed[-1] if signed else ""
        check("the owner signs the whole plan in plain words", msg.startswith("Smart Flow · set the copy trading of my agent")
              and "My agent chooses whom to copy" in msg and "Strike ends the copy if it loses" in msg and "sub-account of its own" in msg, msg[:200])
        # ---- the host carries it out on Strike testnet and reports back (it passes once a minute)
        t0, state, why = time.time(), "", ""
        while time.time() - t0 < 200:
            page.wait_for_timeout(10_000)
            card = page.locator(".copy-card")
            state = card.locator(".copy-state").inner_text() if card.locator(".copy-state").count() else ""
            why = card.locator(".copy-why").first.inner_text() if card.locator(".copy-why").count() else ""
            if "applying" not in why and state:
                break
        page.locator(".copy-card").scroll_into_view_if_needed()
        page.screenshot(path=str(OUT / "c05_section_status.png"))
        log = page.locator(".copy-log").inner_text() if page.locator(".copy-log").count() else ""
        check("the agents' host carried the plan out and reported how it went", "applying" not in why and bool(state), f"{state} · {why} · {log[:300]}")
        # the test wallet's Strike testnet account holds nothing: the owner is told so, and it waits for a deposit
        check("an empty account is said plainly (no copy asked of Strike without the money)", state == "Waiting" and "Not enough money" in why
              and "Not enough money" in log, f"{state} · {why}")
        axe(page, "copy section", ".copy-card")
        page.set_viewport_size({"width": 390, "height": 844})
        page.wait_for_timeout(500)
        page.locator(".copy-card").scroll_into_view_if_needed()
        page.screenshot(path=str(OUT / "c06_section_390.png"))
        page.get_by_role("button", name="Change the plan").click()
        page.wait_for_selector("#cp-plan-title")
        page.wait_for_timeout(600)
        page.screenshot(path=str(OUT / "c07_plan_390.png"))
        check("the plan fits a phone", page.evaluate("() => document.querySelector('.copy-dialog').scrollWidth <= innerWidth"))
        page.get_by_role("button", name="Cancel").click()
        page.set_viewport_size({"width": 1440, "height": 900})
        # ---- stop copying
        n0 = len(signed)
        page.get_by_role("button", name="Stop copying").click()
        t1 = time.time()
        while len(signed) == n0 and time.time() - t1 < 30:
            page.wait_for_timeout(300)
        page.wait_for_timeout(1500)
        check("stopping is signed too", (signed[-1] if signed else "").startswith("Smart Flow · set the copy trading of my agent")
              and "My agent stops copying" in signed[-1], signed[-1][:120] if signed else "")
    finally:
        # ---- the throwaway agent goes
        page.keyboard.press("Escape")
        go("#/city?me")
        page.wait_for_selector("#agent-title", timeout=30000)
        page.get_by_role("button", name="Delete agent").click()
        page.wait_for_function("() => !document.getElementById('agent-title')", timeout=30000)
        check("the test agent is deleted", page.locator("#agent-title").count() == 0)
    check("no JS errors", not errors, " | ".join(errors[:3]))
    browser.close()
(OUT / "copy_live_report.json").write_text(json.dumps(results, indent=2), encoding="utf-8")
print(f"\n{sum(r['ok'] for r in results)}/{len(results)} checks passed")

"""Screenshots of the landing's live city section at 1440 and 390 px, and (with --poster) the poster image taken from
the same live frame without the text.

    python web/scripts/shot_landing_city.py <base_url> <out_dir> [--poster web/public/city-preview.webp]
"""

import sys
from pathlib import Path

from playwright.sync_api import sync_playwright

BASE, OUT = sys.argv[1].rstrip("/"), Path(sys.argv[2])
POSTER = sys.argv[sys.argv.index("--poster") + 1] if "--poster" in sys.argv else None
OUT.mkdir(parents=True, exist_ok=True)


def section(p, name, viewport, mobile, lang="es-ES"):
    b = p.chromium.launch()
    ctx = b.new_context(viewport=viewport, locale=lang, device_scale_factor=2 if mobile else 1, is_mobile=mobile, has_touch=mobile)
    page = ctx.new_page()
    errors = []
    page.on("pageerror", lambda e: errors.append(str(e)))
    page.goto(f"{BASE}/", wait_until="networkidle")
    page.locator("#city").scroll_into_view_if_needed()
    page.wait_for_selector(".city-show-canvas.on", timeout=30000)
    page.wait_for_timeout(5000)
    page.locator("#city").screenshot(path=str(OUT / f"landing_city_{name}.png"))
    stats = page.locator(".city-show-stats").inner_text() if page.locator(".city-show-stats").count() else ""
    over = page.evaluate("() => document.documentElement.scrollWidth - innerWidth")
    print(f"{name}: stats='{stats}' overflow={over}px errors={errors[:2]}")
    b.close()


def poster(p):
    b = p.chromium.launch()
    ctx = b.new_context(viewport={"width": 1240, "height": 900}, device_scale_factor=1.5)
    page = ctx.new_page()
    page.goto(f"{BASE}/", wait_until="networkidle")
    page.locator("#city").scroll_into_view_if_needed()
    page.wait_for_selector(".city-show-canvas.on", timeout=30000)
    page.add_style_tag(content=".city-show-text, .city-show-shade, .city-show-poster, .statusbar, .mobile-cta, .header { display: none !important; }")
    page.wait_for_timeout(6000)
    page.locator(".city-show-frame").screenshot(path=POSTER, type="jpeg", quality=82)
    b.close()
    print("poster ->", POSTER)


with sync_playwright() as p:
    section(p, "desktop", {"width": 1440, "height": 900}, False)
    section(p, "mobile", {"width": 390, "height": 844}, True)
    if POSTER:
        poster(p)

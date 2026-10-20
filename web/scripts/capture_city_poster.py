"""Captures the EdgeCraft-StrikeCity poster for the landing (web/public/city-preview.jpg) from the live site.

    python web/scripts/capture_city_poster.py <base_url> <out.jpg>

Only the map: the city UI (top bar, dock, widgets) is hidden for the capture. The landing shows this image while the
live city loads in its place.
"""

import sys

from playwright.sync_api import sync_playwright

BASE, OUT = sys.argv[1].rstrip("/"), sys.argv[2]
with sync_playwright() as p:
    b = p.chromium.launch()
    ctx = b.new_context(viewport={"width": 1920, "height": 1080}, locale="en-US", device_scale_factor=1)
    ctx.add_init_script("localStorage.setItem('sf-city-welcome', '1')")
    page = ctx.new_page()
    page.goto(f"{BASE}/#/city?night=1", wait_until="networkidle")
    page.wait_for_selector(".city-canvas", timeout=30000)
    page.add_style_tag(content=".city-scale, .city-zoom, .city-source-warn, .city-empty { display: none !important; }")
    page.wait_for_timeout(6000)   # agents spread out, fonts and prices in
    box = page.locator(".city-canvas").bounding_box()
    page.screenshot(path=OUT, type="jpeg", quality=84, clip=box)
    b.close()
print("poster ->", OUT)

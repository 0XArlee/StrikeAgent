"""Quick look at EdgeCraft-StrikeCity: python web/scripts/shot_city.py <out_dir> [base_url] — map at 1440 and 390 px, day and night."""
import sys
from pathlib import Path

from playwright.sync_api import sync_playwright

OUT = Path(sys.argv[1]); OUT.mkdir(parents=True, exist_ok=True)
BASE = sys.argv[2] if len(sys.argv) > 2 else "http://localhost:4173"
with sync_playwright() as p:
    b = p.chromium.launch()
    for name, vp, mob in [("desktop", {"width": 1440, "height": 900}, False), ("mobile", {"width": 390, "height": 844}, True)]:
        for night in ("0.5", "1"):
            ctx = b.new_context(viewport=vp, locale="en-US", device_scale_factor=2 if mob else 1, is_mobile=mob, has_touch=mob)
            ctx.add_init_script("localStorage.setItem('sf-city-welcome', '1')")
            pg = ctx.new_page()
            pg.goto(f"{BASE}/#/city?night={night}", wait_until="networkidle")
            pg.wait_for_selector(".city[data-ready]")
            pg.wait_for_timeout(5000)
            pg.screenshot(path=str(OUT / f"q_{name}_night{night}.png"))
            ctx.close()
    b.close()
print("done")

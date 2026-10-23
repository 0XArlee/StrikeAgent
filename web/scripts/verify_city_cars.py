"""Real-browser check of the cars, which are Strike's real trades, and of the top bar's figures, at 1440 and 390 px.

    python web/scripts/verify_city_cars.py <out_dir> <base_url> <all|real>

The city reads /price/v2/trades, a car of the buy or sell colour drives in, a car under the mouse stops with a light
outline, and pressing a car shows the trade it is. all: staging, whose top bar counts every agent; real: production,
whose top bar counts real accounts only. The page opens with ?night=0 so the cars keep their exact colours.
"""
import sys
from pathlib import Path
from playwright.sync_api import sync_playwright

OUT, BASE, EXPECT = Path(sys.argv[1]), sys.argv[2].rstrip("/"), sys.argv[3]
OUT.mkdir(parents=True, exist_ok=True)
results = []


def check(name, ok, detail=""):
    results.append(bool(ok))
    print(("PASS " if ok else "FAIL ") + name + (f" · {detail}" if detail else ""), flush=True)


FIND = """() => {
  const c = document.querySelector('.city-canvas'), g = c.getContext('2d');
  const d = g.getImageData(0, 0, c.width, c.height).data, dpr = c.width / c.clientWidth, r = c.getBoundingClientRect();
  const want = [[0x1d, 0x7a, 0x55], [0x9b, 0x2c, 0x3b]];
  for (let y = 0; y < c.height; y += 2) for (let x = 0; x < c.width; x += 2) {
    const i = (y * c.width + x) * 4;
    for (const [R, G, B] of want) if (d[i] === R && d[i + 1] === G && d[i + 2] === B) return { x: r.left + x / dpr, y: r.top + y / dpr };   // page coordinates
  }
  return null;
}"""

NEAR = """({x, y}) => {   // around a page point: a car's colour, and the light outline of a stopped car
  const c = document.querySelector('.city-canvas'), g = c.getContext('2d'), r = c.getBoundingClientRect(), dpr = c.width / c.clientWidth;
  const px = Math.round((x - r.left) * dpr), py = Math.round((y - r.top) * dpr), R = Math.round(14 * dpr);
  const d = g.getImageData(px - R, py - R, 2 * R, 2 * R).data;
  let car = false, light = 0;
  for (let i = 0; i < d.length; i += 4) {
    if ((d[i] === 0x1d && d[i + 1] === 0x7a && d[i + 2] === 0x55) || (d[i] === 0x9b && d[i + 1] === 0x2c && d[i + 2] === 0x3b)) car = true;
    if (d[i] === 0xff && d[i + 1] === 0xf7 && d[i + 2] === 0xd6) light++;
  }
  return { car, outline: light > 20, light };   // the headlights alone are 4 pixels
}"""

with sync_playwright() as p:
    b = p.chromium.launch()
    for name, vp in (("desktop", {"width": 1440, "height": 900}), ("mobile", {"width": 390, "height": 844})):
        c = b.new_context(viewport=vp, locale="en-US", device_scale_factor=1, is_mobile=name == "mobile", has_touch=name == "mobile")
        c.add_init_script("localStorage.setItem('sf-city-welcome', '1'); localStorage.setItem('sf-lang', 'en')")
        pg = c.new_page()
        errors, reads = [], []
        pg.on("pageerror", lambda e: errors.append(str(e)))
        pg.on("request", lambda r: reads.append(r.url) if "/price/v2/trades" in r.url else None)
        pg.goto(f"{BASE}/#/city?night=0", wait_until="load")   # daylight: the cars in their own colours
        pg.wait_for_selector(".city[data-ready]", timeout=45000)
        # what the figures count (Results' summary): every agent on staging, real accounts only in production
        pg.locator(".city-dock-btn", has_text="Results").click()
        pg.wait_for_selector("#city-panel .rs-tile[data-k=r24]")
        bar = pg.locator("#city-panel .rs-panel").inner_text().replace("\n", " | ")
        if EXPECT == "all":
            check(f"{name}: test site counts every agent", "Staging:" in bar and "Result, last 24 h" in bar, bar[:160])
        else:
            check(f"{name}: production counts real accounts only", "Real accounts only" in bar and "Result, last 24 h" in bar, bar[:160])
        pg.locator("#city-panel .city-panel-head .icon-btn").click()
        spot = None
        for _ in range(40):   # a car shows up as soon as a trade comes in (Strike trades every few seconds)
            pg.wait_for_timeout(1500)
            spot = pg.evaluate(FIND)
            if spot:
                break
        check(f"{name}: the city reads Strike's trades", len(reads) > 0, f"{len(reads)} reads, e.g. {reads[0] if reads else '-'}")
        check(f"{name}: a car (a real trade) drives in", spot is not None, str(spot))
        pg.screenshot(path=str(OUT / f"{name}_cars.png"))
        if spot and name == "desktop":   # the mouse on a car stops it (and outlines it), so it is easy to press
            spot = pg.evaluate(FIND) or spot
            hx, hy = spot["x"] + 5, spot["y"] + 3
            pg.mouse.move(hx, hy)
            pg.wait_for_timeout(2000)
            near = pg.evaluate(NEAR, {"x": hx, "y": hy})
            check(f"{name}: a car under the mouse stops there, outlined", near["car"] and near["outline"], str(near))
            pg.screenshot(path=str(OUT / f"{name}_held.png"), clip={"x": max(0, hx - 80), "y": max(0, hy - 60), "width": 160, "height": 120})
            pg.mouse.click(hx, hy)
            pg.wait_for_timeout(500)
            check(f"{name}: pressing the stopped car shows its trade", pg.locator(".city-trade").count() == 1)
            pg.mouse.move(5, 300)
            if pg.locator(".city-trade").count():
                pg.locator(".city-trade button").click()
                pg.wait_for_timeout(300)
            spot = pg.evaluate(FIND)
        if spot:
            for _ in range(3):   # the car moves: find it again right before pressing
                spot = pg.evaluate(FIND) or spot
                pg.mouse.click(spot["x"] + 5, spot["y"] + 3) if name == "desktop" else pg.touchscreen.tap(spot["x"] + 5, spot["y"] + 3)
                pg.wait_for_timeout(500)
                if pg.locator(".city-trade").count():
                    break
            ok = pg.locator(".city-trade").count() == 1
            txt = pg.locator(".city-trade").inner_text().replace("\n", " | ") if ok else ""
            check(f"{name}: pressing a car shows the real trade it is", ok and ("bought" in txt or "sold" in txt) and "$" in txt, txt)
            pg.screenshot(path=str(OUT / f"{name}_trade.png"))
        check(f"{name}: no JS errors", not errors, " | ".join(errors[:3]))
        c.close()
    b.close()
print(f"{sum(results)}/{len(results)} checks passed")

"""The city's art from LimeZu's Modern Exteriors (art/limezu, only on the PC, never in git) on Strike City's own map:
web/public/art/city/base.png (ground, streets and buildings, as by day), web/public/art/city/glow.png (what lights up
at night: windows, lamps) and web/src/city/city2.json (where everything is: buildings, lamps, trees, benches; the
city's walkable grid and lights are built from it).

The map is the same as before (96 x 64 tiles of 16 px, the same roads, plaza and doors): every building keeps its
place and its door, only the facades are taller where the art has floors (a ground floor is 3 tiles, a floor 4).

Licence (Modern Exteriors, the PDF in the pack): commercial use, edits and open source allowed; no reselling or
distributing the asset, no NFT minting; credits to limezu.itch.io (shown on the site). What the site serves is this
composed picture, never the pack's files.

Run (on the PC): .venv/Scripts/python.exe web/scripts/build_city.py
"""
from __future__ import annotations

import json
import math
import random
from pathlib import Path

from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parents[2]
ME = ROOT / "art" / "limezu" / "modern_exteriors" / "Modern_Exteriors_16x16" / "ME_Theme_Sorter_16x16"
OUT = ROOT / "web" / "public" / "art" / "city"
MANIFEST = ROOT / "web" / "src" / "city" / "city2.json"

T = 16
COLS, ROWS = 96, 64
W, H = COLS * T, ROWS * T
HROADS = [18, 42]
VROADS = [24, 48, 72]
PEDESTRIAN = (48, 49, 20, 41)          # x0, x1, y0, y1: the avenue stops at the plaza
PLAZA = (27, 28, 44, 13)               # x, y, w, d
FOUNTAIN = (48 * T + T, 35 * T)

# each building: where it is (tiles), its roof depth d, how many floors over the ground floor, and its look.
# door.x is the tile the agents walk to (the same as before); the door row comes from the facade's height.
# colour: 0 brick, 1 blue, 2 grey (LimeZu's three schemes)
BUILDINGS = [
    dict(id="lab", x=4, y=1, w=14, d=6, floors=1, colour=1, roof="Roof_7", middle=4, ground=6, door=11),
    dict(id="btc", x=29, y=0, w=14, d=4, floors=2, colour=2, roof="Roof_5", middle=4, ground=9, door=36),
    dict(id="eth", x=53, y=0, w=14, d=4, floors=2, colour=1, roof="Roof_3", middle=5, ground=5, door=60),
    dict(id="sol", x=77, y=0, w=10, d=3, floors=2, colour=0, roof="Roof_1", middle=4, ground=1, door=82),
    dict(id="alts", x=88, y=1, w=7, d=4, floors=1, colour=0, roof="Roof_2", middle=1, ground=2, door=91),
    dict(id="risk", x=4, y=21, w=12, d=3, floors=1, colour=2, roof="Roof_5", middle=5, ground=12, door=10),
    dict(id="alley", x=17, y=30, w=5, d=4, floors=0, colour=0, roof="Roof_6", middle=None, ground=4, door=19),
    dict(id="exchange", x=32, y=21, w=32, d=4, floors=1, colour=2, roof="Roof_11", middle=1, ground=11, door=48),
    dict(id="vault", x=77, y=21, w=14, d=3, floors=1, colour=2, roof="Roof_3", middle=3, ground=10, door=84),
    dict(id="clan", x=78, y=34, w=12, d=3, floors=0, colour=1, roof="Roof_4", middle=None, ground=8, door=84),
    dict(id="homes", x=3, y=46, w=18, d=3, floors=1, colour=0, roof="Roof_2", middle=3, ground=4, door=12),
    dict(id="hq", x=28, y=45, w=12, d=4, floors=1, colour=2, roof="Roof_1", middle=4, ground=9, door=34),
    dict(id="cafe", x=41, y=49, w=6, d=3, floors=0, colour=0, roof="Roof_2", middle=None, ground=2, door=44),
    dict(id="arena", x=53, y=45, w=16, d=4, floors=1, colour=0, roof="Roof_8", middle=1, ground=3, door=61),
]
GROUND_H, FLOOR_H = 48, 64
# where the door is in each of LimeZu's ground floors (Ground_Floor_Condo_1..12: the first column of its double door)
DOOR_COL = {1: 4, 2: 3, 3: 4, 4: 3}    # by variant within a colour (1..4)


def piece(folder: str, name: str) -> Image.Image:
    f = next((ME / folder).glob(f"*_{name}.png"), None)
    if f is None:
        raise SystemExit(f"missing piece {name} in {folder}")
    return Image.open(f).convert("RGBA")


def floor_piece(name: str) -> Image.Image:
    return piece("5_Floor_Modular_Building_Singles_16x16", name)


def terrain(name: str) -> Image.Image:
    return piece("2_City_Terrains_Singles_16x16", name)


def prop(name: str) -> Image.Image:
    return piece("3_City_Props_Singles_16x16", name)


# ---------------------------------------------------------------- the map's tiles (same rules as world.ts)
def is_road_row(y): return any(y in (r, r + 1) for r in HROADS)
def is_road_col(x): return any(x in (c, c + 1) for c in VROADS)


def v_road(x, y):
    x0, x1, y0, y1 = PEDESTRIAN
    return is_road_col(x) and not (x0 <= x <= x1 and y0 <= y <= y1)


def is_road(x, y):
    if x < 0 or y < 0 or x >= COLS or y >= ROWS:
        return False
    return is_road_row(y) or v_road(x, y)


def is_crosswalk(x, y):
    near = any(c - 2 <= x <= c + 3 for c in VROADS) and any(r - 2 <= y <= r + 3 for r in HROADS)
    return near and is_road(x, y) and not (is_road_row(y) and v_road(x, y))


def is_sidewalk(x, y):
    if is_road(x, y):
        return False
    return any(y in (r - 1, r + 2) for r in HROADS) or any(x in (c - 1, c + 2) and v_road(c, y) for c in VROADS)


def in_plaza(x, y):
    px, py, pw, pd = PLAZA
    return px <= x < px + pw and py <= y < py + pd


# ---------------------------------------------------------------- ground
def stretch(im: Image.Image, w: int, h: int, cap_x: int = 16, cap_y: int = 16) -> Image.Image:
    """A piece made w x h by repeating its middle and keeping its edges (roofs)."""
    out = Image.new("RGBA", (w, h))
    sx = [(0, cap_x)] + [(cap_x, im.width - cap_x)] + [(im.width - cap_x, im.width)]
    sy = [(0, cap_y)] + [(cap_y, im.height - cap_y)] + [(im.height - cap_y, im.height)]
    tx = [(0, cap_x), (cap_x, w - cap_x), (w - cap_x, w)]
    ty = [(0, cap_y), (cap_y, h - cap_y), (h - cap_y, h)]
    for (a0, a1), (b0, b1) in zip(sy, ty):
        for (c0, c1), (d0, d1) in zip(sx, tx):
            src = im.crop((c0, a0, c1, a1))
            for yy in range(b0, b1, max(1, a1 - a0)):
                for xx in range(d0, d1, max(1, c1 - c0)):
                    tile = src.crop((0, 0, min(src.width, d1 - xx), min(src.height, b1 - yy)))
                    out.alpha_composite(tile, (xx, yy))
    return out


def draw_ground(img: Image.Image, R: random.Random) -> None:
    grass = [prop_t for prop_t in (piece("1_Terrains_and_Fences_Singles_16x16", f"Grass_1_{i}") for i in (10, 11, 12))]
    asphalt = terrain("Sidewalk_1_10")
    walk = terrain("Sidewalk_3_9")
    slabs = [terrain(f"Sidewalk_6_{i}") for i in (25, 26, 27, 28)]
    curb = {k: terrain(f"Sidewalk_3_{n}") for k, n in (("top", 6), ("bottom", 2), ("left", 4), ("right", 8),
                                                        ("tl", 5), ("tr", 7), ("bl", 3), ("br", 1))}
    for y in range(ROWS):
        for x in range(COLS):
            p = (x * T, y * T)
            if is_road(x, y):
                img.alpha_composite(asphalt, p)
                side = lambda dx, dy: not is_road(x + dx, y + dy) and 0 <= x + dx < COLS and 0 <= y + dy < ROWS
                for k, (dx, dy) in (("top", (0, -1)), ("bottom", (0, 1)), ("left", (-1, 0)), ("right", (1, 0))):
                    if side(dx, dy):
                        img.alpha_composite(curb[k], p)
                for k, (dx, dy) in (("tl", (-1, -1)), ("tr", (1, -1)), ("bl", (-1, 1)), ("br", (1, 1))):
                    if side(dx, dy) and not side(dx, 0) and not side(0, dy):
                        img.alpha_composite(curb[k], p)
            elif in_plaza(x, y) and not is_sidewalk(x, y):
                if x % 2 == 0 and y % 2 == 0:
                    img.alpha_composite(slabs[(x * 3 + y * 5) % 4], p)
            elif is_sidewalk(x, y):
                img.alpha_composite(walk, p)
            else:
                img.alpha_composite(grass[(x * 7 + y * 13) % 3], p)
    # plaza slabs that start on an odd tile (its edges): the sidewalk paving
    for y in range(ROWS):
        for x in range(COLS):
            if in_plaza(x, y) and not is_sidewalk(x, y) and (not in_plaza(x - x % 2, y - y % 2) or is_sidewalk(x - x % 2, y - y % 2)):
                img.alpha_composite(walk, (x * T, y * T))
    g = ImageDraw.Draw(img)
    paint = (224, 220, 236, 255)
    # lane markings: a dashed line between the two lanes, never across crossings
    for r in HROADS:
        yy = (r + 1) * T - 1
        for x in range(0, W, 24):
            tx = x // T
            if not is_road_col(tx) and not is_crosswalk(tx, r) and not is_crosswalk((x + 11) // T, r):
                g.rectangle([x, yy, x + 11, yy + 1], fill=paint)
    for c in VROADS:
        xx = (c + 1) * T - 1
        for y in range(0, H, 24):
            ty = y // T
            if not is_road_row(ty) and v_road(c, ty) and v_road(c, (y + 11) // T) and not is_crosswalk(c, ty) and not is_crosswalk(c, (y + 11) // T):
                g.rectangle([xx, y, xx + 1, y + 11], fill=paint)
    # crossings: stripes along the walking direction
    for y in range(ROWS):
        for x in range(COLS):
            if not is_crosswalk(x, y):
                continue
            px, py = x * T, y * T
            if is_road_row(y):      # crossing a horizontal road: vertical stripes
                for i in range(1, T, 5):
                    g.rectangle([px + i, py + 1, px + i + 2, py + T - 2], fill=paint)
            else:
                for i in range(1, T, 5):
                    g.rectangle([px + 1, py + i, px + T - 2, py + i + 2], fill=paint)


# ---------------------------------------------------------------- buildings
def cols(im: Image.Image, c0: int, c1: int) -> Image.Image:
    return im.crop((c0 * T, 0, c1 * T, im.height))


def ground_floor(b: dict) -> Image.Image:
    """The ground floor: the colour's corner columns at both ends, wide windows in between, and one door (LimeZu's
    piece b["ground"], cut out with its frame) right in front of the agents' door tile."""
    c, v = b["colour"], b["ground"]
    w = b["w"] * T
    out = Image.new("RGBA", (w, GROUND_H))
    base = floor_piece(f"Ground_Floor_Condo_{c * 4 + 1}")
    fills = [cols(floor_piece(f"Ground_Floor_Condo_{c * 4 + k}"), 1, 4) for k in (1, 3)]   # window grid, wide window
    wall = floor_piece(f"Ground_Floor_Condo_Modular_{c * 8 + 2}")
    out.alpha_composite(cols(base, 0, 1), (0, 0))
    out.alpha_composite(cols(base, 6, 7), (w - T, 0))
    rel = (b["door"] - b["x"]) * T + 8                        # the door tile's centre, in the facade
    dc = DOOR_COL[(v - 1) % 4 + 1]
    door = floor_piece(f"Ground_Floor_Condo_{v}").crop((dc * T - 6, 0, dc * T + 2 * T + 6, GROUND_H))
    d0, d1 = rel - door.width // 2, rel + door.width // 2

    def fill(x0: int, x1: int, k: int) -> None:   # windows from x0 to x1 (px), walls where a window does not fit
        x = x0
        while x < x1:
            seg = fills[k % 2] if x1 - x >= 3 * T else wall
            out.alpha_composite(seg.crop((0, 0, min(seg.width, x1 - x), GROUND_H)), (x, 0))
            x += seg.width
            k += 1
    fill(T, max(T, d0), 0)
    fill(min(w - T, d1), w - T, 1)
    out.alpha_composite(door, (d0, 0))
    return out


def middle_floors(b: dict) -> Image.Image | None:
    """The floors over the ground floor: the corner columns of a LimeZu floor and one pair of its window columns
    repeated in between (b["middle"]: 1 tall window, 2 pipe, 3 window with an ornament, 4 two windows, 5 window)."""
    if not b["floors"]:
        return None
    c, k = b["colour"], b["middle"]
    w = b["w"] * T
    caps = floor_piece(f"Middle_Floor_{c * 6 + 1}")
    pair = [floor_piece(f"Middle_Floor_Modular_{c * 10 + 2 * k - 1}"), floor_piece(f"Middle_Floor_Modular_{c * 10 + 2 * k}")]
    out = Image.new("RGBA", (w, FLOOR_H * b["floors"]))
    inner = b["w"] - 2
    for f in range(b["floors"]):
        y = f * FLOOR_H
        out.alpha_composite(cols(caps, 0, 1), (0, y))
        out.alpha_composite(cols(caps, 6, 7), (w - T, y))
        x = T + (T // 2 if inner % 2 else 0) * 0
        cols_ = [pair[i % 2] for i in range(inner - inner % 2)]
        if inner % 2:                                          # an odd width: a plain column in the middle
            cols_.insert(len(cols_) // 2, cols(caps, 1, 2))
        for col in cols_:
            out.alpha_composite(col, (x, y))
            x += T
    return out


def edges(im: Image.Image, dark=(20, 18, 28, 140)) -> None:
    g = ImageDraw.Draw(im)
    g.rectangle([0, 0, 1, im.height - 1], fill=dark)
    g.rectangle([im.width - 2, 0, im.width - 1, im.height - 1], fill=dark)


def draw_building(img: Image.Image, shadow: Image.Image, b: dict) -> dict:
    x, y, w = b["x"] * T, b["y"] * T, b["w"] * T
    roof = stretch(floor_piece(b["roof"]), w, b["d"] * T)
    mids = middle_floors(b)
    ground = ground_floor(b)
    facade_h = (mids.height if mids else 0) + GROUND_H
    # shadow to the bottom right (the light comes from the top left)
    ImageDraw.Draw(shadow).rectangle([x + 6, y + 8, x + w + 6, y + b["d"] * T + facade_h + 4], fill=(0, 0, 0, 110))
    img.alpha_composite(roof, (x, y))
    fy = y + b["d"] * T
    if mids:
        edges(mids)
        img.alpha_composite(mids, (x, fy))
    edges(ground)
    img.alpha_composite(ground, (x, fy + facade_h - GROUND_H))
    door_y = b["y"] + b["d"] + facade_h // T
    return {"id": b["id"], "x": b["x"], "y": b["y"], "w": b["w"], "d": b["d"], "h": facade_h, "door": {"x": b["door"], "y": door_y},
            "facade": [x, fy, w, facade_h]}


# ---------------------------------------------------------------- night: what lights up
def is_glass(p) -> bool:
    r, g, b, a = p
    return a > 200 and b >= 150 and b - r >= 25 and g >= 120


def glow_layer(img: Image.Image, facades: list[list[int]], R: random.Random) -> tuple[Image.Image, int]:
    """Windows lit at night: the facades' glass pixels, in warm or cool light, about two thirds of the windows on.
    A window is the glass in one 16 px column of one floor (so each lights up on its own)."""
    out = Image.new("RGBA", img.size)
    px, po = img.load(), out.load()
    warm = [(255, 214, 140), (255, 230, 170), (190, 230, 255), (255, 200, 120)]
    lit = 0
    for fx, fy, fw, fh in facades:
        for cx in range(fx, fx + fw, T):
            for cy in range(fy, fy + fh, T):
                cells = [(xx, yy) for yy in range(cy, min(cy + T, fy + fh)) for xx in range(cx, min(cx + T, fx + fw)) if is_glass(px[xx, yy])]
                if len(cells) < 6:
                    continue
                if R.random() > 0.66:
                    continue
                col = warm[R.randrange(len(warm))]
                for xx, yy in cells:
                    r, g, b, _ = px[xx, yy]
                    k = 0.55 + 0.45 * (r + g + b) / 765
                    po[xx, yy] = (int(col[0] * k), int(col[1] * k), int(col[2] * k), 235)
                lit += 1
    return out, lit


# ---------------------------------------------------------------- props
def place(img: Image.Image, im: Image.Image, x: int, y: int) -> None:
    """A prop standing at (x, y) px: its bottom centre there."""
    img.alpha_composite(im, (x - im.width // 2, y - im.height))


KIOSKS = [(33, 37), (62, 37)]                                       # 2 x 2 tiles each (world.ts)
BENCHES = [(FOUNTAIN[0] + dx * T, FOUNTAIN[1] + dy * T, True) for dx in (-5, 5) for dy in (-1, 2)] + \
          [(FOUNTAIN[0] + int(dx * T * 1.4), FOUNTAIN[1] + 4 * T, False) for dx in (-2, 2)]
PLANTERS = [(29, 29), (67, 29), (29, 38), (67, 38)]


def draw_fountain(img: Image.Image) -> None:
    """The plaza's fountain: an octagonal stone basin (the water and its jets are drawn live by the city)."""
    g = ImageDraw.Draw(img)
    fx, fy = FOUNTAIN[0], FOUNTAIN[1] + 6

    def octagon(r: float, ry: float, dx: float = 0, dy: float = 0):
        return [(fx + dx + math.cos(i / 8 * 2 * math.pi + math.pi / 8) * r, fy + dy + math.sin(i / 8 * 2 * math.pi + math.pi / 8) * ry) for i in range(8)]
    g.polygon(octagon(39, 25, 3, 4), fill=(0, 0, 0, 90))
    g.polygon(octagon(37, 23), fill=(92, 96, 116, 255))
    g.polygon(octagon(36, 22), fill=(150, 152, 170, 255))
    g.polygon(octagon(32, 19), fill=(116, 120, 140, 255))
    g.polygon(octagon(30, 17), fill=(44, 92, 120, 255))
    g.ellipse([fx - 6, fy - 4, fx + 6, fy + 4], fill=(150, 152, 170, 255))
    g.rectangle([fx - 2, fy - 10, fx + 2, fy], fill=(176, 178, 194, 255))


class Decor:
    """Props on the map and the tiles they take (agents walk around those)."""

    def __init__(self, keep: set[tuple[int, int]], taken: set[tuple[int, int]]):
        self.keep = keep               # tiles that stay free: in front of the doors, the plaza's middle
        self.taken = taken             # buildings
        self.blocked: set[tuple[int, int]] = set()
        self.lamps: list[list[int]] = []
        self.items: list[tuple[int, Image.Image, int]] = []   # (y px, image, x px)

    def free(self, x: int, y: int, w: int = 1, h: int = 1) -> bool:
        return all(0 <= x + i < COLS and 0 <= y + j < ROWS and (x + i, y + j) not in self.blocked
                   and (x + i, y + j) not in self.keep and (x + i, y + j) not in self.taken for i in range(w) for j in range(h))

    def add(self, im: Image.Image, x: int, y: int, tiles: list[tuple[int, int]] = ()) -> None:
        self.items.append((y, im, x))
        self.blocked.update(tiles)

    def draw(self, img: Image.Image) -> None:
        for y, im, x in sorted(self.items, key=lambda t: t[0]):
            place(img, im, x, y)


def decorate(placed: list[dict], R: random.Random) -> Decor:
    taken = {(xx, yy) for b in placed for yy in range(b["y"], b["door"]["y"]) for xx in range(b["x"], b["x"] + b["w"])}
    keep = {(xx, yy) for b in placed for yy in range(b["door"]["y"], b["door"]["y"] + 4) for xx in range(b["door"]["x"] - 2, b["door"]["x"] + 3)}
    px_, py_, pw, pd = PLAZA
    keep |= {(xx, yy) for yy in range(py_ + 3, py_ + pd - 1) for xx in range(px_ + 3, px_ + pw - 3)}
    D = Decor(keep, taken)
    lamp = prop("Street_Lamp_5")
    trees_street = [prop(f"Tree_{i}") for i in (9, 13, 14)]
    trees_park = [prop(f"Tree_{i}") for i in (1, 2, 3, 4, 5, 6, 11, 12)]
    bushes = [prop(f"Shrub_{i}") for i in (1, 2, 3, 5, 6, 9)] + [prop(f"Flower_Bush_{i}") for i in (1, 3, 5)]
    flowers = [prop(f"Flowers_{i}") for i in range(1, 6)]
    # street lamps on the sidewalks along the roads (their light pools: the night layer)
    for r in HROADS:
        for x in range(3, COLS, 7):
            for sy in (r - 1, r + 2):
                if is_sidewalk(x, sy) and not is_road_col(x):
                    foot = sy * T + (T - 1 if sy < r else T - 3)
                    D.add(lamp, x * T + 8, foot)
                    D.lamps.append([x * T + 8, foot, foot - 56])
    for c in VROADS:
        for y in range(4, ROWS, 8):
            if is_road_row(y) or not v_road(c, y):
                continue
            for sx in (c - 1, c + 2):
                if is_sidewalk(sx, y):
                    D.add(lamp, sx * T + 8, y * T + T - 1)
                    D.lamps.append([sx * T + 8, y * T + T - 1, y * T + T - 57])
    # trees in planters on the grass along the sidewalks, every 6 tiles
    for y in range(ROWS):
        for x in range(COLS):
            if not is_sidewalk(x, y) or (x + y) % 6:
                continue
            for nx, ny in ((x, y - 1), (x, y + 1), (x - 1, y), (x + 1, y)):
                if not is_road(nx, ny) and not is_sidewalk(nx, ny) and not in_plaza(nx, ny) and D.free(nx, ny) and D.free(nx, ny - 1):
                    D.add(trees_street[(nx * 3 + ny) % 3], nx * T + 8, ny * T + T, [(nx, ny)])
                    break
    # parks: trees, bushes and flowers on the free grass
    for y in range(ROWS):
        for x in range(COLS):
            if is_road(x, y) or is_sidewalk(x, y) or in_plaza(x, y) or not D.free(x, y):
                continue
            roll = R.random()
            if roll < 0.13 and D.free(x - 1, y - 1, 3, 2):
                D.add(trees_park[R.randrange(len(trees_park))], x * T + 8 + R.randrange(-3, 4), y * T + T, [(x, y)])
            elif roll < 0.19:
                D.add(bushes[R.randrange(len(bushes))], x * T + 8, y * T + T - 2, [(x, y)])
            elif roll < 0.27:
                D.add(flowers[R.randrange(len(flowers))], x * T + 8, y * T + T - 3)
    # the plaza: planters at its corners, benches facing the fountain, two carts
    planter = prop("Tree_10")
    for x, y in PLANTERS:
        D.add(planter, x * T + 16, y * T + 24, [(x, y), (x + 1, y)])
    bench_h, bench_v = prop("Bench_1"), prop("Bench_3")
    for bx, by, v in BENCHES:
        D.add(bench_v if v else bench_h, int(bx), int(by) + (16 if v else 10))
    carts = [prop("Candies_Cart_1"), prop("Candies_Cart_2")]
    for i, (x, y) in enumerate(KIOSKS):
        D.add(carts[i % 2], x * T + 16, y * T + 32, [(x, y), (x + 1, y), (x, y + 1), (x + 1, y + 1)])
    return D


def main() -> None:
    if not ME.exists():
        raise SystemExit(f"LimeZu's Modern Exteriors is not unpacked in {ME.parents[2]}")
    R = random.Random(42)
    img = Image.new("RGBA", (W, H), (0, 0, 0, 255))
    draw_ground(img, R)
    draw_fountain(img)
    shadow = Image.new("RGBA", (W, H))
    placed, facades = [], []
    layer = Image.new("RGBA", (W, H))
    for b in sorted(BUILDINGS, key=lambda b: b["y"]):
        info = draw_building(layer, shadow, b)
        placed.append(info)
        facades.append(info["facade"])
    img.alpha_composite(shadow)
    img.alpha_composite(layer)
    glow, lit = glow_layer(img, facades, R)
    decor = decorate(placed, R)
    decor.draw(img)
    OUT.mkdir(parents=True, exist_ok=True)
    img.convert("RGB").save(OUT / "base.png", optimize=True)
    glow.save(OUT / "glow.png", optimize=True)
    doc = {"about": "Strike City drawn with LimeZu's Modern Exteriors by web/scripts/build_city.py. Credits: limezu.itch.io.",
           "tile": T, "cols": COLS, "rows": ROWS, "buildings": placed, "lamps": decor.lamps, "blocked": sorted(map(list, decor.blocked))}
    MANIFEST.write_text(json.dumps(doc, separators=(",", ":")) + "\n", encoding="utf-8", newline="\n")
    size = sum(f.stat().st_size for f in OUT.glob("*.png"))
    print(f"{len(placed)} buildings, {lit} windows lit at night, {len(decor.lamps)} lamps, {len(decor.items)} props, "
          f"{len(decor.blocked)} tiles taken by props, {size / 1e6:.2f} MB -> {OUT}")


if __name__ == "__main__":
    main()

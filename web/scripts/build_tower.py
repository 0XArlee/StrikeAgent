"""The News Tower's floors, drawn with LimeZu's Modern Interiors (art/limezu, only on the PC, never in git):
web/public/art/tower/<room>.webp + web/src/city/tower.json (per room: where each thing you can look at is, where the
agent stands to look at it, the screens the page writes on, the tiles you can walk and the staff standing around).

Every floor is the same 28 x 14 tiles of 16 px (the same tower), with the lift at the top right:
  lobby     the newsroom (ground floor, the door to the city): the video wall, the teleprinter, the scoreboard
  macro     the Fed press room: the release board, the lectern
  geo       the situation room: the world on a table, the wall screen, the world's clocks
  rules     the court: the bench, the regulators' lectern
  money     the trading floor: the ETF ticker, the desks, the news screens
  security  the security room: the alarm wall, the exchanges' board, the servers

Licence (Modern Interiors, full version): commercial use, edits allowed; no reselling or distributing the asset;
credits to limezu.itch.io. What the site serves is these composed pictures, never the pack's files.

Run (on the PC): .venv/Scripts/python.exe web/scripts/build_tower.py
"""
from __future__ import annotations

import json
from pathlib import Path

from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parents[2]
MI = ROOT / "art" / "limezu" / "modern_interiors"
SINGLES = MI / "1_Interiors" / "16x16" / "Theme_Sorter_Singles"
TV = MI / "6_Home_Designs" / "TV_Studio_Designs" / "16x16"
GENERIC = MI / "1_Interiors" / "16x16" / "Theme_Sorter" / "1_Generic_16x16.png"
BUILDER = MI / "1_Interiors" / "16x16" / "Room_Builder_subfiles"
OUT = ROOT / "web" / "public" / "art" / "tower"
MANIFEST = ROOT / "web" / "src" / "city" / "tower.json"

T = 16
W, H = 28, 14
STAGE_X = 8          # the TV design's columns land here (its stage, columns 2-8, becomes 10-16)
LIFT = {"rect": [24 * T, 1 * T, 2 * T, 2 * T], "stand": [24, 3], "face": "up"}


def single(theme: str, n: int) -> Image.Image:
    folder = next(p for p in SINGLES.iterdir() if p.name.lower().startswith(theme.lower()))
    return Image.open(next(folder.glob(f"*_{n}.png"))).convert("RGBA")


def tile(im: Image.Image, c: int, r: int, w: int = 1, h: int = 1) -> Image.Image:
    return im.crop((c * T, r * T, (c + w) * T, (r + h) * T))


def tinted(im: Image.Image, k: tuple[float, float, float]) -> Image.Image:
    r, g, b, a = im.split()
    return Image.merge("RGBA", tuple(ch.point(lambda v, f=f: min(255, int(v * f))) for ch, f in zip((r, g, b), k)) + (a,))


def mean(im: Image.Image) -> tuple[float, float, float]:
    px = [p for p in (im.get_flattened_data() if hasattr(im, "get_flattened_data") else im.getdata()) if p[3] > 0]
    return tuple(sum(p[i] for p in px) / len(px) for i in range(3))


class Room:
    """One floor: the picture, what blocks the way, the spots, the screens and the staff."""

    def __init__(self, rid: str):
        self.id = rid
        self.im = Image.new("RGBA", (W * T, H * T), (0, 0, 0, 255))
        self.d = ImageDraw.Draw(self.im)
        self.blocked: list[tuple[float, float, float, float]] = []
        self.spots: dict[str, dict] = {}
        self.screens: dict[str, list[int]] = {}
        self.staff: list[dict] = []
        self.extra: dict = {}

    def put(self, im: Image.Image, x: float, y: float, block: tuple[float, float, float, float] | None = None) -> None:
        self.im.alpha_composite(im, (int(x * T), int(y * T)))
        if block:
            self.blocked.append(block)

    def walk(self, door: bool) -> list[str]:
        g = [[1 if 3 <= y <= H - 2 and 2 <= x <= W - 3 else 0 for x in range(W)] for y in range(H)]
        for bx, by, bw, bh in self.blocked:
            for y in range(int(by), int(by + bh + 0.999)):
                for x in range(int(bx), int(bx + bw + 0.999)):
                    if 0 <= x < W and 0 <= y < H:
                        g[y][x] = 0
        for s in self.spots.values():
            g[s["stand"][1]][s["stand"][0]] = 1
        if door:
            g[H - 1][13] = g[H - 1][14] = 1
        # every spot must be reachable from the lift (and the door)
        start = tuple(LIFT["stand"])
        seen, todo = {start}, [start]
        while todo:
            x, y = todo.pop()
            for nx, ny in ((x + 1, y), (x - 1, y), (x, y + 1), (x, y - 1)):
                if 0 <= nx < W and 0 <= ny < H and g[ny][nx] and (nx, ny) not in seen:
                    seen.add((nx, ny)); todo.append((nx, ny))
        for k, s in self.spots.items():
            assert tuple(s["stand"]) in seen, f"{self.id}: {k} cannot be reached"
        for p in self.staff:
            assert g[p["y"]][p["x"]], f"{self.id}: staff on a blocked tile {p}"
        return ["".join(map(str, r)) for r in g]


# ---------------------------------------------------------------------------------------------- the shell
def shell(r: Room, l1: Image.Image, wall: tuple[int, int] | None, floor: tuple[int, int] | None,
          tint: tuple[float, float, float] | None = None, door: bool = False) -> None:
    """Walls, floor and borders: the TV design's frame (columns 0 and 10: the border and the side walls), with this
    floor's wall paper and floor tile (None: the design's own grey wall and carpet)."""
    walls = Image.open(BUILDER / "Room_Builder_Walls_16x16.png").convert("RGBA")
    floors = Image.open(BUILDER / "Room_Builder_Floors_16x16.png").convert("RGBA")
    BORDER = {(248, 248, 248), (58, 58, 80)}

    def src_row(y: int) -> int:   # our rows -> the design's: 0 border, 1-2 wall, 3.. floor, last the bottom border
        return 0 if y == 0 else y if y <= 2 else 9 if y == H - 1 else 8 if y == H - 2 else 5

    wall_t = [tile(walls, *wall), tile(walls, wall[0], wall[1] + 1)] if wall else [tile(l1, 2, 1), tile(l1, 2, 2)]
    side_k = (1.0, 1.0, 1.0)
    if wall:
        a, b = mean(wall_t[0].crop((0, 6, 16, 16))), mean(tile(l1, 2, 1).crop((0, 6, 16, 16)))
        side_k = tuple(max(0.35, min(1.6, x / max(1, y))) for x, y in zip(a, b))
    if tint:
        side_k = tuple(k * t for k, t in zip(side_k, tint))

    def paint(t: Image.Image, k) -> Image.Image:
        """Tint a frame tile, leaving the white border and its dark line alone."""
        px = list(t.get_flattened_data()) if hasattr(t, "get_flattened_data") else list(t.getdata())
        out = [p if p[:3] in BORDER or p[3] == 0 else (min(255, int(p[0] * k[0])), min(255, int(p[1] * k[1])), min(255, int(p[2] * k[2])), p[3])
               for p in px]
        im = Image.new("RGBA", t.size); im.putdata(out)
        return im

    floor_tile = tile(floors, *floor) if floor else None
    for y in range(H):
        for x in range(W):
            edge = x in (0, 1, W - 2, W - 1)
            sx = x if x < 2 else x - (W - 11)
            if y == 0:
                r.put(tile(l1, sx, 0) if edge else tile(l1, 2, 0), x, y)
            elif y == H - 1:
                r.put(tile(l1, 0 if x == 0 else 10 if x == W - 1 else 2, 9), x, y)
            elif y <= 2:
                r.put(paint(tile(l1, sx, y), side_k) if edge else wall_t[y - 1], x, y)
            elif x in (0, W - 1):
                r.put(paint(tile(l1, sx, src_row(y)), side_k), x, y)
            elif floor_tile is None:
                r.put(tile(l1, sx, src_row(y)) if edge else tile(l1, 4, 8), x, y)
            else:
                r.put(floor_tile, x, y)
    if tint and floor:   # the wall paper between the corners and the floor (the frame was painted above)
        r.im.paste(tinted(r.im.crop((2 * T, T, (W - 2) * T, 3 * T)), tint), (2 * T, T))
        r.im.paste(tinted(r.im.crop((T, 3 * T, (W - 1) * T, (H - 1) * T)), tint), (T, 3 * T))
    # the shadows of the back wall and the side walls on the floor
    sh = Image.new("RGBA", (W * T, H * T))
    sd = ImageDraw.Draw(sh)
    for i in range(6):
        sd.rectangle([T, 3 * T + i, (W - 1) * T - 1, 3 * T + i], fill=(0, 0, 0, 70 - i * 11))
        if floor:
            sd.rectangle([T + i, 3 * T, T + i, (H - 1) * T - 1], fill=(0, 0, 0, 60 - i * 10))
            sd.rectangle([(W - 1) * T - 1 - i, 3 * T, (W - 1) * T - 1 - i, (H - 1) * T - 1], fill=(0, 0, 0, 60 - i * 10))
    r.im.alpha_composite(sh)
    if door:
        r.put(tile(l1, 6, 9, 4, 1), 12, H - 1)
    # the lift on every floor (the same shaft)
    generic = Image.open(GENERIC).convert("RGBA")
    r.put(tile(generic, 0, 21, 2, 2), 24, 1)
    r.spots["lift"] = dict(LIFT)
    r.screens["lift"] = [388, 17, 24, 5]


# ---------------------------------------------------------------------------------------------- what the page writes on
def panel(r: Room, x: float, y: float, w: float, h: float, glass=(10, 14, 26), frame=(28, 31, 43), rim=(70, 78, 104),
          dots: tuple[int, int, int] | None = None, name: str | None = None, inset: int = 3) -> list[int]:
    """A screen drawn in the pack's style: dark rim, a lighter frame, glass (with an LED board's unlit dots)."""
    x0, y0, x1, y1 = int(x * T), int(y * T), int((x + w) * T) - 1, int((y + h) * T) - 1
    d = r.d
    d.rectangle([x0 + 1, y1 + 1, x1 + 1, y1 + 2], fill=(0, 0, 0, 90))                 # its shadow on the wall
    d.rectangle([x0, y0, x1, y1], fill=frame + (255,))
    d.rectangle([x0, y0, x1, y1], outline=(18, 20, 28, 255))
    d.line([x0 + 1, y0 + 1, x1 - 1, y0 + 1], fill=rim + (255,))
    gx0, gy0, gx1, gy1 = x0 + inset, y0 + inset, x1 - inset, y1 - inset
    d.rectangle([gx0, gy0, gx1, gy1], fill=glass + (255,))
    if dots:
        for yy in range(gy0 + 1, gy1, 2):
            for xx in range(gx0 + 1, gx1, 2):
                d.point((xx, yy), fill=dots + (255,))
    d.line([gx0, gy0, gx0 + 5, gy0], fill=tuple(min(255, c + 40) for c in glass) + (255,))
    d.point((x1 - 3, y1 - 1), fill=(74, 222, 128, 255))                               # the power light
    rect = [gx0, gy0, gx1 - gx0 + 1, gy1 - gy0 + 1]
    if name:
        r.screens[name] = rect
    return rect


# the continents, roughly (lon, lat): enough for a map of dots
LAND = [
    [(-168, 66), (-162, 70), (-156, 71), (-140, 70), (-128, 70), (-115, 68), (-95, 72), (-85, 70), (-80, 63), (-90, 58), (-94, 56),
     (-82, 55), (-78, 58), (-77, 62), (-70, 60), (-64, 60), (-60, 55), (-56, 52), (-60, 47), (-66, 44), (-70, 42), (-74, 40),
     (-76, 35), (-81, 31), (-80, 26), (-82, 25), (-82, 29), (-85, 30), (-90, 29), (-94, 29), (-97, 26), (-97, 22), (-94, 18),
     (-90, 21), (-87, 21), (-88, 16), (-84, 15), (-83, 10), (-79, 9), (-77, 8), (-80, 7), (-83, 8), (-86, 11), (-88, 13),
     (-92, 14), (-95, 16), (-100, 17), (-105, 20), (-106, 23), (-109, 23), (-114, 30), (-117, 32), (-120, 34), (-123, 38),
     (-124, 42), (-124, 47), (-127, 50), (-132, 54), (-136, 58), (-142, 60), (-150, 60), (-153, 57), (-158, 57), (-164, 55),
     (-158, 58), (-162, 60), (-165, 62)],
    [(-73, 78), (-60, 82), (-35, 83), (-20, 82), (-18, 76), (-22, 70), (-30, 68), (-40, 65), (-43, 60), (-50, 62), (-53, 67), (-56, 72), (-66, 76)],
    [(-120, 74), (-100, 78), (-85, 80), (-70, 82), (-62, 82), (-75, 76), (-80, 73), (-90, 74), (-100, 73), (-110, 72)],
    [(-80, 73), (-68, 70), (-62, 66), (-66, 62), (-75, 65), (-85, 70)],
    [(-77, 8), (-72, 12), (-64, 11), (-60, 8), (-52, 5), (-50, 0), (-44, -2), (-35, -5), (-35, -9), (-39, -14), (-39, -18), (-41, -22),
     (-45, -24), (-48, -27), (-49, -29), (-53, -33), (-58, -35), (-57, -38), (-62, -39), (-65, -42), (-66, -47), (-68, -50), (-69, -53),
     (-68, -55), (-72, -54), (-75, -50), (-74, -44), (-73, -37), (-71, -30), (-70, -18), (-76, -14), (-80, -6), (-81, -2), (-80, 1), (-78, 4)],
    [(5, 58), (5, 62), (10, 64), (14, 68), (18, 70), (25, 71), (30, 70), (28, 66), (25, 65), (22, 65), (19, 63), (17, 61), (18, 59),
     (16, 56), (12, 56), (10, 59), (7, 58)],
    [(-9, 37), (-9, 43), (-2, 43.5), (-1, 46), (-4, 48), (2, 51), (5, 53), (8, 54), (9, 57), (11, 56), (12, 54), (14, 54), (20, 55),
     (21, 57), (24, 59), (28, 60), (32, 65), (40, 66), (44, 68), (55, 68), (60, 69), (70, 73), (80, 73), (90, 75), (100, 77),
     (110, 76), (120, 73), (130, 71), (140, 72), (150, 71), (160, 70), (170, 70), (180, 68), (180, 65), (178, 62), (170, 60),
     (163, 58), (162, 55), (157, 51), (156, 57), (160, 61), (155, 60), (150, 59), (142, 59), (137, 55), (141, 52), (140, 48),
     (135, 43), (130, 42), (129, 36), (126, 35), (126, 38), (125, 40), (121, 40), (122, 37), (119, 35), (121, 32), (122, 30),
     (120, 26), (116, 23), (110, 21), (108, 21), (106, 18), (109, 13), (107, 10), (105, 9), (103, 10), (101, 13), (100, 8),
     (103, 1), (101, 3), (98, 8), (98, 14), (95, 16), (94, 19), (92, 22), (90, 22), (87, 21), (85, 19), (80, 15), (80, 10),
     (77, 8), (73, 16), (72, 21), (68, 23), (66, 25), (62, 25), (57, 25), (56, 27), (52, 28), (50, 30), (48, 30), (50, 26),
     (52, 24), (56, 24), (57, 22), (59, 22), (56, 18), (52, 16), (44, 13), (43, 16), (39, 21), (35, 28), (34, 28), (33, 31),
     (35, 33), (36, 36), (30, 36), (27, 37), (26, 40), (23, 40), (22, 37), (21, 39), (20, 42), (15, 45), (13, 45), (12, 44),
     (14, 42), (16, 41), (18, 40), (16, 38), (15, 40), (12, 42), (10, 44), (8, 44), (4, 43), (3, 42), (0, 39), (-1, 37), (-5, 36)],
    [(-17, 21), (-17, 15), (-16, 12), (-13, 8), (-8, 5), (-4, 5), (2, 6), (6, 4), (9, 4), (9, 1), (10, -2), (12, -5), (13, -12),
     (12, -17), (15, -27), (18, -34), (22, -34), (27, -33), (32, -29), (35, -24), (35, -19), (40, -15), (40, -10), (39, -5),
     (42, 0), (47, 4), (51, 11), (44, 11), (43, 12), (39, 16), (37, 22), (34, 28), (32, 31), (29, 31), (25, 32), (20, 31),
     (19, 30), (15, 32), (11, 33), (10, 37), (3, 37), (-2, 35), (-6, 36), (-10, 30), (-13, 27)],
    [(44, -25), (47, -25), (50, -15), (49, -12), (44, -17)],
    [(-5, 50), (1, 51), (2, 53), (0, 54), (-2, 56), (-2, 58), (-5, 58), (-6, 56), (-5, 54), (-3, 54), (-5, 52)],
    [(-10, 52), (-6, 52), (-6, 55), (-8, 55), (-10, 54)],
    [(-24, 64), (-14, 64), (-14, 66), (-22, 66.5)],
    [(130, 31), (132, 34), (135, 34), (140, 35), (141, 38), (142, 40), (141, 43), (145, 44), (142, 46), (140, 42), (139, 38),
     (136, 36), (132, 35), (130, 33)],
    [(120, 18), (122, 18), (124, 12), (126, 7), (125, 6), (122, 7), (121, 12), (120, 14)],
    [(95, 5), (98, 4), (104, -2), (106, -6), (102, -4)], [(105, -6), (114, -7), (114, -8), (106, -7)],
    [(109, 1), (110, -3), (116, -4), (118, 1), (117, 6), (115, 5), (111, 2)], [(119, 0), (125, 1), (121, -5), (119, -5)],
    [(131, -1), (141, -3), (150, -10), (143, -9), (138, -8)],
    [(114, -22), (114, -34), (118, -35), (124, -33), (131, -31), (135, -35), (138, -35), (140, -38), (146, -39), (150, -37),
     (153, -28), (153, -25), (146, -19), (142, -11), (141, -17), (136, -12), (130, -12), (126, -14), (122, -17)],
    [(172, -35), (175, -37), (178, -38), (174, -41), (171, -44), (167, -46), (170, -46), (174, -41)],
    [(-85, 22), (-80, 23), (-75, 20), (-78, 20)],
]
# where each region's pin goes (lon, lat)
REGIONS = {"us": (-98, 39), "canada": (-105, 57), "latam": (-60, -15), "uk": (-2, 53), "europe": (12, 48), "russia": (50, 58),
           "ukraine": (31, 49), "middle_east": (45, 29), "africa": (20, 3), "india": (78, 22), "china": (108, 34), "japan": (138, 37),
           "korea": (127.5, 36.5), "southeast_asia": (110, 6), "oceania": (140, -26)}
LAT0, LAT1 = 80, -58


def world(r: Room, x: float, y: float, w: float, h: float) -> None:
    """The situation room's table: a world of dots on dark glass, every region's pin position for the page."""
    x0, y0, x1, y1 = int(x * T), int(y * T), int((x + w) * T) - 1, int((y + h) * T) - 1
    d = r.d
    d.rectangle([x0 + 3, y1 + 1, x1 + 3, y1 + 4], fill=(0, 0, 0, 110))               # the table's shadow
    d.rectangle([x0, y0, x1, y1], fill=(33, 38, 58, 255), outline=(14, 16, 26, 255))
    d.rectangle([x0 + 1, y0 + 1, x1 - 1, y0 + 1], fill=(84, 96, 132, 255))
    d.rectangle([x0 + 1, y1 - 2, x1 - 1, y1 - 1], fill=(22, 25, 38, 255))           # its front edge
    gx0, gy0, gx1, gy1 = x0 + 4, y0 + 4, x1 - 4, y1 - 5
    d.rectangle([gx0, gy0, gx1, gy1], fill=(5, 16, 34, 255))
    gw, gh = gx1 - gx0 + 1, gy1 - gy0 + 1
    # the land at 4x, then one dot per 3 px
    k = 4
    mask = Image.new("L", (gw * k, gh * k))
    md = ImageDraw.Draw(mask)
    to_px = lambda lon, lat: ((lon + 180) / 360 * gw * k, (LAT0 - lat) / (LAT0 - LAT1) * gh * k)
    for poly in LAND:
        md.polygon([to_px(*p) for p in poly], fill=255)
    for yy in range(1, gh - 1, 3):
        for xx in range(1, gw - 1, 3):
            land = mask.getpixel((xx * k + k // 2, yy * k + k // 2)) > 0
            col = (34, 211, 238, 200) if land else (16, 40, 62, 255)
            d.rectangle([gx0 + xx, gy0 + yy, gx0 + xx + (1 if land else 0), gy0 + yy + (1 if land else 0)], fill=col)
    for lat in (60, 30, 0, -30):                                                      # faint parallels
        yy = gy0 + int((LAT0 - lat) / (LAT0 - LAT1) * gh)
        for xx in range(gx0, gx1, 4):
            d.point((xx, yy), fill=(20, 70, 96, 255))
    r.screens["map"] = [gx0, gy0, gw, gh]
    r.extra["pins"] = {k_: [round(gx0 + (lon + 180) / 360 * gw), round(gy0 + (LAT0 - lat) / (LAT0 - LAT1) * gh)]
                       for k_, (lon, lat) in REGIONS.items()}


# ---------------------------------------------------------------------------------------------- the floors
def lobby(l1, l2, l3, generic) -> Room:
    r = Room("lobby")
    shell(r, l1, None, None, door=True)
    put = r.put
    # the white stage under the anchors' desk (the design's columns 2-8, rows 3-6), the video wall
    for y in range(3, 7):
        for x in range(2, 9):
            put(tile(l1, x, y), x + STAGE_X, y + 1)
    put(tile(l1, 3, 1, 5, 2), 3 + STAGE_X, 1)
    # the TV set: lights, stools, the anchors' chairs and desk, cameras (the design's furniture, one row down)
    r.im.alpha_composite(l2.crop((0, 0, l2.width, 2 * T)), (STAGE_X * T, 0))      # the light rail stays at the ceiling
    r.im.alpha_composite(l2.crop((0, 2 * T, l2.width, l2.height)), (STAGE_X * T, 3 * T))
    r.im.alpha_composite(l3, (STAGE_X * T, 1 * T))
    r.blocked += [(STAGE_X + 1, 2, 9, 5), (STAGE_X + 1, 7, 2, 4), (STAGE_X + 7, 8, 2, 3), (STAGE_X + 3, 7, 5, 2)]
    # the newsroom (left): the events board and the world map on the wall, two rows of desks with their editors
    put(single("5_Classroom", 33), 2, 1.5)
    put(single("5_Classroom", 31), 5, 1)
    for y in (5, 9):
        put(single("5_Classroom", 49), 1, y)
        put(single("5_Classroom", 50), 3, y)
        put(single("5_Classroom", 51), 4, y)
        put(single("5_Classroom", 52), 5, y, block=(1, y, 6, 3))
    put(tile(generic, 13, 28, 2, 3), 7, 10, block=(7, 12, 2, 1))
    # the right: the scoreboard screens, the teleprinter, a desk, a water cooler, a palm
    put(single("23_Television", 41), 19, 1)
    put(single("23_Television", 41), 21, 1)
    put(single("5_Classroom", 54), 20, 6, block=(20, 6, 2, 3))
    put(single("5_Classroom", 49), 22, 9)
    put(single("5_Classroom", 50), 24, 9)
    put(single("5_Classroom", 52), 25, 9, block=(22, 9, 5, 3))
    put(single("13_Conference", 43), 25, 4, block=(25, 4, 1, 2))
    put(tile(generic, 13, 28, 2, 3), 18, 10, block=(18, 12, 2, 1))
    r.spots.update({
        "screen":  {"rect": [(3 + STAGE_X) * T + 22, 1 * T + 3, 4 * T - 12, 2 * T - 8], "stand": [13, 10], "face": "up"},
        "desks":   {"rect": [1 * T, 5 * T, 6 * T, 3 * T], "stand": [4, 8], "face": "up"},
        "board":   {"rect": [2 * T, int(1.5 * T), 2 * T, 1 * T], "stand": [3, 4], "face": "up"},
        "printer": {"rect": [20 * T, 6 * T, 2 * T, 3 * T], "stand": [21, 9], "face": "up"},
        "score":   {"rect": [19 * T + 2, 1 * T + 2, 4 * T - 4, 2 * T - 6], "stand": [20, 4], "face": "up"},
        "door":    {"rect": [12 * T, (H - 1) * T, 4 * T, T], "stand": [13, H - 2], "face": "down"},
    })
    r.screens.update({"wall": [195, 19, 42, 17], "wallL": [179, 19, 10, 17], "wallR": [243, 19, 10, 17],
                      "score1": [307, 19, 29, 17], "score2": [339, 19, 29, 17], "board": [33, 25, 30, 13], "paper": [325, 101, 14, 8]})
    r.staff = [{"x": 16, "y": 11, "dir": "up", "anim": "idle", "seed": "camera-op"},
               {"x": 23, "y": 6, "dir": "left", "anim": "read", "seed": "wire-editor"}]
    return r


def macro(l1) -> Room:
    """The Fed press room: blue backdrop, the release board, a stage with the lectern and flags, the press."""
    r = Room("macro")
    shell(r, l1, (12, 34), (8, 16))
    put = r.put
    panel(r, 6, 1, 14, 2, glass=(8, 8, 10), frame=(24, 26, 34), rim=(60, 64, 84), dots=(26, 22, 18), name="board", inset=2)
    for x in range(9, 19):                                                            # the stage
        for y in (3, 4):
            put(single("13_Conference", 22), x, y)
        put(single("13_Conference", 23), x, 5)
    put(single("13_Conference", 64), 9, 3, block=(9, 3, 1, 2))
    put(single("13_Conference", 61), 10, 3, block=(10, 3, 1, 2))
    put(single("13_Conference", 61), 17, 3, block=(17, 3, 1, 2))
    put(single("13_Conference", 64), 18, 3, block=(18, 3, 1, 2))
    put(single("13_Conference", 46), 13, 3, block=(13, 3, 1, 2))                    # the lectern, with its seal
    for y in (7, 9):                                                                  # the press
        for x in (4, 5, 6, 7, 8, 9, 17, 18, 19, 20, 21, 22):
            put(single("13_Conference", 39), x, y, block=(x, y + 1, 1, 1))
    put(single("23_Television", 5), 3, 4, block=(3, 5, 1, 1))                        # cameras on the sides
    put(single("23_Television", 6), 23, 4, block=(23, 5, 1, 1))
    put(single("23_Television", 1), 12, 11, block=(12, 12, 2, 1))                    # the pool camera, at the back
    put(single("13_Conference", 43), 2, 3, block=(2, 4, 1, 1))
    put(single("22_Museum", 196), 2, 10, block=(2, 12, 2, 1))
    put(single("22_Museum", 196), 23, 10, block=(23, 12, 2, 1))
    r.spots.update({
        "board":  {"rect": r.screens["board"], "stand": [14, 6], "face": "up"},
        "podium": {"rect": [12 * T, 3 * T, 3 * T, 2 * T], "stand": [14, 4], "face": "down"},
    })
    r.staff = [{"x": 11, "y": 10, "dir": "up", "anim": "read", "seed": "reporter-1"},
               {"x": 16, "y": 8, "dir": "up", "anim": "phone", "seed": "reporter-2"},
               {"x": 15, "y": 4, "dir": "down", "anim": "idle", "seed": "fed-aide"}]
    return r


def geo(l1) -> Room:
    """The situation room: the world on a table, the wall screen, the clocks of the markets."""
    r = Room("geo")
    shell(r, l1, (1, 30), (12, 16), tint=(0.62, 0.74, 1.05))
    put = r.put
    panel(r, 2.5, 1, 9, 2, glass=(6, 14, 28), name="wall")
    for i, x in enumerate((13, 15.5, 18)):
        panel(r, x, 1, 2.25, 2, glass=(8, 10, 16), dots=(18, 20, 28), name=f"clock{i}", inset=2)
    put(single("23_Television", 77), 21.25, 1.25)
    world(r, 6, 5, 16, 6)
    r.blocked.append((6, 5, 16, 6))
    for x in (8, 11, 16, 19):
        put(single("13_Conference", 39), x, 3, block=(x, 4, 1, 1))
    put(single("22_Museum", 196), 2, 9, block=(2, 11, 2, 1))
    put(single("22_Museum", 196), 23, 9, block=(23, 11, 2, 1))
    r.spots.update({
        "map":    {"rect": r.screens["map"], "stand": [13, 11], "face": "up"},
        "wall":   {"rect": r.screens["wall"], "stand": [6, 4], "face": "up"},
        "clocks": {"rect": [13 * T, 1 * T, 7 * T + 4, 2 * T], "stand": [17, 4], "face": "up"},
    })
    r.staff = [{"x": 4, "y": 7, "dir": "right", "anim": "read", "seed": "analyst-1"},
               {"x": 23, "y": 7, "dir": "left", "anim": "phone", "seed": "analyst-2"}]
    return r


def rules(l1) -> Room:
    """The court: columns, the bench under the docket, flags, the regulators' lectern, the public's benches."""
    r = Room("rules")
    shell(r, l1, (1, 6), (12, 4))
    put = r.put
    d = r.d
    # the red carpet up the middle
    x0, x1, y0, y1 = 11 * T + 4, 16 * T - 5, 6 * T, (H - 1) * T - 1
    d.rectangle([x0, y0, x1, y1], fill=(122, 26, 40, 255))
    d.rectangle([x0, y0, x1, y1], outline=(201, 162, 74, 255))
    d.rectangle([x0 + 2, y0 + 2, x1 - 2, y1], outline=(150, 40, 54, 255))
    for x in (3, 7, 20, 22):
        put(single("22_Museum", 143), x, 0.6, block=(x, 3, 1, 1))
    panel(r, 10, 1, 7, 2, glass=(20, 44, 34), frame=(92, 58, 30), rim=(150, 104, 60), name="docket")
    for x in (11, 13, 15):
        put(single("13_Conference", 40), x, 2.6)
    for i, x in enumerate(range(10, 17)):
        put(single("13_Conference", 27 if x == 13 else 26), x, 4)
    r.blocked.append((10, 3, 7, 3))
    put(single("13_Conference", 60), 9, 3, block=(9, 3, 1, 2))
    put(single("13_Conference", 63), 17, 3, block=(17, 3, 1, 2))
    put(single("13_Conference", 45), 5, 5, block=(5, 5, 1, 2))                       # the regulators' lectern
    for y in (9, 11):
        for x in (4, 7, 17, 20):
            put(single("22_Museum", 36), x, y, block=(x, y, 2, 1))
    put(single("5_Classroom", 47), 4.5, 0.4, block=(4, 3, 3, 1))                    # the law library
    put(single("5_Classroom", 46), 18, 0.4, block=(18, 3, 2, 1))
    put(single("22_Museum", 197), 2, 10, block=(2, 12, 2, 1))
    put(single("22_Museum", 197), 23, 10, block=(23, 12, 2, 1))
    put(single("22_Museum", 79), 9, 7, block=(9, 8, 1, 1))
    put(single("22_Museum", 79), 17, 7, block=(17, 8, 1, 1))
    r.spots.update({
        "bench":   {"rect": [10 * T, 1 * T, 7 * T, 5 * T], "stand": [13, 7], "face": "up"},
        "rostrum": {"rect": [4 * T, 4 * T, 3 * T, 3 * T], "stand": [5, 8], "face": "up"},
    })
    r.staff = [{"x": 8, "y": 6, "dir": "up", "anim": "read", "seed": "lawyer-1"},
               {"x": 19, "y": 7, "dir": "left", "anim": "phone", "seed": "clerk-1"}]
    return r


def money(l1) -> Room:
    """The trading floor: the ETF ticker, two rows of terminals each side, the news channels on the wall."""
    r = Room("money")
    shell(r, l1, (23, 24), (12, 26))
    put = r.put
    panel(r, 2.5, 1, 9.5, 2, glass=(4, 12, 8), dots=(10, 26, 16), name="ticker", inset=2)
    put(single("23_Television", 48), 13, 1)
    put(single("23_Television", 49), 15, 1)
    put(single("23_Television", 52), 17, 1)
    put(single("23_Television", 53), 19, 1)
    put(single("5_Classroom", 31), 21, 1)
    for y in (5, 9):
        for i, x in enumerate((3, 4, 5, 6, 7, 8)):
            put(single("13_Conference", (29, 31, 30, 32, 29, 28)[i]), x, y)
            put(single("13_Conference", (29, 31, 30, 32, 29, 28)[(i + 3) % 6]), x + 13, y)
        r.blocked += [(3, y, 6, 2), (16, y, 6, 2)]
        for x in (3, 5, 7, 16, 18, 20):
            put(single("13_Conference", 37), x, y + 1.6, block=(x, y + 2, 1, 1))
    put(single("22_Museum", 195), 12, 11, block=(12, 12, 1, 1))
    put(single("22_Museum", 195), 14, 11, block=(14, 12, 1, 1))
    r.spots.update({
        "etf":   {"rect": r.screens["ticker"], "stand": [7, 4], "face": "up"},
        "flows": {"rect": [13 * T, 1 * T, 7 * T, 2 * T], "stand": [16, 4], "face": "up"},
        "desks": {"rect": [16 * T, 5 * T, 6 * T, 7 * T], "stand": [13, 8], "face": "right"},
    })
    r.staff = [{"x": 4, "y": 8, "dir": "up", "anim": "phone", "seed": "trader-1"},
               {"x": 19, "y": 12, "dir": "up", "anim": "read", "seed": "trader-2"},
               {"x": 10, "y": 6, "dir": "down", "anim": "idle", "seed": "trader-3"}]
    return r


def security(l1) -> Room:
    """The security room: the alarm wall, the exchanges' board, the monitoring desks, the servers."""
    r = Room("security")
    shell(r, l1, (1, 30), (8, 28), tint=(0.92, 0.86, 0.9))
    put = r.put
    panel(r, 2.5, 1, 9.5, 2, glass=(10, 8, 10), name="alarm")
    panel(r, 13.5, 1, 8, 2, glass=(8, 10, 16), dots=(16, 18, 26), name="exchanges", inset=2)
    put(single("23_Television", 77), 12.25, 1.25)
    put(single("23_Television", 77), 22.25, 1.25)
    for i, x in enumerate(range(9, 17)):
        put(single("13_Conference", 31 if i % 2 else 32), x, 6)
        if i % 2 == 0:
            put(single("13_Conference", 39), x + 0.5, 7.6, block=(x, 8, 2, 1))
    r.blocked.append((9, 6, 8, 2))
    leds = []
    for x in list(range(3, 9)) + list(range(18, 24)):
        put(single("5_Classroom", 40), x, 10, block=(x, 10, 1, 2))
        leds.append([x * T + 4, 10 * T + 7])
    r.extra["leds"] = leds          # the servers' lights, blinking on the page
    r.spots.update({
        "alarm":     {"rect": r.screens["alarm"], "stand": [7, 4], "face": "up"},
        "exchanges": {"rect": r.screens["exchanges"], "stand": [17, 4], "face": "up"},
        "servers":   {"rect": [3 * T, 10 * T, 6 * T, 2 * T], "stand": [5, 9], "face": "down"},
    })
    r.staff = [{"x": 12, "y": 9, "dir": "up", "anim": "phone", "seed": "soc-1"},
               {"x": 20, "y": 9, "dir": "down", "anim": "read", "seed": "soc-2"}]
    return r


def main() -> None:
    if not TV.exists():
        raise SystemExit(f"LimeZu's Modern Interiors is not unpacked in {MI}")
    l1, l2, l3 = (Image.open(TV / f"Tv_Studio_Design_layer_{i}.png").convert("RGBA") for i in (1, 2, 3))
    generic = Image.open(GENERIC).convert("RGBA")
    rooms = [lobby(l1, l2, l3, generic), macro(l1), geo(l1), rules(l1), money(l1), security(l1)]
    OUT.mkdir(parents=True, exist_ok=True)
    for old in OUT.glob("floor*"):
        old.unlink()
    out = {"about": "The News Tower's floors drawn with LimeZu's Modern Interiors by web/scripts/build_tower.py. Credits: limezu.itch.io.",
           "tile": T, "w": W, "h": H, "rooms": {}}
    for r in rooms:
        r.im.convert("RGB").save(OUT / f"{r.id}.webp", lossless=True, method=6)
        out["rooms"][r.id] = {"spots": r.spots, "screens": r.screens, "staff": r.staff, "walk": r.walk(door=r.id == "lobby"), **r.extra}
        print(f"{r.id}: {(OUT / f'{r.id}.webp').stat().st_size / 1e3:.0f} KB, {len(r.spots)} spots")
    MANIFEST.write_text(json.dumps(out, separators=(",", ":")) + "\n", encoding="utf-8", newline="\n")


if __name__ == "__main__":
    main()

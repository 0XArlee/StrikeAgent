"""The LimeZu character pieces cut down for the web: art/limezu (the licensed pack, only on the PC, never in git) ->
web/public/art/chars/<part>/<id>.png (the 5 animation rows the city uses, 16x16 scale) + per-part thumbnail strips
+ web/src/city/chars.json (the catalogue: every piece, its group and colour, and the sheet layout).

LimeZu's character generator: every piece (body, eyes, outfit, hairstyle, accessory) is a sheet with the same frame
grid (16x32 frames), stacked in that order. Licence (Modern Interiors full version): commercial use allowed, no
reselling or redistributing the asset, credits to limezu.itch.io (shown on the site).

Run (on the PC, after downloading the pack): .venv/Scripts/python.exe web/scripts/build_art.py
"""
from __future__ import annotations

import json
import re
from collections import Counter
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "art" / "limezu" / "modern_interiors" / "2_Characters" / "Character_Generator"
OUT = ROOT / "web" / "public" / "art" / "chars"
MANIFEST = ROOT / "web" / "src" / "city" / "chars.json"

FW, FH = 16, 32
FRAMES = 24                                   # 6 frames x 4 directions (right, up, left, down)
ROWS = {"idle": 1, "walk": 2, "sit": 4, "phone": 6, "read": 7}   # rows of LimeZu's sheet the city uses
FRONT = 18                                    # the first idle frame facing down (the thumbnails)
PARTS = {   # part -> (glob, id pattern from the file name)
    "body": ("Bodies/16x16/Body_*.png", r"Body_(\d+)$"),
    "eyes": ("Eyes/16x16/Eyes_*.png", r"Eyes_(\d+)$"),
    "outfit": ("Outfits/16x16/Outfit_*.png", r"Outfit_(\d+)_(\d+)$"),
    "hair": ("Hairstyles/16x16/Hairstyle_*.png", r"Hairstyle_(\d+)_(\d+)$"),
    "acc": ("Accessories/16x16/Accessory_*.png", r"Accessory_(\d+)_([A-Za-z_]+?)_(\d+)$"),   # names like Party_Cone
}
DEFAULTS = {"body": "03", "eyes": "01", "outfit": "01_01", "hair": "01_01", "acc": None}


def strip(im: Image.Image) -> Image.Image:
    """The rows the city uses, one under the other, 24 frames wide."""
    out = Image.new("RGBA", (FRAMES * FW, len(ROWS) * FH))
    for i, r in enumerate(ROWS.values()):
        out.alpha_composite(im.crop((0, r * FH, FRAMES * FW, r * FH + FH)), (0, i * FH))
    return out


def front(im: Image.Image) -> Image.Image:
    return im.crop((FRONT * FW, ROWS["idle"] * FH, FRONT * FW + FW, ROWS["idle"] * FH + FH))


def main_colour(frame: Image.Image) -> str:
    """The piece's dominant colour (opaque pixels, outlines left out): its swatch, and how old looks are matched."""
    data = frame.get_flattened_data() if hasattr(frame, "get_flattened_data") else frame.getdata()
    px = [p[:3] for p in data if p[3] == 255 and sum(p[:3]) > 120]
    if not px:
        return "#808080"
    r, g, b = Counter(px).most_common(1)[0][0]
    return f"#{r:02x}{g:02x}{b:02x}"


def variant_colours(ims: list[Image.Image]) -> list[str]:
    """Each colour variant of one style, by the colour that changes between them (the recoloured part): the most
    common pixel among those that differ from variant to variant. The most common pixel overall is often the outline
    or the shading, which every variant shares."""
    flat = lambda im: list(im.get_flattened_data() if hasattr(im, 'get_flattened_data') else im.getdata())
    frames = [flat(front(im)) for im in ims]
    if len(frames) < 2:
        return [main_colour(front(ims[0]))]
    idx = [i for i in range(len(frames[0])) if all(f[i][3] == 255 for f in frames) and any(f[i] != frames[0][i] for f in frames[1:])]
    out = []
    for f, im in zip(frames, ims):
        c = Counter(f[i][:3] for i in idx)
        if not c:
            out.append(main_colour(front(im)))
            continue
        r, g, b = c.most_common(1)[0][0]
        out.append(f"#{r:02x}{g:02x}{b:02x}")
    return out


def main() -> None:
    if not SRC.exists():
        raise SystemExit(f"LimeZu's Modern Interiors is not unpacked in {SRC.parent.parent.parent}")
    catalogue: dict[str, list[dict]] = {}
    images: dict[str, dict[str, Image.Image]] = {}
    for part, (pattern, rx) in PARTS.items():
        items, imgs = [], {}
        for f in sorted(SRC.glob(pattern)):
            m = re.match(rx, f.stem)
            if not m:
                continue
            im = Image.open(f).convert("RGBA")
            if part == "acc":
                style, name, var = m.group(1), m.group(2), m.group(3)
                pid = f"{style}_{var}"
                item = {"id": pid, "style": style, "name": name.replace("_", " ")}
            elif part in ("outfit", "hair"):
                style, var = m.group(1), m.group(2)
                pid = f"{style}_{var}"
                item = {"id": pid, "style": style}
            else:
                pid = m.group(1)
                item = {"id": pid}
            item["rgb"] = main_colour(front(im))
            items.append(item)
            imgs[pid] = im
            dst = OUT / part / f"{pid}.png"
            dst.parent.mkdir(parents=True, exist_ok=True)
            strip(im).save(dst, optimize=True)
        if part in ("outfit", "hair", "acc"):
            for style in dict.fromkeys(it["style"] for it in items):
                group = [it for it in items if it["style"] == style]
                for it, rgb in zip(group, variant_colours([imgs[it["id"]] for it in group])):
                    it["rgb"] = rgb
        catalogue[part], images[part] = items, imgs

    # thumbnails: every piece facing you on a default character, side by side (one image per part for the editor)
    base_body, base_eyes = images["body"][DEFAULTS["body"]], images["eyes"][DEFAULTS["eyes"]]
    base_outfit = images["outfit"][DEFAULTS["outfit"]]
    for part, items in catalogue.items():
        sheet = Image.new("RGBA", (len(items) * FW, FH))
        for i, it in enumerate(items):
            piece = images[part][it["id"]]
            if part == "body":
                layers = [piece, base_eyes, base_outfit]
            elif part == "eyes":
                layers = [base_body, piece, base_outfit]
            elif part == "outfit":
                layers = [base_body, base_eyes, piece]
            elif part == "hair":
                layers = [base_body, base_eyes, base_outfit, piece]
            else:
                layers = [base_body, base_eyes, base_outfit, images["hair"][DEFAULTS["hair"]], piece]
            cell = Image.new("RGBA", (FW, FH))
            for layer in layers:
                cell.alpha_composite(front(layer))
            sheet.alpha_composite(cell, (i * FW, 0))
        sheet.save(OUT / f"{part}_thumbs.png", optimize=True)

    doc = {
        "about": "LimeZu Modern Interiors character pieces, cut down by web/scripts/build_art.py. Credits: limezu.itch.io.",
        "credit": "LimeZu (limezu.itch.io)",
        "frame": [FW, FH], "feet": 31, "top": 10,
        "rows": {k: i for i, k in enumerate(ROWS)},
        "dirs": ["right", "up", "left", "down"],
        "anims": {"idle": {"perDir": 6, "fps": 5}, "walk": {"perDir": 6, "fps": 10}, "sit": {"perDir": 6, "fps": 4},
                  "phone": {"frames": 12, "loop": [4, 9], "fps": 6}, "read": {"frames": 12, "loop": [1, 6], "fps": 5}},
        "order": ["body", "eyes", "outfit", "hair", "acc"],
        "defaults": DEFAULTS,
        "parts": catalogue,
    }
    MANIFEST.write_text(json.dumps(doc, indent=1) + "\n", encoding="utf-8", newline="\n")
    size = sum(f.stat().st_size for f in OUT.rglob("*.png"))
    print({p: len(v) for p, v in catalogue.items()}, f"{size / 1e6:.2f} MB in {OUT}", "->", MANIFEST)


if __name__ == "__main__":
    main()

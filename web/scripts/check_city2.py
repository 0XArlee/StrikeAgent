"""Checks the new art's map (city2.json, from build_city.py) the way the city walks it (world.ts): every building's door
and the plaza must be reachable on foot from each other, and no door may be covered by a prop.

Run: .venv/Scripts/python.exe web/scripts/check_city2.py   (exit 1 if something is not reachable)
"""
from __future__ import annotations

import json
import sys
from collections import deque
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import build_city as bc  # noqa: E402

doc = json.loads(bc.MANIFEST.read_text(encoding="utf-8"))
walk = [[False] * bc.COLS for _ in range(bc.ROWS)]
for y in range(bc.ROWS):
    for x in range(bc.COLS):
        walk[y][x] = bc.is_crosswalk(x, y) if bc.is_road(x, y) else True
for b in doc["buildings"]:
    for y in range(b["y"], b["door"]["y"]):
        for x in range(b["x"], b["x"] + b["w"]):
            walk[y][x] = False
for y in range(34, 37):            # the fountain's basin (world.ts)
    for x in range(47, 51):
        walk[y][x] = False
for x, y in bc.KIOSKS:
    for yy in (y, y + 1):
        for xx in (x, x + 1):
            walk[yy][xx] = False
for x, y in doc["blocked"]:
    walk[y][x] = False

start = (40, 33)                    # world.ts plazaSpot's fallback: a plaza tile
seen = {start}
q = deque([start])
while q:
    x, y = q.popleft()
    for nx, ny in ((x + 1, y), (x - 1, y), (x, y + 1), (x, y - 1)):
        if 0 <= nx < bc.COLS and 0 <= ny < bc.ROWS and walk[ny][nx] and (nx, ny) not in seen:
            seen.add((nx, ny))
            q.append((nx, ny))
bad = []
for b in doc["buildings"]:
    d = (b["door"]["x"], b["door"]["y"])
    if not walk[d[1]][d[0]]:
        bad.append(f"{b['id']}: its door tile {d} is not walkable")
    elif d not in seen:
        bad.append(f"{b['id']}: its door {d} cannot be reached from the plaza")
total = sum(row.count(True) for row in walk)
print(f"walkable tiles {total}, reachable from the plaza {len(seen)} ({len(seen) / total:.0%}), doors checked {len(doc['buildings'])}")
for m in bad:
    print("FAIL", m)
sys.exit(1 if bad else 0)

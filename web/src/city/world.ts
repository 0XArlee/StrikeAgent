// Strike City layout (tile = 16 art px) and its static rendering (pre-rendered once to an offscreen canvas).
//
// The new art (LimeZu's Modern Exteriors, composed by web/scripts/build_city.py into art/city/base.png + glow.png and
// city2.json): for now only with ?art=new in the city's address (kept for the tab), to compare it with the city drawn
// here. Same map, roads, plaza and doors; its buildings are taller (their floors) and its props are where city2.json
// says.
import city2 from "./city2.json";

export const ART2 = (() => {
  try {
    if (/[?&]art=new\b/.test(location.hash + location.search)) sessionStorage.setItem("sf-art", "new");
    if (/[?&]art=old\b/.test(location.hash + location.search)) sessionStorage.removeItem("sf-art");
    return sessionStorage.getItem("sf-art") === "new";
  } catch { return false; }
})();
const art: { base?: HTMLImageElement; glow?: HTMLImageElement } = {};
/** The new art's pictures, loaded (resolves at once without the new art, or if they cannot be loaded). */
export const artReady: Promise<void> = !ART2 ? Promise.resolve() : Promise.all((["base", "glow"] as const).map((k) => new Promise<void>((ok) => {
  const im = new Image();
  im.onload = () => { art[k] = im; ok(); };
  im.onerror = () => ok();
  im.src = `${import.meta.env.BASE_URL ?? "/"}art/city/${k}.png`;
}))).then(() => undefined);
export const TILE = 16;
export const COLS = 96;
export const ROWS = 64;
export const W = COLS * TILE;
export const H = ROWS * TILE;

export type Kind = "exchange" | "tower" | "lab" | "risk" | "vault" | "clan" | "hq" | "home" | "cafe" | "shop" | "arena" | "alley";

export interface Building {
  id: string;
  kind: Kind;
  label: string;
  sub?: string;
  x: number; y: number; w: number; d: number;  // roof footprint in tiles
  h: number;                                    // facade height in art px
  wall: string; roof: string; neon: string;
  market?: string;                              // for market towers
  door: { x: number; y: number };               // walkable tile in front of the door
}

const HROADS = [18, 42];       // top tile row of each 2-tile horizontal road
const VROADS = [24, 48, 72];   // left tile col of each 2-tile vertical road

export const BUILDINGS: Building[] = [
  { id: "lab", kind: "lab", label: "SIGNAL LAB", sub: "chart analysis", x: 4, y: 4, w: 14, d: 7, h: 40, wall: "#1b2440", roof: "#253256", neon: "#67e8f9", door: { x: 11, y: 16 } },
  { id: "btc", kind: "tower", label: "BTC TOWER", market: "BTC-USD", x: 29, y: 2, w: 14, d: 8, h: 72, wall: "#2a1d10", roof: "#3b2a16", neon: "#f7931a", door: { x: 36, y: 16 } },
  { id: "eth", kind: "tower", label: "ETH TOWER", market: "ETH-USD", x: 53, y: 2, w: 14, d: 8, h: 72, wall: "#1c1f3b", roof: "#272c55", neon: "#8b9cff", door: { x: 60, y: 16 } },
  { id: "sol", kind: "tower", label: "SOL TOWER", market: "SOL-USD", x: 77, y: 2, w: 10, d: 8, h: 64, wall: "#16263a", roof: "#1d3550", neon: "#14f195", door: { x: 82, y: 16 } },
  { id: "alts", kind: "shop", label: "ALT ROW", sub: "XRP · BNB · ADA", x: 88, y: 6, w: 7, d: 4, h: 30, wall: "#262033", roof: "#342b47", neon: "#c084fc", door: { x: 91, y: 16 } },
  { id: "risk", kind: "risk", label: "RISK OFFICE", sub: "every order checked", x: 4, y: 22, w: 12, d: 6, h: 36, wall: "#2a2f37", roof: "#363c46", neon: "#f8931a", door: { x: 10, y: 34 } },
  { id: "alley", kind: "alley", label: "LIQUIDATION ALLEY", x: 17, y: 30, w: 5, d: 5, h: 26, wall: "#2a1215", roof: "#3a171c", neon: "#f43f5e", door: { x: 19, y: 40 } },
  { id: "exchange", kind: "exchange", label: "STRIKE EXCHANGE", sub: "order book", x: 32, y: 21, w: 32, d: 6, h: 52, wall: "#0d1f19", roof: "#123026", neon: "#4efab0", door: { x: 48, y: 31 } },
  { id: "vault", kind: "vault", label: "VAULT BANK", sub: "strike vaults", x: 77, y: 22, w: 14, d: 6, h: 40, wall: "#1f2333", roof: "#2a3046", neon: "#facc15", door: { x: 84, y: 34 } },
  { id: "clan", kind: "clan", label: "CLAN HALL", x: 78, y: 34, w: 12, d: 4, h: 30, wall: "#251a33", roof: "#33244a", neon: "#a78bfa", door: { x: 84, y: 40 } },
  { id: "homes", kind: "home", label: "AGENT HOMES", sub: "paused agents rest here", x: 3, y: 46, w: 18, d: 7, h: 34, wall: "#22262d", roof: "#2e333c", neon: "#93c5fd", door: { x: 12, y: 59 } },
  { id: "hq", kind: "hq", label: "SMART FLOW HQ", sub: "builder", x: 28, y: 46, w: 12, d: 7, h: 46, wall: "#0b1d17", roof: "#0f2c22", neon: "#4efab0", door: { x: 34, y: 59 } },
  { id: "cafe", kind: "cafe", label: "FUNDING CAFE", x: 41, y: 49, w: 6, d: 4, h: 24, wall: "#2b211a", roof: "#3a2c22", neon: "#fb923c", door: { x: 44, y: 59 } },
  { id: "arena", kind: "arena", label: "RANKS ARENA", sub: "leaderboard", x: 53, y: 46, w: 16, d: 7, h: 40, wall: "#2a1820", roof: "#3a2230", neon: "#fb7185", door: { x: 61, y: 59 } },
];
// the new art's buildings are as tall as their floors: the same place and door, another depth and height
if (ART2) for (const g of city2.buildings) {
  const b = BUILDINGS.find((x) => x.id === g.id);
  if (b) Object.assign(b, { y: g.y, d: g.d, h: g.h });
}

// plaza (walkable, decorated) in front of the exchange; the fountain sits in the middle
export const PLAZA = { x: 27, y: 28, w: 44, d: 13 };
export const FOUNTAIN = { x: 48 * TILE + TILE, y: 35 * TILE };
export const SCREEN = { x: 36 * TILE, y: 21 * TILE - 2, w: 24 * TILE, h: 4 * TILE };   // exchange roof screen

// ---------------------------------------------------------------- walkability
export const walk = new Uint8Array(COLS * ROWS);   // 1 = walkable
const isRoadRow = (y: number) => HROADS.some((r) => y === r || y === r + 1);
const isRoadCol = (x: number) => VROADS.some((c) => x === c || x === c + 1);
// the central avenue stops at the plaza: the exchange block is pedestrian
const PEDESTRIAN = { x0: 48, x1: 49, y0: 20, y1: 41 };
function vRoad(x: number, y: number) {
  return isRoadCol(x) && !(x >= PEDESTRIAN.x0 && x <= PEDESTRIAN.x1 && y >= PEDESTRIAN.y0 && y <= PEDESTRIAN.y1);
}

export function isRoad(x: number, y: number) { return isRoadRow(y) || vRoad(x, y); }
export function isCrosswalk(x: number, y: number) {
  // stripes across each road next to every intersection
  const nearI = VROADS.some((c) => x >= c - 2 && x <= c + 3) && HROADS.some((r) => y >= r - 2 && y <= r + 3);
  return nearI && isRoad(x, y) && !(isRoadRow(y) && vRoad(x, y));
}
export function isSidewalk(x: number, y: number) {
  if (isRoad(x, y)) return false;
  return HROADS.some((r) => y === r - 1 || y === r + 2) || VROADS.some((c) => (x === c - 1 || x === c + 2) && vRoad(c, y));
}
// each door sits on the first walkable row right under its facade
for (const b of BUILDINGS) b.door.y = b.y + b.d + Math.ceil(b.h / TILE);

export function footprint(b: Building) { return { x0: b.x, y0: b.y, x1: b.x + b.w, y1: b.y + b.d + Math.ceil(b.h / TILE) }; }

for (let y = 0; y < ROWS; y++) for (let x = 0; x < COLS; x++) {
  const road = isRoad(x, y);
  walk[y * COLS + x] = road ? (isCrosswalk(x, y) ? 1 : 0) : 1;
}
for (const b of BUILDINGS) {
  const f = footprint(b);
  for (let y = f.y0; y < f.y1; y++) for (let x = f.x0; x < f.x1; x++) if (x < COLS && y < ROWS) walk[y * COLS + x] = 0;
}
// fountain basin
for (let y = 34; y <= 36; y++) for (let x = 47; x <= 50; x++) walk[y * COLS + x] = 0;
// plaza furniture: two kiosks and benches facing the fountain
export const KIOSKS = [{ x: 33, y: 37, color: "#4efab0" }, { x: 62, y: 37, color: "#fb923c" }];
for (const k of KIOSKS) for (let y = k.y; y < k.y + 2; y++) for (let x = k.x; x < k.x + 2; x++) walk[y * COLS + x] = 0;
// the new art: every tile its trees, planters, benches and carts take
if (ART2) for (const [x, y] of city2.blocked) walk[y * COLS + x] = 0;
export const BENCHES: { x: number; y: number; v: boolean }[] = [];
for (const dx of [-5, 5]) for (const dy of [-1, 2]) BENCHES.push({ x: FOUNTAIN.x + dx * TILE, y: FOUNTAIN.y + dy * TILE, v: true });
for (const dx of [-2, 2]) BENCHES.push({ x: FOUNTAIN.x + dx * TILE * 1.4, y: FOUNTAIN.y + 4 * TILE, v: false });

/** A random walkable plaza tile (agents waiting for a setup gather here, watching the exchange screen). */
export function plazaSpot(R: () => number): { x: number; y: number } {
  for (let i = 0; i < 30; i++) {
    const x = PLAZA.x + 2 + Math.floor(R() * (PLAZA.w - 4)), y = PLAZA.y + 3 + Math.floor(R() * (PLAZA.d - 4));
    if (canWalk(x, y)) return { x, y };
  }
  return { x: 40, y: 33 };
}
export const canWalk = (x: number, y: number) => x >= 0 && y >= 0 && x < COLS && y < ROWS && walk[y * COLS + x] === 1;

// ---------------------------------------------------------------- lamps (for lighting) and trees
export const LAMPS: { x: number; y: number }[] = [];
for (const r of HROADS) for (let x = 3; x < COLS; x += 7) if (!isRoadCol(x)) { LAMPS.push({ x: x * TILE + 8, y: (r - 1) * TILE + 2 }); LAMPS.push({ x: x * TILE + 8, y: (r + 2) * TILE + 14 }); }
for (const c of VROADS) for (let y = 4; y < ROWS; y += 8) if (!isRoadRow(y) && vRoad(c, y)) { LAMPS.push({ x: (c - 1) * TILE + 2, y: y * TILE }); LAMPS.push({ x: (c + 2) * TILE + 14, y: y * TILE }); }
for (const [x, y] of [[30, 30], [66, 30], [30, 39], [66, 39]]) LAMPS.push({ x: x * TILE + 8, y: y * TILE + 8 });

function rng(seed: number) {
  return () => { seed |= 0; seed = (seed + 0x6d2b79f5) | 0; let t = Math.imul(seed ^ (seed >>> 15), 1 | seed);
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t; return ((t ^ (t >>> 14)) >>> 0) / 4294967296; };
}

const TREES: { x: number; y: number; r: number }[] = [];
if (ART2) {   // the new art's lamps (their foot: the light pool; their head: the glow)
  LAMPS.length = 0;
  for (const [x, y] of city2.lamps) LAMPS.push({ x, y: y - 6 });
} else {
  const R = rng(7);
  for (let i = 0; i < 260; i++) {
    const x = Math.floor(R() * COLS), y = Math.floor(R() * ROWS);
    if (!canWalk(x, y) || isSidewalk(x, y) || isCrosswalk(x, y)) continue;
    if (x >= PLAZA.x && x < PLAZA.x + PLAZA.w && y >= PLAZA.y && y < PLAZA.y + PLAZA.d) continue;
    if (BUILDINGS.some((b) => Math.abs(b.door.x - x) < 2 && Math.abs(b.door.y - y) < 3)) continue;
    TREES.push({ x: x * TILE + 8, y: y * TILE + 8, r: 6 + Math.floor(R() * 4) });
    walk[y * COLS + x] = 0;
  }
}

// ---------------------------------------------------------------- static rendering
function shade(hex: string, f: number): string {
  const n = parseInt(hex.slice(1), 16);
  const ch = (v: number) => Math.max(0, Math.min(255, Math.round(v * f)));
  return `rgb(${ch(n >> 16)},${ch((n >> 8) & 255)},${ch(n & 255)})`;
}

// light sources recorded while the static city is painted; drawn again over the night mask so they glow
const GLOWS: { x: number; y: number; w: number; h: number; c: string; a: number }[] = [];

function drawBuilding(g: CanvasRenderingContext2D, b: Building, R: () => number) {
  const x = b.x * TILE, y = b.y * TILE, w = b.w * TILE, d = b.d * TILE, h = b.h;
  // drop shadow
  g.fillStyle = "rgba(0,0,0,0.45)";
  g.fillRect(x + 6, y + 6, w, d + h);
  // roof
  g.fillStyle = b.roof;
  g.fillRect(x, y, w, d);
  g.fillStyle = shade(b.roof, 1.25);
  g.fillRect(x, y, w, 2);
  g.fillRect(x, y, 2, d);
  g.fillStyle = shade(b.roof, 0.7);
  g.fillRect(x, y + d - 2, w, 2);
  // roof details: AC units / vents / antenna
  const units = Math.max(1, Math.floor(b.w / 4));
  for (let i = 0; i < units; i++) {
    const ux = x + 8 + Math.floor(R() * (w - 28)), uy = y + 6 + Math.floor(R() * Math.max(1, d - 20));
    g.fillStyle = shade(b.roof, 1.5); g.fillRect(ux, uy, 12, 9);
    g.fillStyle = shade(b.roof, 0.8); g.fillRect(ux + 2, uy + 2, 8, 5);
  }
  if (b.kind === "tower") {
    g.fillStyle = "#9ca3af"; g.fillRect(x + w / 2 - 1, y - 14, 2, 14);
  }
  if (b.kind === "lab") {   // observatory dome
    g.fillStyle = "#334155"; g.beginPath(); g.arc(x + w - 30, y + d / 2, 18, 0, Math.PI * 2); g.fill();
    g.fillStyle = "#475569"; g.fillRect(x + w - 32, y + d / 2 - 18, 4, 36);
  }
  // facade
  const fy = y + d;
  g.fillStyle = b.wall;
  g.fillRect(x, fy, w, h);
  g.fillStyle = shade(b.wall, 0.7);
  g.fillRect(x, fy + h - 3, w, 3);
  // windows
  const lit = ["#ffd479", "#9be7ff", "#4efab0", "#ffe7a8"];
  const rowsN = Math.max(1, Math.floor((h - 18) / 11));
  for (let r = 0; r < rowsN; r++) {
    for (let cx = x + 6; cx < x + w - 8; cx += 9) {
      const on = R() < (b.kind === "home" ? 0.35 : 0.62);
      const c = on ? lit[Math.floor(R() * lit.length)] : shade(b.wall, 0.55);
      g.fillStyle = c;
      g.globalAlpha = on ? 0.85 : 1;
      g.fillRect(cx, fy + 5 + r * 11, 5, 6);
      g.globalAlpha = 1;
      if (on) GLOWS.push({ x: cx, y: fy + 5 + r * 11, w: 5, h: 6, c, a: 0.8 });
    }
  }
  // pilasters
  g.fillStyle = shade(b.wall, 0.78);
  for (let px = x; px <= x + w - 3; px += 48) g.fillRect(px, fy, 3, h - 3);
  g.fillRect(x + w - 3, fy, 3, h - 3);
  // roof trim in the building's neon colour
  g.fillStyle = b.neon;
  g.globalAlpha = 0.45;
  g.fillRect(x, fy - 1, w, 1);
  GLOWS.push({ x, y: fy - 1, w, h: 1, c: b.neon, a: 0.6 });
  g.globalAlpha = 0.18;
  g.fillRect(x + 2, y + 2, w - 4, 1);
  g.globalAlpha = 1;
  // door with a lit canopy and steps
  const dx = b.door.x * TILE + 1;
  g.fillStyle = "#05070a";
  g.fillRect(dx, fy + h - 15, 14, 15);
  g.fillStyle = shade(b.neon, 0.35);
  g.fillRect(dx + 2, fy + h - 13, 10, 13);
  g.fillStyle = b.neon;
  g.globalAlpha = 0.9;
  g.fillRect(dx - 4, fy + h - 19, 22, 3);
  GLOWS.push({ x: dx - 4, y: fy + h - 19, w: 22, h: 3, c: b.neon, a: 1 });
  GLOWS.push({ x: dx + 2, y: fy + h - 13, w: 10, h: 13, c: b.neon, a: 0.25 });
  g.globalAlpha = 0.35;
  g.fillRect(dx - 3, fy + h - 16, 20, 1);
  g.globalAlpha = 1;
  g.fillStyle = "#3a404b";
  g.fillRect(dx - 3, fy + h, 20, 2);
  g.fillStyle = "#2f343d";
  g.fillRect(dx - 5, fy + h + 2, 24, 2);
}

export function renderStatic(): HTMLCanvasElement {
  const c = document.createElement("canvas");
  c.width = W; c.height = H;
  const g = c.getContext("2d")!;
  if (ART2 && art.base) { g.drawImage(art.base, 0, 0); return c; }
  const R = rng(42);
  GLOWS.length = 0;   // deterministic repaint (rng 42): never accumulate light sources twice
  // ground
  for (let y = 0; y < ROWS; y++) for (let x = 0; x < COLS; x++) {
    const px = x * TILE, py = y * TILE;
    if (isRoad(x, y)) {
      g.fillStyle = "#14161a"; g.fillRect(px, py, TILE, TILE);
      if (R() < 0.08) { g.fillStyle = "#191c21"; g.fillRect(px + Math.floor(R() * 12), py + Math.floor(R() * 12), 3, 2); }
    } else if (isSidewalk(x, y) || (x >= PLAZA.x && x < PLAZA.x + PLAZA.w && y >= PLAZA.y && y < PLAZA.y + PLAZA.d)) {
      if (!isSidewalk(x, y)) {
        // plaza: 2×2-tile stone slabs with slight tone variation
        const sx = Math.floor(x / 2), sy = Math.floor(y / 2);
        g.fillStyle = ["#262b36", "#292e3a", "#242935", "#2b303c"][(sx * 3 + sy * 5) % 4];
        g.fillRect(px, py, TILE, TILE);
        g.fillStyle = "#1d212b";
        if (x % 2 === 0) g.fillRect(px, py, 1, TILE);
        if (y % 2 === 0) g.fillRect(px, py, TILE, 1);
      } else {
        g.fillStyle = "#272a31"; g.fillRect(px, py, TILE, TILE);
        g.fillStyle = "#30343d"; g.fillRect(px, py, TILE, 1); g.fillRect(px, py, 1, TILE);
      }
    } else {
      g.fillStyle = (x * 7 + y * 13) % 5 === 0 ? "#10241a" : "#0e2017";
      g.fillRect(px, py, TILE, TILE);
      if (R() < 0.25) { g.fillStyle = "#143023"; g.fillRect(px + Math.floor(R() * 13), py + Math.floor(R() * 13), 2, 2); }
      if (R() < 0.1) { g.fillStyle = ["#f9a8d4", "#fde68a", "#a7f3d0", "#c4b5fd"][Math.floor(R() * 4)]; g.fillRect(px + Math.floor(R() * 14), py + Math.floor(R() * 14), 1, 1); }
    }
  }
  // curbs: a lit edge wherever pavement meets the road
  g.fillStyle = "#3b404a";
  for (let y = 0; y < ROWS; y++) for (let x = 0; x < COLS; x++) {
    if (isRoad(x, y)) continue;
    if (y + 1 < ROWS && isRoad(x, y + 1)) g.fillRect(x * TILE, y * TILE + TILE - 2, TILE, 2);
    if (y > 0 && isRoad(x, y - 1)) g.fillRect(x * TILE, y * TILE, TILE, 2);
    if (x + 1 < COLS && isRoad(x + 1, y)) g.fillRect(x * TILE + TILE - 2, y * TILE, 2, TILE);
    if (x > 0 && isRoad(x - 1, y)) g.fillRect(x * TILE, y * TILE, 2, TILE);
  }
  // lane markings and crosswalks
  g.fillStyle = "#4a505a";
  for (const r of HROADS) for (let x = 0; x < W; x += 24) if (!isRoadCol(Math.floor(x / TILE))) g.fillRect(x, (r + 1) * TILE - 1, 12, 2);
  for (const cc of VROADS) for (let y = 0; y < H; y += 24) { const ty = Math.floor(y / TILE); if (!isRoadRow(ty) && vRoad(cc, ty)) g.fillRect((cc + 1) * TILE - 1, y, 2, 12); }
  g.fillStyle = "rgba(220,226,235,0.55)";
  for (let y = 0; y < ROWS; y++) for (let x = 0; x < COLS; x++) if (isCrosswalk(x, y)) {
    if (isRoadRow(y)) for (let i = 2; i < TILE; i += 5) g.fillRect(x * TILE + i, y * TILE + 1, 3, TILE - 2);
    else for (let i = 2; i < TILE; i += 5) g.fillRect(x * TILE + 1, y * TILE + i, TILE - 2, 3);
  }
  // plaza mosaic: a mint compass ring set in the stone around the fountain
  g.save();
  g.translate(FOUNTAIN.x, FOUNTAIN.y + 6);
  g.scale(1, 0.62);
  g.strokeStyle = "rgba(78,250,176,0.16)"; g.lineWidth = 3;
  g.beginPath(); g.arc(0, 0, 118, 0, Math.PI * 2); g.stroke();
  g.strokeStyle = "rgba(78,250,176,0.09)"; g.lineWidth = 2;
  g.beginPath(); g.arc(0, 0, 150, 0, Math.PI * 2); g.stroke();
  for (let i = 0; i < 16; i++) {
    const a = (i / 16) * Math.PI * 2, r0 = i % 2 ? 70 : 58;
    g.beginPath(); g.moveTo(Math.cos(a) * r0, Math.sin(a) * r0); g.lineTo(Math.cos(a) * 118, Math.sin(a) * 118); g.stroke();
  }
  g.restore();
  // fountain: octagonal stone basin with a lit rim and a central pedestal (the water is drawn live)
  const oct = (r: number, ry: number) => {
    g.beginPath();
    for (let i = 0; i < 8; i++) {
      const a = (i / 8) * Math.PI * 2 + Math.PI / 8;
      const px = FOUNTAIN.x + Math.cos(a) * r, py = FOUNTAIN.y + 6 + Math.sin(a) * ry;
      if (i) g.lineTo(px, py); else g.moveTo(px, py);
    }
    g.closePath();
  };
  g.fillStyle = "rgba(0,0,0,0.35)"; oct(39, 25); g.fill();
  g.fillStyle = "#4a5263"; oct(36, 22); g.fill();
  g.save(); oct(36, 22); g.clip(); g.fillStyle = "#5d6679"; g.fillRect(FOUNTAIN.x - 40, FOUNTAIN.y - 18, 80, 7); g.restore();
  g.fillStyle = "#082b26"; oct(30, 17); g.fill();
  g.fillStyle = "#4a5263"; g.beginPath(); g.ellipse(FOUNTAIN.x, FOUNTAIN.y + 6, 6, 4, 0, 0, Math.PI * 2); g.fill();
  g.fillStyle = "#6b7488"; g.fillRect(FOUNTAIN.x - 2, FOUNTAIN.y - 4, 4, 10);
  // planters with shrubs
  for (const [px, py] of [[29, 29], [67, 29], [29, 38], [67, 38]]) {
    g.fillStyle = "rgba(0,0,0,0.35)"; g.fillRect(px * TILE - 2, py * TILE - 1, 24, 24);
    g.fillStyle = "#3a4152"; g.fillRect(px * TILE - 4, py * TILE - 4, 24, 24);
    g.fillStyle = "#4a5263"; g.fillRect(px * TILE - 4, py * TILE - 4, 24, 2);
    g.fillStyle = "#2b1d14"; g.fillRect(px * TILE - 1, py * TILE - 1, 18, 18);
    for (const [ox, oy, r] of [[4, 5, 5], [12, 6, 5], [8, 12, 6]]) {
      g.fillStyle = "#14532d"; g.beginPath(); g.arc(px * TILE + ox, py * TILE + oy, r, 0, Math.PI * 2); g.fill();
      g.fillStyle = "#1f7a3f"; g.beginPath(); g.arc(px * TILE + ox - 1, py * TILE + oy - 2, r * 0.55, 0, Math.PI * 2); g.fill();
    }
  }
  // benches
  for (const b of BENCHES) {
    const w = b.v ? 6 : 22, h = b.v ? 20 : 6;
    g.fillStyle = "rgba(0,0,0,0.35)"; g.fillRect(b.x - w / 2 + 2, b.y - h / 2 + 2, w, h);
    g.fillStyle = "#6b4a2e"; g.fillRect(b.x - w / 2, b.y - h / 2, w, h);
    g.fillStyle = "#8a6240";
    if (b.v) for (let i = 0; i < h; i += 4) g.fillRect(b.x - w / 2, b.y - h / 2 + i, w, 2);
    else for (let i = 0; i < w; i += 4) g.fillRect(b.x - w / 2 + i, b.y - h / 2, 2, h);
  }
  // kiosks with striped awnings
  for (const k of KIOSKS) {
    const kx = k.x * TILE, ky = k.y * TILE;
    g.fillStyle = "rgba(0,0,0,0.4)"; g.fillRect(kx + 3, ky + 5, 32, 28);
    g.fillStyle = "#2b2f3a"; g.fillRect(kx, ky + 10, 32, 20);
    g.fillStyle = "#151821"; g.fillRect(kx + 4, ky + 16, 24, 8);
    g.fillStyle = "#ffd479"; g.globalAlpha = 0.7; g.fillRect(kx + 5, ky + 17, 22, 6); g.globalAlpha = 1;
    GLOWS.push({ x: kx + 5, y: ky + 17, w: 22, h: 6, c: "#ffd479", a: 0.9 });
    for (let i = 0; i < 8; i++) { g.fillStyle = i % 2 ? "#e5e7eb" : k.color; g.fillRect(kx - 2 + i * 4.5, ky + 2, 4.5, 9); }
    g.fillStyle = "rgba(0,0,0,0.25)"; g.fillRect(kx - 2, ky + 9, 36, 2);
  }
  // buildings, back to front
  [...BUILDINGS].sort((a, b) => a.y - b.y).forEach((b) => drawBuilding(g, b, R));
  // trees
  for (const t of TREES) {
    g.fillStyle = "rgba(0,0,0,0.35)"; g.beginPath(); g.ellipse(t.x + 3, t.y + t.r - 1, t.r, t.r / 2, 0, 0, Math.PI * 2); g.fill();
    g.fillStyle = "#3f2a1d"; g.fillRect(t.x - 1, t.y, 3, t.r);
    g.fillStyle = "#14532d"; g.beginPath(); g.arc(t.x, t.y - 2, t.r, 0, Math.PI * 2); g.fill();
    g.fillStyle = "#166534"; g.beginPath(); g.arc(t.x - 2, t.y - 4, t.r * 0.6, 0, Math.PI * 2); g.fill();
  }
  // lamp posts
  for (const l of LAMPS) {
    g.fillStyle = "#1f2937"; g.fillRect(l.x - 1, l.y - 10, 2, 12);
    g.fillStyle = "#fde68a"; g.fillRect(l.x - 2, l.y - 12, 4, 3);
    GLOWS.push({ x: l.x - 2, y: l.y - 12, w: 4, h: 3, c: "#fff1b8", a: 1 });
  }
  return c;
}

/** Emissive layer (windows, neon trims, canopies, lamps) with a soft halo; call after renderStatic(). */
export function renderGlow(): HTMLCanvasElement {
  const c = document.createElement("canvas");
  c.width = W; c.height = H;
  const g = c.getContext("2d")!;
  if (ART2 && art.base) {   // the lit windows (build_city.py) and every lamp's head
    if (art.glow) g.drawImage(art.glow, 0, 0);
    for (const [x, , y] of city2.lamps) {
      g.globalAlpha = 0.3; g.fillStyle = "#fff1b8"; g.fillRect(x - 4, y - 3, 8, 7);
      g.globalAlpha = 1; g.fillRect(x - 2, y - 1, 4, 3);
    }
    g.globalAlpha = 1;
    return c;
  }
  for (const s of GLOWS) {
    g.globalAlpha = s.a * 0.35;
    g.fillStyle = s.c;
    g.fillRect(s.x - 2, s.y - 2, s.w + 4, s.h + 4);
    g.globalAlpha = s.a;
    g.fillRect(s.x, s.y, s.w, s.h);
  }
  return c;
}

/** Night light mask: dark overlay with light pools punched out (lamps, plaza, doors). */
export function renderLight(): HTMLCanvasElement {
  const c = document.createElement("canvas");
  c.width = W; c.height = H;
  const g = c.getContext("2d")!;
  g.fillStyle = "rgba(3,6,16,0.66)";
  g.fillRect(0, 0, W, H);
  g.globalCompositeOperation = "destination-out";
  const pool = (x: number, y: number, r: number, a: number) => {
    const grd = g.createRadialGradient(x, y, 0, x, y, r);
    grd.addColorStop(0, `rgba(0,0,0,${a})`);
    grd.addColorStop(1, "rgba(0,0,0,0)");
    g.fillStyle = grd;
    g.fillRect(x - r, y - r, 2 * r, 2 * r);
  };
  for (const l of LAMPS) pool(l.x, l.y + 6, 46, 0.9);
  pool(FOUNTAIN.x, FOUNTAIN.y, 150, 0.7);
  for (const k of KIOSKS) pool(k.x * TILE + 16, k.y * TILE + 20, 34, 0.8);
  for (const b of BUILDINGS) pool(b.door.x * TILE + 8, (b.y + b.d) * TILE + b.h, 40, 0.85);
  return c;
}

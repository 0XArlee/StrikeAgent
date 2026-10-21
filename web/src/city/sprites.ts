// Characters from LimeZu's character generator (city/chars.json): the five pieces of a look stacked into one sheet
// (body, eyes, outfit, hairstyle, accessory), shared by the city, the landing's city and the character editor. Every
// piece is a small image under /art/chars, loaded once; a look's sheet is composed once and cached. Until its pieces
// have loaded a look has no sheet yet (sheetFor returns null): the city draws its ring meanwhile, and whoever needs to
// redraw when it arrives listens with onSheet.
//
// Sheet rows (chars.json "rows"): idle, walk, sit, phone, read. idle and walk: 6 frames per direction, in the order
// right, up, left, down. phone and read: 12 frames facing you, the middle ones loop.
import chars from "./chars.json";
import { randomLook, NONE, type Look, type Part } from "./look";
import { hash, mulberry } from "./rand";

export type Dir = "down" | "up" | "left" | "right";
export type Anim = "idle" | "walk" | "phone" | "read";
export { hash };

export const [FW, FH] = chars.frame as [number, number];
/** Feet line inside a frame (the sprite stands on y - FEET) and the top of the head. */
export const FEET = chars.feet, HEAD_TOP = chars.top;
const ROWS = chars.rows as Record<string, number>;
const DIRS = chars.dirs as Dir[];
const ANIMS = chars.anims as unknown as Record<string, { perDir?: number; frames?: number; loop?: [number, number]; fps: number }>;
const ORDER = chars.order as Part[];
const BASE = `${import.meta.env.BASE_URL ?? "/"}art/chars/`;
const SHEET_W = 24 * FW, SHEET_H = Object.keys(ROWS).length * FH;

const images = new Map<string, Promise<HTMLImageElement>>();
function image(url: string): Promise<HTMLImageElement> {
  let p = images.get(url);
  if (!p) {
    p = new Promise((ok, fail) => { const im = new Image(); im.decoding = "async"; im.onload = () => ok(im); im.onerror = fail; im.src = url; });
    p.catch(() => images.delete(url));   // a failed load is tried again next time
    images.set(url, p);
  }
  return p;
}
const urlOf = (part: Part, id: string) => `${BASE}${part}/${id}.png`;
export const thumbsUrl = (part: Part) => `${BASE}${part}_thumbs.png`;

const sheets = new Map<string, HTMLCanvasElement | null>();   // null: its pieces are loading
const listeners = new Set<() => void>();
/** Called whenever a sheet that was loading is ready (redraw whatever showed nothing). */
export function onSheet(f: () => void): () => void { listeners.add(f); return () => listeners.delete(f); }

const keyOf = (l: Look) => `${l.body}|${l.eyes}|${l.outfit}|${l.hair}|${l.acc}`;

/** The look's composed sheet, or null while its pieces load (it starts loading them). */
export function sheetOf(look: Look): HTMLCanvasElement | null {
  const key = keyOf(look);
  const hit = sheets.get(key);
  if (hit !== undefined) return hit;
  sheets.set(key, null);
  const layers = ORDER.map((p) => [p, look[p]] as const).filter(([, id]) => id && id !== NONE);
  Promise.all(layers.map(([p, id]) => image(urlOf(p, id)))).then((ims) => {
    const c = document.createElement("canvas");
    c.width = SHEET_W; c.height = SHEET_H;
    const g = c.getContext("2d")!;
    for (const im of ims) g.drawImage(im, 0, 0);
    if (sheets.size > 600) sheets.clear();
    sheets.set(key, c);
    for (const f of listeners) f();
  }).catch(() => sheets.delete(key));
  return null;
}

/** The look of an agent without a saved one: stable per id, varied across the city. */
export function lookFor(seed: string): Look { return randomLook(mulberry(hash(seed))); }

export function sheetFor(seed: string, look?: Look | null): HTMLCanvasElement | null { return sheetOf(look ?? lookFor(seed)); }

/** Where a frame is in a sheet: [x, y]. t in seconds (0 = the first frame, for reduced motion). */
export function frameAt(anim: Anim, dir: Dir, t: number): [number, number] {
  const a = ANIMS[anim], row = ROWS[anim];
  if (a.perDir) {
    const f = Math.floor(t * a.fps) % a.perDir;
    return [(DIRS.indexOf(dir) * a.perDir + f) * FW, row * FH];
  }
  const [lo, hi] = a.loop ?? [0, (a.frames ?? 1) - 1];
  return [(lo + (Math.floor(t * a.fps) % (hi - lo + 1))) * FW, row * FH];
}

/** Draws one frame of a look standing at (x, feetY) in g's units, `scale` pixels per art pixel. */
export function drawFrame(g: CanvasRenderingContext2D, sheet: HTMLCanvasElement, anim: Anim, dir: Dir, t: number, x: number, feetY: number, scale = 1) {
  const [sx, sy] = frameAt(anim, dir, t);
  g.drawImage(sheet, sx, sy, FW, FH, Math.round(x - (FW / 2) * scale), Math.round(feetY - FEET * scale), FW * scale, FH * scale);
}

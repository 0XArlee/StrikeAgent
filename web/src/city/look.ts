// An agent's look (the character creator): pieces of LimeZu's character generator (city/chars.json, cut down by
// web/scripts/build_art.py): a body (the skin tone), eyes, an outfit, a hairstyle and an accessory, stacked in that
// order. Shared by the page (sprites, editor) and the site API (web/server validates what owners save), so both accept
// exactly the same values. Looks saved with the first creator (drawn styles and free colours, no "v") become the
// closest pieces, so nobody loses their character.
import chars from "./chars.json";

export type Part = "body" | "eyes" | "outfit" | "hair" | "acc";
export const PARTS: Part[] = ["body", "eyes", "outfit", "hair", "acc"];
export interface Piece { id: string; style?: string; name?: string; rgb: string }
/** hair and acc may be NONE (no hair, no accessory). */
export interface Look { v: 2; body: string; eyes: string; outfit: string; hair: string; acc: string }
export const NONE = "none";

export const PIECES = chars.parts as Record<Part, Piece[]>;
const IDS = Object.fromEntries(PARTS.map((p) => [p, new Set(PIECES[p].map((x) => x.id))])) as Record<Part, Set<string>>;
const OPTIONAL: Part[] = ["hair", "acc"];

export const DEFAULT_LOOK: Look = {
  v: 2, body: chars.defaults.body, eyes: chars.defaults.eyes, outfit: chars.defaults.outfit, hair: chars.defaults.hair, acc: NONE,
};

/** The styles of a part (outfits, hairstyles, accessories), each with its colour variants, in catalogue order. */
export function stylesOf(part: Part): { style: string; name?: string; pieces: Piece[] }[] {
  const out: { style: string; name?: string; pieces: Piece[] }[] = [];
  for (const p of PIECES[part]) {
    const s = p.style ?? p.id;
    const last = out[out.length - 1];
    if (last && last.style === s) last.pieces.push(p); else out.push({ style: s, name: p.name, pieces: [p] });
  }
  return out;
}

const valid = (part: Part, v: unknown, dflt: string) =>
  typeof v === "string" && (IDS[part].has(v) || (OPTIONAL.includes(part) && v === NONE)) ? v : dflt;

/** Any input -> a valid look (unknown pieces fall back to defaults), or null when it is not an object. */
export function normalizeLook(v: unknown): Look | null {
  if (!v || typeof v !== "object" || Array.isArray(v)) return null;
  const o = v as Record<string, unknown>, d = DEFAULT_LOOK;
  if (o.v !== 2) return fromV1(o);
  return { v: 2, body: valid("body", o.body, d.body), eyes: valid("eyes", o.eyes, d.eyes), outfit: valid("outfit", o.outfit, d.outfit),
    hair: valid("hair", o.hair, d.hair), acc: valid("acc", o.acc, NONE) };
}

// ---------------------------------------------------------------- the first creator's looks -> pieces
const HEX = /^#[0-9a-f]{6}$/i;
const rgb = (h: string) => [1, 3, 5].map((i) => parseInt(h.slice(i, i + 2), 16));
const dist = (a: string, b: string) => { const [x, y] = [rgb(a), rgb(b)]; return (x[0] - y[0]) ** 2 + (x[1] - y[1]) ** 2 + (x[2] - y[2]) ** 2; };
function nearest(pieces: Piece[], hex: unknown, dflt: string): string {
  if (typeof hex !== "string" || !HEX.test(hex) || !pieces.length) return dflt;
  return pieces.reduce((a, b) => (dist(b.rgb, hex) < dist(a.rgb, hex) ? b : a)).id;
}
const inStyle = (part: Part, style: string) => PIECES[part].filter((p) => p.style === style);
// the drawn hairstyles of the first creator -> the closest LimeZu style (by eye); shaved is no hair
const HAIR_V1: Record<string, string> = { short: "16", long: "10", spiky: "21", mohawk: "26", ponytail: "11", afro: "08" };
// one accessory slot: the head one first, then the face, then the back
const HEAD_V1: Record<string, string> = { cap: "04", beanie: "11" };
const FACE_V1: Record<string, string> = { glasses: "15", shades: "15" };
const BACK_V1: Record<string, string> = { backpack: "03" };

function fromV1(o: Record<string, unknown>): Look {
  const d = DEFAULT_LOOK;
  const hairStyle = typeof o.hair === "string" ? o.hair : "";
  const hair = hairStyle === "shaved" ? NONE : HAIR_V1[hairStyle] ? nearest(inStyle("hair", HAIR_V1[hairStyle]), o.hairColor, d.hair) : d.hair;
  let acc = NONE;
  for (const [table, field, color] of [[HEAD_V1, "head", "headColor"], [FACE_V1, "face", "faceColor"], [BACK_V1, "back", "backColor"]] as const) {
    const style = typeof o[field] === "string" ? table[o[field] as string] : undefined;
    if (style) { acc = nearest(inStyle("acc", style), o[color], NONE); break; }
  }
  return { v: 2, body: nearest(PIECES.body, o.skin, d.body), eyes: d.eyes, outfit: nearest(PIECES.outfit, o.topColor, d.outfit), hair, acc };
}

/** Deterministic look for an agent without one (stable per id, varied across the city). */
export function randomLook(R: () => number): Look {
  const one = <T,>(xs: readonly T[]) => xs[Math.floor(R() * xs.length)];
  const natural = PIECES.body.slice(0, 7);   // the two last bodies are fantasy tones: only when chosen
  return {
    v: 2, body: one(natural).id, eyes: one(PIECES.eyes).id, outfit: one(PIECES.outfit).id,
    hair: R() < 0.06 ? NONE : one(PIECES.hair.filter((h) => Number(h.style) < 27)).id,   // 27-29: the bright anime ones
    acc: R() < 0.72 ? NONE : one(PIECES.acc).id,
  };
}

/** Short stable fingerprint (shown in the signed message: what you sign is the look that gets saved). */
export function lookId(l: Look): string {
  let h = 2166136261;
  const s = JSON.stringify(l);
  for (let i = 0; i < s.length; i++) { h ^= s.charCodeAt(i); h = Math.imul(h, 16777619); }
  return (h >>> 0).toString(16).padStart(8, "0");
}
